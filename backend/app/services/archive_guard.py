"""The "archived assignments accept no new work" guard, importable from every service without cycles."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.models import Assignment, AssignmentStatus

ARCHIVED_MESSAGE = "This assignment has been archived. It no longer accepts new work or changes."


def archived_error(message: str = ARCHIVED_MESSAGE) -> AppError:
    return AppError("ASSIGNMENT_ARCHIVED", 409, message)


def require_active(db: Session, assignment_id: uuid.UUID, message: str = ARCHIVED_MESSAGE) -> None:
    """Share-lock the assignment row and raise 409 ASSIGNMENT_ARCHIVED if it is archived.

    The share lock waits for a concurrent archive (which takes the row FOR UPDATE) to finish, so the answer is always
    current, and it is held until the caller's transaction ends, so an archive cannot slip in between this check and
    the write that follows."""
    current = db.execute(
        select(Assignment.status)
        .where(Assignment.id == assignment_id)
        .with_for_update(read=True)
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if current == AssignmentStatus.ARCHIVED:
        raise archived_error(message)
