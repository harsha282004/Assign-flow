"""Resource-scope rules (architecture §8.2) against the seeded academic structure."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.models import (
    Assignment,
    AssignmentStatus,
    LateRequest,
    Section,
    Subject,
    Submission,
    SubmissionVersion,
    UploadContext,
    User,
)
from app.services import scope

DEADLINE = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)


@pytest.fixture
def s(db: Session, seeded_engine):
    """Session over the seeded test database (changes roll back)."""
    return db


def user(db, login_id) -> User:
    return db.scalar(select(User).where(User.login_id == login_id))


def slot(db, code, label):
    return (
        db.scalar(select(Subject).where(Subject.code == code)),
        db.scalar(select(Section).where(Section.label == label)),
    )


def assignment(db, creator="FAC001", code="CS503", label="CSE-5A", status=AssignmentStatus.PUBLISHED) -> Assignment:
    subject, section = slot(db, code, label)
    row = Assignment(
        title="Scope test",
        instructions="x",
        subject_id=subject.id,
        section_id=section.id,
        created_by=user(db, creator).id,
        status=status,
        original_deadline=DEADLINE,
        deadline=DEADLINE,
        allowed_types=["pdf"],
    )
    db.add(row)
    db.flush()
    return row


def submission_with_version(db, a: Assignment, student="STU0101"):
    sub = Submission(assignment_id=a.id, student_id=user(db, student).id, latest_version_no=1)
    db.add(sub)
    db.flush()
    version = SubmissionVersion(
        submission_id=sub.id,
        version_no=1,
        storage_key=f"submissions/{uuid.uuid4()}.pdf",
        original_filename="a.pdf",
        mime_type="application/pdf",
        size_bytes=5,
        sha256="b" * 64,
        uploaded_at=DEADLINE - timedelta(hours=1),
        uploaded_by=sub.student_id,
        deadline_at_upload=DEADLINE,
        upload_context=UploadContext.REGULAR,
    )
    db.add(version)
    db.flush()
    return sub, version


def status_of(fn, *args):
    with pytest.raises(AppError) as err:
        fn(*args)
    return err.value.http_status


# --- assignments: student -----------------------------------------------------------------------

def test_student_sees_published_assignment_of_own_section_only(s):
    a = assignment(s)
    assert scope.get_student_assignment_or_404(s, user(s, "STU0101"), a.id) is a
    assert scope.get_student_assignment_or_404(s, user(s, "STU0117"), a.id) is a  # last student of 5A
    assert status_of(scope.get_student_assignment_or_404, s, user(s, "STU0118"), a.id) == 404  # 5B
    assert status_of(scope.get_student_assignment_or_404, s, user(s, "STU0135"), a.id) == 404  # 5C
    assert status_of(scope.get_student_assignment_or_404, s, user(s, "STU0101"), uuid.uuid4()) == 404


def test_draft_assignment_is_invisible_to_students(s):
    a = assignment(s, status=AssignmentStatus.DRAFT)
    assert status_of(scope.get_student_assignment_or_404, s, user(s, "STU0101"), a.id) == 404


# --- assignments: faculty --------------------------------------------------------------------------

def test_faculty_manages_only_own_assignments_in_own_classes(s):
    a = assignment(s)
    assert scope.get_faculty_assignment_or_404(s, user(s, "FAC001"), a.id) is a
    assert status_of(scope.get_faculty_assignment_or_404, s, user(s, "FAC002"), a.id) == 404  # other faculty
    assert status_of(scope.get_faculty_assignment_or_404, s, user(s, "QAFAC01"), a.id) == 404  # no classes
    assert status_of(scope.get_faculty_assignment_or_404, s, user(s, "FAC001"), uuid.uuid4()) == 404


def test_creator_who_does_not_teach_the_class_has_no_access(s):
    a = assignment(s, creator="FAC002")  # FAC002 created it but does not teach CS503/CSE-5A
    assert status_of(scope.get_faculty_assignment_or_404, s, user(s, "FAC002"), a.id) == 404


def test_teaching_slot_check_returns_403_not_your_class(s):
    subject, section_5a = slot(s, "CS503", "CSE-5A")
    _, section_5b = slot(s, "CS503", "CSE-5B")
    scope.require_teaching_slot(s, user(s, "FAC001"), subject.id, section_5a.id)  # own slot: no error
    for faculty, section in (("FAC001", section_5b), ("QAFAC01", section_5a), ("FAC002", section_5a)):
        with pytest.raises(AppError) as err:
            scope.require_teaching_slot(s, user(s, faculty), subject.id, section.id)
        assert (err.value.http_status, err.value.code) == (403, "NOT_YOUR_CLASS")


# --- submissions, versions, late requests -----------------------------------------------------------------

def test_submission_and_version_scope(s):
    a = assignment(s)
    sub, version = submission_with_version(s, a)
    owner, classmate, teacher, other_teacher = user(s, "STU0101"), user(s, "STU0102"), user(s, "FAC001"), user(s, "FAC002")

    assert scope.get_student_submission_or_404(s, owner, sub.id) is sub
    assert status_of(scope.get_student_submission_or_404, s, classmate, sub.id) == 404
    assert scope.get_faculty_submission_or_404(s, teacher, sub.id) is sub
    assert status_of(scope.get_faculty_submission_or_404, s, other_teacher, sub.id) == 404

    assert scope.get_version_for_user_or_404(s, owner, version.id) is version
    assert scope.get_version_for_user_or_404(s, teacher, version.id) is version
    for outsider in (classmate, other_teacher, user(s, "STU0135"), user(s, "QAFAC01")):
        assert status_of(scope.get_version_for_user_or_404, s, outsider, version.id) == 404
    assert status_of(scope.get_version_for_user_or_404, s, owner, uuid.uuid4()) == 404


def test_late_request_scope(s):
    a = assignment(s)
    request = LateRequest(
        assignment_id=a.id,
        student_id=user(s, "STU0101").id,
        reason="Medical emergency, certificate attached.",
        deadline_at_request=DEADLINE,
    )
    s.add(request)
    s.flush()
    assert scope.get_student_late_request_or_404(s, user(s, "STU0101"), request.id) is request
    assert status_of(scope.get_student_late_request_or_404, s, user(s, "STU0102"), request.id) == 404
    assert scope.get_faculty_late_request_or_404(s, user(s, "FAC001"), request.id) is request
    assert status_of(scope.get_faculty_late_request_or_404, s, user(s, "FAC002"), request.id) == 404
    assert status_of(scope.get_faculty_late_request_or_404, s, user(s, "FAC001"), uuid.uuid4()) == 404
