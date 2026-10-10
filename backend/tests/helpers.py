"""Minimal row factories for constraint tests (random unique natural keys)."""

import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.db.models import (
    Assignment,
    LateRequest,
    Section,
    Subject,
    Submission,
    SubmissionVersion,
    UploadContext,
    User,
    UserRole,
)

NOW = datetime(2026, 10, 11, 12, 0, tzinfo=UTC)
LONG_REASON = "Medical emergency, certificate attached."  # >= 20 chars


def _rand() -> str:
    return secrets.token_hex(4)


def make_user(db: Session, role: UserRole = UserRole.STUDENT) -> User:
    user = User(login_id=f"T{_rand()}", full_name="Test Person", role=role, password_hash="x")
    db.add(user)
    db.flush()
    return user


def make_section(db: Session, semester: int = 3, name: str | None = None) -> Section:
    name = name or f"T{_rand()}"
    section = Section(semester=semester, name=name, label=f"LBL-{_rand()}")
    db.add(section)
    db.flush()
    return section


def make_subject(db: Session, semester: int = 3) -> Subject:
    subject = Subject(code=f"T{_rand()}", name="Test Subject", semester=semester)
    db.add(subject)
    db.flush()
    return subject


def make_assignment(db: Session) -> Assignment:
    faculty = make_user(db, UserRole.FACULTY)
    assignment = Assignment(
        title="Test",
        instructions="Do it",
        subject_id=make_subject(db).id,
        section_id=make_section(db).id,
        created_by=faculty.id,
        original_deadline=NOW,
        deadline=NOW,
        allowed_types=["pdf"],
    )
    db.add(assignment)
    db.flush()
    return assignment


def make_submission(db: Session, assignment: Assignment | None = None, student: User | None = None):
    assignment = assignment or make_assignment(db)
    student = student or make_user(db)
    submission = Submission(assignment_id=assignment.id, student_id=student.id)
    db.add(submission)
    db.flush()
    return submission


def version_kwargs(submission: Submission, version_no: int = 1, **overrides) -> dict:
    values = dict(
        submission_id=submission.id,
        version_no=version_no,
        storage_key=f"submissions/{_rand()}{_rand()}.pdf",
        original_filename="a.pdf",
        mime_type="application/pdf",
        size_bytes=10,
        sha256="a" * 64,
        uploaded_at=NOW,
        uploaded_by=submission.student_id,
        deadline_at_upload=NOW + timedelta(hours=1),
        upload_context=UploadContext.REGULAR,
    )
    values.update(overrides)
    return values


def make_version(db: Session, submission: Submission, version_no: int = 1, **overrides):
    version = SubmissionVersion(**version_kwargs(submission, version_no, **overrides))
    db.add(version)
    db.flush()
    return version


def make_late_request(db: Session, assignment: Assignment, student: User, **overrides) -> LateRequest:
    values = dict(
        assignment_id=assignment.id,
        student_id=student.id,
        reason=LONG_REASON,
        deadline_at_request=NOW,
    )
    values.update(overrides)
    request = LateRequest(**values)
    db.add(request)
    db.flush()
    return request
