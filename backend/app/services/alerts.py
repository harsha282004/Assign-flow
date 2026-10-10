"""Computed alerts (architecture §22 table 1). Calculated from the server clock on each request; nothing is stored,
so there is no scheduler and duplicates are impossible. Students only; faculty are informed through stored
notifications (new late requests)."""

import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Assignment,
    AssignmentStatus,
    LateRequest,
    LateRequestStatus,
    Submission,
    SubmissionVersion,
    User,
    UserRole,
)
from app.services import late_windows, scope

SOON = timedelta(hours=3)
DAY = timedelta(hours=24)
URGENCY = {"WINDOW_CLOSING": 0, "DUE_3H": 1, "MISSING": 2, "DUE_24H": 3, "WINDOW_EXPIRED": 4}


def compute(db: Session, user: User, now: datetime) -> list[dict]:
    if user.role != UserRole.STUDENT:
        return []
    section_id = scope.student_section_id(db, user.id)
    if section_id is None:
        return []
    assignments = db.scalars(
        select(Assignment).where(Assignment.section_id == section_id, Assignment.status == AssignmentStatus.PUBLISHED)
    ).all()
    ids = [a.id for a in assignments]
    if not ids:
        return []
    submitted: set[uuid.UUID] = set(
        db.scalars(
            select(Submission.assignment_id)
            .join(SubmissionVersion, SubmissionVersion.submission_id == Submission.id)
            .where(Submission.student_id == user.id, Submission.assignment_id.in_(ids))
            .distinct()
        )
    )
    requests = {
        r.assignment_id: r
        for r in db.scalars(
            select(LateRequest).where(LateRequest.student_id == user.id, LateRequest.assignment_id.in_(ids))
        )
    }
    used = late_windows.used_request_ids(db, [r.id for r in requests.values()])

    out: list[dict] = []

    def add(kind: str, a: Assignment, at: datetime, message: str) -> None:
        out.append(dict(type=kind, assignment_id=a.id, assignment_title=a.title, message=message, at=at))

    for a in assignments:
        request = requests.get(a.id)
        open_window = (
            request is not None
            and request.status == LateRequestStatus.APPROVED
            and request.id not in used
            and request.window_end is not None
            and now <= request.window_end
        )
        if a.id not in submitted:
            if now <= a.deadline <= now + SOON:
                add("DUE_3H", a, a.deadline, f'"{a.title}" is due within 3 hours and has no submission yet.')
            elif now <= a.deadline <= now + DAY:
                add("DUE_24H", a, a.deadline, f'"{a.title}" is due within 24 hours and has no submission yet.')
            elif a.deadline < now and not open_window:
                add("MISSING", a, a.deadline, f'"{a.title}" is missing: the deadline passed with no submission.')
        if request is not None and request.status == LateRequestStatus.APPROVED and request.id not in used:
            if open_window and request.window_end <= now + SOON:
                add(
                    "WINDOW_CLOSING",
                    a,
                    request.window_end,
                    f'Your approved late-submission window for "{a.title}" closes within 3 hours.',
                )
            elif request.window_end is not None and request.window_end < now:
                add(
                    "WINDOW_EXPIRED",
                    a,
                    request.window_end,
                    f'Your approved late-submission window for "{a.title}" has expired.',
                )
    return sorted(out, key=lambda x: (URGENCY[x["type"]], x["at"]))
