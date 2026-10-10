"""Submission engine: upload pipeline, versions, timing views, faculty roster (architecture §15, §16, §18).

Upload order (§16.1, §18): validate -> capture received_at -> eligibility -> store object -> DB transaction.
On a database failure the stored object is deleted (best effort); if storage fails nothing is written.
"""

import hashlib
import logging
import uuid
from datetime import datetime

from botocore.client import BaseClient
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.db.models import (
    Assignment,
    AssignmentStatus,
    Section,
    StudentProfile,
    Subject,
    Submission,
    SubmissionVersion,
    TeachingAssignment,
    UploadContext,
    User,
    UserRole,
)
from app.schemas.submissions import (
    RosterRow,
    StudentRef,
    StudentSubmissionDetail,
    UploadResult,
    VersionOut,
)
from app.services import (
    archive_guard,
    eligibility,
    file_validation,
    late_windows,
    notifications,
    reviews,
    scope,
    status,
    storage,
    timeline,
)

logger = logging.getLogger("assignflow.submissions")


def _duplicate() -> AppError:
    return AppError(
        "DUPLICATE_UPLOAD", 409, "This file is identical to your latest version, so no new version was created."
    )


# --- reading -------------------------------------------------------------------------------------

def latest_review_status(db: Session, submission_id: uuid.UUID):
    """The current review: the latest review of the LATEST version; none means NOT_REVIEWED (None).
    A new version starts as NOT_REVIEWED and the earlier review stays in history (architecture §16.3)."""
    return reviews.current_review_status(db, submission_id)


def get_submission(db: Session, assignment_id: uuid.UUID, student_id: uuid.UUID) -> Submission | None:
    return db.scalar(
        select(Submission).where(Submission.assignment_id == assignment_id, Submission.student_id == student_id)
    )


def list_versions(db: Session, submission_id: uuid.UUID) -> list[SubmissionVersion]:
    return list(
        db.scalars(
            select(SubmissionVersion)
            .where(SubmissionVersion.submission_id == submission_id)
            .order_by(SubmissionVersion.version_no)
        )
    )


def version_out(v: SubmissionVersion, current_deadline: datetime) -> VersionOut:
    return VersionOut(
        id=v.id,
        version_no=v.version_no,
        original_filename=v.original_filename,
        mime_type=v.mime_type,
        size_bytes=v.size_bytes,
        sha256=v.sha256,
        uploaded_at=v.uploaded_at,
        deadline_at_upload=v.deadline_at_upload,
        upload_context=v.upload_context.value,
        timing_at_upload=status.version_timing(v.uploaded_at, v.deadline_at_upload).value,
        timing_now=status.version_timing(v.uploaded_at, current_deadline).value,
    )


def late_approved_flag(first_context: UploadContext | None, first_uploaded_at: datetime | None, deadline: datetime) -> bool:
    """"Late (approved)": the first version came through an approved late request and is still late against the
    current deadline. If the deadline was later extended past that upload, the work is simply on time (§15.3)."""
    return (
        first_context == UploadContext.LATE_APPROVED
        and first_uploaded_at is not None
        and status.version_timing(first_uploaded_at, deadline) == status.Timing.LATE
    )


def student_submission_info(
    db: Session, student_id: uuid.UUID, assignment_ids: list[uuid.UUID]
) -> dict[uuid.UUID, tuple[datetime, int, UploadContext, uuid.UUID]]:
    """assignment_id -> (first version uploaded_at, latest_version_no, first version context, submission id)."""
    if not assignment_ids:
        return {}
    rows = db.execute(
        select(
            Submission.assignment_id,
            SubmissionVersion.uploaded_at,
            Submission.latest_version_no,
            SubmissionVersion.upload_context,
            Submission.id,
        )
        .join(SubmissionVersion, SubmissionVersion.submission_id == Submission.id)
        .where(
            Submission.student_id == student_id,
            Submission.assignment_id.in_(assignment_ids),
            SubmissionVersion.version_no == 1,
        )
    ).all()
    return {a: (uploaded, latest, ctx, sub_id) for a, uploaded, latest, ctx, sub_id in rows}


def _first_context(versions: list[SubmissionVersion]) -> UploadContext | None:
    return versions[0].upload_context if versions else None


def student_view(db: Session, student: User, assignment: Assignment, now: datetime):
    """Everything a student sees about their own submission: versions, timing, eligibility."""
    submission = get_submission(db, assignment.id, student.id)
    versions = list_versions(db, submission.id) if submission else []
    first = versions[0].uploaded_at if versions else None
    review = latest_review_status(db, submission.id) if submission else None
    decision = eligibility.evaluate_upload(
        now,
        assignment.deadline,
        review,
        grant=late_windows.approved_grant(db, assignment.id, student.id),
        first_context=_first_context(versions),
    )
    archived = assignment.status == AssignmentStatus.ARCHIVED
    return dict(
        versions=[version_out(v, assignment.deadline) for v in versions],
        timing=status.submission_timing(first, assignment.deadline, now).value,
        is_resubmitted=status.is_resubmitted(len(versions)),
        can_upload=decision.allowed and not archived,
        upload_blocked_reason="ARCHIVED" if archived else decision.blocked_code,
    )


# --- uploading ------------------------------------------------------------------------------------

def _lock_submission(db: Session, assignment_id: uuid.UUID, student_id: uuid.UUID) -> Submission:
    """Create the submission row if needed (race-safe), then lock it so version numbers cannot collide."""
    db.execute(
        insert(Submission)
        .values(assignment_id=assignment_id, student_id=student_id)
        .on_conflict_do_nothing(index_elements=["assignment_id", "student_id"])
    )
    return db.execute(
        select(Submission)
        .where(Submission.assignment_id == assignment_id, Submission.student_id == student_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one()


def upload_submission(
    db: Session,
    s3: BaseClient,
    settings: Settings,
    student: User,
    assignment_id: uuid.UUID,
    filename: str | None,
    data: bytes,
    clock,
) -> UploadResult:
    # 1. Scope: published and in the student's own section, otherwise 404.
    assignment = scope.get_student_assignment_or_404(db, student, assignment_id)
    if assignment.assignment_type == "QUIZ":
        raise AppError("IS_A_QUIZ", 409, "This is a quiz. Open it to answer the questions.")
    if assignment.status == AssignmentStatus.ARCHIVED:  # readable history, but no new work
        raise archive_guard.archived_error()

    # 2. Validate size, extension, content type and archive structure (413 / 415 / 422).
    validated = file_validation.validate_file(
        filename, data, list(assignment.allowed_types), assignment.max_file_mb, settings.max_upload_mb
    )
    sha256 = hashlib.sha256(data).hexdigest()

    # 3. The official time: captured once, after the whole file was received and validated. The browser's
    #    clock is never sent or used.
    received_at: datetime = clock()

    # 4. Eligibility at received_at (409 DEADLINE_PASSED / SUBMISSION_ACCEPTED), and cheap duplicate pre-check.
    submission = get_submission(db, assignment.id, student.id)
    review = latest_review_status(db, submission.id) if submission else None
    versions = list_versions(db, submission.id) if submission else []
    eligibility.require_upload_allowed(
        received_at,
        assignment.deadline,
        review,
        grant=late_windows.approved_grant(db, assignment.id, student.id),
        first_context=_first_context(versions),
    )
    if versions and versions[-1].sha256 == sha256:
        raise _duplicate()

    # 5. Store the object under a server-generated key (no user-supplied text in it).
    key = f"submissions/{assignment.id}/{student.id}/{uuid.uuid4()}.{validated.extension}"
    storage.put_object(s3, settings.s3_bucket, key, data, validated.mime_type)  # StorageUnavailable -> 503

    # 6. Database transaction. Any failure after step 5 removes the object again (best effort).
    try:
        submission = _lock_submission(db, assignment.id, student.id)
        # An archive that committed before this point is honoured; one that starts later waits for this upload.
        archive_guard.require_active(db, assignment.id)
        # Authoritative checks under the row lock (double clicks, concurrent tabs, a review recorded meanwhile).
        review = latest_review_status(db, submission.id)
        versions = list_versions(db, submission.id)
        # The late request is re-read here: its decision fields are written exactly once, so what is read now is
        # final. A request decided (or not yet decided) between the pre-check and this point is honoured.
        decision = eligibility.require_upload_allowed(
            received_at,
            assignment.deadline,
            review,
            grant=late_windows.approved_grant(db, assignment.id, student.id),
            first_context=_first_context(versions),
        )
        context = decision.context
        if versions and versions[-1].sha256 == sha256:
            raise _duplicate()

        version_no = submission.latest_version_no + 1
        version = SubmissionVersion(
            submission_id=submission.id,
            version_no=version_no,
            storage_key=key,
            original_filename=validated.original_filename,
            mime_type=validated.mime_type,
            size_bytes=validated.size_bytes,
            sha256=sha256,
            uploaded_at=received_at,
            uploaded_by=student.id,
            deadline_at_upload=assignment.deadline,
            upload_context=context,
            late_request_id=decision.late_request_id,  # set only for LATE_APPROVED (DB CHECK enforces the pairing)
        )
        db.add(version)
        submission.latest_version_no = version_no
        db.flush()
        # In the SAME transaction as the version: committed together, rolled back together (no orphan notification).
        _notify_faculty(db, assignment, student, submission, version)
        first_uploaded_at = (
            received_at
            if version_no == 1
            else db.scalar(
                select(SubmissionVersion.uploaded_at).where(
                    SubmissionVersion.submission_id == submission.id, SubmissionVersion.version_no == 1
                )
            )
        )
        db.commit()
    except BaseException:
        db.rollback()
        storage.delete_object_best_effort(s3, settings.s3_bucket, key)
        raise

    logger.info("upload ok user=%s assignment=%s version=%d", student.id, assignment.id, version_no)
    return UploadResult(
        submission_id=submission.id,
        version_id=version.id,
        version_no=version_no,
        uploaded_at=received_at,
        deadline_at_upload=assignment.deadline,
        upload_context=context.value,
        version_timing=status.version_timing(received_at, assignment.deadline).value,
        submission_timing=status.submission_timing(first_uploaded_at, assignment.deadline, received_at).value,
        is_resubmitted=status.is_resubmitted(version_no),
    )


def _notify_faculty(
    db: Session, assignment: Assignment, student: User, submission: Submission, version: SubmissionVersion
) -> None:
    """Tell the faculty member who owns the assignment (and still teaches the class) about the new version. The
    names come from the database and the authenticated student, never from the request."""
    from app.services.timeline import fmt  # local import: timeline imports this module

    subject = db.get(Subject, assignment.subject_id)
    section = db.get(Section, assignment.section_id)
    recipients = db.scalars(
        select(TeachingAssignment.faculty_id).where(
            TeachingAssignment.subject_id == assignment.subject_id,
            TeachingAssignment.section_id == assignment.section_id,
            TeachingAssignment.faculty_id == assignment.created_by,
        )
    ).all()
    first = version.version_no == 1
    title = "New assignment submission" if first else "New submission version"
    body = (
        f'{student.full_name} ({student.login_id}) submitted "{assignment.title}" for '
        f"{subject.name} — {section.label}."
        if first
        else f'{student.full_name} ({student.login_id}) uploaded version {version.version_no} of '
        f'"{assignment.title}" for {subject.name} — {section.label}.'
    )
    for faculty_id in recipients:
        notifications.notify(
            db,
            user_id=faculty_id,
            type="SUBMISSION_NEW" if first else "SUBMISSION_VERSION",
            title=title,
            body=f"{body} Submitted {fmt(version.uploaded_at)}.",
            ref_type="SUBMISSION",
            ref_id=submission.id,
            dedup_key=f"SUBMISSION:{version.id}:{faculty_id}",
        )


# --- faculty views ---------------------------------------------------------------------------------------

def _require_published(assignment: Assignment) -> None:
    if assignment.status not in (AssignmentStatus.PUBLISHED, AssignmentStatus.ARCHIVED):  # archived: history stays visible
        raise AppError("NOT_PUBLISHED", 409, "This assignment has not been published, so it has no submissions.")


def roster(
    db: Session, assignment: Assignment, now: datetime, timing_filter: str | None
) -> list[RosterRow]:
    """One row per expected student (everyone in the section), with submission-level timing."""
    _require_published(assignment)
    students = db.execute(
        select(User)
        .join(StudentProfile, StudentProfile.user_id == User.id)
        .where(StudentProfile.section_id == assignment.section_id, User.role == UserRole.STUDENT)
        .order_by(User.login_id)
    ).scalars().all()

    subs = {
        s.student_id: s
        for s in db.scalars(select(Submission).where(Submission.assignment_id == assignment.id))
    }
    first_at: dict[uuid.UUID, datetime] = {}
    first_ctx: dict[uuid.UUID, UploadContext] = {}
    last_at: dict[uuid.UUID, datetime] = {}
    if subs:
        ids = [s.id for s in subs.values()]
        for sid, uploaded, ctx in db.execute(
            select(
                SubmissionVersion.submission_id, SubmissionVersion.uploaded_at, SubmissionVersion.upload_context
            ).where(SubmissionVersion.submission_id.in_(ids), SubmissionVersion.version_no == 1)
        ).all():
            first_at[sid] = uploaded
            first_ctx[sid] = ctx
        last_at = dict(
            db.execute(
                select(SubmissionVersion.submission_id, func.max(SubmissionVersion.uploaded_at))
                .where(SubmissionVersion.submission_id.in_(ids))
                .group_by(SubmissionVersion.submission_id)
            ).all()
        )

    request_status = late_windows.request_states(db, assignment.id, now)
    current = reviews.current_reviews(db, [s.id for s in subs.values()])

    rows: list[RosterRow] = []
    for student in students:
        sub = subs.get(student.id)
        first = first_at.get(sub.id) if sub else None
        timing = status.submission_timing(first, assignment.deadline, now)
        if timing_filter and timing.value != timing_filter:
            continue
        rows.append(
            RosterRow(
                student=StudentRef(id=student.id, login_id=student.login_id, full_name=student.full_name),
                timing=timing.value,
                late_approved=late_approved_flag(first_ctx.get(sub.id) if sub else None, first, assignment.deadline),
                is_resubmitted=status.is_resubmitted(sub.latest_version_no if sub else 0),
                version_count=sub.latest_version_no if sub else 0,
                latest_uploaded_at=last_at.get(sub.id) if sub else None,
                request_status=request_status.get(student.id, "NONE"),
                review_status=current[sub.id].status.value if sub and sub.id in current else "NOT_REVIEWED",
            )
        )
    return rows


def faculty_student_submission(
    db: Session, faculty: User, assignment_id: uuid.UUID, student_id: uuid.UUID, now: datetime
) -> StudentSubmissionDetail:
    assignment = scope.get_faculty_assignment_or_404(db, faculty, assignment_id)
    _require_published(assignment)
    student = db.scalar(
        select(User)
        .join(StudentProfile, StudentProfile.user_id == User.id)
        .where(User.id == student_id, StudentProfile.section_id == assignment.section_id)
    )
    if student is None:  # not a student of this assignment's section: indistinguishable from "no such student"
        raise AppError("NOT_FOUND", 404, "The requested resource was not found.")
    submission = get_submission(db, assignment.id, student.id)
    versions = list_versions(db, submission.id) if submission else []
    first = versions[0].uploaded_at if versions else None
    events, why = timeline.build(db, assignment, student, now)
    review = latest_review_status(db, submission.id) if submission else None
    return StudentSubmissionDetail(
        student=StudentRef(id=student.id, login_id=student.login_id, full_name=student.full_name),
        deadline=assignment.deadline,
        original_deadline=assignment.original_deadline,
        timing=status.submission_timing(first, assignment.deadline, now).value,
        late_approved=late_approved_flag(_first_context(versions), first, assignment.deadline),
        is_resubmitted=status.is_resubmitted(len(versions)),
        request_status=late_windows.request_states(db, assignment.id, now).get(student.id, "NONE"),
        submission_id=submission.id if submission else None,
        latest_version_no=len(versions),
        review_status=review.value if review else "NOT_REVIEWED",
        reviews=reviews.review_outs(db, submission),
        versions=[version_out(v, assignment.deadline) for v in versions],
        events=events,
        why_this_status=why,
    )


__all__ = [
    "UploadContext",
    "faculty_student_submission",
    "get_submission",
    "latest_review_status",
    "list_versions",
    "roster",
    "student_submission_info",
    "student_view",
    "upload_submission",
    "version_out",
]
