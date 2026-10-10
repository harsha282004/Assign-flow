"""Profile / academic mapping for GET /auth/me."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Section,
    StudentProfile,
    Subject,
    TeachingAssignment,
    User,
    UserRole,
)
from app.schemas.auth import (
    MeResponse,
    SectionOut,
    StudentSubjectOut,
    SubjectOut,
    TeachingOut,
)


def _section_out(section: Section) -> SectionOut:
    return SectionOut(id=section.id, label=section.label, semester=section.semester, name=section.name)


def build_me(db: Session, user: User) -> MeResponse:
    me = MeResponse(id=user.id, login_id=user.login_id, full_name=user.full_name, role=user.role.value)

    if user.role == UserRole.STUDENT:
        section = db.scalar(
            select(Section).join(StudentProfile, StudentProfile.section_id == Section.id).where(
                StudentProfile.user_id == user.id
            )
        )
        if section is not None:
            me.section = _section_out(section)
            rows = db.execute(
                select(Subject, User.full_name)
                .outerjoin(
                    TeachingAssignment,
                    (TeachingAssignment.subject_id == Subject.id) & (TeachingAssignment.section_id == section.id),
                )
                .outerjoin(User, User.id == TeachingAssignment.faculty_id)
                .where(Subject.semester == section.semester)
                .order_by(Subject.code)
            ).all()
            me.subjects = [
                StudentSubjectOut(id=s.id, code=s.code, name=s.name, faculty_name=faculty_name) for s, faculty_name in rows
            ]
        else:
            me.subjects = []
    else:
        rows = db.execute(
            select(Subject, Section)
            .join(TeachingAssignment, TeachingAssignment.subject_id == Subject.id)
            .join(Section, Section.id == TeachingAssignment.section_id)
            .where(TeachingAssignment.faculty_id == user.id)
            .order_by(Section.semester, Section.name, Subject.code)
        ).all()
        me.teaching = [
            TeachingOut(subject=SubjectOut(id=s.id, code=s.code, name=s.name), section=_section_out(sec)) for s, sec in rows
        ]
    return me
