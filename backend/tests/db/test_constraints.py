"""Database constraint tests (each runs inside a rolled-back transaction)."""

import uuid
from contextlib import contextmanager
from datetime import timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    Assignment,
    LateRequest,
    LateRequestStatus,
    Review,
    ReviewStatus,
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
from tests.helpers import (
    LONG_REASON,
    NOW,
    make_assignment,
    make_late_request,
    make_section,
    make_subject,
    make_submission,
    make_user,
    make_version,
    version_kwargs,
)


@contextmanager
def violates(db: Session, exc=IntegrityError):
    """Expect a DB error; the savepoint is rolled back so the session stays usable."""
    with pytest.raises(exc):
        with db.begin_nested():
            yield
            db.flush()


def test_foreign_key_rejects_missing_parent(db: Session):
    with violates(db):  # section does not exist
        db.add(StudentProfile(user_id=make_user(db).id, section_id=uuid.uuid4()))
    with violates(db):  # user does not exist
        db.add(TeachingAssignment(faculty_id=uuid.uuid4(), subject_id=make_subject(db).id, section_id=make_section(db).id))


def test_foreign_key_restrict_blocks_deleting_referenced_row(db: Session):
    user = make_user(db)
    section = make_section(db)
    db.add(StudentProfile(user_id=user.id, section_id=section.id))
    db.flush()
    with violates(db):
        db.execute(text("DELETE FROM sections WHERE id = :i"), {"i": section.id})


def test_login_id_is_unique(db: Session):
    user = make_user(db)
    with violates(db):
        db.add(User(login_id=user.login_id, full_name="Dup", role=UserRole.STUDENT, password_hash="x"))


def test_subject_code_is_unique(db: Session):
    subject = make_subject(db)
    with violates(db):
        db.add(Subject(code=subject.code, name="Dup", semester=3))


def test_section_semester_name_and_label_are_unique(db: Session):
    section = make_section(db, semester=5, name="ZZ")
    with violates(db):
        db.add(Section(semester=5, name="ZZ", label="OTHER-LABEL"))
    with violates(db):
        db.add(Section(semester=6, name="ZZ", label=section.label))


def test_teaching_slot_cannot_be_duplicated(db: Session):
    subject, section = make_subject(db), make_section(db)
    db.add(TeachingAssignment(faculty_id=make_user(db, UserRole.FACULTY).id, subject_id=subject.id, section_id=section.id))
    db.flush()
    with violates(db):
        db.add(
            TeachingAssignment(
                faculty_id=make_user(db, UserRole.FACULTY).id, subject_id=subject.id, section_id=section.id
            )
        )


def test_one_submission_per_assignment_and_student(db: Session):
    submission = make_submission(db)
    with violates(db):
        db.add(Submission(assignment_id=submission.assignment_id, student_id=submission.student_id))


def test_submission_version_number_is_unique_per_submission(db: Session):
    submission = make_submission(db)
    make_version(db, submission, 1)
    with violates(db):
        db.add(SubmissionVersion(**version_kwargs(submission, 1)))
    make_version(db, submission, 2)  # a different number is fine


def test_storage_key_is_unique(db: Session):
    submission = make_submission(db)
    first = make_version(db, submission, 1)
    with violates(db):
        db.add(SubmissionVersion(**version_kwargs(submission, 2, storage_key=first.storage_key)))


def test_one_late_request_per_student_and_assignment(db: Session):
    assignment, student = make_assignment(db), make_user(db)
    make_late_request(db, assignment, student)
    with violates(db):
        db.add(LateRequest(assignment_id=assignment.id, student_id=student.id, reason=LONG_REASON, deadline_at_request=NOW))


def test_invalid_enum_value_is_rejected(db: Session):
    with violates(db, DBAPIError):
        db.execute(
            text(
                "INSERT INTO users (login_id, full_name, role, password_hash) "
                "VALUES ('BADROLE1', 'x', 'ADMIN', 'x')"
            )
        )


def test_check_constraints_reject_invalid_values(db: Session):
    # sections.semester range
    with violates(db):
        db.add(Section(semester=9, name="Q", label=f"BAD-{make_user(db).login_id}"))
    # assignments.max_file_mb range
    faculty = make_user(db, UserRole.FACULTY)
    with violates(db):
        db.add(
            Assignment(
                title="t", instructions="i", subject_id=make_subject(db).id, section_id=make_section(db).id,
                created_by=faculty.id, original_deadline=NOW, deadline=NOW, allowed_types=["pdf"], max_file_mb=11,
            )
        )
    # late request reason too short
    assignment, student = make_assignment(db), make_user(db)
    with violates(db):
        db.add(LateRequest(assignment_id=assignment.id, student_id=student.id, reason="too short", deadline_at_request=NOW))


def test_version_context_requires_matching_late_request(db: Session):
    submission = make_submission(db)
    with violates(db):  # LATE_APPROVED without a late_request_id
        db.add(SubmissionVersion(**version_kwargs(submission, 1, upload_context=UploadContext.LATE_APPROVED)))
    assignment, student = make_assignment(db), make_user(db)
    faculty = make_user(db, UserRole.FACULTY)
    request = make_late_request(
        db, assignment, student, status=LateRequestStatus.APPROVED, decided_by=faculty.id, decided_at=NOW,
        window_start=NOW, window_end=NOW + timedelta(hours=24),
    )
    with violates(db):  # REGULAR carrying a late_request_id
        db.add(SubmissionVersion(**version_kwargs(submission, 2, late_request_id=request.id)))
    # the valid combination succeeds
    make_version(db, submission, 3, upload_context=UploadContext.LATE_APPROVED, late_request_id=request.id)


def test_late_request_decision_and_window_fields_must_match_status(db: Session):
    assignment, faculty = make_assignment(db), make_user(db, UserRole.FACULTY)
    with violates(db):  # APPROVED without decision/window fields
        db.add(LateRequest(assignment_id=assignment.id, student_id=make_user(db).id, reason=LONG_REASON,
                           deadline_at_request=NOW, status=LateRequestStatus.APPROVED))
    with violates(db):  # PENDING with a window
        db.add(LateRequest(assignment_id=assignment.id, student_id=make_user(db).id, reason=LONG_REASON,
                           deadline_at_request=NOW, window_start=NOW, window_end=NOW + timedelta(hours=1)))
    # REJECTED with decision fields and no window is valid
    make_late_request(db, assignment, make_user(db), status=LateRequestStatus.REJECTED, decided_by=faculty.id, decided_at=NOW)


def test_review_requires_valid_references_and_status(db: Session):
    submission = make_submission(db)
    version = make_version(db, submission, 1)
    reviewer = make_user(db, UserRole.FACULTY)
    db.add(Review(submission_id=submission.id, version_id=version.id, reviewer_id=reviewer.id, status=ReviewStatus.ACCEPTED))
    db.flush()
    with violates(db, DBAPIError):
        db.execute(
            text(
                "INSERT INTO reviews (submission_id, version_id, reviewer_id, status) "
                "VALUES (:s, :v, :r, 'PASSED')"
            ),
            {"s": submission.id, "v": version.id, "r": reviewer.id},
        )
