"""Seed orchestration and post-seed integrity checks."""

import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from app.db.models import (
    Section,
    StudentProfile,
    Subject,
    TeachingAssignment,
    User,
    UserRole,
)
from app.db.seeds import seed_config as cfg
from app.db.seeds.seed_academics import seed_academics
from app.db.seeds.seed_users import seed_users

logger = logging.getLogger("assignflow.seed")


class SeedError(RuntimeError):
    pass


class DatasetMismatch(SeedError):
    """The database holds a different dataset than the configured one. Nothing was changed."""


TRANSITION_HINT = (
    "This database holds a different dataset than the configured one (exactly "
    f"{cfg.FACULTY_COUNT} faculty and {len(cfg.student_ids())} students). Nothing was deleted. "
    "Review it with `python -m app.db.transition_dataset` (dry run), then apply it with `--apply`."
)


def run_seed(session: Session, password: str, *, allow_extra_users: bool = False) -> None:
    """Seed academic structure and users, verify integrity, commit. Safe to run repeatedly.

    `allow_extra_users` exists only for the test-suite (which adds a throw-away account to an isolated database);
    the application never sets it, so a real database always ends up with exactly the configured accounts.
    """
    if not password:
        raise SeedError("SEED_DEMO_PASSWORD is required to seed demo accounts")
    if not allow_extra_users:
        _refuse_foreign_dataset(session)  # before any insert: the database is left exactly as it was
    seed_academics(session)
    seed_users(session, password)
    verify_seed(session, allow_extra_users=allow_extra_users)
    session.commit()


def _refuse_foreign_dataset(session: Session) -> None:
    """Raise DatasetMismatch if any account exists that is not part of the configured dataset."""
    wanted = set(cfg.faculty_ids()) | set(cfg.student_ids())
    rows = session.execute(select(User.login_id, User.role)).all()
    extra = [login for login, _ in rows if login not in wanted]
    if extra:
        faculty = sum(1 for _, role in rows if role == UserRole.FACULTY)
        students = len(rows) - faculty
        raise DatasetMismatch(
            f"Expected {cfg.FACULTY_COUNT} FACULTY and {len(cfg.student_ids())} STUDENT accounts; the database has "
            f"{faculty} and {students} ({len(extra)} accounts are outside the configured dataset). " + TRANSITION_HINT
        )


def count_users(session: Session, role: UserRole) -> int:
    return session.scalar(select(func.count()).select_from(User).where(User.role == role)) or 0


def verify_seed(session: Session, *, allow_extra_users: bool = False) -> None:
    """Raise SeedError unless the dataset matches the approved shape."""
    logins = {
        role: set(session.scalars(select(User.login_id).where(User.role == role)))
        for role in (UserRole.FACULTY, UserRole.STUDENT)
    }
    faculty, students = len(logins[UserRole.FACULTY]), len(logins[UserRole.STUDENT])
    wanted_faculty, wanted_students = set(cfg.faculty_ids()), set(cfg.student_ids())
    missing = (wanted_faculty - logins[UserRole.FACULTY]) | (wanted_students - logins[UserRole.STUDENT])
    extra = (logins[UserRole.FACULTY] - wanted_faculty) | (logins[UserRole.STUDENT] - wanted_students)
    if missing or (extra and not allow_extra_users):
        raise DatasetMismatch(
            f"Expected {cfg.FACULTY_COUNT} FACULTY and {len(wanted_students)} STUDENT accounts, "
            f"found {faculty} and {students} ({len(extra)} outside the dataset, {len(missing)} missing). "
            + TRANSITION_HINT
        )

    expected_slots = {(sl.subject_code, sl.section_label): fid for fid, sls in cfg.faculty_slot_map().items() for sl in sls}
    actual_slots = {
        (code, label): login
        for code, label, login in session.execute(
            select(Subject.code, Section.label, User.login_id)
            .select_from(TeachingAssignment)
            .join(Subject, Subject.id == TeachingAssignment.subject_id)
            .join(Section, Section.id == TeachingAssignment.section_id)
            .join(User, User.id == TeachingAssignment.faculty_id)
            .where(User.login_id.in_(wanted_faculty))
        )
    }
    if actual_slots != expected_slots:
        raise DatasetMismatch(
            f"Teaching assignments differ from the configured mapping ({len(actual_slots)} found, "
            f"{len(expected_slots)} expected). " + TRANSITION_HINT
        )
    wanted_section = {sid: cfg.section_label(sem, nm) for sid, (sem, nm) in cfg.student_section_map().items()}
    actual_section = {
        login: label
        for login, label in session.execute(
            select(User.login_id, Section.label)
            .select_from(StudentProfile)
            .join(User, User.id == StudentProfile.user_id)
            .join(Section, Section.id == StudentProfile.section_id)
            .where(User.login_id.in_(wanted_section))
        )
    }
    if actual_section != wanted_section:
        wrong = sum(1 for k, v in wanted_section.items() if actual_section.get(k) != v)
        raise DatasetMismatch(f"{wrong} students are not in their configured section. " + TRANSITION_HINT)
    idle = [fid for fid, sls in cfg.faculty_slot_map().items() if not sls]
    if idle:
        raise SeedError(f"Faculty without a teaching assignment: {idle}")

    no_profile = session.scalar(
        select(func.count())
        .select_from(User)
        .outerjoin(StudentProfile, StudentProfile.user_id == User.id)
        .where(User.role == UserRole.STUDENT, StudentProfile.user_id.is_(None))
    )
    if no_profile:
        raise SeedError(f"{no_profile} students have no section profile")

    non_student_profiles = session.scalar(
        select(func.count())
        .select_from(StudentProfile)
        .join(User, User.id == StudentProfile.user_id)
        .where(User.role != UserRole.STUDENT)
    )
    if non_student_profiles:
        raise SeedError("A student profile references a non-student user")

    wrong_faculty = session.scalar(
        select(func.count())
        .select_from(TeachingAssignment)
        .join(User, User.id == TeachingAssignment.faculty_id)
        .where(User.role != UserRole.FACULTY)
    )
    if wrong_faculty:
        raise SeedError("A teaching assignment references a non-faculty user")

    sub, sec = aliased(Subject), aliased(Section)
    mismatched = session.scalar(
        select(func.count())
        .select_from(TeachingAssignment)
        .join(sub, sub.id == TeachingAssignment.subject_id)
        .join(sec, sec.id == TeachingAssignment.section_id)
        .where(sub.semester != sec.semester)
    )
    if mismatched:
        raise SeedError(f"{mismatched} teaching assignments pair a subject with a section of another semester")

    logger.info("seed: verified %d faculty, %d students", faculty, students)
