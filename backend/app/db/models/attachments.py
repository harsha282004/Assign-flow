"""Reference materials attached by faculty to an assignment (PDF / PPT / PPTX in private object storage)."""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, uuid_pk


class AssignmentAttachment(Base):
    """One reference document of an assignment. The bytes live in MinIO under `storage_key` (server-generated);
    the display filename is metadata only. Rows are added or removed while the assignment is a DRAFT and are
    frozen once it is published."""

    __tablename__ = "assignment_attachments"
    __table_args__ = (
        CheckConstraint("size_bytes > 0", name="size_positive"),
        Index("ix_assignment_attachments_assignment_created", "assignment_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    assignment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assignments.id", ondelete="RESTRICT")
    )
    original_filename: Mapped[str] = mapped_column(String(200))
    storage_key: Mapped[str] = mapped_column(String(300), unique=True)
    mime_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
