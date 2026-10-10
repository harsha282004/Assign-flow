import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, uuid_pk


class UploadContext(str, enum.Enum):
    REGULAR = "REGULAR"
    LATE_APPROVED = "LATE_APPROVED"
    REVISION = "REVISION"


class Submission(Base):
    """One logical submission per student per assignment; versions hold the uploads."""

    __tablename__ = "submissions"
    __table_args__ = (
        UniqueConstraint("assignment_id", "student_id", name="uq_submissions_assignment_student"),
        CheckConstraint("latest_version_no >= 0", name="latest_version_no_nonneg"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    assignment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assignments.id", ondelete="RESTRICT")
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # 0 until the first version is inserted; version_no = latest_version_no + 1 under row lock.
    latest_version_no: Mapped[int] = mapped_column(Integer, server_default=text("0"), default=0)


class SubmissionVersion(Base):
    """Immutable upload record (insert-only)."""

    __tablename__ = "submission_versions"
    __table_args__ = (
        UniqueConstraint(
            "submission_id", "version_no", name="uq_submission_versions_submission_version"
        ),
        CheckConstraint("version_no >= 1", name="version_no_positive"),
        CheckConstraint("size_bytes > 0", name="size_positive"),
        CheckConstraint("char_length(sha256) = 64", name="sha256_length"),
        CheckConstraint(
            "(upload_context = 'LATE_APPROVED') = (late_request_id IS NOT NULL)",
            name="late_context_iff_request",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    submission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("submissions.id", ondelete="RESTRICT")
    )
    version_no: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(String(300), unique=True)
    original_filename: Mapped[str] = mapped_column(String(200))
    mime_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    deadline_at_upload: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    upload_context: Mapped[UploadContext] = mapped_column(Enum(UploadContext, name="upload_context"))
    late_request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("late_requests.id", ondelete="RESTRICT"), nullable=True
    )
