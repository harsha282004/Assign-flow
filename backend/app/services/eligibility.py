"""Upload eligibility (architecture §16.3), evaluated at `received_at`. Pure functions.

  2. latest review ACCEPTED                     -> 409 SUBMISSION_ACCEPTED
  3. received_at <= deadline                    -> REGULAR
  4. after deadline, latest review REVISION_REQUESTED -> REVISION
  5. after deadline, own late request APPROVED, window_start <= received_at <= window_end, and the student
     has no submission yet (or the submission started inside this approved window) -> LATE_APPROVED
  6/7. after deadline otherwise                 -> 409 DEADLINE_PASSED
Rule 1 (scope / published) is enforced by the scope helpers. Reviews can only be read here; the review
workflow itself belongs to a later phase.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from app.core.errors import AppError
from app.db.models import ReviewStatus, UploadContext

MESSAGES = {
    "DEADLINE_PASSED": "The deadline for this assignment has passed.",
    "SUBMISSION_ACCEPTED": "Your submission has already been accepted, so it can no longer be replaced.",
}


@dataclass(frozen=True)
class LateGrant:
    """An APPROVED late request: the only way to upload after the deadline without a faculty revision."""

    request_id: uuid.UUID
    window_start: datetime
    window_end: datetime


@dataclass(frozen=True)
class UploadDecision:
    context: UploadContext | None
    blocked_code: str | None = None
    late_request_id: uuid.UUID | None = None

    @property
    def allowed(self) -> bool:
        return self.context is not None


def evaluate_upload(
    received_at: datetime,
    deadline: datetime,
    latest_review: ReviewStatus | None,
    *,
    grant: LateGrant | None = None,
    first_context: UploadContext | None = None,
) -> UploadDecision:
    """`first_context` is the context of the student's first version (None when they have not submitted)."""
    if latest_review == ReviewStatus.ACCEPTED:
        return UploadDecision(None, "SUBMISSION_ACCEPTED")
    if received_at <= deadline:  # exactly at the deadline is still on time
        return UploadDecision(UploadContext.REGULAR)
    if latest_review == ReviewStatus.REVISION_REQUESTED:
        return UploadDecision(UploadContext.REVISION)
    if (
        grant is not None
        and grant.window_start <= received_at <= grant.window_end  # both ends inclusive
        and first_context in (None, UploadContext.LATE_APPROVED)  # rule 6: no late request for existing work
    ):
        return UploadDecision(UploadContext.LATE_APPROVED, late_request_id=grant.request_id)
    return UploadDecision(None, "DEADLINE_PASSED")


def require_upload_allowed(
    received_at: datetime,
    deadline: datetime,
    latest_review: ReviewStatus | None,
    *,
    grant: LateGrant | None = None,
    first_context: UploadContext | None = None,
) -> UploadDecision:
    decision = evaluate_upload(received_at, deadline, latest_review, grant=grant, first_context=first_context)
    if decision.context is None:
        code = decision.blocked_code or "DEADLINE_PASSED"
        raise AppError(code, 409, MESSAGES[code])
    return decision
