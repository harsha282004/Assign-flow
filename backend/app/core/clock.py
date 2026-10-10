"""The only source of "now" (architecture §12). Tests override the `get_now` dependency."""

from datetime import UTC, datetime


def now_utc() -> datetime:
    return datetime.now(UTC)


def get_now() -> datetime:
    """FastAPI dependency; override via app.dependency_overrides[get_now] to freeze time."""
    return now_utc()


def get_clock():
    """Dependency returning the clock function itself, for code that must read "now" *later* in the
    request (the upload pipeline captures `received_at` after the file is received and validated)."""
    return now_utc
