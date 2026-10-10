"""Import every model so Base.metadata is complete (used by Alembic and tests)."""

from app.db.models.academics import Section, StudentProfile, Subject, TeachingAssignment
from app.db.models.assignments import (
    Assignment,
    AssignmentStateChange,
    AssignmentStatus,
    DeadlineChange,
)
from app.db.models.attachments import AssignmentAttachment
from app.db.models.late_requests import LateRequest, LateRequestStatus
from app.db.models.notifications import Notification
from app.db.models.quiz import QuizAnswer, QuizAttempt, QuizOption, QuizQuestion
from app.db.models.reviews import Review, ReviewStatus
from app.db.models.submissions import Submission, SubmissionVersion, UploadContext
from app.db.models.users import User, UserRole

__all__ = [
    "Assignment",
    "AssignmentAttachment",
    "AssignmentStateChange",
    "AssignmentStatus",
    "DeadlineChange",
    "LateRequest",
    "LateRequestStatus",
    "Notification",
    "QuizAnswer",
    "QuizAttempt",
    "QuizOption",
    "QuizQuestion",
    "Review",
    "ReviewStatus",
    "Section",
    "StudentProfile",
    "Subject",
    "Submission",
    "SubmissionVersion",
    "TeachingAssignment",
    "UploadContext",
    "User",
    "UserRole",
]
