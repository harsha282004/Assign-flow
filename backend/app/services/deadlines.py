"""Deadline changes (architecture §15.3): one transaction writes the history row and updates the deadline."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.models import Assignment, AssignmentStatus, DeadlineChange, StudentProfile, User
from app.services import notifications, scope
from app.services.timeline import fmt


def change_deadline(
    db: Session,
    faculty: User,
    assignment_id: uuid.UUID,
    new_deadline: datetime,
    reason: str | None,
    now: datetime,
) -> Assignment:
    """Who: the creating faculty member only (404 otherwise). Constraint: PUBLISHED assignments only, and the
    new deadline must be after `now` (extensions after the old deadline has passed are allowed).
    `original_deadline` is never touched; `changed_at` is the server clock."""
    scope.get_faculty_assignment_or_404(db, faculty, assignment_id)  # scope check (404)
    # Lock the row so concurrent changes record a consistent old -> new chain.
    assignment = db.execute(
        select(Assignment).where(Assignment.id == assignment_id).with_for_update()
    ).scalar_one()

    if assignment.status == AssignmentStatus.ARCHIVED:
        raise AppError("ASSIGNMENT_ARCHIVED", 409, "This assignment is archived. Restore it before changing the deadline.")
    if assignment.status != AssignmentStatus.PUBLISHED:
        raise AppError("NOT_PUBLISHED", 409, "The deadline can only be changed on a published assignment.")
    new_deadline = new_deadline.astimezone(UTC)
    if new_deadline <= now:
        raise AppError("DEADLINE_IN_PAST", 422, "The new deadline must be in the future.")

    change = DeadlineChange(
        assignment_id=assignment.id,
        old_deadline=assignment.deadline,
        new_deadline=new_deadline,
        changed_by=faculty.id,
        changed_at=now,
        reason=reason,
    )
    db.add(change)
    assignment.deadline = new_deadline
    db.flush()
    # One notification per student of the section, in the same transaction (architecture §22: DL_CHANGED).
    for student_id in db.scalars(
        select(StudentProfile.user_id).where(StudentProfile.section_id == assignment.section_id)
    ):
        notifications.notify(
            db,
            user_id=student_id,
            type="DEADLINE_CHANGED",
            title="Deadline changed",
            body=f'The deadline for "{assignment.title}" is now {fmt(new_deadline)}.',
            ref_type="ASSIGNMENT",
            ref_id=assignment.id,
            dedup_key=f"DL_CHANGED:{change.id}:{student_id}",
        )
    return assignment
