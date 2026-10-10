"""Deadline Integrity Timeline for one student x one assignment (architecture §17.5).

Every event is read from a real record (assignment, deadline_changes, late_requests, submission_versions, reviews)
with that record's own timestamp and actor. Nothing is written here. The only events that are not stored records
are the two derived markers (`REQUEST_WINDOW_EXPIRED`, `DEADLINE_PASSED_NO_SUBMISSION`), flagged `derived`.
Events are sorted by time; ties are broken by the event order below, then by version number.
"""

import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Assignment,
    AssignmentStateChange,
    DeadlineChange,
    LateRequest,
    LateRequestStatus,
    Review,
    Submission,
    SubmissionVersion,
    UploadContext,
    User,
)
from app.schemas.timeline import TimelineEvent, WhyThisStatus
from app.services import late_windows, status

IST = ZoneInfo("Asia/Kolkata")

# Tie-break order for events with the same timestamp.
ORDER = {
    "ASSIGNMENT_CREATED": 0,
    "ASSIGNMENT_PUBLISHED": 1,
    "ASSIGNMENT_ARCHIVED": 2,
    "ASSIGNMENT_RESTORED": 2,
    "DEADLINE_CHANGED": 2,
    "LATE_REQUESTED": 3,
    "REQUEST_APPROVED": 4,
    "REQUEST_REJECTED": 4,
    "VERSION_UPLOADED": 5,
    "REVIEW_RECORDED": 6,
    "REQUEST_WINDOW_EXPIRED": 7,
    "DEADLINE_PASSED_NO_SUBMISSION": 7,
}
REVIEW_LABELS = {"UNDER_REVIEW": "Under review", "ACCEPTED": "Accepted", "REVISION_REQUESTED": "Revision requested"}
CONTEXT_LABELS = {"REGULAR": "regular", "LATE_APPROVED": "late (approved)", "REVISION": "revision"}


def fmt(moment: datetime) -> str:
    return moment.astimezone(IST).strftime("%d %b %Y, %I:%M %p IST").lstrip("0")


def duration(delta: timedelta) -> str:
    seconds = int(abs(delta).total_seconds())
    if seconds < 60:
        return f"{seconds} s"
    minutes = seconds // 60
    days, rest = divmod(minutes, 1440)
    hours, mins = divmod(rest, 60)
    if days:
        return f"{days} d {hours} h"
    if hours:
        return f"{hours} h {mins} min"
    return f"{mins} min"


def _names(db: Session, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not ids:
        return {}
    return dict(db.execute(select(User.id, User.full_name).where(User.id.in_(ids))).all())


def build(
    db: Session, assignment: Assignment, student: User, now: datetime
) -> tuple[list[TimelineEvent], WhyThisStatus]:
    submission = db.scalar(
        select(Submission).where(Submission.assignment_id == assignment.id, Submission.student_id == student.id)
    )
    versions = (
        list(
            db.scalars(
                select(SubmissionVersion)
                .where(SubmissionVersion.submission_id == submission.id)
                .order_by(SubmissionVersion.version_no)
            )
        )
        if submission
        else []
    )
    reviews = (
        list(
            db.execute(
                select(Review, SubmissionVersion.version_no)
                .join(SubmissionVersion, SubmissionVersion.id == Review.version_id)
                .where(Review.submission_id == submission.id)
                .order_by(Review.reviewed_at, Review.id)
            ).all()
        )
        if submission
        else []
    )
    changes = list(
        db.scalars(
            select(DeadlineChange)
            .where(DeadlineChange.assignment_id == assignment.id)
            .order_by(DeadlineChange.changed_at, DeadlineChange.id)
        )
    )
    state_changes = list(
        db.scalars(
            select(AssignmentStateChange)
            .where(AssignmentStateChange.assignment_id == assignment.id)
            .order_by(AssignmentStateChange.changed_at, AssignmentStateChange.id)
        )
    )
    request = late_windows.get_request(db, assignment.id, student.id)

    ids = {assignment.created_by, student.id}
    ids |= {c.changed_by for c in changes}
    ids |= {c.changed_by for c in state_changes}
    ids |= {r.reviewer_id for r, _ in reviews}
    if request and request.decided_by:
        ids.add(request.decided_by)
    names = _names(db, ids)

    rows: list[tuple[datetime, int, int, TimelineEvent]] = []

    def add(event: TimelineEvent, seq: int = 0) -> None:
        rows.append((event.at, ORDER[event.type], seq, event))

    creator = names.get(assignment.created_by)
    add(
        TimelineEvent(
            type="ASSIGNMENT_CREATED",
            at=assignment.created_at,
            actor=creator,
            summary=f"Assignment created by {creator}. Deadline {fmt(assignment.original_deadline)}.",
            data={"original_deadline": assignment.original_deadline.isoformat()},
        )
    )
    if assignment.published_at is not None:
        add(
            TimelineEvent(
                type="ASSIGNMENT_PUBLISHED",
                at=assignment.published_at,
                actor=creator,
                summary=f"Published to the section with the original deadline {fmt(assignment.original_deadline)}.",
                data={"original_deadline": assignment.original_deadline.isoformat()},
            )
        )
    for i, sc in enumerate(state_changes):
        archived = sc.to_status == "ARCHIVED"
        actor = names.get(sc.changed_by)
        reason = f" Reason: {sc.reason}" if sc.reason else ""
        add(
            TimelineEvent(
                type="ASSIGNMENT_ARCHIVED" if archived else "ASSIGNMENT_RESTORED",
                at=sc.changed_at,
                actor=actor,
                summary=(
                    f"{actor} archived the assignment: it accepts no new work. All submissions and reviews are kept."
                    if archived
                    else f"{actor} restored the assignment: it accepts work again, with the same deadline."
                )
                + reason,
                data={"from": sc.from_status, "to": sc.to_status, "reason": sc.reason},
            ),
            i,
        )
    for i, c in enumerate(changes):
        actor = names.get(c.changed_by)
        reason = f" Reason: {c.reason}" if c.reason else ""
        add(
            TimelineEvent(
                type="DEADLINE_CHANGED",
                at=c.changed_at,
                actor=actor,
                summary=f"{actor} moved the deadline from {fmt(c.old_deadline)} to {fmt(c.new_deadline)}.{reason}",
                data={
                    "old_deadline": c.old_deadline.isoformat(),
                    "new_deadline": c.new_deadline.isoformat(),
                    "reason": c.reason,
                },
            ),
            i,
        )

    used = False
    if request is not None:
        used = bool(late_windows.used_request_ids(db, [request.id]))
        add(
            TimelineEvent(
                type="LATE_REQUESTED",
                at=request.requested_at,
                actor=student.full_name,
                summary=f"{student.full_name} requested a late submission (deadline at request: {fmt(request.deadline_at_request)}).",
                data={
                    "request_id": str(request.id),
                    "reason": request.reason,
                    "deadline_at_request": request.deadline_at_request.isoformat(),
                },
            )
        )
        if request.status != LateRequestStatus.PENDING and request.decided_at is not None:
            decider = names.get(request.decided_by)
            note = f" Note: {request.decision_note}" if request.decision_note else ""
            if request.status == LateRequestStatus.APPROVED:
                hours = round((request.window_end - request.window_start).total_seconds() / 3600, 2)
                add(
                    TimelineEvent(
                        type="REQUEST_APPROVED",
                        at=request.decided_at,
                        actor=decider,
                        summary=(
                            f"{decider} approved the request: upload window {fmt(request.window_start)} to "
                            f"{fmt(request.window_end)} ({hours:g} h).{note}"
                        ),
                        data={
                            "request_id": str(request.id),
                            "window_start": request.window_start.isoformat(),
                            "window_end": request.window_end.isoformat(),
                            "window_hours": hours,
                            "note": request.decision_note,
                        },
                    )
                )
            else:
                add(
                    TimelineEvent(
                        type="REQUEST_REJECTED",
                        at=request.decided_at,
                        actor=decider,
                        summary=f"{decider} rejected the request.{note}",
                        data={"request_id": str(request.id), "note": request.decision_note},
                    )
                )
        if (
            request.status == LateRequestStatus.APPROVED
            and not used
            and request.window_end is not None
            and now > request.window_end
        ):
            add(
                TimelineEvent(
                    type="REQUEST_WINDOW_EXPIRED",
                    at=request.window_end,
                    actor=None,
                    summary=f"The approved window closed at {fmt(request.window_end)} with no upload.",
                    data={"request_id": str(request.id)},
                    derived=True,
                )
            )

    for v in versions:
        at_upload = status.version_timing(v.uploaded_at, v.deadline_at_upload)
        now_timing = status.version_timing(v.uploaded_at, assignment.deadline)
        text = (
            f"Version {v.version_no} uploaded ({v.original_filename}, {CONTEXT_LABELS[v.upload_context.value]}) "
            f"at {fmt(v.uploaded_at)}; deadline at upload {fmt(v.deadline_at_upload)}; "
            f"{'late' if at_upload == status.Timing.LATE else 'on time'} at upload"
        )
        if now_timing != at_upload:
            text += f"; {'late' if now_timing == status.Timing.LATE else 'on time'} against the current deadline {fmt(assignment.deadline)}"
        add(
            TimelineEvent(
                type="VERSION_UPLOADED",
                at=v.uploaded_at,
                actor=names.get(v.uploaded_by) or student.full_name,
                summary=text + ".",
                data={
                    "version_no": v.version_no,
                    "version_id": str(v.id),
                    "filename": v.original_filename,
                    "sha256": v.sha256,
                    "upload_context": v.upload_context.value,
                    "deadline_at_upload": v.deadline_at_upload.isoformat(),
                    "timing_at_upload": at_upload.value,
                    "timing_now": now_timing.value,
                    "late_request_id": str(v.late_request_id) if v.late_request_id else None,
                },
            ),
            v.version_no,
        )

    for r, version_no in reviews:
        reviewer = names.get(r.reviewer_id)
        label = REVIEW_LABELS[r.status.value]
        feedback = f" Feedback: {r.feedback}" if r.feedback else ""
        add(
            TimelineEvent(
                type="REVIEW_RECORDED",
                at=r.reviewed_at,
                actor=reviewer,
                summary=f"{reviewer} recorded \"{label}\" for version {version_no}.{feedback}",
                data={
                    "review_id": str(r.id),
                    "status": r.status.value,
                    "version_no": version_no,
                    "feedback": r.feedback,
                },
            )
        )

    if not versions and now > assignment.deadline:
        add(
            TimelineEvent(
                type="DEADLINE_PASSED_NO_SUBMISSION",
                at=assignment.deadline,
                actor=None,
                summary=f"The deadline {fmt(assignment.deadline)} passed with no submission.",
                data={"deadline": assignment.deadline.isoformat()},
                derived=True,
            )
        )

    rows.sort(key=lambda r: (r[0], r[1], r[2]))
    events = [r[3] for r in rows]
    return events, _why(assignment, versions, request, used, names, reviews, now)


def _why(
    assignment: Assignment,
    versions: list[SubmissionVersion],
    request: LateRequest | None,
    used: bool,
    names: dict[uuid.UUID, str],
    reviews: list,
    now: datetime,
) -> WhyThisStatus:
    deadline = assignment.deadline
    lines: list[str] = []
    first = versions[0] if versions else None
    timing = status.submission_timing(first.uploaded_at if first else None, deadline, now)

    if first is None:
        if timing == status.Timing.PENDING:
            headline = "Pending"
            lines.append(f"No submission yet. The deadline is {fmt(deadline)} ({duration(deadline - now)} left).")
        else:
            headline = "Missing"
            lines.append(f"The deadline {fmt(deadline)} passed {duration(now - deadline)} ago and nothing was submitted.")
        if request is not None:
            state = late_windows.derive_state(request.status, request.window_end, used, now)
            lines.append(
                {
                    "PENDING": "A late-submission request is waiting for a decision.",
                    "APPROVED": f"A late request is approved: uploads are open until {fmt(request.window_end)}."
                    if request.window_end
                    else "A late request is approved.",
                    "REJECTED": "The late-submission request was rejected, so the student stays missing.",
                    "EXPIRED": "The approved window closed without an upload, so the student stays missing.",
                    "USED": "The approved window was used.",
                }[state]
            )
    else:
        delta = first.uploaded_at - deadline
        approved = first.upload_context == UploadContext.LATE_APPROVED and timing == status.Timing.LATE
        if timing == status.Timing.ON_TIME:
            headline = "On time"
            when = "exactly at the deadline" if delta == timedelta(0) else f"{duration(delta)} before the deadline"
            lines.append(f"First upload {fmt(first.uploaded_at)}, {when} ({fmt(deadline)}).")
            if first.uploaded_at > first.deadline_at_upload:
                lines.append(
                    f"It was late at upload (deadline then {fmt(first.deadline_at_upload)}); the deadline was later moved to {fmt(deadline)}."
                )
        else:
            headline = "Late (approved)" if approved else "Late"
            lines.append(f"First upload {fmt(first.uploaded_at)}, {duration(delta)} after the deadline ({fmt(deadline)}).")
            if approved and request is not None and request.window_start and request.window_end:
                lines.append(
                    f"It was received inside the window approved by {names.get(request.decided_by)} "
                    f"({fmt(request.window_start)} to {fmt(request.window_end)})."
                )
        if len(versions) > 1:
            lines.append(
                f"{len(versions)} versions were uploaded; the status above follows the first one, so later versions do not change it."
            )

    if reviews and versions and reviews[-1][1] != versions[-1].version_no:
        r, version_no = reviews[-1]
        lines.append(
            f"Review status is separate from timing: the latest version ({versions[-1].version_no}) is not reviewed yet; "
            f"version {version_no} was {REVIEW_LABELS[r.status.value]} by {names.get(r.reviewer_id)}."
        )
    elif reviews:
        r, version_no = reviews[-1]
        lines.append(
            f"Review status is separate from timing: latest review is {REVIEW_LABELS[r.status.value]} "
            f"(version {version_no}, {names.get(r.reviewer_id)}, {fmt(r.reviewed_at)})."
        )
    else:
        lines.append("Review status is separate from timing: not reviewed yet.")
    return WhyThisStatus(timing=timing.value, headline=headline, lines=lines)
