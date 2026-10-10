"""Read-only helpers shared by the submission and late-request services (architecture §17.2, §17.3).

Kept separate so that `submissions` (uploads) and `late_requests` (workflow) do not import each other.
"""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import LateRequest, LateRequestStatus, SubmissionVersion
from app.services.eligibility import LateGrant


def derive_state(
    status: LateRequestStatus, window_end: datetime | None, used: bool, now: datetime
) -> str:
    """Display state: the stored status, plus the derived USED / EXPIRED labels of an APPROVED request.
    Nothing is stored and no background job runs. The window is inclusive, so EXPIRED starts after window_end."""
    if status != LateRequestStatus.APPROVED:
        return status.value
    if used:
        return "USED"
    if window_end is not None and now > window_end:
        return "EXPIRED"
    return "APPROVED"


def get_request(db: Session, assignment_id: uuid.UUID, student_id: uuid.UUID) -> LateRequest | None:
    return db.scalar(
        select(LateRequest)
        .where(LateRequest.assignment_id == assignment_id, LateRequest.student_id == student_id)
        # Always the committed row, never a copy cached earlier in this session: a decision may have landed since.
        .execution_options(populate_existing=True)
    )


def request_states(db: Session, assignment_id: uuid.UUID, now: datetime) -> dict[uuid.UUID, str]:
    """student_id -> display state of that student's request for one assignment (students without one are absent)."""
    requests = list(db.scalars(select(LateRequest).where(LateRequest.assignment_id == assignment_id)))
    used = used_request_ids(db, [r.id for r in requests])
    return {r.student_id: derive_state(r.status, r.window_end, r.id in used, now) for r in requests}


def student_request_states(
    db: Session, student_id: uuid.UUID, assignment_ids: list[uuid.UUID], now: datetime
) -> dict[uuid.UUID, str]:
    """assignment_id -> display state of this student's request (assignments without one are absent)."""
    if not assignment_ids:
        return {}
    requests = list(
        db.scalars(
            select(LateRequest).where(
                LateRequest.student_id == student_id, LateRequest.assignment_id.in_(assignment_ids)
            )
        )
    )
    used = used_request_ids(db, [r.id for r in requests])
    return {r.assignment_id: derive_state(r.status, r.window_end, r.id in used, now) for r in requests}


def approved_grant(db: Session, assignment_id: uuid.UUID, student_id: uuid.UUID) -> LateGrant | None:
    """The student's APPROVED request for this assignment as an upload grant (None otherwise)."""
    request = get_request(db, assignment_id, student_id)
    if (
        request is None
        or request.status != LateRequestStatus.APPROVED
        or request.window_start is None
        or request.window_end is None
    ):
        return None
    return LateGrant(request.id, request.window_start, request.window_end)


def used_request_ids(db: Session, request_ids: list[uuid.UUID]) -> set[uuid.UUID]:
    """Requests that already authorized at least one upload."""
    if not request_ids:
        return set()
    return set(
        db.scalars(
            select(SubmissionVersion.late_request_id)
            .where(SubmissionVersion.late_request_id.in_(request_ids))
            .distinct()
        )
    )
