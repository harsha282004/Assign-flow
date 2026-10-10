"""Password hashing and JWT unit tests (frozen clock, no I/O)."""

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.config import Settings
from app.core.security import (
    TokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    require_jwt_secret,
    verify_password,
)

NOW = datetime(2026, 10, 11, 12, 0, tzinfo=UTC)
SECRET = "s" * 48


@pytest.fixture
def cfg(settings: Settings) -> Settings:
    return settings.model_copy(update={"jwt_secret": SECRET, "jwt_expire_minutes": 120})


def test_password_hash_is_argon2_salted_and_verifies():
    a, b = hash_password("correct horse"), hash_password("correct horse")
    assert a.startswith("$argon2") and a != b
    assert verify_password("correct horse", a)
    assert not verify_password("wrong", a)


def test_token_claims_and_two_hour_expiry(cfg: Settings):
    uid = uuid.uuid4()
    token, jti, expires = create_access_token(cfg, uid, "STUDENT", NOW)
    claims = decode_access_token(cfg, token, NOW)
    assert (claims.sub, claims.role, claims.jti) == (str(uid), "STUDENT", jti)
    assert claims.exp - claims.iat == 7200
    assert expires == NOW + timedelta(hours=2)
    assert uuid.UUID(jti).version == 4


def test_token_expires_exactly_at_exp(cfg: Settings):
    token, _, expires = create_access_token(cfg, uuid.uuid4(), "FACULTY", NOW)
    decode_access_token(cfg, token, expires - timedelta(seconds=1))  # still valid
    with pytest.raises(TokenError) as err:
        decode_access_token(cfg, token, expires)
    assert err.value.code == "TOKEN_EXPIRED"


def test_wrong_secret_garbage_and_missing_claims_are_invalid(cfg: Settings):
    token, _, _ = create_access_token(cfg, uuid.uuid4(), "STUDENT", NOW)
    other = cfg.model_copy(update={"jwt_secret": "o" * 48})
    for bad in (token + "x", "not-a-jwt", ""):
        with pytest.raises(TokenError) as err:
            decode_access_token(cfg, bad, NOW)
        assert err.value.code == "INVALID_TOKEN"
    with pytest.raises(TokenError):
        decode_access_token(other, token, NOW)  # signed with a different secret
    no_jti = jwt.encode({"sub": "x", "iat": 1, "exp": 9999999999}, SECRET, algorithm="HS256")
    with pytest.raises(TokenError):
        decode_access_token(cfg, no_jti, NOW)


def test_alg_none_and_other_algorithms_are_rejected(cfg: Settings):
    payload = {"sub": str(uuid.uuid4()), "role": "FACULTY", "jti": "j", "iat": 1, "exp": 9999999999}
    unsigned = jwt.encode(payload, None, algorithm="none")
    with pytest.raises(TokenError):
        decode_access_token(cfg, unsigned, NOW)
    hs512 = jwt.encode(payload, SECRET, algorithm="HS512")
    with pytest.raises(TokenError):
        decode_access_token(cfg, hs512, NOW)


def test_weak_or_missing_secret_is_refused(settings: Settings):
    for secret in (None, "", "short"):
        with pytest.raises(RuntimeError, match="JWT_SECRET"):
            require_jwt_secret(settings.model_copy(update={"jwt_secret": secret}))
