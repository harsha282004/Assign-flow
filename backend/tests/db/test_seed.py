"""Seed tests: dataset shape (exactly 15 faculty and 50 students), mappings, hashing, idempotence, transition."""

import pytest
from alembic import command
from sqlalchemy import Engine, create_engine, func, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_password, verify_password
from app.db.models import (
    Assignment,
    Section,
    StudentProfile,
    Subject,
    TeachingAssignment,
    User,
    UserRole,
)
from app.db.seeds import seed_config as cfg
from app.db.seeds.runner import SeedError, run_seed, verify_seed
from app.db.transition_dataset import apply_plan, build_plan
from tests.conftest import alembic_config, drop_database, recreate_database


@pytest.fixture
def seeded(seeded_engine: Engine):
    with Session(seeded_engine) as session:
        yield session


def _count(session: Session, model) -> int:
    return session.scalar(select(func.count()).select_from(model))


# The API tests add one throw-away faculty account (QAFAC01) to this isolated database, so the counts below are
# taken over the configured dataset (FAC%/STU% accounts) and re-seeding passes allow_extra_users.
def _dataset_users(session: Session, role: UserRole) -> list[str]:
    prefix = "FAC" if role == UserRole.FACULTY else "STU"
    return sorted(
        session.scalars(select(User.login_id).where(User.role == role, User.login_id.like(f"{prefix}%"))).all()
    )


def test_exactly_15_faculty_and_50_students(seeded: Session):
    assert _dataset_users(seeded, UserRole.FACULTY) == [f"FAC{i:03d}" for i in range(1, 16)]
    assert _dataset_users(seeded, UserRole.STUDENT) == [f"STU{i:04d}" for i in range(101, 151)]
    assert len(cfg.faculty_ids()) == 15 and len(cfg.student_ids()) == 50


def test_academic_structure_counts(seeded: Session):
    assert _count(seeded, Section) == 3
    assert _count(seeded, Subject) == 6
    assert _count(seeded, TeachingAssignment) == 18
    assert _count(seeded, StudentProfile) == 50
    assert set(seeded.scalars(select(Section.label))) == {"CSE-5A", "CSE-5B", "CSE-5C"}


def test_sections_have_17_17_and_16_students(seeded: Session):
    rows = seeded.execute(select(StudentProfile.section_id, func.count()).group_by(StudentProfile.section_id)).all()
    assert len(rows) == 3
    assert sorted(count for _, count in rows) == [16, 17, 17]
    orphan = seeded.scalar(
        select(func.count())
        .select_from(User)
        .outerjoin(StudentProfile, StudentProfile.user_id == User.id)
        .where(User.role == UserRole.STUDENT, StudentProfile.user_id.is_(None))
    )
    assert orphan == 0


def test_teaching_mappings_are_valid(seeded: Session):
    verify_seed(seeded, allow_extra_users=True)  # raises SeedError on any inconsistency
    bad = seeded.scalar(
        select(func.count())
        .select_from(TeachingAssignment)
        .join(Subject, Subject.id == TeachingAssignment.subject_id)
        .join(Section, Section.id == TeachingAssignment.section_id)
        .where(Subject.semester != Section.semester)
    )
    assert bad == 0


def test_fac001_teaches_cse_5a_demo_class(seeded: Session):
    rows = seeded.execute(
        select(Subject.code, Section.label)
        .select_from(TeachingAssignment)
        .join(User, User.id == TeachingAssignment.faculty_id)
        .join(Subject, Subject.id == TeachingAssignment.subject_id)
        .join(Section, Section.id == TeachingAssignment.section_id)
        .where(User.login_id == "FAC001")
    ).all()
    assert [tuple(r) for r in rows] == [("CS503", "CSE-5A")]


def test_all_15_faculty_teach_and_every_class_has_exactly_one_teacher(seeded: Session):
    per_faculty = dict(
        seeded.execute(
            select(User.login_id, func.count())
            .select_from(TeachingAssignment)
            .join(User, User.id == TeachingAssignment.faculty_id)
            .group_by(User.login_id)
        ).all()
    )
    assert sorted(per_faculty) == cfg.faculty_ids()  # nobody is left without a class
    assert sum(per_faculty.values()) == 18 and set(per_faculty.values()) == {1, 2}
    mapping = cfg.faculty_slot_map()
    slots = [sl for sls in mapping.values() for sl in sls]
    assert len(slots) == 18 and len(set(slots)) == 18  # a class never has two teachers
    for sls in mapping.values():  # a faculty member's classes differ
        assert len(set(sls)) == len(sls)


def test_passwords_are_independent_argon2_hashes(seeded: Session, test_password: str):
    hashes = seeded.scalars(select(User.password_hash).where(User.login_id.regexp_match("^(FAC|STU)"))).all()
    assert len(hashes) == 65
    assert all(h.startswith("$argon2") for h in hashes)
    assert len(set(hashes)) == 65  # unique salt per account
    assert test_password not in "".join(hashes)
    sample = seeded.scalar(select(User.password_hash).where(User.login_id == "FAC001"))
    assert verify_password(test_password, sample)
    assert not verify_password(test_password + "x", sample)


def test_accounts_are_active_with_fictional_names(seeded: Session):
    rows = seeded.execute(select(User.is_active, User.full_name).where(User.login_id.regexp_match("^(FAC|STU)"))).all()
    assert len(rows) == 65 and all(active for active, _ in rows)
    assert all(name.strip() for _, name in rows)


def test_names_are_curated_distinct_indian_names_and_deterministic(seeded: Session):
    from app.db.seeds.seed_names import FIRST_NAMES, SURNAMES

    names = {
        login: name
        for login, name in seeded.execute(select(User.login_id, User.full_name).where(User.login_id.regexp_match("^(FAC|STU)")))
    }
    assert len(names) == 65 and len(set(names.values())) == 65  # every display name is distinct
    for name in names.values():
        first, last = name.split(" ")
        assert first in FIRST_NAMES and last in SURNAMES
    assert names["STU0101"] == cfg.display_name("STU0101") == cfg.display_name("STU0101")  # deterministic
    assert cfg.display_name("FAC001") == names["FAC001"] and cfg.display_name("STU0150") == names["STU0150"]


def test_second_seed_run_creates_no_duplicates_and_does_not_rehash(seeded: Session, test_password: str):
    before_counts = {m: _count(seeded, m) for m in (User, Section, Subject, StudentProfile, TeachingAssignment)}
    before_hashes = dict(seeded.execute(select(User.login_id, User.password_hash)).all())
    run_seed(seeded, test_password, allow_extra_users=True)
    run_seed(seeded, test_password, allow_extra_users=True)
    after_counts = {m: _count(seeded, m) for m in before_counts}
    after_hashes = dict(seeded.execute(select(User.login_id, User.password_hash)).all())
    assert after_counts == before_counts
    assert after_hashes == before_hashes  # existing accounts are not re-hashed


def test_seed_requires_a_password(seeded: Session):
    with pytest.raises(SeedError):
        run_seed(seeded, "")


def test_seed_creates_no_operational_records(seeded: Session):
    """No fake assignments, submissions, versions, late requests, reviews or notifications at startup."""
    assert _count(seeded, Assignment) == 0
    for table in ("submissions", "submission_versions", "late_requests", "reviews", "notifications", "deadline_changes"):
        assert seeded.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 0


def test_seed_config_is_internally_consistent():
    slots = cfg.all_slots()
    assert len(slots) == 18 and len(set(slots)) == 18
    mapping = cfg.faculty_slot_map()
    assert len({sl for sls in mapping.values() for sl in sls}) == 18
    assert mapping["FAC001"][0].subject_code == "CS503" and mapping["FAC001"][0].section_label == "CSE-5A"
    assert len(cfg.student_section_map()) == 50
    assert {sem for sem, _ in cfg.student_section_map().values()} == {5}


def test_a_legacy_database_is_refused_with_a_hint_and_transitioned_safely(test_password: str):
    """Configured dataset plus legacy leftovers -> seed refuses (nothing deleted) -> transition fixes it."""
    settings = get_settings()
    url = recreate_database(settings, "assignflow_inittest")
    try:
        command.upgrade(alembic_config(url), "head")
        engine = create_engine(url)
        with Session(engine) as db:
            run_seed(db, test_password)
            pw = hash_password(test_password)
            sec7 = Section(semester=7, name="A", label="CSE-7A")
            sub7 = Subject(code="CS701", name="Machine Learning", semester=7)
            student = User(login_id="STU0001", full_name="Legacy S", role=UserRole.STUDENT, password_hash=pw)
            faculty = User(login_id="FAC016", full_name="Legacy F", role=UserRole.FACULTY, password_hash=pw)
            db.add_all([sec7, sub7, student, faculty])
            db.flush()
            db.add(StudentProfile(user_id=student.id, section_id=sec7.id))
            db.add(TeachingAssignment(faculty_id=faculty.id, subject_id=sub7.id, section_id=sec7.id))
            # A configured student (CSE-5B) sitting in the wrong section, and an account with an old name.
            db.execute(
                text("UPDATE student_profiles SET section_id = :s WHERE user_id = (SELECT id FROM users WHERE login_id = 'STU0130')"),
                {"s": sec7.id},
            )
            db.execute(text("UPDATE users SET full_name = 'Old Name' WHERE login_id = 'FAC001'"))
            db.commit()

            with pytest.raises(SeedError, match="transition_dataset"):
                run_seed(db, test_password)
            db.rollback()
            assert _count(db, User) == 67  # refused: nothing deleted

            plan = build_plan(db)
            assert plan.blockers == [] and plan.remove_users == ["FAC016", "STU0001"]
            assert plan.remove_sections == ["CSE-7A"] and plan.remove_subjects == ["CS701"]
            assert plan.moves == [("STU0130", "CSE-7A", "CSE-5B")]
            assert plan.renames == [("FAC001", "Old Name", cfg.display_name("FAC001"))]
            assert _count(db, User) == 67  # building a plan changes nothing
            apply_plan(db, plan)
            run_seed(db, test_password)
            assert _count(db, User) == 65
            assert _count(db, Section) == 3 and _count(db, Subject) == 6 and _count(db, TeachingAssignment) == 18
            assert db.scalar(select(User.full_name).where(User.login_id == "FAC001")) == cfg.display_name("FAC001")

        # A student who owns real data is never moved silently: the plan is blocked and nothing changes.
        with Session(engine) as db:
            sec7 = Section(semester=7, name="A", label="CSE-7A")
            db.add(sec7)
            db.flush()
            uid = db.scalar(select(User.id).where(User.login_id == "STU0140"))
            db.execute(text("UPDATE student_profiles SET section_id = :s WHERE user_id = :u"), {"s": sec7.id, "u": uid})
            db.execute(
                text(
                    "INSERT INTO notifications (user_id, type, title, body, dedup_key) "
                    "VALUES (:u, 'T', 't', 'b', 'k1')"
                ),
                {"u": uid},
            )
            db.commit()
            plan = build_plan(db)
            assert any("STU0140" in b and "explicit approval" in b for b in plan.blockers)
        engine.dispose()
    finally:
        drop_database(settings, "assignflow_inittest")
