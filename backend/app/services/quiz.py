"""Teacher-built quizzes (see db/models/quiz.py).

Policies (documented in docs/IMPLEMENTATION_LOG.md):
  * Definition: written by the owning faculty member (teaches the subject x section) while the assignment is a DRAFT;
    every save replaces the whole question list after full validation. Published quizzes are frozen (only the deadline
    can change, through the existing deadline endpoint). The server calculates the total marks.
  * Attempts: exactly one per student and quiz (UNIQUE in the database). The questions are sent to a student only after
    they start the attempt and never contain the answer key. The attempt expires at min(deadline, start + duration);
    the server enforces it. After expiry nothing can be saved, and the attempt is closed with the answers saved so far
    (timed_out = true, submitted_at = the moment it expired).
  * Grading: objective and server-side only. A question earns its full marks only when the selected option set equals
    the correct option set (all-or-nothing, also for multiple-select); otherwise 0. Unanswered = 0.
  * Release policy: the student sees their score at once after submitting; the answer key (correct options) is shown
    only after the deadline has passed, so a classmate cannot be tipped off before the quiz closes.
  * Late requests do not apply to quizzes: after the deadline no attempt can start.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.models import (
    Assignment,
    AssignmentStatus,
    QuizAnswer,
    QuizAttempt,
    QuizOption,
    QuizQuestion,
    Section,
    StudentProfile,
    Subject,
    TeachingAssignment,
    User,
)
from app.schemas.auth import SectionOut, SubjectOut
from app.schemas.quiz import (
    AnswerIn,
    AttemptState,
    OptionFaculty,
    OptionStudent,
    QuestionFaculty,
    QuestionResult,
    QuestionStudent,
    QuizCreate,
    QuizDefinition,
    QuizFacultyDetail,
    QuizParticipant,
    QuizParticipation,
    QuizResult,
    QuizStudentView,
)
from app.services import archive_guard, notifications, scope
from app.services.timeline import fmt


def _utc(value: datetime) -> datetime:
    return value.astimezone(UTC)


def _not_found() -> AppError:
    return AppError("NOT_FOUND", 404, "The requested resource was not found.")


# --- Faculty: definition -------------------------------------------------------------------------------------

def _write_questions(db: Session, assignment: Assignment, data: QuizDefinition) -> None:
    """Replace the question list (DRAFT only). IDs are new on every save; nothing refers to a draft's questions."""
    old_ids = select(QuizQuestion.id).where(QuizQuestion.assignment_id == assignment.id)
    db.execute(delete(QuizOption).where(QuizOption.question_id.in_(old_ids)))
    db.execute(delete(QuizQuestion).where(QuizQuestion.assignment_id == assignment.id))
    for position, q in enumerate(data.questions, start=1):
        question = QuizQuestion(
            assignment_id=assignment.id,
            question_type=q.question_type,
            text=q.text,
            marks=q.marks,
            position=position,
        )
        db.add(question)
        db.flush()
        for opt_position, o in enumerate(q.options, start=1):
            db.add(QuizOption(question_id=question.id, text=o.text, position=opt_position, is_correct=o.is_correct))
    db.flush()


def _question_count(db: Session, assignment_id: uuid.UUID) -> int:
    return db.scalar(select(func.count()).select_from(QuizQuestion).where(QuizQuestion.assignment_id == assignment_id)) or 0


def total_marks(db: Session, assignment_id: uuid.UUID) -> int:
    """Always calculated from the questions; there is no stored (client-supplied) total."""
    return db.scalar(select(func.coalesce(func.sum(QuizQuestion.marks), 0)).where(QuizQuestion.assignment_id == assignment_id)) or 0


def create_quiz(db: Session, faculty: User, data: QuizCreate, now: datetime) -> Assignment:
    from app.services import assignments as base  # lazy: assignments imports this module

    scope.require_teaching_slot(db, faculty, data.subject_id, data.section_id)  # 403 NOT_YOUR_CLASS
    deadline = _utc(data.deadline)
    base.require_deadline_lead(deadline, now)
    assignment = Assignment(
        title=data.title,
        instructions=data.instructions,
        description=data.description,
        subject_id=data.subject_id,
        section_id=data.section_id,
        created_by=faculty.id,
        status=AssignmentStatus.DRAFT,
        original_deadline=deadline,
        deadline=deadline,
        allowed_types=[],
        assignment_type="QUIZ",
        duration_minutes=data.duration_minutes,
        created_at=now,
    )
    db.add(assignment)
    db.flush()
    _write_questions(db, assignment, data)
    if data.publish:
        publish(db, assignment, now)
    return assignment


def update_quiz(db: Session, faculty: User, assignment_id: uuid.UUID, data: QuizDefinition, now: datetime) -> Assignment:
    from app.services import assignments as base

    assignment = scope.get_faculty_assignment_or_404(db, faculty, assignment_id)
    if assignment.assignment_type != "QUIZ":
        raise AppError("NOT_A_QUIZ", 409, "This assignment is not a quiz.")
    db.refresh(assignment, with_for_update=True)
    if assignment.status != AssignmentStatus.DRAFT:
        raise AppError(
            "NOT_DRAFT", 409, "Only a draft quiz can be edited. Use the deadline change for a published quiz."
        )
    deadline = _utc(data.deadline)
    base.require_deadline_lead(deadline, now)
    assignment.title = data.title
    assignment.instructions = data.instructions
    assignment.description = data.description
    assignment.duration_minutes = data.duration_minutes
    assignment.deadline = deadline
    assignment.original_deadline = deadline  # nothing is published yet: no history to preserve
    _write_questions(db, assignment, data)
    return assignment


def publish(db: Session, assignment: Assignment, now: datetime) -> None:
    """Publish-time checks for a quiz, called by the shared publish path. Notifies the section's students."""
    if _question_count(db, assignment.id) < 1:
        raise AppError("QUIZ_EMPTY", 422, "Add at least one question before publishing the quiz.")
    # Re-validate the stored definition so a quiz can never be published with a broken answer key.
    for q in db.scalars(select(QuizQuestion).where(QuizQuestion.assignment_id == assignment.id)):
        options = db.scalars(select(QuizOption).where(QuizOption.question_id == q.id)).all()
        correct = sum(o.is_correct for o in options)
        valid = len(options) >= 2 and (correct >= 1 if q.question_type == "MULTIPLE_SELECT" else correct == 1)
        if not valid or q.marks < 1:
            raise AppError("QUIZ_INVALID", 422, "A question in this quiz is incomplete.")
    from app.services import assignments as base

    base.require_deadline_lead(assignment.deadline, now)
    assignment.status = AssignmentStatus.PUBLISHED
    assignment.published_at = now
    db.flush()
    for student_id in db.scalars(
        select(StudentProfile.user_id).where(StudentProfile.section_id == assignment.section_id)
    ):
        notifications.notify(
            db,
            user_id=student_id,
            type="QUIZ_PUBLISHED",
            title="New quiz",
            body=f'"{assignment.title}" is open until {fmt(assignment.deadline)}.',
            ref_type="ASSIGNMENT",
            ref_id=assignment.id,
            dedup_key=f"QUIZ_PUBLISHED:{assignment.id}:{student_id}",
        )


# --- Faculty: reads ------------------------------------------------------------------------------------------

def _require_quiz(assignment: Assignment) -> None:
    if assignment.assignment_type != "QUIZ":
        raise _not_found()


def faculty_detail(db: Session, faculty: User, assignment_id: uuid.UUID) -> QuizFacultyDetail:
    from app.services import assignments as base

    assignment = scope.get_faculty_assignment_or_404(db, faculty, assignment_id)
    _require_quiz(assignment)
    return faculty_detail_of(db, assignment, base)


def faculty_detail_of(db: Session, assignment: Assignment, base=None) -> QuizFacultyDetail:
    if base is None:
        from app.services import assignments as base
    subject = db.get(Subject, assignment.subject_id)
    section = db.get(Section, assignment.section_id)
    expected = db.scalar(
        select(func.count()).select_from(StudentProfile).where(StudentProfile.section_id == section.id)
    )
    questions = db.scalars(
        select(QuizQuestion).where(QuizQuestion.assignment_id == assignment.id).order_by(QuizQuestion.position)
    ).all()
    out = []
    for q in questions:
        options = db.scalars(
            select(QuizOption).where(QuizOption.question_id == q.id).order_by(QuizOption.position)
        ).all()
        out.append(
            QuestionFaculty(
                id=q.id,
                question_type=q.question_type,
                text=q.text,
                marks=q.marks,
                options=[OptionFaculty(id=o.id, text=o.text, is_correct=o.is_correct) for o in options],
            )
        )
    return QuizFacultyDetail(
        **base._summary(assignment, subject, section, expected or 0),
        instructions=assignment.instructions,
        description=assignment.description,
        duration_minutes=assignment.duration_minutes,
        question_count=len(out),
        total_marks=sum(q.marks for q in out),
        questions=out,
    )


def participation(db: Session, faculty: User, assignment_id: uuid.UUID) -> QuizParticipation:
    assignment = scope.get_faculty_assignment_or_404(db, faculty, assignment_id)
    _require_quiz(assignment)
    rows = db.execute(
        select(User, QuizAttempt)
        .join(StudentProfile, StudentProfile.user_id == User.id)
        .outerjoin(
            QuizAttempt, (QuizAttempt.student_id == User.id) & (QuizAttempt.assignment_id == assignment.id)
        )
        .where(StudentProfile.section_id == assignment.section_id)
        .order_by(User.login_id)
    ).all()
    participants = [
        QuizParticipant(
            student_id=u.id,
            login_id=u.login_id,
            full_name=u.full_name,
            status=a.status if a else "NOT_STARTED",
            started_at=a.started_at if a else None,
            submitted_at=a.submitted_at if a else None,
            score=a.score if a else None,
            max_score=a.max_score if a else None,
            timed_out=bool(a and a.timed_out),
        )
        for u, a in rows
    ]
    scores = [p.score for p in participants if p.score is not None]
    return QuizParticipation(
        assignment_id=assignment.id,
        total_marks=total_marks(db, assignment.id),
        expected_students=len(participants),
        started=sum(p.status != "NOT_STARTED" for p in participants),
        submitted=sum(p.status == "SUBMITTED" for p in participants),
        average_score=round(sum(scores) / len(scores), 2) if scores else None,
        participants=participants,
    )


# --- Student: attempts -----------------------------------------------------------------------------------------

def expires_at(assignment: Assignment, attempt: QuizAttempt) -> datetime:
    if assignment.duration_minutes is None:
        return assignment.deadline
    return min(assignment.deadline, attempt.started_at + timedelta(minutes=assignment.duration_minutes))


def _get_quiz_for_student(db: Session, student: User, assignment_id: uuid.UUID) -> Assignment:
    assignment = scope.get_student_assignment_or_404(db, student, assignment_id)  # 404 outside my section / draft
    _require_quiz(assignment)
    return assignment


def _questions(db: Session, assignment_id: uuid.UUID) -> list[QuizQuestion]:
    return list(
        db.scalars(
            select(QuizQuestion).where(QuizQuestion.assignment_id == assignment_id).order_by(QuizQuestion.position)
        )
    )


def _options_by_question(db: Session, assignment_id: uuid.UUID) -> dict[uuid.UUID, list[QuizOption]]:
    result: dict[uuid.UUID, list[QuizOption]] = {}
    for o in db.scalars(
        select(QuizOption)
        .join(QuizQuestion, QuizQuestion.id == QuizOption.question_id)
        .where(QuizQuestion.assignment_id == assignment_id)
        .order_by(QuizOption.position)
    ):
        result.setdefault(o.question_id, []).append(o)
    return result


def _selected(db: Session, attempt_id: uuid.UUID) -> dict[uuid.UUID, list[uuid.UUID]]:
    selected: dict[uuid.UUID, list[uuid.UUID]] = {}
    for question_id, option_id in db.execute(
        select(QuizAnswer.question_id, QuizAnswer.option_id).where(QuizAnswer.attempt_id == attempt_id)
    ):
        selected.setdefault(question_id, []).append(option_id)
    return selected


def _grade(db: Session, assignment_id: uuid.UUID, attempt_id: uuid.UUID) -> tuple[int, int]:
    """(score, max score). All-or-nothing per question; the score can never exceed the total."""
    questions = _questions(db, assignment_id)
    options = _options_by_question(db, assignment_id)
    selected = _selected(db, attempt_id)
    score = 0
    for q in questions:
        correct = {o.id for o in options.get(q.id, []) if o.is_correct}
        if correct and set(selected.get(q.id, [])) == correct:
            score += q.marks
    maximum = sum(q.marks for q in questions)
    return min(score, maximum), maximum


def _lock_attempt(db: Session, student: User, attempt_id: uuid.UUID) -> QuizAttempt:
    attempt = db.execute(
        select(QuizAttempt)
        .where(QuizAttempt.id == attempt_id, QuizAttempt.student_id == student.id)  # only my own attempts
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if attempt is None:
        raise _not_found()
    return attempt


def _finalize(db: Session, assignment: Assignment, attempt: QuizAttempt, at: datetime, timed_out: bool) -> None:
    score, maximum = _grade(db, assignment.id, attempt.id)
    attempt.score = score
    attempt.max_score = maximum
    attempt.status = "SUBMITTED"
    attempt.submitted_at = at
    attempt.timed_out = timed_out
    db.flush()


def _close_if_expired(db: Session, assignment: Assignment, attempt: QuizAttempt, now: datetime) -> None:
    if attempt.status == "IN_PROGRESS" and now > expires_at(assignment, attempt):
        _finalize(db, assignment, attempt, expires_at(assignment, attempt), timed_out=True)


def _attempt_state(assignment: Assignment, attempt: QuizAttempt, selected) -> AttemptState:
    return AttemptState(
        id=attempt.id,
        status=attempt.status,
        started_at=attempt.started_at,
        expires_at=expires_at(assignment, attempt),
        submitted_at=attempt.submitted_at,
        timed_out=attempt.timed_out,
        answers=selected if attempt.status == "IN_PROGRESS" else {},
    )


def _my_attempt(db: Session, student: User, assignment_id: uuid.UUID) -> QuizAttempt | None:
    return db.scalar(
        select(QuizAttempt).where(QuizAttempt.assignment_id == assignment_id, QuizAttempt.student_id == student.id)
    )


def student_view(db: Session, student: User, assignment_id: uuid.UUID, now: datetime) -> QuizStudentView:
    assignment = _get_quiz_for_student(db, student, assignment_id)
    attempt = _my_attempt(db, student, assignment.id)
    if attempt is not None:
        attempt = _lock_attempt(db, student, attempt.id)
        _close_if_expired(db, assignment, attempt, now)
    subject = db.get(Subject, assignment.subject_id)
    section = db.get(Section, assignment.section_id)
    faculty_name = db.scalar(
        select(User.full_name)
        .join(TeachingAssignment, TeachingAssignment.faculty_id == User.id)
        .where(
            TeachingAssignment.subject_id == assignment.subject_id,
            TeachingAssignment.section_id == assignment.section_id,
        )
    )
    blocked = None
    if assignment.status == AssignmentStatus.ARCHIVED:
        blocked = "ARCHIVED"
    elif now > assignment.deadline:
        blocked = "DEADLINE_PASSED"
    questions = None
    state = None
    if attempt is not None:
        selected = _selected(db, attempt.id)
        state = _attempt_state(assignment, attempt, selected)
        if attempt.status == "IN_PROGRESS":
            options = _options_by_question(db, assignment.id)
            questions = [
                QuestionStudent(
                    id=q.id,
                    question_type=q.question_type,
                    text=q.text,
                    marks=q.marks,
                    options=[OptionStudent(id=o.id, text=o.text) for o in options.get(q.id, [])],
                )
                for q in _questions(db, assignment.id)
            ]
    return QuizStudentView(
        assignment_id=assignment.id,
        title=assignment.title,
        description=assignment.description,
        instructions=assignment.instructions,
        subject=SubjectOut(id=subject.id, code=subject.code, name=subject.name),
        section=SectionOut(id=section.id, label=section.label, semester=section.semester, name=section.name),
        faculty_name=faculty_name,
        deadline=assignment.deadline,
        duration_minutes=assignment.duration_minutes,
        question_count=_question_count(db, assignment.id),
        total_marks=total_marks(db, assignment.id),
        can_attempt=attempt is None and blocked is None,
        blocked_reason=blocked if attempt is None else None,
        attempt=state,
        questions=questions,
    )


def start_attempt(db: Session, student: User, assignment_id: uuid.UUID, now: datetime) -> QuizStudentView:
    """Begin the single attempt. Repeating the request (retry, refresh) returns the existing attempt."""
    assignment = _get_quiz_for_student(db, student, assignment_id)
    archive_guard.require_active(db, assignment.id)
    if _my_attempt(db, student, assignment.id) is None:
        if now > assignment.deadline:
            raise AppError("DEADLINE_PASSED", 409, "The deadline for this quiz has passed.")
        if _question_count(db, assignment.id) < 1:
            raise AppError("QUIZ_EMPTY", 409, "This quiz has no questions.")
        try:
            with db.begin_nested():
                db.add(
                    QuizAttempt(
                        assignment_id=assignment.id, student_id=student.id, status="IN_PROGRESS", started_at=now
                    )
                )
                db.flush()
        except IntegrityError:  # a concurrent identical request created it first: one attempt per student
            pass
    return student_view(db, student, assignment_id, now)


def _check_answers(db: Session, assignment: Assignment, answers: list[AnswerIn]) -> dict[uuid.UUID, list[uuid.UUID]]:
    """Every question and option id must belong to THIS quiz; the option count must fit the question type."""
    questions = {q.id: q for q in _questions(db, assignment.id)}
    options = _options_by_question(db, assignment.id)
    cleaned: dict[uuid.UUID, list[uuid.UUID]] = {}
    for a in answers:
        q = questions.get(a.question_id)
        if q is None:
            raise AppError("INVALID_ANSWER", 422, "An answer refers to a question that is not part of this quiz.")
        if a.question_id in cleaned:
            raise AppError("INVALID_ANSWER", 422, "A question was answered more than once.")
        valid = {o.id for o in options.get(q.id, [])}
        if len(set(a.option_ids)) != len(a.option_ids) or not set(a.option_ids) <= valid:
            raise AppError("INVALID_ANSWER", 422, "An answer refers to an option that does not belong to its question.")
        if q.question_type != "MULTIPLE_SELECT" and len(a.option_ids) > 1:
            raise AppError("INVALID_ANSWER", 422, "This question accepts only one answer.")
        cleaned[q.id] = list(a.option_ids)
    return cleaned


def _store(db: Session, assignment: Assignment, attempt: QuizAttempt, cleaned: dict[uuid.UUID, list[uuid.UUID]]) -> None:
    for question_id, option_ids in cleaned.items():
        db.execute(
            delete(QuizAnswer).where(QuizAnswer.attempt_id == attempt.id, QuizAnswer.question_id == question_id)
        )
        for option_id in option_ids:
            db.add(
                QuizAnswer(
                    attempt_id=attempt.id,
                    assignment_id=assignment.id,
                    question_id=question_id,
                    option_id=option_id,
                )
            )
    db.flush()


def _attempt_context(db: Session, student: User, attempt_id: uuid.UUID) -> tuple[Assignment, QuizAttempt]:
    attempt = _lock_attempt(db, student, attempt_id)
    assignment = scope.get_student_assignment_or_404(db, student, attempt.assignment_id)
    return assignment, attempt


def save_answers(
    db: Session, student: User, attempt_id: uuid.UUID, answers: list[AnswerIn], now: datetime
) -> AttemptState:
    assignment, attempt = _attempt_context(db, student, attempt_id)
    if attempt.status != "IN_PROGRESS":
        raise AppError("ALREADY_SUBMITTED", 409, "This quiz has already been submitted.")
    if now > expires_at(assignment, attempt):
        raise AppError("QUIZ_TIME_UP", 409, "Time is up for this quiz. Your saved answers will be submitted.")
    archive_guard.require_active(db, assignment.id)
    _store(db, assignment, attempt, _check_answers(db, assignment, answers))
    return _attempt_state(assignment, attempt, _selected(db, attempt.id))


def submit(
    db: Session, student: User, attempt_id: uuid.UUID, answers: list[AnswerIn] | None, now: datetime
) -> QuizResult:
    """Final submission. Idempotent: submitting an already submitted attempt just returns its result."""
    assignment, attempt = _attempt_context(db, student, attempt_id)
    if attempt.status == "IN_PROGRESS":
        if now > expires_at(assignment, attempt):
            _close_if_expired(db, assignment, attempt, now)  # late: only the answers saved before expiry count
        else:
            archive_guard.require_active(db, assignment.id)
            if answers is not None:
                _store(db, assignment, attempt, _check_answers(db, assignment, answers))
            _finalize(db, assignment, attempt, now, timed_out=False)
    return _result(db, assignment, attempt, now)


def result(db: Session, student: User, attempt_id: uuid.UUID, now: datetime) -> QuizResult:
    assignment, attempt = _attempt_context(db, student, attempt_id)
    _close_if_expired(db, assignment, attempt, now)
    if attempt.status != "SUBMITTED":
        raise AppError("NOT_SUBMITTED", 409, "The result is available after the quiz is submitted.")
    return _result(db, assignment, attempt, now)


def _result(db: Session, assignment: Assignment, attempt: QuizAttempt, now: datetime) -> QuizResult:
    released = now > assignment.deadline  # release policy: the answer key appears only after the deadline
    options = _options_by_question(db, assignment.id)
    selected = _selected(db, attempt.id)
    questions = []
    for q in _questions(db, assignment.id):
        opts = options.get(q.id, [])
        correct = {o.id for o in opts if o.is_correct}
        chosen = selected.get(q.id, [])
        questions.append(
            QuestionResult(
                question_id=q.id,
                text=q.text,
                marks=q.marks,
                awarded=q.marks if correct and set(chosen) == correct else 0,
                question_type=q.question_type,
                options=[OptionStudent(id=o.id, text=o.text) for o in opts],
                selected_option_ids=chosen,
                correct_option_ids=[o.id for o in opts if o.is_correct] if released else None,
            )
        )
    return QuizResult(
        attempt_id=attempt.id,
        assignment_id=assignment.id,
        title=assignment.title,
        status="SUBMITTED",
        started_at=attempt.started_at,
        submitted_at=attempt.submitted_at,
        timed_out=attempt.timed_out,
        score=attempt.score,
        max_score=attempt.max_score,
        answers_released=released,
        questions=questions,
    )


# --- Student list support --------------------------------------------------------------------------------------

def student_list_info(db: Session, student_id: uuid.UUID, assignment_ids: list[uuid.UUID]) -> dict[uuid.UUID, dict]:
    """Per quiz id: question count, total marks and the student's own attempt state, in two queries."""
    if not assignment_ids:
        return {}
    info = {
        aid: dict(question_count=n, total_marks=int(marks))
        for aid, n, marks in db.execute(
            select(QuizQuestion.assignment_id, func.count(), func.coalesce(func.sum(QuizQuestion.marks), 0))
            .where(QuizQuestion.assignment_id.in_(assignment_ids))
            .group_by(QuizQuestion.assignment_id)
        )
    }
    attempts = {
        a.assignment_id: a
        for a in db.scalars(
            select(QuizAttempt).where(QuizAttempt.student_id == student_id, QuizAttempt.assignment_id.in_(assignment_ids))
        )
    }
    for aid in assignment_ids:
        row = info.setdefault(aid, dict(question_count=0, total_marks=0))
        attempt = attempts.get(aid)
        row["quiz_status"] = attempt.status if attempt else "NOT_STARTED"
        row["score"] = attempt.score if attempt else None
        row["submitted_at"] = attempt.submitted_at if attempt else None
    return info
