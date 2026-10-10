import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, uuid_pk


class LateRequestStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class LateRequest(Base):
    """One late-submission request per student per assignment. EXPIRED is derived, not stored."""

    __tablename__ = "late_requests"
    __table_args__ = (
        UniqueConstraint("assignment_id", "student_id", name="uq_late_requests_assignment_student"),
        CheckConstraint("char_length(reason) BETWEEN 20 AND 1000", name="reason_length"),
        # Decision fields are set iff status <> PENDING.
        CheckConstraint(
            "(status = 'PENDING') = (decided_by IS NULL AND decided_at IS NULL)",
            name="decision_fields_iff_decided",
        ),
        # Window fields are set iff status = APPROVED.
        CheckConstraint(
            "(status = 'APPROVED') = (window_start IS NOT NULL AND window_end IS NOT NULL)",
            name="window_fields_iff_approved",
        ),
        CheckConstraint("window_start IS NULL OR window_end > window_start", name="window_order"),
        Index("ix_late_requests_assignment_status", "assignment_id", "status"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    assignment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assignments.id", ondelete="RESTRICT")
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    reason: Mapped[str] = mapped_column(String(1000))
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deadline_at_request: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[LateRequestStatus] = mapped_column(
        Enum(LateRequestStatus, name="late_request_status"),
        server_default=text("'PENDING'"),
        default=LateRequestStatus.PENDING,
    )
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
