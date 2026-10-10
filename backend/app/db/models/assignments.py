import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, uuid_pk


class AssignmentStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    # Removed from active use but fully preserved (submissions, reviews, files). Reversible: restore -> PUBLISHED.
    ARCHIVED = "ARCHIVED"


class Assignment(Base):
    __tablename__ = "assignments"
    __table_args__ = (
        CheckConstraint("max_file_mb BETWEEN 1 AND 10", name="max_file_mb_range"),
        CheckConstraint("(status = 'ARCHIVED') = (archived_at IS NOT NULL)", name="archived_at_iff_archived"),
        CheckConstraint("assignment_type IN ('FILE', 'QUIZ')", name="type_valid"),
        CheckConstraint("duration_minutes IS NULL OR duration_minutes BETWEEN 1 AND 300", name="duration_range"),
        Index("ix_assignments_section_status", "section_id", "status"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    title: Mapped[str] = mapped_column(String(150))
    instructions: Mapped[str] = mapped_column(String(5000))
    subject_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subjects.id", ondelete="RESTRICT")
    )
    section_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sections.id", ondelete="RESTRICT")
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[AssignmentStatus] = mapped_column(
        Enum(AssignmentStatus, name="assignment_status"),
        server_default=text("'DRAFT'"),
        default=AssignmentStatus.DRAFT,
    )
    original_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Only mutable business field, and only through the deadline endpoint (architecture §14.2).
    deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    allowed_types: Mapped[list[str]] = mapped_column(ARRAY(Text))
    max_file_mb: Mapped[int] = mapped_column(Integer, server_default=text("10"), default=10)
    # FILE (instructions + file upload, the original workflow) or QUIZ (questions built in AssignFlow).
    assignment_type: Mapped[str] = mapped_column(String(10), server_default=text("'FILE'"), default="FILE")
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)  # quizzes: optional description
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)  # quizzes: optional time limit
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DeadlineChange(Base):
    """Insert-only audit row for every deadline change."""

    __tablename__ = "deadline_changes"
    __table_args__ = (
        Index("ix_deadline_changes_assignment_changed", "assignment_id", "changed_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    assignment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assignments.id", ondelete="RESTRICT")
    )
    old_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    new_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    changed_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)


class AssignmentStateChange(Base):
    """Insert-only audit row for every archive / restore (shown in the Deadline Integrity Timeline)."""

    __tablename__ = "assignment_state_changes"
    __table_args__ = (
        Index("ix_assignment_state_changes_assignment_changed", "assignment_id", "changed_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    assignment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assignments.id", ondelete="RESTRICT")
    )
    from_status: Mapped[str] = mapped_column(String(20))
    to_status: Mapped[str] = mapped_column(String(20))
    changed_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
