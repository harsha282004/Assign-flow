import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas.reviews import ReviewOut, ReviewStatusLiteral
from app.schemas.timeline import TimelineEvent, WhyThisStatus

TimingLiteral = Literal["PENDING", "ON_TIME", "LATE", "MISSING"]
UploadContextLiteral = Literal["REGULAR", "LATE_APPROVED", "REVISION"]
# Stored request status plus the derived display states (architecture §15.1, §17.2).
RequestStateLiteral = Literal["PENDING", "APPROVED", "REJECTED", "EXPIRED", "USED"]
RequestStatusLiteral = Literal["NONE", "PENDING", "APPROVED", "REJECTED", "EXPIRED", "USED"]


class VersionOut(BaseModel):
    """One immutable upload. The storage key is internal and never exposed."""

    id: uuid.UUID
    version_no: int
    original_filename: str
    mime_type: str
    size_bytes: int
    sha256: str
    uploaded_at: datetime  # server clock, UTC
    deadline_at_upload: datetime  # snapshot of the deadline in force when the file was received
    upload_context: UploadContextLiteral
    timing_at_upload: Literal["ON_TIME", "LATE"]  # against deadline_at_upload
    timing_now: Literal["ON_TIME", "LATE"]  # against the current deadline


class UploadResult(BaseModel):
    submission_id: uuid.UUID
    version_id: uuid.UUID
    version_no: int
    uploaded_at: datetime
    deadline_at_upload: datetime
    upload_context: UploadContextLiteral
    version_timing: Literal["ON_TIME", "LATE"]
    submission_timing: TimingLiteral
    is_resubmitted: bool


class StudentRef(BaseModel):
    id: uuid.UUID
    login_id: str
    full_name: str


class RosterRow(BaseModel):
    student: StudentRef
    timing: TimingLiteral
    late_approved: bool  # first version came through an approved late request and is still late: "Late (approved)"
    is_resubmitted: bool
    version_count: int
    latest_uploaded_at: datetime | None
    request_status: RequestStatusLiteral
    review_status: ReviewStatusLiteral  # the current review, independent of timing


class StudentSubmissionDetail(BaseModel):
    """GET /faculty/assignments/{id}/students/{student_id}/timeline (versions part; events arrive in Phase 7)."""

    student: StudentRef
    deadline: datetime
    original_deadline: datetime
    timing: TimingLiteral
    late_approved: bool
    is_resubmitted: bool
    request_status: RequestStatusLiteral
    submission_id: uuid.UUID | None  # needed by the review form; None until the first upload
    latest_version_no: int
    review_status: ReviewStatusLiteral
    reviews: list[ReviewOut]
    versions: list[VersionOut]
    events: list[TimelineEvent]
    why_this_status: WhyThisStatus
