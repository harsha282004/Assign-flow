"""Faculty assignment endpoints (architecture §20.2 #4-#8; PATCH on drafts is a documented addition)."""

import uuid
from datetime import datetime
from typing import Literal

from botocore.client import BaseClient
from fastapi import APIRouter, Depends, File, Query, Response, UploadFile
from sqlalchemy.orm import Session

from app.core.clock import get_now
from app.core.config import Settings
from app.core.deps import get_app_settings, get_db, get_s3, require_role
from app.core.errors import AppError
from app.db.models import User, UserRole
from app.schemas.assignments import (
    ArchiveIn,
    AssignmentCreate,
    AssignmentUpdate,
    DeadlineChangeIn,
    DeletionCheck,
    DeletionResult,
    FacultyAssignmentDetail,
    FacultyAssignmentSummary,
)
from app.schemas.attachments import AttachmentOut
from app.schemas.late_requests import (
    FacultyLateRequestDetail,
    FacultyLateRequestItem,
    LateRequestDecisionIn,
)
from app.schemas.overview import OverviewResponse, OverviewStudents, ReviewFilter, TimingFilter
from app.schemas.quiz import QuizCreate, QuizDefinition, QuizFacultyDetail, QuizParticipation
from app.schemas.reviews import ReviewIn, ReviewOut
from app.schemas.submissions import RosterRow, StudentSubmissionDetail
from app.services import (
    assignment_archive,
    assignment_deletion,
    attachments,
    deadlines,
    file_validation,
    late_requests,
    overview,
    quiz,
    reviews,
    scope,
    submissions,
)
from app.services import assignments as svc

router = APIRouter(prefix="/faculty", tags=["faculty"])

FacultyUser = Depends(require_role(UserRole.FACULTY))


@router.get("/assignments", response_model=list[FacultyAssignmentSummary])
def list_assignments(
    subject_id: uuid.UUID | None = None,
    section_id: uuid.UUID | None = None,
    state: Literal["active", "archived", "all"] = "all",
    faculty: User = FacultyUser,
    db: Session = Depends(get_db),
):
    """My assignments, optionally for one subject and / or one section (403 unless I teach it).
    `state`: active (drafts + published), archived, or all."""
    return svc.list_faculty_assignments(db, faculty, subject_id, section_id, state)


@router.post("/assignments", response_model=FacultyAssignmentDetail, status_code=201)
def create_assignment(
    body: AssignmentCreate,
    faculty: User = FacultyUser,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
):
    assignment = svc.create_assignment(db, faculty, body, now)
    return svc.faculty_assignment_detail(db, assignment)


@router.post("/quizzes", response_model=QuizFacultyDetail, status_code=201)
def create_quiz(
    body: QuizCreate,
    faculty: User = FacultyUser,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
):
    """Create a quiz (draft, or published when `publish` is true). Total marks are calculated by the server."""
    return quiz.faculty_detail_of(db, quiz.create_quiz(db, faculty, body, now))


@router.get("/quizzes/{assignment_id}", response_model=QuizFacultyDetail)
def get_quiz(assignment_id: uuid.UUID, faculty: User = FacultyUser, db: Session = Depends(get_db)):
    """The full quiz definition including the answer key (faculty only)."""
    return quiz.faculty_detail(db, faculty, assignment_id)


@router.put("/quizzes/{assignment_id}", response_model=QuizFacultyDetail)
def update_quiz(
    assignment_id: uuid.UUID,
    body: QuizDefinition,
    faculty: User = FacultyUser,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
):
    """Replace the definition of a DRAFT quiz. Publish with POST /faculty/assignments/{id}/publish."""
    return quiz.faculty_detail_of(db, quiz.update_quiz(db, faculty, assignment_id, body, now))


@router.get("/quizzes/{assignment_id}/participation", response_model=QuizParticipation)
def quiz_participation(assignment_id: uuid.UUID, faculty: User = FacultyUser, db: Session = Depends(get_db)):
    """Who has started / submitted and the scores, for my own quiz (real database values)."""
    return quiz.participation(db, faculty, assignment_id)


@router.get("/assignments/{assignment_id}", response_model=FacultyAssignmentDetail)
def get_assignment(assignment_id: uuid.UUID, faculty: User = FacultyUser, db: Session = Depends(get_db)):
    assignment = scope.get_faculty_assignment_or_404(db, faculty, assignment_id)
    return svc.faculty_assignment_detail(db, assignment)


@router.patch("/assignments/{assignment_id}", response_model=FacultyAssignmentDetail)
def update_assignment(
    assignment_id: uuid.UUID,
    body: AssignmentUpdate,
    faculty: User = FacultyUser,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
):
    assignment = scope.get_faculty_assignment_or_404(db, faculty, assignment_id)
    svc.update_draft(db, assignment, body, now)
    return svc.faculty_assignment_detail(db, assignment)


@router.get("/assignments/{assignment_id}/deletion-check", response_model=DeletionCheck)
def deletion_check(assignment_id: uuid.UUID, faculty: User = FacultyUser, db: Session = Depends(get_db)):
    """Whether (and why not) the assignment can be permanently deleted. Read-only."""
    return assignment_deletion.check(db, faculty, assignment_id)


@router.delete("/assignments/{assignment_id}", response_model=DeletionResult)
def delete_assignment(
    assignment_id: uuid.UUID,
    faculty: User = FacultyUser,
    db: Session = Depends(get_db),
    s3: BaseClient = Depends(get_s3),
    settings: Settings = Depends(get_app_settings),
):
    """Permanently delete one of my assignments, only if no student work or history refers to it (409 otherwise)."""
    return assignment_deletion.delete_assignment(db, s3, settings, faculty, assignment_id)


@router.post("/assignments/{assignment_id}/archive", response_model=FacultyAssignmentDetail)
def archive_assignment(
    assignment_id: uuid.UUID,
    body: ArchiveIn | None = None,
    faculty: User = FacultyUser,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
):
    """Take a published assignment out of active use. Nothing is deleted; reversible with /restore."""
    return assignment_archive.archive(db, faculty, assignment_id, body.reason if body else None, now)


@router.post("/assignments/{assignment_id}/restore", response_model=FacultyAssignmentDetail)
def restore_assignment(
    assignment_id: uuid.UUID,
    body: ArchiveIn | None = None,
    faculty: User = FacultyUser,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
):
    return assignment_archive.restore(db, faculty, assignment_id, body.reason if body else None, now)


@router.post("/assignments/{assignment_id}/publish", response_model=FacultyAssignmentDetail)
def publish_assignment(
    assignment_id: uuid.UUID,
    faculty: User = FacultyUser,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
):
    assignment = scope.get_faculty_assignment_or_404(db, faculty, assignment_id)
    svc.publish_assignment(db, assignment, now)
    return svc.faculty_assignment_detail(db, assignment)


@router.patch("/assignments/{assignment_id}/deadline", response_model=FacultyAssignmentDetail)
def change_deadline(
    assignment_id: uuid.UUID,
    body: DeadlineChangeIn,
    faculty: User = FacultyUser,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
):
    assignment = deadlines.change_deadline(db, faculty, assignment_id, body.new_deadline, body.reason, now)
    return svc.faculty_assignment_detail(db, assignment)


@router.post("/assignments/{assignment_id}/attachments", response_model=AttachmentOut, status_code=201)
def add_attachment(
    assignment_id: uuid.UUID,
    file: UploadFile = File(...),
    faculty: User = FacultyUser,
    db: Session = Depends(get_db),
    s3: BaseClient = Depends(get_s3),
    settings: Settings = Depends(get_app_settings),
    now: datetime = Depends(get_now),
):
    """Attach one reference document (PDF, PPT or PPTX) to a DRAFT assignment of mine."""
    cap = settings.max_upload_mb * file_validation.MB
    data = file.file.read(cap + 1)
    if len(data) > cap:
        raise AppError("FILE_TOO_LARGE", 413, f"The file is larger than the {settings.max_upload_mb} MB limit.")
    return attachments.add_attachment(db, s3, settings, faculty, assignment_id, file.filename, data, now)


@router.delete("/assignments/{assignment_id}/attachments/{attachment_id}", status_code=204)
def remove_attachment(
    assignment_id: uuid.UUID,
    attachment_id: uuid.UUID,
    faculty: User = FacultyUser,
    db: Session = Depends(get_db),
    s3: BaseClient = Depends(get_s3),
    settings: Settings = Depends(get_app_settings),
):
    attachments.remove_attachment(db, s3, settings, faculty, assignment_id, attachment_id)
    return Response(status_code=204)


@router.post("/submissions/{submission_id}/reviews", response_model=ReviewOut, status_code=201)
def record_review(
    submission_id: uuid.UUID,
    body: ReviewIn,
    faculty: User = FacultyUser,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
):
    """Blueprint #11: append a review of the submission's latest version. Reviewer, version and time are server-set."""
    return reviews.record_review(db, faculty, submission_id, body, now)


@router.get("/submissions/{submission_id}/locator")
def submission_locator(submission_id: uuid.UUID, faculty: User = FacultyUser, db: Session = Depends(get_db)):
    """Resolve a notification's submission id to its page (404 unless it belongs to one of my assignments)."""
    submission = scope.get_faculty_submission_or_404(db, faculty, submission_id)
    return {"assignment_id": submission.assignment_id, "student_id": submission.student_id}


@router.get("/overview", response_model=OverviewResponse)
def get_overview(
    assignment_id: uuid.UUID | None = None,
    subject_id: uuid.UUID | None = None,
    section_id: uuid.UUID | None = None,
    faculty: User = FacultyUser,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
):
    """Blueprint #13: counts per assignment and in total, from SQL, for the faculty member's own scope."""
    return overview.overview(db, faculty, now, assignment_id, subject_id, section_id)


@router.get("/overview/students", response_model=OverviewStudents)
def get_overview_students(
    assignment_id: uuid.UUID | None = None,
    subject_id: uuid.UUID | None = None,
    section_id: uuid.UUID | None = None,
    timing: TimingFilter | None = None,
    review_status: ReviewFilter | None = None,
    limit: int = Query(default=200, ge=1, le=500),
    faculty: User = FacultyUser,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
):
    """The students behind the counts (same query), filterable by timing and review status."""
    return overview.students(db, faculty, now, assignment_id, subject_id, section_id, timing, review_status, limit)


@router.get("/late-requests", response_model=list[FacultyLateRequestItem])
def list_late_requests(
    status: Literal["PENDING", "APPROVED", "REJECTED", "EXPIRED", "USED"] | None = None,
    assignment_id: uuid.UUID | None = None,
    subject_id: uuid.UUID | None = None,
    section_id: uuid.UUID | None = None,
    faculty: User = FacultyUser,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
):
    """Blueprint #12: requests on my own assignments. `status` also accepts the derived EXPIRED / USED labels.
    Optional subject / section filters (403 unless I teach them)."""
    return late_requests.list_requests(db, faculty, now, status, assignment_id, subject_id, section_id)


@router.get("/late-requests/{request_id}", response_model=FacultyLateRequestDetail)
def get_late_request(
    request_id: uuid.UUID,
    faculty: User = FacultyUser,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
):
    return late_requests.request_detail(db, faculty, request_id, now)


@router.post("/late-requests/{request_id}/decision", response_model=FacultyLateRequestItem)
def decide_late_request(
    request_id: uuid.UUID,
    body: LateRequestDecisionIn,
    faculty: User = FacultyUser,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
):
    """Blueprint #14. The decision time and the approved window come from the server clock."""
    return late_requests.decide(db, faculty, request_id, body, now)


@router.get("/assignments/{assignment_id}/roster", response_model=list[RosterRow])
def roster(
    assignment_id: uuid.UUID,
    status: Literal["PENDING", "ON_TIME", "LATE", "MISSING"] | None = None,
    faculty: User = FacultyUser,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
):
    assignment = scope.get_faculty_assignment_or_404(db, faculty, assignment_id)
    return submissions.roster(db, assignment, now, status)


@router.get(
    "/assignments/{assignment_id}/students/{student_id}/timeline", response_model=StudentSubmissionDetail
)
def student_submission(
    assignment_id: uuid.UUID,
    student_id: uuid.UUID,
    faculty: User = FacultyUser,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
):
    """Blueprint #10: versions, reviews, the Deadline Integrity Timeline events and "why this status"."""
    return submissions.faculty_student_submission(db, faculty, assignment_id, student_id, now)
