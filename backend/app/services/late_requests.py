"""Late-submission request workflow (architecture §17). Create, decide, derived EXPIRED / USED.

* One request per student per assignment (UNIQUE), only while the student's timing is MISSING.
* A decision is one conditional UPDATE ... WHERE status = 'PENDING': the decision fields are written once and a
  second decision (two tabs, two clicks) gets 409 ALREADY_DECIDED.
* All timestamps are the server clock; the client never sends a time or a window start/end.
* Approving does not upload anything or change a timing: the window is only honoured by the upload eligibility
  rule 5 (services/eligibility.py), which is evaluated again under the submission row lock.
"""

import uuid
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.models import (
    Assignment,
    AssignmentStatus,
    LateRequest,
    LateRequestStatus,
    Section,
    Subject,
    Submission,
    SubmissionVersion,
    TeachingAssignment,
    User,
)
from app.schemas.auth import SectionOut, SubjectOut
from app.schemas.late_requests import (
    AssignmentRef,
    FacultyLateRequestDetail,
    FacultyLateRequestItem,
    LateRequestDecisionIn,
    LateRequestOut,
)
from app.schemas.submissions import StudentRef
from app.services import archive_guard, late_windows, notifications, scope, status, submissions
from app.services.timeline import fmt

FILTERS = ("PENDING", "APPROVED", "REJECTED", "EXPIRED", "USED")


# --- output --------------------------------------------------------------------------------------------

def _decider_name(db: Session, request: LateRequest) -> str | None:
    if request.decided_by is None:
        return None
    return db.scalar(select(User.full_name).where(User.id == request.decided_by))


def _out_fields(request: LateRequest, decider: str | None, state: str) -> dict:
    return dict(
        id=request.id,
        status=request.status.value,
        state=state,
        reason=request.reason,
        requested_at=request.requested_at,
        deadline_at_request=request.deadline_at_request,
        decided_by_name=decider,
        decided_at=request.decided_at,
        decision_note=request.decision_note,
        window_start=request.window_start,
        window_end=request.window_end,
    )


def student_request_out(db: Session, request: LateRequest, now: datetime) -> LateRequestOut:
    used = bool(late_windows.used_request_ids(db, [request.id]))
    state = late_windows.derive_state(request.status, request.window_end, used, now)
    return LateRequestOut(**_out_fields(request, _decider_name(db, request), state))


def _faculty_item(
    db: Session,
    request: LateRequest,
    student: User,
    assignment: Assignment,
    subject: Subject,
    section: Section,
    used: bool,
    now: datetime,
) -> dict:
    state = late_windows.derive_state(request.status, request.window_end, used, now)
    return dict(
        **_out_fields(request, _decider_name(db, request), state),
        student=StudentRef(id=student.id, login_id=student.login_id, full_name=student.full_name),
        assignment=AssignmentRef(
            id=assignment.id,
            title=assignment.title,
            subject=SubjectOut(id=subject.id, code=subject.code, name=subject.name),
            section=SectionOut(id=section.id, label=section.label, semester=section.semester, name=section.name),
        ),
        current_deadline=assignment.deadline,
    )


# --- student: create -----------------------------------------------------------------------------------

def can_request_late(timing: str, request: LateRequest | None) -> bool:
    return timing == status.Timing.MISSING.value and request is None


def create_request(
    db: Session, student: User, assignment_id: uuid.UUID, reason: str, now: datetime
) -> LateRequestOut:
    # 404 unless the assignment is published and in the student's own section.
    if scope.get_student_assignment_or_404(db, student, assignment_id).assignment_type == "QUIZ":
        raise AppError("IS_A_QUIZ", 409, "Late requests do not apply to quizzes.")
    # Share-lock the assignment row and re-read it: a concurrent deadline change (which takes the row FOR UPDATE)
    # either commits first, and we see the new deadline, or waits until this request is stored.
    assignment = db.execute(
        select(Assignment)
        .where(Assignment.id == assignment_id)
        .with_for_update(read=True)
        .execution_options(populate_existing=True)
    ).scalar_one()
    if assignment.status == AssignmentStatus.ARCHIVED:
        raise archive_guard.archived_error()

    submitted = db.scalar(
        select(SubmissionVersion.id)
        .join(Submission, Submission.id == SubmissionVersion.submission_id)
        .where(Submission.assignment_id == assignment.id, Submission.student_id == student.id)
        .limit(1)
    )
    if submitted is not None or now <= assignment.deadline:  # §17.3: only MISSING students may ask
        raise AppError(
            "NOT_MISSING",
            409,
            "A late submission can be requested only after the deadline has passed and only if you have not "
            "submitted yet.",
        )

    # The UNIQUE(assignment_id, student_id) constraint makes this idempotent under double clicks and races.
    request_id = db.execute(
        insert(LateRequest)
        .values(
            assignment_id=assignment.id,
            student_id=student.id,
            reason=reason,
            requested_at=now,
            deadline_at_request=assignment.deadline,
            status=LateRequestStatus.PENDING,
        )
        .on_conflict_do_nothing(index_elements=["assignment_id", "student_id"])
        .returning(LateRequest.id)
    ).scalar_one_or_none()
    if request_id is None:
        db.rollback()
        raise AppError("REQUEST_EXISTS", 409, "You have already sent a late-submission request for this assignment.")
    # Same transaction as the request; the dedup key makes a retried action a no-op.
    notifications.notify(
        db,
        user_id=assignment.created_by,
        type="LATE_REQUEST_CREATED",
        title="New late-submission request",
        body=f'{student.full_name} ({student.login_id}) asked to submit "{assignment.title}" late.',
        ref_type="LATE_REQUEST",
        ref_id=request_id,
        dedup_key=f"LR_CREATED:{request_id}",
    )
    db.commit()
    request = db.get(LateRequest, request_id)
    return student_request_out(db, request, now)


# --- faculty: list, inspect -----------------------------------------------------------------------------

def _scoped_rows(
    db: Session,
    faculty: User,
    request_id: uuid.UUID | None = None,
    assignment_id=None,
    subject_id: uuid.UUID | None = None,
    section_id: uuid.UUID | None = None,
):
    """Requests on assignments this faculty member created AND teaches (architecture §8.2)."""
    stmt = (
        select(LateRequest, User, Assignment, Subject, Section)
        .join(Assignment, Assignment.id == LateRequest.assignment_id)
        .join(User, User.id == LateRequest.student_id)
        .join(Subject, Subject.id == Assignment.subject_id)
        .join(Section, Section.id == Assignment.section_id)
        .join(
            TeachingAssignment,
            (TeachingAssignment.subject_id == Assignment.subject_id)
            & (TeachingAssignment.section_id == Assignment.section_id)
            & (TeachingAssignment.faculty_id == faculty.id),
        )
        .where(Assignment.created_by == faculty.id)
    )
    if request_id is not None:
        stmt = stmt.where(LateRequest.id == request_id)
    if assignment_id is not None:
        stmt = stmt.where(LateRequest.assignment_id == assignment_id)
    if subject_id is not None:
        stmt = stmt.where(Assignment.subject_id == subject_id)
    if section_id is not None:
        stmt = stmt.where(Assignment.section_id == section_id)
    return db.execute(stmt.execution_options(populate_existing=True)).all()


def list_requests(
    db: Session,
    faculty: User,
    now: datetime,
    state: str | None = None,
    assignment_id: uuid.UUID | None = None,
    subject_id: uuid.UUID | None = None,
    section_id: uuid.UUID | None = None,
) -> list[FacultyLateRequestItem]:
    scope.require_filter_scope(db, faculty, subject_id, section_id)
    rows = _scoped_rows(db, faculty, assignment_id=assignment_id, subject_id=subject_id, section_id=section_id)
    if state == "PENDING":  # nothing can be decided on an archived assignment, so it is not waiting for a decision
        rows = [row for row in rows if row[2].status != AssignmentStatus.ARCHIVED]
    used = late_windows.used_request_ids(db, [r.id for r, *_ in rows])
    items = [
        FacultyLateRequestItem(**_faculty_item(db, r, st, a, sub, sec, r.id in used, now))
        for r, st, a, sub, sec in rows
    ]
    if state:
        items = [i for i in items if i.state == state]
    # Pending requests first (oldest first, so nothing waits forever), then the decided ones, newest first.
    pending = sorted((i for i in items if i.state == "PENDING"), key=lambda i: i.requested_at)
    decided = sorted((i for i in items if i.state != "PENDING"), key=lambda i: i.requested_at, reverse=True)
    return pending + decided


def request_detail(
    db: Session, faculty: User, request_id: uuid.UUID, now: datetime
) -> FacultyLateRequestDetail:
    scope.get_faculty_late_request_or_404(db, faculty, request_id)  # 404 for out-of-scope requests
    rows = _scoped_rows(db, faculty, request_id=request_id)
    if not rows:  # scope helper and join agree, but never serve what the scoped query did not return
        raise AppError("NOT_FOUND", 404, "The requested resource was not found.")
    request, student, assignment, subject, section = rows[0]
    used = bool(late_windows.used_request_ids(db, [request.id]))
    submission = submissions.get_submission(db, assignment.id, student.id)
    versions = submissions.list_versions(db, submission.id) if submission else []
    first = versions[0].uploaded_at if versions else None
    return FacultyLateRequestDetail(
        **_faculty_item(db, request, student, assignment, subject, section, used, now),
        submission_timing=status.submission_timing(first, assignment.deadline, now).value,
        versions=[submissions.version_out(v, assignment.deadline) for v in versions],
    )


# --- faculty: decide ---------------------------------------------------------------------------------------

def decide(
    db: Session, faculty: User, request_id: uuid.UUID, body: LateRequestDecisionIn, now: datetime
) -> FacultyLateRequestItem:
    """Approve (window [now, now + hours]) or reject. `now` is the server clock; the client sends no time."""
    target = scope.get_faculty_late_request_or_404(db, faculty, request_id)  # 404 unless on my own assignment
    student_id, assignment_id = target.student_id, target.assignment_id
    archive_guard.require_active(
        db, assignment_id, "This assignment is archived. Restore it before deciding late requests."
    )

    if body.decision == "APPROVE":
        values = dict(
            status=LateRequestStatus.APPROVED,
            window_start=now,
            window_end=now + timedelta(hours=body.effective_window_hours),
        )
    else:
        values = dict(status=LateRequestStatus.REJECTED, window_start=None, window_end=None)

    # Conditional update: only a PENDING row can be decided, and only once. Two simultaneous decisions are
    # serialized by the row lock; the loser matches no row and gets 409 ALREADY_DECIDED.
    decided = db.execute(
        update(LateRequest)
        .where(LateRequest.id == request_id, LateRequest.status == LateRequestStatus.PENDING)
        .values(decided_by=faculty.id, decided_at=now, decision_note=body.note, **values)
        .returning(LateRequest.id)
    ).scalar_one_or_none()
    if decided is None:
        db.rollback()
        raise AppError("ALREADY_DECIDED", 409, "This request has already been decided.")
    title = db.scalar(select(Assignment.title).where(Assignment.id == assignment_id))
    if body.decision == "APPROVE":
        headline = "Late request approved"
        text = (
            f'Your request for "{title}" was approved. Upload until {fmt(values["window_end"])}.'
        )
    else:
        headline = "Late request rejected"
        text = f'Your request for "{title}" was rejected.'
    notifications.notify(
        db,
        user_id=student_id,
        type="LATE_REQUEST_DECIDED",
        title=headline,
        body=text,
        ref_type="ASSIGNMENT",
        ref_id=assignment_id,
        dedup_key=f"LR_DECIDED:{request_id}",
    )
    db.commit()

    rows = _scoped_rows(db, faculty, request_id=request_id)
    request, student, assignment, subject, section = rows[0]
    return FacultyLateRequestItem(**_faculty_item(db, request, student, assignment, subject, section, False, now))

