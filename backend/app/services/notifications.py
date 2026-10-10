"""Stored event notifications (architecture §22). Insert-only except `read_at`.

Every notification carries a deterministic `dedup_key` (UNIQUE) and is inserted with ON CONFLICT DO NOTHING, in the
same transaction as the event that causes it. A retried action therefore never produces a second notification.
Recipients own their notifications: nobody can list or mark another user's.
"""

import uuid
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.models import Notification, User
from app.schemas.notifications import AlertOut, NotificationOut, NotificationsResponse
from app.services import alerts

LIST_LIMIT = 50


def notify(
    db: Session,
    *,
    user_id: uuid.UUID,
    type: str,
    title: str,
    body: str,
    ref_type: str | None,
    ref_id: uuid.UUID | None,
    dedup_key: str,
) -> bool:
    """Insert one notification unless the same event already produced it. Returns True when a row was added."""
    inserted = db.execute(
        insert(Notification)
        .values(
            user_id=user_id,
            type=type,
            title=title[:200],
            body=body[:1000],
            ref_type=ref_type,
            ref_id=ref_id,
            dedup_key=dedup_key,
        )
        .on_conflict_do_nothing(index_elements=["dedup_key"])
        .returning(Notification.id)
    ).scalar_one_or_none()
    return inserted is not None


def list_for_user(db: Session, user: User, now: datetime) -> NotificationsResponse:
    rows = db.scalars(
        select(Notification)
        .where(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(LIST_LIMIT)
    ).all()
    unread = db.scalar(
        select(func.count()).select_from(Notification).where(Notification.user_id == user.id, Notification.read_at.is_(None))
    )
    return NotificationsResponse(
        alerts=[AlertOut(**a) for a in alerts.compute(db, user, now)],
        items=[
            NotificationOut(
                id=n.id,
                type=n.type,
                title=n.title,
                body=n.body,
                ref_type=n.ref_type,
                ref_id=n.ref_id,
                created_at=n.created_at,
                read_at=n.read_at,
            )
            for n in rows
        ],
        unread_count=unread or 0,
    )


def unread_count(db: Session, user: User) -> int:
    """One COUNT query over the caller's own unread rows (cheap enough to poll)."""
    return (
        db.scalar(
            select(func.count()).select_from(Notification).where(Notification.user_id == user.id, Notification.read_at.is_(None))
        )
        or 0
    )


def mark_all_read(db: Session, user: User, now: datetime) -> int:
    """Mark every unread notification of the caller (and only the caller) as read. Returns how many changed."""
    changed = db.execute(
        update(Notification)
        .where(Notification.user_id == user.id, Notification.read_at.is_(None))
        .values(read_at=now)
    ).rowcount
    db.commit()
    return changed


def mark_read(db: Session, user: User, notification_id: uuid.UUID, now: datetime) -> None:
    """404 unless the notification is the caller's own. Marking twice is harmless (the first time is kept)."""
    owned = db.scalar(
        select(Notification.id).where(Notification.id == notification_id, Notification.user_id == user.id)
    )
    if owned is None:
        raise AppError("NOT_FOUND", 404, "The requested resource was not found.")
    db.execute(
        update(Notification)
        .where(
            Notification.id == notification_id,
            Notification.user_id == user.id,
            Notification.read_at.is_(None),
        )
        .values(read_at=now)
    )
    db.commit()
