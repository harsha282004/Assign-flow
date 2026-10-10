import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.auth import SectionOut, SubjectOut
from app.schemas.submissions import RequestStateLiteral, StudentRef, TimingLiteral, VersionOut

DEFAULT_WINDOW_HOURS = 24  # architecture §17.3


def _plain_text(value: str) -> str:
    """Plain text only: reject control characters (PostgreSQL cannot store NUL) but keep newlines and tabs."""
    if any(ord(c) < 32 and c not in "\n\r\t" for c in value):
        raise ValueError("Control characters are not allowed")
    return value


class LateRequestCreate(BaseModel):
    """POST /student/assignments/{id}/late-request. Only the reason is accepted; every other field is rejected."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    reason: str = Field(min_length=20, max_length=1000)

    @field_validator("reason")
    @classmethod
    def _reason(cls, v: str) -> str:
        return _plain_text(v)


class LateRequestDecisionIn(BaseModel):
    """POST /faculty/late-requests/{id}/decision. `decided_at` and the window are computed by the server."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    decision: Literal["APPROVE", "REJECT"]
    note: str | None = Field(default=None, max_length=500)
    window_hours: int | None = Field(default=None, ge=1, le=72, strict=True)  # a real integer, not "24" or true

    @field_validator("note")
    @classmethod
    def _note(cls, v: str | None) -> str | None:
        return _plain_text(v) if v else None

    @model_validator(mode="after")
    def _window_only_for_approval(self) -> "LateRequestDecisionIn":
        if self.decision == "REJECT" and self.window_hours is not None:
            raise ValueError("window_hours applies only to an approval")
        return self

    @property
    def effective_window_hours(self) -> int:
        return self.window_hours if self.window_hours is not None else DEFAULT_WINDOW_HOURS


class LateRequestOut(BaseModel):
    """A request as its student sees it."""

    id: uuid.UUID
    status: Literal["PENDING", "APPROVED", "REJECTED"]  # stored
    state: RequestStateLiteral  # stored status with the derived EXPIRED / USED labels
    reason: str
    requested_at: datetime
    deadline_at_request: datetime
    decided_by_name: str | None
    decided_at: datetime | None
    decision_note: str | None
    window_start: datetime | None
    window_end: datetime | None


class AssignmentRef(BaseModel):
    id: uuid.UUID
    title: str
    subject: SubjectOut
    section: SectionOut


class FacultyLateRequestItem(LateRequestOut):
    student: StudentRef
    assignment: AssignmentRef
    current_deadline: datetime


class FacultyLateRequestDetail(FacultyLateRequestItem):
    """Everything needed to decide: the student's current timing and any versions already uploaded."""

    submission_timing: TimingLiteral
    versions: list[VersionOut]
