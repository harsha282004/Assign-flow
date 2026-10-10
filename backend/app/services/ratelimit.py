"""Login throttling (architecture §13.3, §19).

* Per-IP: 10 login requests / minute via SlowAPI, stored in Redis.
* Per-ID: 5 failures per (role, login ID) per 10 minutes via direct Redis counters.
"""

from redis import Redis
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import get_settings
from app.core.errors import AppError

LOGIN_IP_LIMIT = "10/minute"
LOGIN_FAIL_LIMIT = 5
LOGIN_FAIL_WINDOW_SECONDS = 600

# Storage is Redis; if Redis is unreachable the limiter raises and the request fails closed (503).
limiter = Limiter(key_func=get_remote_address, storage_uri=get_settings().redis_url)


def _fail_key(role: str, login_id: str) -> str:
    return f"rl:loginfail:{role}:{login_id}"


def ensure_not_locked_out(redis: Redis, role: str, login_id: str) -> None:
    key = _fail_key(role, login_id)
    count = redis.get(key)
    if count is not None and int(count) >= LOGIN_FAIL_LIMIT:
        retry_after = max(1, int(redis.ttl(key)))
        raise AppError(
            "RATE_LIMITED",
            429,
            "Too many failed login attempts. Please try again later.",
            headers={"Retry-After": str(retry_after)},
        )


def record_login_failure(redis: Redis, role: str, login_id: str) -> None:
    key = _fail_key(role, login_id)
    pipe = redis.pipeline()
    pipe.incr(key)
    pipe.expire(key, LOGIN_FAIL_WINDOW_SECONDS, nx=True)  # TTL starts at the first failure
    pipe.execute()


def clear_login_failures(redis: Redis, role: str, login_id: str) -> None:
    redis.delete(_fail_key(role, login_id))
