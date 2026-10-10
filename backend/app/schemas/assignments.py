import uuid
from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.attachments import AttachmentOut
from app.schemas.auth import SectionOut, SubjectOut
from app.schemas.late_requests import LateRequestOut
from app.schemas.reviews import ReviewOut, ReviewStatusLiteral
from app.schemas.submissions import RequestStatusLiteral, VersionOut
from app.schemas.timeline import TimelineEvent, WhyThisStatus

# Supported upload types (architecture assumption A6).
AllowedType = Literal["pdf", "docx", "pptx", "zip", "png", "jpg"]
AssignmentStatusLiteral = Literal["DRAFT", "PUBLISHED", "ARCHIVED"]


def _dedupe(types: list[str]) -> list[str]:
    return list(dict.fromkeys(types))


class AssignmentCreate(BaseModel):
    """POST /faculty/assignments. Unknown fields (status, created_by, timestamps...) are rejected."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=150)
    instructions: str = Field(min_length=1, max_length=5000)
    subject_id: uuid.UUID
    section_id: uuid.UUID
    deadline: AwareDatetime  # must carry a UTC offset; naive values are rejected
    allowed_types: list[AllowedType] = Field(min_length=1, max_length=6)
    max_file_mb: int = Field(default=10, ge=1, le=10)
    publish: bool = False

    @field_validator("allowed_types")
    @classmethod
    def _unique_types(cls, v: list[str]) -> list[str]:
        return _dedupe(v)


class AssignmentUpdate(BaseModel):
    """PATCH /faculty/assignments/{id}: editable fields of a DRAFT. Subject/section/status are not editable."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str | None = Field(default=None, min_length=1, max_length=150)
    instructions: str | None = Field(default=None, min_length=1, max_length=5000)
    deadline: AwareDatetime | None = None
    allowed_types: list[AllowedType] | None = Field(default=None, min_length=1, max_length=6)
    max_file_mb: int | None = Field(default=None, ge=1, le=10)

    @field_validator("allowed_types")
    @classmethod
    def _unique_types(cls, v: list[str] | None) -> list[str] | None:
        return _dedupe(v) if v is not None else v

    @model_validator(mode="after")
    def _at_least_one_real_value(self) -> "AssignmentUpdate":
        given = {name for name in self.model_fields_set if getattr(self, name) is not None}
        if not given:
            raise ValueError("Provide at least one field to change")
        if self.model_fields_set - given:
            raise ValueError("Fields cannot be set to null")
        return self


class DeadlineChangeIn(BaseModel):
    """PATCH /faculty/assignments/{id}/deadline. The timestamp of the change is set by the server."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    new_deadline: AwareDatetime
    reason: str | None = Field(default=None, max_length=500)

    @field_validator("reason")
    @classmethod
    def _blank_is_none(cls, v: str | None) -> str | None:
        return v or None


class DeadlineChangeOut(BaseModel):
    id: uuid.UUID
    old_deadline: datetime
    new_deadline: datetime
    changed_by_name: str
    changed_at: datetime
    reason: str | None


class FacultyAssignmentSummary(BaseModel):
    id: uuid.UUID
    title: str
    assignment_type: Literal["FILE", "QUIZ"] = "FILE"
    status: AssignmentStatusLiteral
    subject: SubjectOut
    section: SectionOut
    original_deadline: datetime
    deadline: datetime
    published_at: datetime | None
    archived_at: datetime | None = None
    created_at: datetime
    # Real count of students in the section. Submission-based counts arrive with later phases.
    expected_students: int


class FacultyAssignmentDetail(FacultyAssignmentSummary):
    instructions: str
    allowed_types: list[str]
    max_file_mb: int
    deadline_history: list[DeadlineChangeOut]
    attachments: list[AttachmentOut]  # reference materials (editable while DRAFT)


class ArchiveIn(BaseModel):
    """POST /faculty/assignments/{id}/archive and /restore. The time of the change is set by the server."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    reason: str | None = Field(default=None, max_length=500)

    @field_validator("reason")
    @classmethod
    def _blank_is_none(cls, v: str | None) -> str | None:
        return v or None


class DeletionCheck(BaseModel):
    """What stands in the way of permanently deleting an assignment (empty `blockers` = it can be deleted)."""

    assignment_id: uuid.UUID
    title: str
    status: AssignmentStatusLiteral
    can_delete: bool
    # DELETE (a draft), ARCHIVE (a published assignment), RESTORE (an archived one): what the UI should offer.
    action: Literal["DELETE", "ARCHIVE", "RESTORE"]
    can_archive: bool
    student_history: bool  # submissions, reviews, late requests, deadline changes or notifications exist
    blockers: dict[str, int]
    reference_files: int
    message: str | None


class DeletionResult(BaseModel):
    deleted: bool
    assignment_id: uuid.UUID
    title: str
    files_removed: int
    files_left: int  # unreferenced storage objects that could not be removed (cleanup via scripts/find_orphans.py)


class StudentAssignmentItem(BaseModel):
    id: uuid.UUID
    title: str
    assignment_type: Literal["FILE", "QUIZ"] = "FILE"
    # Quizzes only (None for file assignments): own attempt state, size and result.
    quiz_status: Literal["NOT_STARTED", "IN_PROGRESS", "SUBMITTED"] | None = None
    question_count: int | None = None
    total_marks: int | None = None
    duration_minutes: int | None = None
    quiz_score: int | None = None
    subject: SubjectOut
    faculty_name: str | None
    published_at: datetime
    deadline: datetime
    # Submission-level timing (architecture §15.2): PENDING / MISSING without a submission, otherwise the
    # timing of the FIRST version against the current deadline.
    timing: Literal["PENDING", "ON_TIME", "LATE", "MISSING"]
    # True when that first version was uploaded through an approved late request and is still late.
    late_approved: bool
    is_resubmitted: bool
    request_status: RequestStatusLiteral
    # ARCHIVED: kept for the student's own history, read-only, outside the active work list.
    assignment_state: Literal["ACTIVE", "ARCHIVED"] = "ACTIVE"
    # The current review (latest review of the latest version) is private to the student and the teacher.
    review_status: ReviewStatusLiteral
    latest_feedback: str | None


class StudentAssignmentDetail(StudentAssignmentItem):
    instructions: str
    allowed_types: list[str]
    max_file_mb: int
    original_deadline: datetime
    section: SectionOut
    versions: list[VersionOut]
    # Server-evaluated eligibility (architecture §16.3) so the UI never computes statuses itself.
    can_upload: bool
    upload_blocked_reason: Literal["DEADLINE_PASSED", "SUBMISSION_ACCEPTED", "ARCHIVED"] | None
    # The student's own late request (at most one) and whether a new one may be created (architecture §17.3).
    late_request: LateRequestOut | None
    can_request_late: bool
    reviews: list[ReviewOut]
    events: list[TimelineEvent]
    why_this_status: WhyThisStatus
    attachments: list[AttachmentOut]  # reference materials, read-only for students
