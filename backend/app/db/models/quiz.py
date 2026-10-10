"""Teacher-built quizzes: questions, options, one attempt per student and the selected options.

A quiz is an `assignments` row with assignment_type = 'QUIZ'. Its definition (questions and options, including the
`is_correct` answer key) is written by the owning faculty member while the assignment is a DRAFT and is frozen once
published. Answer keys never leave the server before the release policy allows it (services/quiz.py).

Cross-quiz references are impossible at the database level: an answer row carries the assignment id and uses composite
foreign keys, so its attempt, its question and its option must all belong to the same quiz.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, uuid_pk


class QuizQuestion(Base):
    __tablename__ = "quiz_questions"
    __table_args__ = (
        CheckConstraint("question_type IN ('SINGLE_CHOICE', 'MULTIPLE_SELECT', 'TRUE_FALSE')", name="type_valid"),
        CheckConstraint("marks BETWEEN 1 AND 100", name="marks_range"),
        UniqueConstraint("id", "assignment_id", name="uq_quiz_questions_id_assignment"),
        Index("ix_quiz_questions_assignment_position", "assignment_id", "position"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    assignment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assignments.id", ondelete="RESTRICT")
    )
    question_type: Mapped[str] = mapped_column(String(20))
    text: Mapped[str] = mapped_column(String(1000))
    marks: Mapped[int] = mapped_column(Integer)
    position: Mapped[int] = mapped_column(Integer)


class QuizOption(Base):
    __tablename__ = "quiz_options"
    __table_args__ = (
        UniqueConstraint("id", "question_id", name="uq_quiz_options_id_question"),
        Index("ix_quiz_options_question_position", "question_id", "position"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quiz_questions.id", ondelete="RESTRICT")
    )
    text: Mapped[str] = mapped_column(String(300))
    position: Mapped[int] = mapped_column(Integer)
    is_correct: Mapped[bool] = mapped_column(Boolean)  # the answer key: grading logic only


class QuizAttempt(Base):
    """A student's single attempt at a quiz. `submitted_at` is the server time of submission; `timed_out` marks an
    attempt closed by the server because its time (duration or deadline) ran out."""

    __tablename__ = "quiz_attempts"
    __table_args__ = (
        CheckConstraint("status IN ('IN_PROGRESS', 'SUBMITTED')", name="status_valid"),
        CheckConstraint(
            "(status = 'SUBMITTED') = (submitted_at IS NOT NULL AND score IS NOT NULL AND max_score IS NOT NULL)",
            name="submitted_complete",
        ),
        CheckConstraint("score IS NULL OR (score >= 0 AND score <= max_score)", name="score_in_range"),
        UniqueConstraint("assignment_id", "student_id", name="uq_quiz_attempts_assignment_student"),  # one attempt
        UniqueConstraint("id", "assignment_id", name="uq_quiz_attempts_id_assignment"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    assignment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assignments.id", ondelete="RESTRICT")
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[str] = mapped_column(String(12))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    timed_out: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class QuizAnswer(Base):
    """One selected option of one question in an attempt (no row = the question was left unanswered)."""

    __tablename__ = "quiz_answers"
    __table_args__ = (
        ForeignKeyConstraint(
            ["attempt_id", "assignment_id"],
            ["quiz_attempts.id", "quiz_attempts.assignment_id"],
            ondelete="RESTRICT",
            name="fk_quiz_answers_attempt_id_quiz_attempts",
        ),
        ForeignKeyConstraint(
            ["question_id", "assignment_id"],
            ["quiz_questions.id", "quiz_questions.assignment_id"],
            ondelete="RESTRICT",
            name="fk_quiz_answers_question_id_quiz_questions",
        ),
        ForeignKeyConstraint(
            ["option_id", "question_id"],
            ["quiz_options.id", "quiz_options.question_id"],
            ondelete="RESTRICT",
            name="fk_quiz_answers_option_id_quiz_options",
        ),
        UniqueConstraint("attempt_id", "question_id", "option_id", name="uq_quiz_answers_attempt_question_option"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    attempt_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    assignment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    question_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    option_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
