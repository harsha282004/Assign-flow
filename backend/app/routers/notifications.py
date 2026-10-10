"""Notifications (architecture §20.2 #20-#21): computed alerts + stored items + unread count, mark-as-read (own only)."""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.core.clock import get_now
from app.core.deps import get_current_user, get_db
from app.db.models import User
from app.schemas.notifications import NotificationsResponse, UnreadCount
from app.services import notifications

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=NotificationsResponse)
def list_notifications(
    user: User = Depends(get_current_user), db: Session = Depends(get_db), now: datetime = Depends(get_now)
):
    return notifications.list_for_user(db, user, now)


@router.get("/unread-count", response_model=UnreadCount)
def unread_count(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Only the number of my unread notifications (the bell badge polls this instead of the whole list)."""
    return UnreadCount(unread_count=notifications.unread_count(db, user))


@router.post("/read-all", status_code=204)
def mark_all_read(
    user: User = Depends(get_current_user), db: Session = Depends(get_db), now: datetime = Depends(get_now)
):
    notifications.mark_all_read(db, user, now)
    return Response(status_code=204)


@router.post("/{notification_id}/read", status_code=204)
def mark_read(
    notification_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
):
    notifications.mark_read(db, user, notification_id, now)
    return Response(status_code=204)
