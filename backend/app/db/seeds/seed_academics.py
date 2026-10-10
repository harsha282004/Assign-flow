"""Seed sections and subjects (idempotent: INSERT ... ON CONFLICT DO NOTHING on natural keys)."""

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models import Section, Subject
from app.db.seeds import seed_config as cfg


def seed_academics(session: Session) -> None:
    session.execute(
        insert(Section)
        .values(
            [
                {"semester": sem, "name": name, "label": cfg.section_label(sem, name)}
                for sem, name in cfg.sections()
            ]
        )
        .on_conflict_do_nothing(index_elements=["semester", "name"])
    )
    session.execute(
        insert(Subject)
        .values(
            [
                {"code": code, "name": subject_name, "semester": sem}
                for sem, subjects in cfg.SUBJECTS.items()
                if sem in cfg.SEMESTERS
                for code, subject_name in subjects
            ]
        )
        .on_conflict_do_nothing(index_elements=["code"])
    )
