import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# NOT_REVIEWED is never stored: it means "no review of the latest version yet" (architecture §15.1).
ReviewStatusLiteral = Literal["NOT_REVIEWED", "UNDER_REVIEW", "ACCEPTED", "REVISION_REQUESTED"]
RecordableStatus = Literal["UNDER_REVIEW", "ACCEPTED", "REVISION_REQUESTED"]


class ReviewIn(BaseModel):
    """POST /faculty/submissions/{id}/reviews. The reviewer, the version and the time are set by the server."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    status: RecordableStatus
    feedback: str | None = Field(default=None, max_length=2000)
    # Optional guard for the UI: the version the reviewer was looking at. A newer upload makes it a 409.
    expected_version_no: int | None = Field(default=None, ge=1, strict=True)

    @field_validator("feedback")
    @classmethod
    def _feedback(cls, v: str | None) -> str | None:
        if not v:
            return None
        if any(ord(c) < 32 and c not in "\n\r\t" for c in v):
            raise ValueError("Control characters are not allowed")
        return v

    @model_validator(mode="after")
    def _revision_needs_feedback(self) -> "ReviewIn":
        if self.status == "REVISION_REQUESTED" and not self.feedback:
            raise ValueError("Tell the student what to revise: feedback is required for a revision request")
        return self


class ReviewOut(BaseModel):
    id: uuid.UUID
    version_no: int
    status: RecordableStatus
    feedback: str | None
    reviewer_name: str
    reviewed_at: datetime
    is_current: bool  # the latest review of the latest version
