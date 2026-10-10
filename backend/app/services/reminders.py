"""24-hour deadline reminders (stored notifications, created by a background job; never by the browser).

Rules (documented in docs/IMPLEMENTATION_LOG.md):
  * Eligible assignment: PUBLISHED (drafts and archived ones never remind) whose CURRENT deadline is between
    22 and 24 hours away. The 2 h catch-up window makes a restart or a missed tick harmless without sending
    "late" reminders; an assignment published with less than 22 h left gets no 24 h reminder.
  * Recipients: every student of the assignment's section, except those who already completed it: a file assignment
    with at least one uploaded version, a quiz with a submitted attempt.
  * Exactly once per effective deadline: the dedup key contains the assignment, the deadline instant and the student,
    and the insert is ON CONFLICT DO NOTHING. Repeated runs, several backend instances and restarts therefore cannot
    duplicate it; a deadline change makes the old key obsolete (no reminder for the old deadline) and, when the new
    deadline is later, earns one reminder for the new deadline.
  * One run at a time across instances (transaction-scoped PostgreSQL advisory lock).
  * Times are compared and stored in UTC; the text shows the deadline in IST.
"""

import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.clock import now_utc
from app.db.models import (
    Assignment,
    AssignmentStatus,
    QuizAttempt,
    Section,
    StudentProfile,
    Subject,
    Submission,
    SubmissionVersion,
)
from app.db.session import get_sessionmaker
from app.services import notifications
from app.services.timeline import fmt

logger = logging.getLogger("assignflow.reminders")

LEAD = timedelta(hours=24)
CATCH_UP = timedelta(hours=2)
TICK_SECONDS = 60
ADVISORY_LOCK_KEY = 7_240_024  # arbitrary constant shared by every instance


def _done_student_ids(db: Session, a: Assignment) -> set:
    if a.assignment_type == "QUIZ":
        return set(
            db.scalars(
                select(QuizAttempt.student_id).where(
                    QuizAttempt.assignment_id == a.id, QuizAttempt.status == "SUBMITTED"
                )
            )
        )
    return set(
        db.scalars(
            select(Submission.student_id)
            .join(SubmissionVersion, SubmissionVersion.submission_id == Submission.id)
            .where(Submission.assignment_id == a.id)
            .distinct()
        )
    )


def send_due_reminders(db: Session, now: datetime) -> int:
    """Create every reminder that is due at `now`. Returns the number of notifications inserted. Commits."""
    if not db.scalar(text("SELECT pg_try_advisory_xact_lock(:k)"), {"k": ADVISORY_LOCK_KEY}):
        db.rollback()
        return 0  # another instance is running the job
    created = 0
    due = db.scalars(
        select(Assignment).where(
            Assignment.status == AssignmentStatus.PUBLISHED,
            Assignment.deadline > now + LEAD - CATCH_UP,
            Assignment.deadline <= now + LEAD,
        )
    ).all()
    for a in due:
        subject = db.get(Subject, a.subject_id)
        section = db.get(Section, a.section_id)
        done = _done_student_ids(db, a)
        stamp = int(a.deadline.timestamp())
        body = (
            f'"{a.title}" ({subject.code} {subject.name} — {section.label}) is due on {fmt(a.deadline)}. '
            "Please submit on time."
        )
        for student_id in db.scalars(select(StudentProfile.user_id).where(StudentProfile.section_id == a.section_id)):
            if student_id in done:
                continue
            if notifications.notify(
                db,
                user_id=student_id,
                type="DEADLINE_REMINDER_24H",
                title="Assignment due in 24 hours",
                body=body,
                ref_type="ASSIGNMENT",
                ref_id=a.id,
                dedup_key=f"REMINDER_24H:{a.id}:{stamp}:{student_id}",
            ):
                created += 1
    db.commit()
    return created


def run_once() -> int:
    with get_sessionmaker()() as db:
        return send_due_reminders(db, now_utc())


async def scheduler_loop() -> None:
    """Background task started with the application: one pass per minute, failures are logged and retried."""
    while True:
        try:
            created = await asyncio.to_thread(run_once)
            if created:
                logger.info("deadline reminders created: %d", created)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("deadline reminder run failed; will retry")
        await asyncio.sleep(TICK_SECONDS)
