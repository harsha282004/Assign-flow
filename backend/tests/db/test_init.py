"""Initializer and MinIO bucket tests, run against isolated resources (test DB, Redis DB 1, test bucket)."""

import uuid

import httpx
import pytest
from botocore.exceptions import ClientError
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.init_db import InitError, run_init
from app.db.models import TeachingAssignment, User, UserRole
from app.services.storage import assert_bucket_private, ensure_bucket, make_s3_client
from tests.conftest import (
    TEST_BUCKET,
    TEST_REDIS_DB,
    drop_database,
    recreate_database,
    redis_url_for_db,
)


@pytest.fixture
def s3(settings: Settings):
    return make_s3_client(settings)


@pytest.fixture
def scratch_bucket(s3):
    name = f"assignflow-test-{uuid.uuid4().hex[:10]}"
    yield name
    try:
        for obj in s3.list_objects_v2(Bucket=name).get("Contents", []):
            s3.delete_object(Bucket=name, Key=obj["Key"])
        s3.delete_bucket(Bucket=name)
    except ClientError:
        pass


def test_bucket_is_created_when_absent_and_left_alone_when_present(s3, scratch_bucket):
    assert ensure_bucket(s3, scratch_bucket) is True
    assert ensure_bucket(s3, scratch_bucket) is False  # restart-safe
    s3.head_bucket(Bucket=scratch_bucket)


def test_bucket_is_private(settings: Settings, s3, scratch_bucket):
    ensure_bucket(s3, scratch_bucket)
    assert_bucket_private(s3, scratch_bucket)  # no policy, no public ACL grant
    s3.put_object(Bucket=scratch_bucket, Key="probe.txt", Body=b"secret")
    base = settings.s3_endpoint_url.rstrip("/")
    assert httpx.get(f"{base}/{scratch_bucket}/probe.txt", timeout=5).status_code in (401, 403)
    assert httpx.get(f"{base}/{scratch_bucket}/", timeout=5).status_code in (401, 403)


def test_s3_supports_operations_needed_for_uploads(s3, scratch_bucket):
    ensure_bucket(s3, scratch_bucket)
    key = "submissions/a/b/test.bin"
    s3.put_object(Bucket=scratch_bucket, Key=key, Body=b"payload", ContentType="application/octet-stream")
    assert s3.head_object(Bucket=scratch_bucket, Key=key)["ContentLength"] == 7
    assert s3.get_object(Bucket=scratch_bucket, Key=key)["Body"].read() == b"payload"
    s3.delete_object(Bucket=scratch_bucket, Key=key)
    with pytest.raises(ClientError):
        s3.head_object(Bucket=scratch_bucket, Key=key)


def _init_settings(settings: Settings, database_url: str, password: str) -> Settings:
    return settings.model_copy(
        update={
            "database_url": database_url,
            "redis_url": redis_url_for_db(settings.redis_url, TEST_REDIS_DB),
            "s3_bucket": TEST_BUCKET,
            "seed_demo_password": password,
            "init_wait_interval_seconds": 0.2,
            "init_wait_timeout_seconds": 5.0,
        }
    )


def test_full_initialization_is_idempotent(settings: Settings, test_password: str, s3):
    url = recreate_database(settings, "assignflow_inittest")
    try:
        # Start from "bucket absent" to prove creation, then run init twice.
        try:
            for obj in s3.list_objects_v2(Bucket=TEST_BUCKET).get("Contents", []):
                s3.delete_object(Bucket=TEST_BUCKET, Key=obj["Key"])
            s3.delete_bucket(Bucket=TEST_BUCKET)
        except ClientError:
            pass
        init_settings = _init_settings(settings, url, test_password)

        run_init(init_settings)
        s3.head_bucket(Bucket=TEST_BUCKET)
        assert_bucket_private(s3, TEST_BUCKET)

        engine = create_engine(url)
        with Session(engine) as session:
            first_hashes = dict(session.execute(select(User.login_id, User.password_hash)).all())
            teaching_before = session.scalar(select(func.count()).select_from(TeachingAssignment))
        assert len(first_hashes) == 65 and teaching_before == 18

        run_init(init_settings)  # second start: bucket exists, rows exist
        with Session(engine) as session:
            second_hashes = dict(session.execute(select(User.login_id, User.password_hash)).all())
            faculty = session.scalar(select(func.count()).select_from(User).where(User.role == UserRole.FACULTY))
            students = session.scalar(select(func.count()).select_from(User).where(User.role == UserRole.STUDENT))
            teaching_after = session.scalar(select(func.count()).select_from(TeachingAssignment))
        engine.dispose()
        assert second_hashes == first_hashes
        assert (faculty, students, teaching_after) == (15, 50, 18)
    finally:
        drop_database(settings, "assignflow_inittest")


def test_init_does_not_crash_loop_when_a_dataset_transition_is_pending(settings: Settings, test_password: str, s3):
    """A database with another dataset (e.g. the original 50/200) is left exactly as it is and startup completes."""
    from sqlalchemy import text

    from app.core.security import hash_password

    url = recreate_database(settings, "assignflow_inittest")
    try:
        init_settings = _init_settings(settings, url, test_password)
        run_init(init_settings)  # fresh: seeds the configured dataset
        engine = create_engine(url)
        with Session(engine) as session:
            session.execute(
                text(
                    "INSERT INTO users (login_id, full_name, role, password_hash) "
                    "VALUES ('FAC050', 'Legacy', 'FACULTY', :h)"
                ),
                {"h": hash_password(test_password)},
            )
            session.commit()
            before = session.scalar(select(func.count()).select_from(User))
        run_init(init_settings)  # must NOT raise: warns, skips seeding, keeps serving
        with Session(engine) as session:
            assert session.scalar(select(func.count()).select_from(User)) == before  # nothing inserted or deleted
        engine.dispose()
    finally:
        drop_database(settings, "assignflow_inittest")


def test_init_fails_clearly_without_seed_password(settings: Settings):
    bad = settings.model_copy(update={"seed_demo_password": None})
    with pytest.raises(InitError, match="SEED_DEMO_PASSWORD"):
        run_init(bad)


def test_init_times_out_with_clear_error_when_dependency_is_unreachable(settings: Settings, test_password: str):
    bad = settings.model_copy(
        update={
            "seed_demo_password": test_password,
            "redis_url": "redis://127.0.0.1:1/1",
            "init_wait_interval_seconds": 0.1,
            "init_wait_timeout_seconds": 0.5,
        }
    )
    with pytest.raises(InitError, match="Redis not ready"):
        run_init(bad)
