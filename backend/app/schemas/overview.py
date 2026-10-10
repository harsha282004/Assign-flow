from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas.late_requests import AssignmentRef
from app.schemas.reviews import ReviewStatusLiteral
from app.schemas.submissions import RequestStatusLiteral, StudentRef, TimingLiteral


class Counts(BaseModel):
    """Counts for ONE student per assignment (never per version).

    expected = on_time + late + pending + missing        (every student of the section is in exactly one bucket)
    late_approved      subset of late (first version came through an approved late request)
    submitted          students with at least one version (= on_time + late)
    resubmitted        students with more than one version
    under_review / accepted / revision_requested   students whose CURRENT review (latest review of the latest
                       version) has that status; not_reviewed = submitted students with no current review
    reviewed           accepted + revision_requested (a decision was recorded)
    requests_pending   late requests waiting for a decision
    """

    expected: int
    on_time: int
    late: int
    late_approved: int
    pending: int
    missing: int
    submitted: int
    resubmitted: int
    under_review: int
    accepted: int
    revision_requested: int
    not_reviewed: int
    reviewed: int
    requests_pending: int


class AssignmentCounts(Counts):
    assignment: AssignmentRef
    deadline: datetime


class OverviewResponse(BaseModel):
    totals: Counts
    assignments: list[AssignmentCounts]


class OverviewStudentRow(BaseModel):
    assignment: AssignmentRef
    deadline: datetime
    student: StudentRef
    timing: TimingLiteral
    late_approved: bool
    is_resubmitted: bool
    version_count: int
    latest_uploaded_at: datetime | None
    review_status: ReviewStatusLiteral
    request_status: RequestStatusLiteral


class OverviewStudents(BaseModel):
    total: int  # rows matching the filters
    items: list[OverviewStudentRow]  # at most `limit`
    truncated: bool


TimingFilter = Literal["PENDING", "ON_TIME", "LATE", "MISSING"]
ReviewFilter = Literal["NOT_REVIEWED", "UNDER_REVIEW", "ACCEPTED", "REVISION_REQUESTED"]
