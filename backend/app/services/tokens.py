"""Redis-backed JWT revocation (denylist keyed by jti, TTL = remaining token lifetime)."""

from datetime import datetime

from redis import Redis


def _key(jti: str) -> str:
    return f"deny:jti:{jti}"


def revoke_jti(redis: Redis, jti: str, expires_at: datetime, now: datetime) -> None:
    ttl = max(1, int(expires_at.timestamp() - now.timestamp()))
    redis.set(_key(jti), "1", ex=ttl)


def is_revoked(redis: Redis, jti: str) -> bool:
    return bool(redis.exists(_key(jti)))
