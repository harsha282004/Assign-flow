"""Student assignment endpoints (architecture §20.2 #15-#16, Phase 4 subset)."""

import uuid
from collections.abc import Callable
from datetime import datetime

from botocore.client import BaseClient
from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from app.core.clock import get_clock, get_now
from app.core.config import Settings
from app.core.deps import get_app_settings, get_db, get_s3, require_role
from app.core.errors import AppError
from app.db.models import User, UserRole
from app.schemas.assignments import StudentAssignmentDetail, StudentAssignmentItem
from app.schemas.late_requests import LateRequestCreate, LateRequestOut
from app.schemas.quiz import AnswersIn, AttemptState, QuizResult, QuizStudentView, SubmitIn
from app.schemas.submissions import UploadResult
from app.services import assignments as svc
from app.services import file_validation, late_requests, quiz, submissions

router = APIRouter(prefix="/student", tags=["student"])

StudentUser = Depends(require_role(UserRole.STUDENT))


@router.get("/assignments", response_model=list[StudentAssignmentItem])
def list_assignments(
    student: User = StudentUser, db: Session = Depends(get_db), now: datetime = Depends(get_now)
):
    return svc.list_student_assignments(db, student, now)


@router.get("/assignments/archived", response_model=list[StudentAssignmentItem])
def list_archived_assignments(
    student: User = StudentUser, db: Session = Depends(get_db), now: datetime = Depends(get_now)
):
    """Archived assignments of my section on which I have my own submission or late request (read-only history)."""
    return svc.list_student_assignments(db, student, now, archived=True)


@router.get("/assignments/{assignment_id}", response_model=StudentAssignmentDetail)
def get_assignment(
    assignment_id: uuid.UUID,
    student: User = StudentUser,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
):
    return svc.student_assignment_detail(db, student, assignment_id, now)


@router.get("/quizzes/{assignment_id}", response_model=QuizStudentView)
def get_quiz(
    assignment_id: uuid.UUID,
    student: User = StudentUser,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
):
    """Quiz details and, once I have started, its questions (never the answer key)."""
    return quiz.student_view(db, student, assignment_id, now)


@router.post("/quizzes/{assignment_id}/attempts", response_model=QuizStudentView)
def start_quiz_attempt(
    assignment_id: uuid.UUID,
    student: User = StudentUser,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
):
    """Begin my single attempt (repeating the call returns the same attempt)."""
    return quiz.start_attempt(db, student, assignment_id, now)


@router.put("/quiz-attempts/{attempt_id}/answers", response_model=AttemptState)
def save_quiz_answers(
    attempt_id: uuid.UUID,
    body: AnswersIn,
    student: User = StudentUser,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
):
    return quiz.save_answers(db, student, attempt_id, body.answers, now)


@router.post("/quiz-attempts/{attempt_id}/submit", response_model=QuizResult)
def submit_quiz_attempt(
    attempt_id: uuid.UUID,
    body: SubmitIn | None = None,
    student: User = StudentUser,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
):
    """Final submission (idempotent). Marks and scores are calculated by the server only."""
    return quiz.submit(db, student, attempt_id, body.answers if body else None, now)


@router.get("/quiz-attempts/{attempt_id}/result", response_model=QuizResult)
def quiz_attempt_result(
    attempt_id: uuid.UUID,
    student: User = StudentUser,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
):
    return quiz.result(db, student, attempt_id, now)


@router.post("/assignments/{assignment_id}/late-request", response_model=LateRequestOut, status_code=201)
def create_late_request(
    assignment_id: uuid.UUID,
    body: LateRequestCreate,
    student: User = StudentUser,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
):
    """Blueprint #18. Only the reason is read from the body; the timestamps and status are server-controlled."""
    return late_requests.create_request(db, student, assignment_id, body.reason, now)


@router.post("/assignments/{assignment_id}/submissions", response_model=UploadResult, status_code=201)
def upload_submission(
    assignment_id: uuid.UUID,
    file: UploadFile = File(...),
    student: User = StudentUser,
    db: Session = Depends(get_db),
    s3: BaseClient = Depends(get_s3),
    settings: Settings = Depends(get_app_settings),
    clock: Callable[[], datetime] = Depends(get_clock),
):
    """Upload a file as a new version. Only the file itself is read from the form: the filename is used for
    display, and any timestamp or status sent by the client is ignored."""
    # Read at most the global cap + 1 byte (the per-assignment limit is applied in validation).
    cap = settings.max_upload_mb * file_validation.MB
    data = file.file.read(cap + 1)
    if len(data) > cap:
        raise AppError("FILE_TOO_LARGE", 413, f"The file is larger than the {settings.max_upload_mb} MB limit.")
    return submissions.upload_submission(db, s3, settings, student, assignment_id, file.filename, data, clock)
