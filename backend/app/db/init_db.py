"""Initializer: wait -> advisory lock -> migrate -> seed -> bucket (architecture §10.3).

Run as `python -m app.db.init_db`. Exits non-zero with a clear message on any failure.
"""

import logging
import sys
import time
from collections.abc import Callable
from pathlib import Path

import psycopg
import redis
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from app.core.config import Settings, get_settings
from app.db.models import UserRole
from app.db.seeds.runner import DatasetMismatch, count_users, run_seed
from app.db.session import get_sessionmaker, make_engine
from app.services.storage import assert_bucket_private, ensure_bucket, make_s3_client

logger = logging.getLogger("assignflow.init")

ADVISORY_LOCK_KEY = 7_300_073  # arbitrary constant shared by every starter
BACKEND_DIR = Path(__file__).resolve().parents[2]


class InitError(RuntimeError):
    pass


def _validate_settings(settings: Settings) -> None:
    missing = [
        name
        for name, value in {
            "S3_ACCESS_KEY": settings.s3_access_key,
            "S3_SECRET_KEY": settings.s3_secret_key,
            "SEED_DEMO_PASSWORD": settings.seed_demo_password,
        }.items()
        if not value
    ]
    if missing:
        raise InitError("Missing required environment variables: " + ", ".join(missing))


def _wait(name: str, check: Callable[[], None], settings: Settings) -> None:
    deadline = time.monotonic() + settings.init_wait_timeout_seconds
    attempt = 0
    while True:
        attempt += 1
        try:
            check()
            logger.info("%s is ready (attempt %d)", name, attempt)
            return
        except Exception as exc:  # noqa: BLE001
            if time.monotonic() >= deadline:
                raise InitError(
                    f"{name} not ready after {settings.init_wait_timeout_seconds:.0f}s "
                    f"({type(exc).__name__})"
                ) from exc
            logger.info("waiting for %s (attempt %d, %s)", name, attempt, type(exc).__name__)
            time.sleep(settings.init_wait_interval_seconds)


def _check_db(settings: Settings) -> None:
    dsn = settings.database_url.replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(dsn, connect_timeout=3) as conn:
        conn.execute("SELECT 1")


def _check_redis(settings: Settings) -> None:
    client = redis.Redis.from_url(settings.redis_url, socket_connect_timeout=3, socket_timeout=3)
    try:
        client.ping()
    finally:
        client.close()


def _check_storage(settings: Settings) -> None:
    make_s3_client(settings).list_buckets()


def _alembic_upgrade(settings: Settings) -> None:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
    command.upgrade(cfg, "head")


def run_init(settings: Settings) -> None:
    """Full initialisation against the given settings (also used by tests with isolated resources)."""
    _validate_settings(settings)
    _wait("PostgreSQL", lambda: _check_db(settings), settings)
    _wait("Redis", lambda: _check_redis(settings), settings)
    _wait("MinIO", lambda: _check_storage(settings), settings)

    engine = make_engine(settings.database_url)
    lock_conn = engine.connect()
    try:
        # Session-level advisory lock: serialises migrations/seeding across concurrent starters.
        lock_conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": ADVISORY_LOCK_KEY})
        lock_conn.commit()
        try:
            logger.info("running migrations (alembic upgrade head)")
            _alembic_upgrade(settings)

            try:
                with get_sessionmaker(engine)() as session:
                    run_seed(session, settings.seed_demo_password or "")
                    faculty = count_users(session, UserRole.FACULTY)
                    students = count_users(session, UserRole.STUDENT)
                logger.info("seed complete: %d faculty, %d students", faculty, students)
            except DatasetMismatch as exc:
                # The database holds another dataset (for example the original 50/200). Nothing was inserted or
                # deleted. Restarting cannot fix that, so do not crash-loop: keep serving the existing data and
                # tell the operator clearly. The dataset changes only through `transition_dataset --apply`.
                logger.warning("DATASET TRANSITION PENDING - seeding skipped, database left as it is: %s", exc)

            client = make_s3_client(settings)
            created = ensure_bucket(client, settings.s3_bucket)
            assert_bucket_private(client, settings.s3_bucket)
            logger.info(
                "bucket '%s' %s and is private",
                settings.s3_bucket,
                "created" if created else "already exists",
            )
        finally:
            lock_conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": ADVISORY_LOCK_KEY})
            lock_conn.commit()
    finally:
        lock_conn.close()
        engine.dispose()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logging.getLogger("botocore").setLevel(logging.WARNING)
    try:
        run_init(get_settings())
    except Exception as exc:  # noqa: BLE001
        logger.error("initialization FAILED: %s: %s", type(exc).__name__, exc)
        return 1
    logger.info("initialization complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
