"""Archive / restore of published assignments (the reversible alternative to deletion).

Policy (documented in docs/IMPLEMENTATION_LOG.md):
  * Only a PUBLISHED assignment can be archived, only by the faculty member who owns it (and still teaches the class).
    A draft is deleted instead; an archived assignment is restored (-> PUBLISHED, deadlines and history untouched).
  * ARCHIVED means "out of active use, fully preserved". Nothing is deleted or rewritten: submissions, versions, reviews,
    late requests, deadline changes, notifications and stored files stay exactly as they are.
  * Students: the assignment leaves their active work, alerts and counts. A student who has a submission or a late
    request on it can still open it (read-only), see feedback and download their own files; other students cannot see it.
  * It accepts no new upload, late request, review, late-request decision or deadline change until it is restored.
  * Faculty: it leaves the active list and the board / dashboard counts (those cover active assignments only) and is
    listed under Archived, with its full roster, submissions and timeline still available.
  * Concurrency: archiving takes the assignment row FOR UPDATE; uploads, late requests, reviews and decisions take it
    FOR SHARE and re-check the status, so each is either stored before the archive commits or refused after it.
  * Every change is an insert-only `assignment_state_changes` row, shown in the timeline.
"""

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.models import Assignment, AssignmentStateChange, AssignmentStatus, User
from app.schemas.assignments import FacultyAssignmentDetail
from app.services import assignments as assignment_service
from app.services import scope


def _lock(db: Session, faculty: User, assignment_id: uuid.UUID) -> Assignment:
    assignment = scope.get_faculty_assignment_or_404(db, faculty, assignment_id)  # 404: not mine / not found
    db.refresh(assignment, with_for_update=True)  # re-read under the row lock
    return assignment


def archive(
    db: Session, faculty: User, assignment_id: uuid.UUID, reason: str | None, now: datetime
) -> FacultyAssignmentDetail:
    assignment = _lock(db, faculty, assignment_id)
    if assignment.status == AssignmentStatus.ARCHIVED:
        raise AppError("ALREADY_ARCHIVED", 409, "This assignment is already archived.")
    if assignment.status != AssignmentStatus.PUBLISHED:
        raise AppError(
            "NOT_PUBLISHED",
            409,
            "Only a published assignment can be archived. Delete a draft you no longer need instead.",
        )
    assignment.status = AssignmentStatus.ARCHIVED
    assignment.archived_at = now
    assignment.archived_by = faculty.id
    db.add(
        AssignmentStateChange(
            assignment_id=assignment.id,
            from_status="PUBLISHED",
            to_status="ARCHIVED",
            changed_by=faculty.id,
            changed_at=now,
            reason=reason,
        )
    )
    db.flush()
    return assignment_service.faculty_assignment_detail(db, assignment)


def restore(
    db: Session, faculty: User, assignment_id: uuid.UUID, reason: str | None, now: datetime
) -> FacultyAssignmentDetail:
    assignment = _lock(db, faculty, assignment_id)
    if assignment.status != AssignmentStatus.ARCHIVED:
        raise AppError("NOT_ARCHIVED", 409, "Only an archived assignment can be restored.")
    assignment.status = AssignmentStatus.PUBLISHED
    assignment.archived_at = None
    assignment.archived_by = None
    db.add(
        AssignmentStateChange(
            assignment_id=assignment.id,
            from_status="ARCHIVED",
            to_status="PUBLISHED",
            changed_by=faculty.id,
            changed_at=now,
            reason=reason,
        )
    )
    db.flush()
    return assignment_service.faculty_assignment_detail(db, assignment)
