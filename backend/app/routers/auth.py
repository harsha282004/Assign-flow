"""Authentication endpoints: login, logout, me (architecture §20.2 #1-#3)."""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Request, Response
from redis import Redis
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import get_now
from app.core.config import Settings
from app.core.deps import (
    AuthContext,
    get_app_settings,
    get_auth_context,
    get_current_user,
    get_db,
    get_redis,
)
from app.core.errors import AppError
from app.core.security import create_access_token, dummy_password_hash, verify_password
from app.db.models import User
from app.schemas.auth import LoginRequest, LoginResponse, MeResponse, UserOut
from app.services import ratelimit, tokens
from app.services.profile import build_me

logger = logging.getLogger("assignflow.auth")
router = APIRouter(prefix="/auth", tags=["auth"])

# One message for every failure cause: unknown ID, wrong password, inactive account, role mismatch.
def _invalid_credentials() -> AppError:
    return AppError("INVALID_CREDENTIALS", 401, "Invalid ID or password.")


@router.post("/login", response_model=LoginResponse)
@ratelimit.limiter.limit(ratelimit.LOGIN_IP_LIMIT)
def login(
    request: Request,  # required by SlowAPI for the per-IP key
    response: Response,
    body: LoginRequest,
    db: Session = Depends(get_db),
    redis: Redis = Depends(get_redis),
    settings: Settings = Depends(get_app_settings),
    now: datetime = Depends(get_now),
) -> LoginResponse:
    login_id = body.login_id.strip().upper()
    role = body.role

    ratelimit.ensure_not_locked_out(redis, role, login_id)

    user = db.scalar(select(User).where(User.login_id == login_id))
    # Always run one Argon2 verification (dummy hash if the ID is unknown) so timing is uniform.
    password_ok = verify_password(
        body.password.get_secret_value(), user.password_hash if user else dummy_password_hash()
    )
    if user is None or not password_ok or not user.is_active or user.role.value != role:
        ratelimit.record_login_failure(redis, role, login_id)
        logger.info("login failed (role=%s)", role)  # never log the ID, password or hashes
        raise _invalid_credentials()

    ratelimit.clear_login_failures(redis, role, login_id)
    token, _jti, expires_at = create_access_token(settings, user.id, user.role.value, now)
    response.headers["Cache-Control"] = "no-store"
    logger.info("login ok user=%s", user.id)
    return LoginResponse(access_token=token, expires_at=expires_at, user=UserOut.model_validate(user))


@router.post("/logout", status_code=204)
def logout(
    ctx: AuthContext = Depends(get_auth_context),
    redis: Redis = Depends(get_redis),
    now: datetime = Depends(get_now),
) -> Response:
    # A Redis failure raises -> 503: we never claim a logout we could not record.
    tokens.revoke_jti(redis, ctx.jti, ctx.expires_at, now)
    return Response(status_code=204)


@router.get("/me", response_model=MeResponse)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> MeResponse:
    return build_me(db, user)
