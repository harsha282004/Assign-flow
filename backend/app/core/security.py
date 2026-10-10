"""Password hashing (Argon2 via pwdlib) and HS256 access tokens (PyJWT). No DB or Redis access here."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache

import jwt
from pwdlib import PasswordHash

from app.core.config import Settings

_hasher = PasswordHash.recommended()

JWT_ALGORITHM = "HS256"
MIN_JWT_SECRET_LENGTH = 32


def hash_password(password: str) -> str:
    """Return an Argon2 hash with a fresh random salt."""
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _hasher.verify(password, password_hash)


@lru_cache
def dummy_password_hash() -> str:
    """Valid Argon2 hash verified when the login ID is unknown, so timing does not reveal valid IDs."""
    return hash_password(uuid.uuid4().hex)


def require_jwt_secret(settings: Settings) -> str:
    secret = settings.jwt_secret or ""
    if len(secret) < MIN_JWT_SECRET_LENGTH:
        raise RuntimeError(
            f"JWT_SECRET must be set to at least {MIN_JWT_SECRET_LENGTH} random characters "
            '(generate one with: python -c "import secrets;print(secrets.token_urlsafe(48))")'
        )
    return secret


@dataclass(frozen=True)
class TokenClaims:
    sub: str
    role: str
    jti: str
    iat: int
    exp: int


class TokenError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def create_access_token(
    settings: Settings, user_id: uuid.UUID, role: str, now: datetime
) -> tuple[str, str, datetime]:
    """Return (token, jti, expires_at). Claims: sub, role, jti, iat, exp = iat + JWT_EXPIRE_MINUTES."""
    secret = require_jwt_secret(settings)
    issued = now.astimezone(UTC).replace(microsecond=0)
    expires = issued + timedelta(minutes=settings.jwt_expire_minutes)
    jti = str(uuid.uuid4())
    payload = {
        "sub": str(user_id),
        "role": role,
        "jti": jti,
        "iat": int(issued.timestamp()),
        "exp": int(expires.timestamp()),
    }
    return jwt.encode(payload, secret, algorithm=JWT_ALGORITHM), jti, expires


def decode_access_token(settings: Settings, token: str, now: datetime) -> TokenClaims:
    """Verify signature (HS256 only) and required claims; expiry is checked against the injected clock."""
    secret = require_jwt_secret(settings)
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[JWT_ALGORITHM],
            options={
                "require": ["sub", "jti", "iat", "exp"],
                "verify_exp": False,  # compared with the injectable clock below
                "verify_iat": False,
            },
        )
        claims = TokenClaims(
            sub=str(payload["sub"]),
            role=str(payload.get("role", "")),
            jti=str(payload["jti"]),
            iat=int(payload["iat"]),
            exp=int(payload["exp"]),
        )
    except (jwt.InvalidTokenError, ValueError, TypeError) as exc:
        raise TokenError("INVALID_TOKEN", "The access token is not valid.") from exc
    if claims.exp <= now.timestamp():
        raise TokenError("TOKEN_EXPIRED", "The access token has expired. Please log in again.")
    return claims
