"""Test infrastructure: isolated PostgreSQL databases, Redis DB 1, test bucket (architecture §24.3).

Tests never touch the normal demo database (`POSTGRES_DB`): they create and drop dedicated
databases whose names are checked against an allow-list before any destructive statement.
"""

import os

# API tests must never use the demo Redis database: point the whole process at Redis DB 1 (architecture
# §24.3) *before* anything reads settings. Safe to repeat; a no-op when REDIS_URL is already DB 1.
if os.environ.get("REDIS_URL"):
    os.environ["REDIS_URL"] = os.environ["REDIS_URL"].rsplit("/", 1)[0] + "/1"
# Likewise uploads in tests go to the dedicated test bucket, never the application bucket.
os.environ["S3_BUCKET"] = "assignflow-test"
# The reminder job must never run against a database during tests (tests call it explicitly with a frozen clock).
os.environ["REMINDER_SCHEDULER_ENABLED"] = "false"

import secrets
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.init_db import BACKEND_DIR
from app.db.seeds.runner import run_seed

ALLOWED_TEST_DATABASES = {"assignflow_test", "assignflow_migtest", "assignflow_inittest"}
TEST_DATABASE = "assignflow_test"
TEST_REDIS_DB = 1
TEST_BUCKET = "assignflow-test"


def url_for_database(base_url: str, database: str) -> str:
    return make_url(base_url).set(database=database).render_as_string(hide_password=False)


def redis_url_for_db(base_url: str, db: int) -> str:
    return base_url.rsplit("/", 1)[0] + f"/{db}"


def recreate_database(settings: Settings, name: str) -> str:
    """Drop and create an allow-listed test database; return its URL."""
    assert name in ALLOWED_TEST_DATABASES, f"refusing to recreate non-test database {name!r}"
    assert name != make_url(settings.database_url).database
    admin = create_engine(url_for_database(settings.database_url, "postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    admin.dispose()
    return url_for_database(settings.database_url, name)


def drop_database(settings: Settings, name: str) -> None:
    assert name in ALLOWED_TEST_DATABASES
    admin = create_engine(url_for_database(settings.database_url, "postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    admin.dispose()


def alembic_config(url: str) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return cfg


@pytest.fixture(scope="session")
def settings() -> Settings:
    return get_settings()


@pytest.fixture(scope="session")
def test_password() -> str:
    # Random per run; never printed or committed.
    return secrets.token_urlsafe(16)


@pytest.fixture(scope="session")
def test_engine(settings: Settings) -> Iterator[Engine]:
    """Empty `assignflow_test` database migrated to head with Alembic."""
    url = recreate_database(settings, TEST_DATABASE)
    command.upgrade(alembic_config(url), "head")
    engine = create_engine(url)
    yield engine
    engine.dispose()
    drop_database(settings, TEST_DATABASE)


@pytest.fixture(scope="session")
def seeded_engine(test_engine: Engine, test_password: str) -> Engine:
    with Session(test_engine) as session:
        run_seed(session, test_password)
    return test_engine


@pytest.fixture
def db(test_engine: Engine) -> Iterator[Session]:
    """Session inside an outer transaction that is always rolled back."""
    connection = test_engine.connect()
    outer = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        outer.rollback()
        connection.close()
