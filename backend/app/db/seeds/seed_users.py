"""Seed fictional faculty/students, student profiles and teaching assignments (idempotent)."""

import logging

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.models import Section, StudentProfile, Subject, TeachingAssignment, User, UserRole
from app.db.seeds import seed_config as cfg

logger = logging.getLogger("assignflow.seed")


def seed_users(session: Session, password: str) -> None:
    faculty = cfg.faculty_ids()
    students = cfg.student_ids()
    names = {lid: cfg.display_name(lid) for lid in faculty + students}

    existing = set(session.scalars(select(User.login_id)))
    missing = [lid for lid in faculty + students if lid not in existing]
    # Hash only accounts that do not exist yet: re-running the seed must be fast and idempotent.
    rows = [
        {
            "login_id": lid,
            "full_name": names[lid],
            "role": UserRole.FACULTY if lid.startswith("FAC") else UserRole.STUDENT,
            "password_hash": hash_password(password),
        }
        for lid in missing
    ]
    if rows:
        session.execute(insert(User).values(rows).on_conflict_do_nothing(index_elements=["login_id"]))
    logger.info("seed: users created=%d already_present=%d", len(rows), len(existing))

    user_ids = {u.login_id: u.id for u in session.execute(select(User.login_id, User.id))}
    section_ids = {
        (s.semester, s.name): s.id for s in session.execute(select(Section.semester, Section.name, Section.id))
    }
    subject_ids = {s.code: s.id for s in session.execute(select(Subject.code, Subject.id))}

    # Student -> section profiles.
    profiles = [
        {"user_id": user_ids[sid], "section_id": section_ids[sec]}
        for sid, sec in cfg.student_section_map().items()
    ]
    session.execute(insert(StudentProfile).values(profiles).on_conflict_do_nothing(index_elements=["user_id"]))

    # Faculty teaching slots (semester of subject must equal semester of section).
    slots = []
    for fid, fslots in cfg.faculty_slot_map().items():
        for slot in fslots:
            subject_sem = next(
                sem for sem, subs in cfg.SUBJECTS.items() if any(c == slot.subject_code for c, _ in subs)
            )
            if subject_sem != slot.semester:
                raise ValueError(f"Slot for {fid}: subject {slot.subject_code} is not in semester {slot.semester}")
            slots.append(
                {
                    "faculty_id": user_ids[fid],
                    "subject_id": subject_ids[slot.subject_code],
                    "section_id": section_ids[(slot.semester, slot.section_name)],
                }
            )
    session.execute(
        insert(TeachingAssignment)
        .values(slots)
        .on_conflict_do_nothing(index_elements=["subject_id", "section_id"])
    )
