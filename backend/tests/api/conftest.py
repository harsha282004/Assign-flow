"""API test fixtures: the real app wired to the isolated test database and Redis DB 1."""

from collections.abc import Callable, Iterator
from dataclasses import dataclass

import pytest
import redis
from fastapi import APIRouter, Depends
from fastapi.testclient import TestClient
from sqlalchemy import Engine, delete, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.clock import get_clock, get_now
from app.core.deps import get_db, require_role
from app.core.security import hash_password
from app.db.models import User, UserRole
from app.services.storage import ensure_bucket, make_s3_client

UNASSIGNED_FACULTY = "QAFAC01"


@pytest.fixture(scope="session")
def api_app(seeded_engine: Engine, test_password: str):
    from app.main import app  # imported late so conftest's REDIS_URL override is in effect

    factory = sessionmaker(bind=seeded_engine, expire_on_commit=False)

    # A faculty account with NO teaching classes (the configured dataset gives all 15 faculty a class). It exists
    # only in this isolated test database and lets the scope tests prove that a teacher without classes sees nothing.
    with factory() as session:
        if session.scalar(select(User.id).where(User.login_id == UNASSIGNED_FACULTY)) is None:
            session.add(
                User(
                    login_id=UNASSIGNED_FACULTY,
                    full_name="Test Faculty Without Classes",
                    role=UserRole.FACULTY,
                    password_hash=hash_password(test_password),
                )
            )
            session.commit()

    def _get_db() -> Iterator[Session]:
        session = factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    app.dependency_overrides[get_db] = _get_db

    # Test-only routes to exercise the role guards (no real feature routes exist yet).
    router = APIRouter(prefix="/_test")

    @router.get("/faculty-only")
    def faculty_only(user: User = Depends(require_role(UserRole.FACULTY))):
        return {"login_id": user.login_id}

    @router.get("/student-only")
    def student_only(user: User = Depends(require_role(UserRole.STUDENT))):
        return {"login_id": user.login_id}

    app.include_router(router)
    yield app
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def clean_redis(settings) -> Iterator[None]:
    """Start every API test with an empty Redis DB 1 (rate limits, denylist)."""
    assert settings.redis_url.endswith("/1"), "API tests must run against Redis DB 1"
    client = redis.Redis.from_url(settings.redis_url)
    client.flushdb()
    yield
    client.flushdb()
    client.close()


@pytest.fixture(scope="session")
def s3_client(settings):
    assert settings.s3_bucket == "assignflow-test", "API tests must use the test bucket"
    client = make_s3_client(settings)
    ensure_bucket(client, settings.s3_bucket)
    return client


def _empty_bucket(client, bucket: str) -> None:
    for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket):
        for obj in page.get("Contents", []):
            client.delete_object(Bucket=bucket, Key=obj["Key"])


@pytest.fixture(autouse=True)
def clean_data(seeded_engine: Engine, s3_client, settings) -> Iterator[None]:
    """Everything created through the API is committed to the test database / test bucket: remove it afterwards."""
    ensure_bucket(s3_client, settings.s3_bucket)  # tests/db/test_init may have recreated it
    _empty_bucket(s3_client, settings.s3_bucket)
    yield
    with Session(seeded_engine) as session:
        for table in (
            "notifications",
            "reviews",
            "submission_versions",
            "late_requests",
            "submissions",
            "deadline_changes",
            "assignment_attachments",
            "assignment_state_changes",
            "quiz_answers",
            "quiz_attempts",
            "quiz_options",
            "quiz_questions",
            "assignments",
        ):
            session.execute(text(f"DELETE FROM {table}"))
        session.commit()
    _empty_bucket(s3_client, settings.s3_bucket)


@pytest.fixture
def redis_client(settings) -> Iterator[redis.Redis]:
    client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    yield client
    client.close()


@pytest.fixture
def client(api_app) -> Iterator[TestClient]:
    with TestClient(api_app, raise_server_exceptions=False) as c:
        yield c
    api_app.dependency_overrides.pop(get_now, None)
    api_app.dependency_overrides.pop(get_clock, None)


@pytest.fixture
def freeze_time(api_app) -> Callable:
    def _freeze(moment):
        api_app.dependency_overrides[get_now] = lambda: moment
        api_app.dependency_overrides[get_clock] = lambda: (lambda: moment)

    return _freeze


@dataclass
class Account:
    login_id: str
    password: str
    id: object


@pytest.fixture
def make_account(seeded_engine: Engine) -> Iterator[Callable[..., Account]]:
    """Create throw-away committed accounts (e.g. inactive users) and delete them afterwards."""
    created: list[object] = []

    def _make(login_id: str, role: UserRole, password: str, is_active: bool = True) -> Account:
        with Session(seeded_engine) as session:
            user = User(
                login_id=login_id,
                full_name="Temp Account",
                role=role,
                password_hash=hash_password(password),
                is_active=is_active,
            )
            session.add(user)
            session.commit()
            created.append(user.id)
            return Account(login_id=login_id, password=password, id=user.id)

    yield _make
    with Session(seeded_engine) as session:
        session.execute(delete(User).where(User.id.in_(created)))
        session.commit()


@pytest.fixture
def set_active(seeded_engine: Engine):
    def _set(login_id: str, active: bool) -> None:
        with Session(seeded_engine) as session:
            user = session.scalar(select(User).where(User.login_id == login_id))
            user.is_active = active
            session.commit()

    return _set
