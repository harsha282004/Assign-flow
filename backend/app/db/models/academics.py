import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, uuid_pk


class Section(Base):
    __tablename__ = "sections"
    __table_args__ = (
        UniqueConstraint("semester", "name", name="uq_sections_semester_name"),
        CheckConstraint("semester BETWEEN 1 AND 8", name="semester_range"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    semester: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(10))
    label: Mapped[str] = mapped_column(String(30), unique=True)


class Subject(Base):
    __tablename__ = "subjects"
    __table_args__ = (CheckConstraint("semester BETWEEN 1 AND 8", name="semester_range"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(150))
    semester: Mapped[int] = mapped_column(Integer)


class StudentProfile(Base):
    """Authoritative student -> section mapping. The user must have role STUDENT (seed/service check)."""

    __tablename__ = "student_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True
    )
    section_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sections.id", ondelete="RESTRICT"), index=True
    )


class TeachingAssignment(Base):
    """Faculty authorisation: one faculty member per (subject, section) slot (assumption A3)."""

    __tablename__ = "teaching_assignments"
    __table_args__ = (
        UniqueConstraint("subject_id", "section_id", name="uq_teaching_assignments_subject_section"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    faculty_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    subject_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subjects.id", ondelete="RESTRICT")
    )
    section_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sections.id", ondelete="RESTRICT")
    )
