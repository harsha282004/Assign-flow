import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

AlertType = Literal["DUE_24H", "DUE_3H", "MISSING", "WINDOW_CLOSING", "WINDOW_EXPIRED"]


class NotificationOut(BaseModel):
    id: uuid.UUID
    type: str
    title: str
    body: str
    ref_type: str | None
    ref_id: uuid.UUID | None
    created_at: datetime
    read_at: datetime | None


class AlertOut(BaseModel):
    """A computed alert (architecture §22): derived from the server clock on every request, never stored."""

    type: AlertType
    assignment_id: uuid.UUID
    assignment_title: str
    message: str
    at: datetime  # the deadline or the window end the alert is about


class UnreadCount(BaseModel):
    unread_count: int


class NotificationsResponse(BaseModel):
    alerts: list[AlertOut]
    items: list[NotificationOut]
    unread_count: int
