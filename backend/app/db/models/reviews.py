import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, uuid_pk


class ReviewStatus(str, enum.Enum):
    UNDER_REVIEW = "UNDER_REVIEW"
    ACCEPTED = "ACCEPTED"
    REVISION_REQUESTED = "REVISION_REQUESTED"


class Review(Base):
    """Append-only review log. The current review is the latest row; no row = NOT_REVIEWED."""

    __tablename__ = "reviews"
    __table_args__ = (
        Index("ix_reviews_submission_reviewed_desc", "submission_id", text("reviewed_at DESC")),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    submission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("submissions.id", ondelete="RESTRICT")
    )
    version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("submission_versions.id", ondelete="RESTRICT")
    )
    reviewer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    status: Mapped[ReviewStatus] = mapped_column(Enum(ReviewStatus, name="review_status"))
    feedback: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
