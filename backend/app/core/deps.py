"""FastAPI dependencies: DB session, Redis, authentication and role guards (architecture §8.2, §12).

Authentication order: signature -> expiry -> Redis denylist -> user loaded from PostgreSQL and active.
The role always comes from the database row; the token's role claim is only a hint.
"""

import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis import Redis
from sqlalchemy.orm import Session

from app.core.clock import get_now
from app.core.config import Settings
from app.core.errors import AppError
from app.core.security import TokenError, decode_access_token
from app.db.models import User, UserRole
from app.db.session import get_sessionmaker
from app.services.tokens import is_revoked

_bearer = HTTPBearer(auto_error=False)


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_redis(request: Request) -> Redis:
    return request.app.state.redis


def get_s3(request: Request):
    """The shared boto3 S3 client (thread-safe, connects lazily)."""
    return request.app.state.s3


def get_db() -> Iterator[Session]:
    """One transaction per request: commit on success, roll back on error (architecture §23)."""
    session = get_sessionmaker()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@dataclass(frozen=True)
class AuthContext:
    user: User
    jti: str
    expires_at: datetime


def _unauthenticated(code: str, message: str) -> AppError:
    return AppError(code, 401, message, headers={"WWW-Authenticate": "Bearer"})


def get_auth_context(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
    redis: Redis = Depends(get_redis),
    settings: Settings = Depends(get_app_settings),
    now: datetime = Depends(get_now),
) -> AuthContext:
    if credentials is None or not credentials.credentials:
        raise _unauthenticated("UNAUTHENTICATED", "Authentication is required.")
    try:
        claims = decode_access_token(settings, credentials.credentials, now)
    except TokenError as exc:
        raise _unauthenticated(exc.code, exc.message) from exc

    # Redis errors propagate to the RedisError handler -> 503 (fail closed).
    if is_revoked(redis, claims.jti):
        raise _unauthenticated("TOKEN_REVOKED", "This session has been logged out. Please log in again.")

    try:
        user_id = uuid.UUID(claims.sub)
    except ValueError as exc:
        raise _unauthenticated("INVALID_TOKEN", "The access token is not valid.") from exc
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise _unauthenticated("INVALID_TOKEN", "The access token is not valid.")

    request.state.user_id = str(user.id)  # for the request log
    return AuthContext(user=user, jti=claims.jti, expires_at=datetime.fromtimestamp(claims.exp, now.tzinfo))


def get_current_user(ctx: AuthContext = Depends(get_auth_context)) -> User:
    return ctx.user


def require_role(*roles: UserRole) -> Callable[..., User]:
    """Route guard: 401 if unauthenticated, 403 if the (database) role is not allowed."""

    def _guard(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise AppError("FORBIDDEN", 403, "You do not have permission to perform this action.")
        return user

    return _guard
