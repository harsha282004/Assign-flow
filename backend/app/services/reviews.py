"""Faculty reviews (architecture §15.1, §16.3, §20.2 #11).

* `reviews` is an append-only log: a new decision is a new row, nothing is updated or deleted.
* The CURRENT review is the latest review of the LATEST version; no such row means NOT_REVIEWED. This is the
  architecture's rule that a new version "starts as NOT_REVIEWED" while the earlier review stays in history (§16.3).
* The reviewer, version and `reviewed_at` are server-controlled. The submission row is locked, so a review cannot
  interleave with an upload (an upload then sees the new review, and a review always targets the real latest version).
"""

import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.models import (
    Assignment,
    Review,
    ReviewStatus,
    Submission,
    SubmissionVersion,
    User,
)
from app.schemas.reviews import ReviewIn, ReviewOut
from app.services import archive_guard, notifications, scope

LABELS = {
    "UNDER_REVIEW": "Under review",
    "ACCEPTED": "Accepted",
    "REVISION_REQUESTED": "Revision requested",
}


def current_reviews(db: Session, submission_ids: list[uuid.UUID]) -> dict[uuid.UUID, Review]:
    """submission_id -> its current review (latest review of the latest version). Missing key = NOT_REVIEWED."""
    if not submission_ids:
        return {}
    rows = db.scalars(
        select(Review)
        .join(Submission, Submission.id == Review.submission_id)
        .join(
            SubmissionVersion,
            (SubmissionVersion.submission_id == Submission.id)
            & (SubmissionVersion.version_no == Submission.latest_version_no),
        )
        .where(Review.submission_id.in_(submission_ids), Review.version_id == SubmissionVersion.id)
        .order_by(Review.submission_id, Review.reviewed_at.desc(), Review.id.desc())
        .distinct(Review.submission_id)
        .execution_options(populate_existing=True)
    )
    return {r.submission_id: r for r in rows}


def current_review_status(db: Session, submission_id: uuid.UUID) -> ReviewStatus | None:
    review = current_reviews(db, [submission_id]).get(submission_id)
    return review.status if review else None


def review_outs(db: Session, submission: Submission | None) -> list[ReviewOut]:
    """The full review history of one submission, oldest first."""
    if submission is None:
        return []
    rows = db.execute(
        select(Review, SubmissionVersion.version_no, User.full_name)
        .join(SubmissionVersion, SubmissionVersion.id == Review.version_id)
        .join(User, User.id == Review.reviewer_id)
        .where(Review.submission_id == submission.id)
        .order_by(Review.reviewed_at, Review.id)
    ).all()
    current = current_reviews(db, [submission.id]).get(submission.id)
    return [
        ReviewOut(
            id=r.id,
            version_no=version_no,
            status=r.status.value,
            feedback=r.feedback,
            reviewer_name=name,
            reviewed_at=r.reviewed_at,
            is_current=current is not None and current.id == r.id,
        )
        for r, version_no, name in rows
    ]


def record_review(
    db: Session, faculty: User, submission_id: uuid.UUID, body: ReviewIn, now: datetime
) -> ReviewOut:
    # 404 unless the submission belongs to an assignment this faculty member created and teaches.
    scope.get_faculty_submission_or_404(db, faculty, submission_id)
    submission = db.execute(
        select(Submission)
        .where(Submission.id == submission_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one()
    archive_guard.require_active(
        db, submission.assignment_id, "This assignment is archived. Restore it before recording a review."
    )
    if submission.latest_version_no < 1:
        raise AppError("NO_VERSION", 409, "There is nothing to review yet: no file has been submitted.")
    if body.expected_version_no is not None and body.expected_version_no != submission.latest_version_no:
        raise AppError(
            "STALE_VERSION",
            409,
            "The student uploaded a newer version while you were reviewing. Reload and review the latest version.",
        )

    version = db.scalar(
        select(SubmissionVersion).where(
            SubmissionVersion.submission_id == submission.id,
            SubmissionVersion.version_no == submission.latest_version_no,
        )
    )
    current = current_reviews(db, [submission.id]).get(submission.id)
    if current is not None and current.status.value == body.status and (current.feedback or None) == body.feedback:
        # A retried request or a double click: the same decision is already the current review.
        raise AppError("REVIEW_UNCHANGED", 409, "This review is already recorded.")

    # Strictly after the previous review of this submission, so "the latest review" is never ambiguous.
    previous = db.scalar(
        select(Review.reviewed_at)
        .where(Review.submission_id == submission.id)
        .order_by(Review.reviewed_at.desc())
        .limit(1)
    )
    reviewed_at = now if previous is None or now > previous else previous + timedelta(microseconds=1)

    review = Review(
        submission_id=submission.id,
        version_id=version.id,
        reviewer_id=faculty.id,
        status=ReviewStatus(body.status),
        feedback=body.feedback,
        reviewed_at=reviewed_at,
    )
    db.add(review)
    db.flush()

    assignment = db.get(Assignment, submission.assignment_id)
    label = LABELS[body.status]
    notifications.notify(
        db,
        user_id=submission.student_id,
        type="REVIEW_RECORDED",
        title=f"Review: {label}",
        body=f"Your teacher marked your submission for \"{assignment.title}\" as {label.lower()}.",
        ref_type="ASSIGNMENT",
        ref_id=assignment.id,
        dedup_key=f"REVIEW:{review.id}",
    )
    db.commit()
    return ReviewOut(
        id=review.id,
        version_no=version.version_no,
        status=body.status,
        feedback=review.feedback,
        reviewer_name=faculty.full_name,
        reviewed_at=review.reviewed_at,
        is_current=True,
    )
