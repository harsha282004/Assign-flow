"""Resource-scope rules (architecture §8.2). Reused by the assignment, submission and review endpoints.

Out-of-scope resources return 404 (so record IDs cannot be probed); creating something for a
subject x section the faculty member does not teach returns 403 NOT_YOUR_CLASS (architecture §20.2 #5).
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.models import (
    Assignment,
    AssignmentStatus,
    LateRequest,
    StudentProfile,
    Submission,
    SubmissionVersion,
    TeachingAssignment,
    User,
)


def _not_found() -> AppError:
    return AppError("NOT_FOUND", 404, "The requested resource was not found.")


def student_section_id(db: Session, student_id: uuid.UUID) -> uuid.UUID | None:
    return db.scalar(select(StudentProfile.section_id).where(StudentProfile.user_id == student_id))


def faculty_teaches(db: Session, faculty_id: uuid.UUID, subject_id: uuid.UUID, section_id: uuid.UUID) -> bool:
    return (
        db.scalar(
            select(TeachingAssignment.id).where(
                TeachingAssignment.faculty_id == faculty_id,
                TeachingAssignment.subject_id == subject_id,
                TeachingAssignment.section_id == section_id,
            )
        )
        is not None
    )


def require_teaching_slot(db: Session, faculty: User, subject_id: uuid.UUID, section_id: uuid.UUID) -> None:
    """403 NOT_YOUR_CLASS unless the faculty member teaches this subject in this section."""
    if not faculty_teaches(db, faculty.id, subject_id, section_id):
        raise AppError("NOT_YOUR_CLASS", 403, "You do not teach this subject in this section.")


def require_filter_scope(
    db: Session, faculty: User, subject_id: uuid.UUID | None, section_id: uuid.UUID | None
) -> None:
    """A subject / section filter is honoured only for classes the faculty member really teaches.

    The ID comes from the browser and is never trusted: an unknown ID and another teacher's section are treated
    the same way (403 NOT_YOUR_CLASS), so nothing about other sections or their students can be probed.
    """
    for column, value, what in (
        (TeachingAssignment.subject_id, subject_id, "subject"),
        (TeachingAssignment.section_id, section_id, "section"),
    ):
        if value is None:
            continue
        found = db.scalar(
            select(TeachingAssignment.id).where(TeachingAssignment.faculty_id == faculty.id, column == value).limit(1)
        )
        if found is None:
            raise AppError("NOT_YOUR_CLASS", 403, f"You do not teach this {what}.")


# --- Assignments -----------------------------------------------------------------------------

def student_has_history(db: Session, student_id: uuid.UUID, assignment_id: uuid.UUID) -> bool:
    """True if the student has a submission or a late request on the assignment."""
    return (
        db.scalar(
            select(Submission.id).where(Submission.assignment_id == assignment_id, Submission.student_id == student_id)
        )
        is not None
        or db.scalar(
            select(LateRequest.id).where(LateRequest.assignment_id == assignment_id, LateRequest.student_id == student_id)
        )
        is not None
    )


def get_student_assignment_or_404(db: Session, student: User, assignment_id: uuid.UUID) -> Assignment:
    """Student rule: assignment.section_id == student's section and status == PUBLISHED. An ARCHIVED assignment stays
    readable (never writable) for a student who has a submission or a late request on it: their own history."""
    assignment = db.get(Assignment, assignment_id)
    if assignment is None or assignment.section_id != student_section_id(db, student.id):
        raise _not_found()
    if assignment.status == AssignmentStatus.PUBLISHED:
        return assignment
    if assignment.status == AssignmentStatus.ARCHIVED and student_has_history(db, student.id, assignment.id):
        return assignment
    raise _not_found()


def get_faculty_assignment_or_404(db: Session, faculty: User, assignment_id: uuid.UUID) -> Assignment:
    """Faculty rule: created_by == me and a teaching assignment (me, subject, section) exists."""
    assignment = db.get(Assignment, assignment_id)
    if (
        assignment is None
        or assignment.created_by != faculty.id
        or not faculty_teaches(db, faculty.id, assignment.subject_id, assignment.section_id)
    ):
        raise _not_found()
    return assignment


# --- Submissions, versions, late requests ------------------------------------------------------

def get_student_submission_or_404(db: Session, student: User, submission_id: uuid.UUID) -> Submission:
    submission = db.get(Submission, submission_id)
    if submission is None or submission.student_id != student.id:
        raise _not_found()
    get_student_assignment_or_404(db, student, submission.assignment_id)
    return submission


def get_faculty_submission_or_404(db: Session, faculty: User, submission_id: uuid.UUID) -> Submission:
    submission = db.get(Submission, submission_id)
    if submission is None:
        raise _not_found()
    get_faculty_assignment_or_404(db, faculty, submission.assignment_id)
    return submission


def get_version_for_user_or_404(db: Session, user: User, version_id: uuid.UUID) -> SubmissionVersion:
    """Download rule: own versions for a student; students of own assignments for faculty."""
    version = db.get(SubmissionVersion, version_id)
    if version is None:
        raise _not_found()
    if user.role.value == "STUDENT":
        get_student_submission_or_404(db, user, version.submission_id)
    else:
        get_faculty_submission_or_404(db, user, version.submission_id)
    return version


def get_student_late_request_or_404(db: Session, student: User, request_id: uuid.UUID) -> LateRequest:
    late_request = db.get(LateRequest, request_id)
    if late_request is None or late_request.student_id != student.id:
        raise _not_found()
    return late_request


def get_faculty_late_request_or_404(db: Session, faculty: User, request_id: uuid.UUID) -> LateRequest:
    late_request = db.get(LateRequest, request_id)
    if late_request is None:
        raise _not_found()
    get_faculty_assignment_or_404(db, faculty, late_request.assignment_id)
    return late_request
