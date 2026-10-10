"""Controlled transition of an existing database to the configured demo dataset.

    python -m app.db.transition_dataset            # dry run: report only, changes nothing
    python -m app.db.transition_dataset --apply    # perform the transition in ONE transaction

What it does (and nothing else):
  * renames dataset accounts to their curated names (login IDs, password hashes and all records are untouched);
  * moves a student between sections only if NOTHING else references that student (otherwise it is reported as
    a blocker and the whole transition stops: such a move needs explicit approval);
  * removes accounts that are not part of the configured dataset, together with their student profile or
    teaching rows, but ONLY if no other record (assignment, submission, late request, review, notification, quiz
    attempt, ...) references them. Every foreign key is discovered from the live schema, so tables added later are
    covered automatically;
  * makes the teaching assignments of the dataset's faculty match the configuration (re-assigning or removing a
    class is refused while an assignment exists for that class);
  * removes sections and subjects that are no longer configured, only when nothing references them;
  * then runs the normal idempotent seed, which creates whatever is missing and verifies the final shape.

If anything blocks the transition, the report says what and why and NOTHING is changed. Surviving accounts keep
their login ID, name, section and password hash. It never drops tables or volumes.
"""

import argparse
import sys
from dataclasses import dataclass, field

from sqlalchemy import inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Section, StudentProfile, Subject, TeachingAssignment, User
from app.db.seeds import seed_config as cfg
from app.db.seeds.runner import run_seed
from app.db.seeds.seed_academics import seed_academics
from app.db.session import make_engine

# Rows in these tables are part of an account / class definition and are removed together with it.
OWNED = {"student_profiles", "teaching_assignments"}


@dataclass
class Plan:
    remove_users: list[str] = field(default_factory=list)
    remove_sections: list[str] = field(default_factory=list)
    remove_subjects: list[str] = field(default_factory=list)
    teaching_to_drop: list[tuple[str, str, str]] = field(default_factory=list)  # (subject, section, faculty)
    renames: list[tuple[str, str, str]] = field(default_factory=list)  # (login, old name, new name)
    moves: list[tuple[str, str, str]] = field(default_factory=list)  # (student, from section, to section)
    blockers: list[str] = field(default_factory=list)
    checks: list[tuple[str, int]] = field(default_factory=list)  # every dependent-record check and its count


def _references(engine: Engine, parent: str) -> list[tuple[str, str]]:
    """(table, column) pairs holding a foreign key to `parent`.id, read from the live schema."""
    insp = inspect(engine)
    found = []
    for table in insp.get_table_names():
        for fk in insp.get_foreign_keys(table):
            if fk["referred_table"] == parent:
                found.extend((table, col) for col in fk["constrained_columns"])
    return found


def build_plan(session: Session) -> Plan:
    engine = session.get_bind()
    plan = Plan()
    wanted_users = set(cfg.faculty_ids()) | set(cfg.student_ids())
    wanted_sections = {cfg.section_label(sem, name) for sem, name in cfg.sections()}
    wanted_subjects = {code for sem in cfg.SEMESTERS for code, _ in cfg.SUBJECTS[sem]}

    legacy_users = {
        u.login_id: u.id for u in session.execute(select(User.login_id, User.id)) if u.login_id not in wanted_users
    }
    plan.remove_users = sorted(legacy_users)
    user_ids = list(legacy_users.values())
    for table, column in _references(engine, "users"):
        if table in OWNED or not user_ids:
            continue
        n = session.execute(
            text(f'SELECT count(*) FROM "{table}" WHERE "{column}" = ANY(:ids)'), {"ids": user_ids}
        ).scalar_one()
        plan.checks.append((f"{table}.{column} rows referencing accounts to REMOVE", n))
        if n:
            plan.blockers.append(f"{n} row(s) in {table}.{column} reference accounts that would be removed")

    for login, name in session.execute(select(User.login_id, User.full_name)):
        if login in wanted_users and name != cfg.display_name(login):
            plan.renames.append((login, name, cfg.display_name(login)))
    plan.renames.sort()

    expected_section = {sid: cfg.section_label(sem, nm) for sid, (sem, nm) in cfg.student_section_map().items()}
    current = session.execute(
        select(User.login_id, User.id, Section.label)
        .select_from(StudentProfile)
        .join(User, User.id == StudentProfile.user_id)
        .join(Section, Section.id == StudentProfile.section_id)
    ).all()
    for login, uid, label in current:
        if login in expected_section and expected_section[login] != label:
            plan.moves.append((login, label, expected_section[login]))
            for table, column in _references(engine, "users"):
                if table in OWNED:
                    continue
                n = session.execute(
                    text(f'SELECT count(*) FROM "{table}" WHERE "{column}" = :id'), {"id": uid}
                ).scalar_one()
                plan.checks.append((f"{table}.{column} rows referencing student {login} (to MOVE)", n))
                if n:
                    plan.blockers.append(
                        f"{login} would move {label} -> {expected_section[login]} but {n} row(s) in "
                        f"{table}.{column} reference the student: moving needs explicit approval"
                    )
    plan.moves.sort()

    legacy_sections = {
        s.label: s.id for s in session.execute(select(Section.label, Section.id)) if s.label not in wanted_sections
    }
    plan.remove_sections = sorted(legacy_sections)
    legacy_subjects = {
        s.code: s.id for s in session.execute(select(Subject.code, Subject.id)) if s.code not in wanted_subjects
    }
    plan.remove_subjects = sorted(legacy_subjects)
    for parent, ids, label in (
        ("sections", list(legacy_sections.values()), "sections"),
        ("subjects", list(legacy_subjects.values()), "subjects"),
    ):
        for table, column in _references(engine, parent):
            if table in OWNED or not ids:
                continue
            n = session.execute(
                text(f'SELECT count(*) FROM "{table}" WHERE "{column}" = ANY(:ids)'), {"ids": ids}
            ).scalar_one()
            plan.checks.append((f"{table}.{column} rows referencing {label} to REMOVE", n))
            if n:
                plan.blockers.append(f"{n} row(s) in {table}.{column} reference {label} that would be removed")

    # Teaching rows of surviving faculty that differ from the configuration.
    expected = {(sl.subject_code, sl.section_label): fid for fid, sls in cfg.faculty_slot_map().items() for sl in sls}
    rows = session.execute(
        select(Subject.code, Section.label, User.login_id, TeachingAssignment.id)
        .select_from(TeachingAssignment)
        .join(Subject, Subject.id == TeachingAssignment.subject_id)
        .join(Section, Section.id == TeachingAssignment.section_id)
        .join(User, User.id == TeachingAssignment.faculty_id)
    ).all()
    for code, label, login, _ in rows:
        key = (code, label)
        if login in legacy_users or key not in expected or expected[key] != login:
            plan.teaching_to_drop.append((code, label, login))
            if login not in legacy_users and code in wanted_subjects and label in wanted_sections:
                # A class that stays but changes teacher: refuse if it already has assignments.
                n = session.execute(
                    text(
                        "SELECT count(*) FROM assignments a JOIN subjects s ON s.id = a.subject_id "
                        "JOIN sections c ON c.id = a.section_id WHERE s.code = :code AND c.label = :label"
                    ),
                    {"code": code, "label": label},
                ).scalar_one()
                plan.checks.append((f"assignments of {code} / {label} (teacher changes from {login})", n))
                if n:
                    plan.blockers.append(
                        f"{code} / {label} has {n} assignment(s); its teacher cannot change from {login}"
                    )
    return plan


def apply_plan(session: Session, plan: Plan) -> None:
    wanted_users = set(cfg.faculty_ids()) | set(cfg.student_ids())
    seed_academics(session)  # make sure every target section exists before students move into it
    section_ids = {label: sid for label, sid in session.execute(select(Section.label, Section.id))}
    for login, _old, new in plan.moves:
        session.execute(
            text(
                "UPDATE student_profiles SET section_id = :s "
                "WHERE user_id = (SELECT id FROM users WHERE login_id = :l)"
            ),
            {"s": section_ids[new], "l": login},
        )
    for login, _old, new in plan.renames:
        session.execute(text("UPDATE users SET full_name = :n WHERE login_id = :l"), {"n": new, "l": login})
    drop = {(c, label) for c, label, _ in plan.teaching_to_drop}
    for code, label in drop:
        session.execute(
            text(
                "DELETE FROM teaching_assignments WHERE subject_id = (SELECT id FROM subjects WHERE code = :c) "
                "AND section_id = (SELECT id FROM sections WHERE label = :l)"
            ),
            {"c": code, "l": label},
        )
    legacy_ids = [
        u.id for u in session.execute(select(User.login_id, User.id)) if u.login_id not in wanted_users
    ]
    if legacy_ids:
        session.execute(text("DELETE FROM student_profiles WHERE user_id = ANY(:ids)"), {"ids": legacy_ids})
        session.execute(text("DELETE FROM teaching_assignments WHERE faculty_id = ANY(:ids)"), {"ids": legacy_ids})
        session.execute(text("DELETE FROM users WHERE id = ANY(:ids)"), {"ids": legacy_ids})
    if plan.remove_sections:
        session.execute(text("DELETE FROM sections WHERE label = ANY(:l)"), {"l": plan.remove_sections})
    if plan.remove_subjects:
        session.execute(text("DELETE FROM subjects WHERE code = ANY(:c)"), {"c": plan.remove_subjects})


def report(plan: Plan, apply: bool, verbose: bool = False) -> None:
    print(f"Target dataset: {cfg.FACULTY_COUNT} faculty, {len(cfg.student_ids())} students")
    print(f"  accounts to rename      : {len(plan.renames)}")
    print(f"  students to move        : {len(plan.moves)}")
    print(f"  accounts to remove      : {len(plan.remove_users)}")
    print(f"  sections to remove      : {plan.remove_sections}")
    print(f"  subjects to remove      : {plan.remove_subjects}")
    print(f"  teaching rows to rewrite: {len(plan.teaching_to_drop)}")
    print()
    print("DEPENDENT-RECORD CHECKS (row counts found; every one must be 0)")
    totals: dict[str, int] = {}
    for name, n in plan.checks:
        key = name.replace(name[name.find("student ") : name.find(" (to MOVE)")], "each moving student") if "(to MOVE)" in name else name
        totals[key] = totals.get(key, 0) + n
    for name, n in totals.items():
        print(f"  {name}: {n}")
    if verbose:
        print()
        print("RENAMES (login: old name -> new name)")
        for login, old, new in plan.renames:
            print(f"  {login}: {old} -> {new}")
        print()
        print("STUDENT SECTION MOVES")
        for login, old, new in plan.moves:
            print(f"  {login}: {old} -> {new}")
        print()
        print("ACCOUNTS TO REMOVE")
        print("  " + ", ".join(plan.remove_users))
        print()
        print("TEACHING ROWS TO REWRITE (subject, section, current teacher)")
        for code, label, login in sorted(plan.teaching_to_drop):
            print(f"  {code} {label} {login}")
    if plan.blockers:
        print("BLOCKED, nothing will be changed:")
        for b in plan.blockers:
            print(f"  - {b}")
    else:
        print("No dependent records found." + (" Applying…" if apply else " Dry run: nothing changed."))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--verbose", action="store_true", help="list every rename, move and removal")
    parser.add_argument("--apply", action="store_true", help="perform the transition (default: dry run)")
    args = parser.parse_args(argv)
    settings = get_settings()
    if not settings.seed_demo_password:
        print("SEED_DEMO_PASSWORD is required (it is used for accounts that do not exist yet).")
        return 2
    engine = make_engine(settings.database_url)
    with Session(engine) as session:
        plan = build_plan(session)
        report(plan, args.apply, args.verbose)
        if plan.blockers:
            return 1
        if not args.apply:
            return 0
        try:
            apply_plan(session, plan)
            run_seed(session, settings.seed_demo_password)  # creates what is missing, verifies, commits
        except Exception as exc:  # noqa: BLE001  (SeedError included: roll everything back)
            session.rollback()
            print(f"FAILED, rolled back, nothing changed: {exc}")
            return 1
    print("Transition complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
