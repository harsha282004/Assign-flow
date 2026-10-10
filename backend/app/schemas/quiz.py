"""Quiz payloads. Faculty payloads carry the answer key; student payloads never do (until the release policy allows)."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.schemas.assignments import FacultyAssignmentSummary
from app.schemas.auth import SectionOut, SubjectOut

QuestionType = Literal["SINGLE_CHOICE", "MULTIPLE_SELECT", "TRUE_FALSE"]
MAX_QUESTIONS = 50
MAX_OPTIONS = 8
MAX_TOTAL_MARKS = 1000


class OptionIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    text: str = Field(min_length=1, max_length=300)
    is_correct: bool = False


class QuestionIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    question_type: QuestionType
    text: str = Field(min_length=1, max_length=1000)
    marks: int = Field(ge=1, le=100)
    options: list[OptionIn] = Field(min_length=2, max_length=MAX_OPTIONS)

    @model_validator(mode="after")
    def _check_options(self) -> "QuestionIn":
        texts = [o.text.casefold() for o in self.options]
        if len(set(texts)) != len(texts):
            raise ValueError("Answer options must be different from each other")
        correct = sum(o.is_correct for o in self.options)
        if self.question_type == "TRUE_FALSE":
            if [o.text for o in self.options] != ["True", "False"]:
                raise ValueError("A True / False question must have exactly the options True and False")
            if correct != 1:
                raise ValueError("A True / False question needs exactly one correct answer")
        elif self.question_type == "SINGLE_CHOICE":
            if correct != 1:
                raise ValueError("A single-choice question needs exactly one correct answer")
        elif correct < 1:
            raise ValueError("A multiple-select question needs at least one correct answer")
        return self


class QuizDefinition(BaseModel):
    """The editable definition of a quiz. Unknown fields (status, total_marks, created_by, ...) are rejected: the
    server calculates the total marks and owns every other field."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=2000)
    instructions: str = Field(min_length=1, max_length=5000)
    deadline: AwareDatetime
    duration_minutes: int | None = Field(default=None, ge=1, le=300)
    questions: list[QuestionIn] = Field(default_factory=list, max_length=MAX_QUESTIONS)

    @model_validator(mode="after")
    def _check_total(self) -> "QuizDefinition":
        if sum(q.marks for q in self.questions) > MAX_TOTAL_MARKS:
            raise ValueError(f"The total marks cannot exceed {MAX_TOTAL_MARKS}")
        if self.description == "":
            self.description = None
        return self


class QuizCreate(QuizDefinition):
    subject_id: uuid.UUID
    section_id: uuid.UUID
    publish: bool = False


# --- Faculty reads -------------------------------------------------------------------------------------------

class OptionFaculty(BaseModel):
    id: uuid.UUID
    text: str
    is_correct: bool


class QuestionFaculty(BaseModel):
    id: uuid.UUID
    question_type: QuestionType
    text: str
    marks: int
    options: list[OptionFaculty]


class QuizFacultyDetail(FacultyAssignmentSummary):
    instructions: str
    description: str | None
    duration_minutes: int | None
    question_count: int
    total_marks: int
    questions: list[QuestionFaculty]


class QuizParticipant(BaseModel):
    student_id: uuid.UUID
    login_id: str
    full_name: str
    status: Literal["NOT_STARTED", "IN_PROGRESS", "SUBMITTED"]
    started_at: datetime | None
    submitted_at: datetime | None
    score: int | None
    max_score: int | None
    timed_out: bool


class QuizParticipation(BaseModel):
    assignment_id: uuid.UUID
    total_marks: int
    expected_students: int
    started: int
    submitted: int
    average_score: float | None
    participants: list[QuizParticipant]


# --- Student ---------------------------------------------------------------------------------------------------

class OptionStudent(BaseModel):
    id: uuid.UUID
    text: str  # never the answer key


class QuestionStudent(BaseModel):
    id: uuid.UUID
    question_type: QuestionType
    text: str
    marks: int
    options: list[OptionStudent]


class AttemptState(BaseModel):
    id: uuid.UUID
    status: Literal["IN_PROGRESS", "SUBMITTED"]
    started_at: datetime
    expires_at: datetime  # the earlier of the deadline and start + duration; enforced by the server
    submitted_at: datetime | None
    timed_out: bool
    answers: dict[uuid.UUID, list[uuid.UUID]]  # question id -> the student's own selected option ids


class QuizStudentView(BaseModel):
    assignment_id: uuid.UUID
    title: str
    description: str | None
    instructions: str
    subject: SubjectOut
    section: SectionOut
    faculty_name: str | None
    deadline: datetime
    duration_minutes: int | None
    question_count: int
    total_marks: int
    can_attempt: bool
    blocked_reason: Literal["DEADLINE_PASSED", "ARCHIVED"] | None
    attempt: AttemptState | None
    # Questions are sent only once the student has started the attempt, and never include the answer key.
    questions: list[QuestionStudent] | None


class AnswerIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: uuid.UUID
    option_ids: list[uuid.UUID] = Field(max_length=MAX_OPTIONS)


class AnswersIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answers: list[AnswerIn] = Field(max_length=MAX_QUESTIONS)


class SubmitIn(BaseModel):
    """Optional final answers, saved in the same transaction as the submission."""

    model_config = ConfigDict(extra="forbid")

    answers: list[AnswerIn] | None = Field(default=None, max_length=MAX_QUESTIONS)


class QuestionResult(BaseModel):
    question_id: uuid.UUID
    text: str
    marks: int
    awarded: int
    question_type: QuestionType
    options: list[OptionStudent]
    selected_option_ids: list[uuid.UUID]
    # The answer key: only after the deadline has passed (see services/quiz.py, release policy).
    correct_option_ids: list[uuid.UUID] | None


class QuizResult(BaseModel):
    attempt_id: uuid.UUID
    assignment_id: uuid.UUID
    title: str
    status: Literal["SUBMITTED"]
    started_at: datetime
    submitted_at: datetime
    timed_out: bool
    score: int
    max_score: int
    answers_released: bool
    questions: list[QuestionResult]
