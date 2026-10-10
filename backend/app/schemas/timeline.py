from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

EventType = Literal[
    "ASSIGNMENT_CREATED",
    "ASSIGNMENT_PUBLISHED",
    "ASSIGNMENT_ARCHIVED",
    "ASSIGNMENT_RESTORED",
    "DEADLINE_CHANGED",
    "LATE_REQUESTED",
    "REQUEST_APPROVED",
    "REQUEST_REJECTED",
    "VERSION_UPLOADED",
    "REVIEW_RECORDED",
    "REQUEST_WINDOW_EXPIRED",
    "DEADLINE_PASSED_NO_SUBMISSION",
]


class TimelineEvent(BaseModel):
    """One entry of the Deadline Integrity Timeline. Everything comes from a stored record, except the two
    derived markers, which are flagged `derived` and computed from the server clock (architecture §17.5)."""

    type: EventType
    at: datetime  # when it happened (the record's own timestamp)
    actor: str | None  # who did it, where a record names an actor
    summary: str  # one human sentence, times in IST
    data: dict[str, Any]  # the structured facts behind the sentence
    derived: bool = False


class WhyThisStatus(BaseModel):
    """"Why this status": the same status functions as everywhere else, explained in words."""

    timing: str
    headline: str
    lines: list[str]
