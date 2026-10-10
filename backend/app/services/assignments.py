"""Assignment creation, editing, publishing and read models (architecture §6 FR-06/07, §15.4, §20.2)."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.models import (
    Assignment,
    AssignmentStatus,
    DeadlineChange,
    LateRequest,
    Section,
    StudentProfile,
    Subject,
    Submission,
    TeachingAssignment,
    UploadContext,
    User,
)
from app.schemas.assignments import (
    AssignmentCreate,
    AssignmentUpdate,
    DeadlineChangeOut,
    FacultyAssignmentDetail,
    FacultyAssignmentSummary,
    StudentAssignmentDetail,
    StudentAssignmentItem,
)
from app.schemas.auth import SectionOut, SubjectOut
from app.services import (
    attachments,
    late_requests,
    late_windows,
    quiz,
    reviews,
    scope,
    status,
    submissions,
    timeline,
)

MIN_DEADLINE_LEAD = timedelta(minutes=1)  # architecture §15.4


def _utc(value: datetime) -> datetime:
    return value.astimezone(UTC)


def require_deadline_lead(deadline: datetime, now: datetime) -> None:
    """A deadline must be at least 1 minute in the future at create or publish time (§15.4)."""
    if _utc(deadline) < now + MIN_DEADLINE_LEAD:
        raise AppError(
            "DEADLINE_IN_PAST", 422, "The deadline must be at least 1 minute in the future."
        )


def _subject_out(s: Subject) -> SubjectOut:
    return SubjectOut(id=s.id, code=s.code, name=s.name)


def _section_out(s: Section) -> SectionOut:
    return SectionOut(id=s.id, label=s.label, semester=s.semester, name=s.name)


# --- Faculty: commands ---------------------------------------------------------------------------

def create_assignment(db: Session, faculty: User, data: AssignmentCreate, now: datetime) -> Assignment:
    # Only for a subject x section the faculty member teaches (403 NOT_YOUR_CLASS; also covers unknown IDs).
    scope.require_teaching_slot(db, faculty, data.subject_id, data.section_id)
    deadline = _utc(data.deadline)
    require_deadline_lead(deadline, now)
    assignment = Assignment(
        title=data.title,
        instructions=data.instructions,
        subject_id=data.subject_id,
        section_id=data.section_id,
        created_by=faculty.id,
        status=AssignmentStatus.PUBLISHED if data.publish else AssignmentStatus.DRAFT,
        original_deadline=deadline,
        deadline=deadline,
        allowed_types=data.allowed_types,
        max_file_mb=data.max_file_mb,
        published_at=now if data.publish else None,
        created_at=now,  # the server clock (also what the timeline shows), not the database's transaction time
    )
    db.add(assignment)
    db.flush()
    return assignment


def update_draft(db: Session, assignment: Assignment, data: AssignmentUpdate, now: datetime) -> Assignment:
    """Edit a DRAFT. Once published, only the deadline can change (through the deadline endpoint)."""
    if assignment.status != AssignmentStatus.DRAFT:
        raise AppError(
            "NOT_DRAFT",
            409,
            "Only draft assignments can be edited. Use the deadline change for a published assignment.",
        )
    changes = data.model_dump(exclude_unset=True)
    if "deadline" in changes:
        deadline = _utc(changes.pop("deadline"))
        require_deadline_lead(deadline, now)
        # Nothing has been published yet, so there is no history to preserve: the "original" deadline
        # is the one the assignment is published with.
        assignment.deadline = deadline
        assignment.original_deadline = deadline
    for field, value in changes.items():
        setattr(assignment, field, value)
    db.flush()
    return assignment


def publish_assignment(db: Session, assignment: Assignment, now: datetime) -> Assignment:
    if assignment.status == AssignmentStatus.PUBLISHED:
        raise AppError("ALREADY_PUBLISHED", 409, "This assignment is already published.")
    if assignment.assignment_type == "QUIZ":
        quiz.publish(db, assignment, now)  # also checks the questions and notifies the section
        return assignment
    require_deadline_lead(assignment.deadline, now)
    assignment.status = AssignmentStatus.PUBLISHED
    assignment.published_at = now
    db.flush()
    return assignment


# --- Faculty: reads --------------------------------------------------------------------------------

def _expected_students():
    return (
        select(func.count())
        .select_from(StudentProfile)
        .where(StudentProfile.section_id == Assignment.section_id)
        .correlate(Assignment)
        .scalar_subquery()
    )


def _summary(a: Assignment, subject: Subject, section: Section, expected: int) -> dict:
    return dict(
        id=a.id,
        title=a.title,
        assignment_type=a.assignment_type,
        status=a.status.value,
        subject=_subject_out(subject),
        section=_section_out(section),
        original_deadline=a.original_deadline,
        deadline=a.deadline,
        published_at=a.published_at,
        archived_at=a.archived_at,
        created_at=a.created_at,
        expected_students=expected,
    )


def list_faculty_assignments(
    db: Session,
    faculty: User,
    subject_id: uuid.UUID | None = None,
    section_id: uuid.UUID | None = None,
    state: str = "all",
) -> list[FacultyAssignmentSummary]:
    """state: `active` = drafts + published, `archived`, or `all`."""
    scope.require_filter_scope(db, faculty, subject_id, section_id)
    stmt = (
        select(Assignment, Subject, Section, _expected_students())
        .join(Subject, Subject.id == Assignment.subject_id)
        .join(Section, Section.id == Assignment.section_id)
        # Faculty rule (§8.2): created by me AND I teach this subject in this section.
        .join(
            TeachingAssignment,
            (TeachingAssignment.subject_id == Assignment.subject_id)
            & (TeachingAssignment.section_id == Assignment.section_id)
            & (TeachingAssignment.faculty_id == faculty.id),
        )
        .where(Assignment.created_by == faculty.id)
        .order_by(Assignment.created_at.desc())
    )
    if subject_id is not None:
        stmt = stmt.where(Assignment.subject_id == subject_id)
    if section_id is not None:
        stmt = stmt.where(Assignment.section_id == section_id)
    if state == "active":
        stmt = stmt.where(Assignment.status != AssignmentStatus.ARCHIVED)
    elif state == "archived":
        stmt = stmt.where(Assignment.status == AssignmentStatus.ARCHIVED)
    rows = db.execute(stmt).all()
    return [FacultyAssignmentSummary(**_summary(a, sub, sec, n)) for a, sub, sec, n in rows]


def faculty_assignment_detail(db: Session, assignment: Assignment) -> FacultyAssignmentDetail:
    subject = db.get(Subject, assignment.subject_id)
    section = db.get(Section, assignment.section_id)
    expected = db.scalar(
        select(func.count()).select_from(StudentProfile).where(StudentProfile.section_id == section.id)
    )
    history = db.execute(
        select(DeadlineChange, User.full_name)
        .join(User, User.id == DeadlineChange.changed_by)
        .where(DeadlineChange.assignment_id == assignment.id)
        .order_by(DeadlineChange.changed_at, DeadlineChange.id)
    ).all()
    return FacultyAssignmentDetail(
        **_summary(assignment, subject, section, expected or 0),
        instructions=assignment.instructions,
        allowed_types=list(assignment.allowed_types),
        max_file_mb=assignment.max_file_mb,
        deadline_history=[
            DeadlineChangeOut(
                id=c.id,
                old_deadline=c.old_deadline,
                new_deadline=c.new_deadline,
                changed_by_name=name,
                changed_at=c.changed_at,
                reason=c.reason,
            )
            for c, name in history
        ],
        attachments=attachments.list_for_assignment(db, assignment.id),
    )


# --- Students: reads ----------------------------------------------------------------------------------

def _student_item(
    a: Assignment,
    subject: Subject,
    faculty_name,
    info: tuple[datetime, int, UploadContext, uuid.UUID] | None,
    request_state: str | None,
    review,
    now: datetime,
    quiz_info: dict | None = None,
) -> dict:
    first_uploaded_at, latest_version_no, first_context, _ = info if info else (None, 0, None, None)
    extra: dict = {}
    if a.assignment_type == "QUIZ":
        q = quiz_info or {}
        submitted_at = q.get("submitted_at")
        first_uploaded_at = submitted_at  # a submitted attempt is on time (the server refuses late attempts)
        extra = dict(
            assignment_type="QUIZ",
            quiz_status=q.get("quiz_status", "NOT_STARTED"),
            question_count=q.get("question_count", 0),
            total_marks=q.get("total_marks", 0),
            duration_minutes=a.duration_minutes,
            quiz_score=q.get("score"),
        )
    return dict(
        **extra,
        review_status=review.status.value if review else "NOT_REVIEWED",
        latest_feedback=review.feedback if review else None,
        id=a.id,
        title=a.title,
        subject=_subject_out(subject),
        faculty_name=faculty_name,
        published_at=a.published_at,
        deadline=a.deadline,
        timing=status.submission_timing(first_uploaded_at, a.deadline, now).value,
        late_approved=submissions.late_approved_flag(first_context, first_uploaded_at, a.deadline),
        is_resubmitted=status.is_resubmitted(latest_version_no),
        request_status=request_state or "NONE",
        assignment_state="ARCHIVED" if a.status == AssignmentStatus.ARCHIVED else "ACTIVE",
    )


def list_student_assignments(
    db: Session, student: User, now: datetime, archived: bool = False
) -> list[StudentAssignmentItem]:
    """Active work (PUBLISHED). With archived=True: ARCHIVED assignments of my section on which I have my own history."""
    section_id = scope.student_section_id(db, student.id)
    if section_id is None:
        return []
    wanted = AssignmentStatus.ARCHIVED if archived else AssignmentStatus.PUBLISHED
    mine = (
        select(Submission.assignment_id).where(Submission.student_id == student.id)
    ).union(select(LateRequest.assignment_id).where(LateRequest.student_id == student.id))
    rows = db.execute(
        select(Assignment, Subject, User.full_name)
        .join(Subject, Subject.id == Assignment.subject_id)
        .outerjoin(
            TeachingAssignment,
            (TeachingAssignment.subject_id == Assignment.subject_id)
            & (TeachingAssignment.section_id == Assignment.section_id),
        )
        .outerjoin(User, User.id == TeachingAssignment.faculty_id)
        .where(
            Assignment.section_id == section_id,
            Assignment.status == wanted,
            *([Assignment.id.in_(mine)] if archived else []),
        )
        .order_by(Assignment.deadline, Assignment.id)
    ).all()
    ids = [a.id for a, _, _ in rows]
    info = submissions.student_submission_info(db, student.id, ids)
    states = late_windows.student_request_states(db, student.id, ids, now)
    current = reviews.current_reviews(db, [i[3] for i in info.values()])
    quiz_info = quiz.student_list_info(db, student.id, [a.id for a, _, _ in rows if a.assignment_type == "QUIZ"])
    return [
        StudentAssignmentItem(
            **_student_item(
                a,
                sub,
                fn,
                info.get(a.id),
                states.get(a.id),
                current.get(info[a.id][3]) if a.id in info else None,
                now,
                quiz_info.get(a.id),
            )
        )
        for a, sub, fn in rows
    ]


def student_assignment_detail(
    db: Session, student: User, assignment_id: uuid.UUID, now: datetime
) -> StudentAssignmentDetail:
    a = scope.get_student_assignment_or_404(db, student, assignment_id)  # 404 if out of scope / draft
    subject = db.get(Subject, a.subject_id)
    section = db.get(Section, a.section_id)
    faculty_name = db.scalar(
        select(User.full_name)
        .join(TeachingAssignment, TeachingAssignment.faculty_id == User.id)
        .where(TeachingAssignment.subject_id == a.subject_id, TeachingAssignment.section_id == a.section_id)
    )
    info = submissions.student_submission_info(db, student.id, [a.id]).get(a.id)
    view = submissions.student_view(db, student, a, now)
    request = late_windows.get_request(db, a.id, student.id)
    submission = submissions.get_submission(db, a.id, student.id)
    current = reviews.current_reviews(db, [submission.id]).get(submission.id) if submission else None
    item = _student_item(
        a,
        subject,
        faculty_name,
        info,
        late_windows.student_request_states(db, student.id, [a.id], now).get(a.id),
        current,
        now,
    )
    events, why = timeline.build(db, a, student, now)
    return StudentAssignmentDetail(
        **item,
        reviews=reviews.review_outs(db, submission),
        events=events,
        why_this_status=why,
        versions=view["versions"],
        can_upload=view["can_upload"],
        upload_blocked_reason=view["upload_blocked_reason"],
        late_request=late_requests.student_request_out(db, request, now) if request else None,
        can_request_late=a.status == AssignmentStatus.PUBLISHED
        and a.assignment_type == "FILE"
        and late_requests.can_request_late(item["timing"], request),
        instructions=a.instructions,
        allowed_types=list(a.allowed_types),
        max_file_mb=a.max_file_mb,
        original_deadline=a.original_deadline,
        section=_section_out(section),
        attachments=attachments.list_for_assignment(db, a.id),
    )
