"""Faculty "Delete assignment" with protection of student work and audit history.

Policy (documented in docs/IMPLEMENTATION_LOG.md):
  * Only the owner (created it AND still teaches the class) can delete; anyone else gets 404, students 403.
  * Only a DRAFT is ever deleted permanently, and only when no submission, version, review, late request, deadline
    change or notification refers to it. Nothing is ever cascaded. A published assignment is ARCHIVED instead
    (services/assignment_archive.py), which keeps every record and file.
  * Reference documents are the teacher's own unpublished upload while the assignment is a DRAFT, so a draft may be
    deleted together with them. For a PUBLISHED assignment reference documents are what students rely on, so they
    block deletion like any other record.
  * The check runs under a row lock on the assignment (a concurrent upload or request needs a share lock on the same
    row), and the foreign keys (ON DELETE RESTRICT) are the last line of defence.
  * Storage objects are removed only AFTER the database transaction committed, and only if no record still
    references them. A failed object removal leaves an unreferenced orphan (reported), never an inconsistent row.
"""

import logging
import uuid

from botocore.client import BaseClient
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.db.models import (
    Assignment,
    AssignmentAttachment,
    AssignmentStatus,
    DeadlineChange,
    LateRequest,
    Notification,
    QuizAttempt,
    QuizOption,
    QuizQuestion,
    Review,
    Submission,
    SubmissionVersion,
    User,
)
from app.schemas.assignments import DeletionCheck, DeletionResult
from app.services import scope, storage

logger = logging.getLogger("assignflow.assignments")

LABELS = {
    "submissions": "submissions",
    "versions": "submitted file versions",
    "reviews": "reviews",
    "late_requests": "late-submission requests",
    "deadline_changes": "deadline changes",
    "notifications": "notifications",
    "quiz_attempts": "quiz attempts",
    "reference_files": "reference documents",
}
HISTORY_MESSAGE = (
    "This assignment has submission, review or other history and cannot be permanently deleted. "
    "All of its records have been preserved."
)


def _count(db: Session, model, *where) -> int:
    return db.scalar(select(func.count()).select_from(model).where(*where)) or 0


def blockers(db: Session, assignment: Assignment) -> tuple[dict[str, int], int]:
    """(records that forbid deletion, number of reference documents). Zero counts are omitted."""
    aid = assignment.id
    found = {
        "submissions": _count(db, Submission, Submission.assignment_id == aid),
        "versions": db.scalar(
            select(func.count())
            .select_from(SubmissionVersion)
            .join(Submission, Submission.id == SubmissionVersion.submission_id)
            .where(Submission.assignment_id == aid)
        )
        or 0,
        "reviews": db.scalar(
            select(func.count())
            .select_from(Review)
            .join(Submission, Submission.id == Review.submission_id)
            .where(Submission.assignment_id == aid)
        )
        or 0,
        "late_requests": _count(db, LateRequest, LateRequest.assignment_id == aid),
        "deadline_changes": _count(db, DeadlineChange, DeadlineChange.assignment_id == aid),
        "notifications": _count(db, Notification, Notification.ref_type == "ASSIGNMENT", Notification.ref_id == aid),
        "quiz_attempts": _count(db, QuizAttempt, QuizAttempt.assignment_id == aid),
    }
    files = _count(db, AssignmentAttachment, AssignmentAttachment.assignment_id == aid)
    if assignment.status == AssignmentStatus.PUBLISHED and files:
        found["reference_files"] = files
    return {k: v for k, v in found.items() if v}, files


HISTORY_KEYS = (
    "submissions",
    "versions",
    "reviews",
    "late_requests",
    "deadline_changes",
    "notifications",
    "quiz_attempts",
)
NOT_A_DRAFT_MESSAGE = (
    "Only a draft can be permanently deleted. A published assignment is archived instead, which keeps every submission, "
    "review and file."
)


def check(db: Session, faculty: User, assignment_id: uuid.UUID) -> DeletionCheck:
    assignment = scope.get_faculty_assignment_or_404(db, faculty, assignment_id)
    found, files = blockers(db, assignment)
    history = any(k in found for k in HISTORY_KEYS)
    if assignment.status == AssignmentStatus.DRAFT:
        action, message = "DELETE", (None if not found else HISTORY_MESSAGE)
    elif assignment.status == AssignmentStatus.PUBLISHED:
        action, message = "ARCHIVE", NOT_A_DRAFT_MESSAGE
    else:
        action, message = "RESTORE", "This assignment is archived. Restore it to accept work again."
    return DeletionCheck(
        assignment_id=assignment.id,
        title=assignment.title,
        status=assignment.status.value,
        can_delete=assignment.status == AssignmentStatus.DRAFT and not found,
        action=action,
        can_archive=assignment.status == AssignmentStatus.PUBLISHED,
        student_history=history,
        blockers=found,
        reference_files=files,
        message=message,
    )


def delete_assignment(
    db: Session,
    s3: BaseClient,
    settings: Settings,
    faculty: User,
    assignment_id: uuid.UUID,
) -> DeletionResult:
    assignment = scope.get_faculty_assignment_or_404(db, faculty, assignment_id)  # 404: not mine / not found
    # Row lock: a concurrent upload or late request needs a share lock on this row and therefore waits (or, if it
    # committed first, is seen by the check below).
    db.refresh(assignment, with_for_update=True)
    if assignment.status != AssignmentStatus.DRAFT:
        raise AppError(
            "NOT_A_DRAFT",
            409,
            NOT_A_DRAFT_MESSAGE,
            details={"action": "ARCHIVE" if assignment.status == AssignmentStatus.PUBLISHED else "RESTORE"},
        )
    found, _ = blockers(db, assignment)
    if found:
        raise AppError(
            "ASSIGNMENT_HAS_HISTORY",
            409,
            HISTORY_MESSAGE,
            details={"blockers": found, "labels": {k: LABELS[k] for k in found}},
        )
    attachments = db.scalars(select(AssignmentAttachment).where(AssignmentAttachment.assignment_id == assignment.id)).all()
    keys = [a.storage_key for a in attachments]
    result = DeletionResult(deleted=True, assignment_id=assignment.id, title=assignment.title, files_removed=0, files_left=0)
    try:
        for a in attachments:
            db.delete(a)
        # A draft quiz's definition (no attempt can exist) goes with it: options first, then questions.
        question_ids = select(QuizQuestion.id).where(QuizQuestion.assignment_id == assignment.id)
        db.execute(delete(QuizOption).where(QuizOption.question_id.in_(question_ids)))
        db.execute(delete(QuizQuestion).where(QuizQuestion.assignment_id == assignment.id))
        db.flush()
        db.delete(assignment)
        db.commit()  # all or nothing; the foreign keys refuse if a dependent row appeared in the meantime
    except IntegrityError as exc:
        db.rollback()
        raise AppError("ASSIGNMENT_HAS_HISTORY", 409, HISTORY_MESSAGE) from exc
    except Exception:
        db.rollback()
        raise
    for key in keys:
        referenced = (
            _count(db, AssignmentAttachment, AssignmentAttachment.storage_key == key)
            + _count(db, SubmissionVersion, SubmissionVersion.storage_key == key)
        )
        if referenced == 0 and storage.delete_object_best_effort(s3, settings.s3_bucket, key):
            result.files_removed += 1
        else:
            result.files_left += 1  # unreferenced orphan: listed by scripts/find_orphans.py, harmless
    logger.info("assignment deleted by its owner (files removed=%d, left=%d)", result.files_removed, result.files_left)
    return result
