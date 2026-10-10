"""Alembic migration tests on an empty, dedicated database."""

from collections.abc import Iterator

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

import app.db.models  # noqa: F401
from app.core.config import Settings
from app.db.base import Base
from tests.conftest import alembic_config, drop_database, recreate_database

EXPECTED_TABLES = {
    "users",
    "sections",
    "subjects",
    "student_profiles",
    "teaching_assignments",
    "assignments",
    "deadline_changes",
    "submissions",
    "submission_versions",
    "late_requests",
    "reviews",
    "notifications",
    "assignment_attachments",
    "assignment_state_changes",
    "quiz_questions",
    "quiz_options",
    "quiz_attempts",
    "quiz_answers",
}
EXPECTED_ENUMS = {
    "user_role",
    "assignment_status",
    "upload_context",
    "late_request_status",
    "review_status",
}


@pytest.fixture
def empty_db(settings: Settings) -> Iterator[tuple[str, Engine]]:
    url = recreate_database(settings, "assignflow_migtest")
    engine = create_engine(url)
    yield url, engine
    engine.dispose()
    drop_database(settings, "assignflow_migtest")


def _enums(engine: Engine) -> set[str]:
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT typname FROM pg_type WHERE typtype = 'e'"))
        return {r[0] for r in rows}


def test_migration_applies_to_empty_database_and_creates_all_tables(empty_db):
    url, engine = empty_db
    assert inspect(engine).get_table_names() == []
    command.upgrade(alembic_config(url), "head")
    tables = set(inspect(engine).get_table_names())
    assert EXPECTED_TABLES <= tables
    assert tables - EXPECTED_TABLES == {"alembic_version"}
    assert _enums(engine) == EXPECTED_ENUMS


def test_migration_matches_models(empty_db):
    url, engine = empty_db
    command.upgrade(alembic_config(url), "head")
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == []


def test_all_foreign_keys_are_on_delete_restrict(empty_db):
    url, engine = empty_db
    command.upgrade(alembic_config(url), "head")
    with engine.connect() as conn:
        actions = {r[0] for r in conn.execute(text("SELECT confdeltype FROM pg_constraint WHERE contype = 'f'"))}
        count = conn.execute(text("SELECT count(*) FROM pg_constraint WHERE contype = 'f'")).scalar()
    assert actions == {"r"}  # 'r' = RESTRICT
    assert count > 0


def test_expected_indexes_exist(empty_db):
    url, engine = empty_db
    command.upgrade(alembic_config(url), "head")
    with engine.connect() as conn:
        names = {r[0] for r in conn.execute(text("SELECT indexname FROM pg_indexes WHERE schemaname = 'public'"))}
    for expected in (
        "ix_student_profiles_section_id",
        "ix_teaching_assignments_faculty_id",
        "ix_assignments_section_status",
        "ix_assignments_created_by",
        "ix_deadline_changes_assignment_changed",
        "ix_late_requests_assignment_status",
        "ix_reviews_submission_reviewed_desc",
        "ix_notifications_user_read_created",
    ):
        assert expected in names


def test_downgrade_is_coherent_and_upgrade_repeatable(empty_db):
    url, engine = empty_db
    cfg = alembic_config(url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    assert set(inspect(engine).get_table_names()) <= {"alembic_version"}
    assert _enums(engine) == set()
    command.upgrade(cfg, "head")
    assert EXPECTED_TABLES <= set(inspect(engine).get_table_names())


def test_0003_upgrade_keeps_data_and_downgrade_refuses_while_an_assignment_is_archived(empty_db):
    """The ARCHIVED migration is additive; going back is refused (nothing changed) while an archived assignment exists."""
    url, engine = empty_db
    cfg = alembic_config(url)
    command.upgrade(cfg, "0002")
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO sections (semester, name, label) VALUES (5, 'A', 'CSE-5A')"))
        conn.execute(text("INSERT INTO subjects (code, name, semester) VALUES ('CS503', 'Database Systems', 5)"))
        conn.execute(text("INSERT INTO users (login_id, full_name, role, password_hash) VALUES ('FAC001', 'T', 'FACULTY', 'x')"))
        conn.execute(
            text(
                "INSERT INTO assignments (title, instructions, subject_id, section_id, created_by, status, original_deadline, "
                "deadline, allowed_types, max_file_mb) SELECT 'Existing', 'i', su.id, se.id, u.id, 'PUBLISHED', now(), now(), "
                "ARRAY['pdf'], 5 FROM subjects su, sections se, users u"
            )
        )
    command.upgrade(cfg, "head")  # an existing published assignment survives untouched
    with engine.begin() as conn:
        assert conn.execute(text("SELECT status::text, archived_at FROM assignments")).one() == ("PUBLISHED", None)
        conn.execute(text("UPDATE assignments SET status = 'ARCHIVED', archived_at = now()"))
        # the CHECK ties the status to archived_at
        with pytest.raises(IntegrityError):
            with conn.begin_nested():
                conn.execute(text("UPDATE assignments SET archived_at = NULL"))
    with pytest.raises(RuntimeError, match="archived assignment"):
        command.downgrade(cfg, "0002")
    with engine.begin() as conn:
        assert conn.execute(text("SELECT status::text FROM assignments")).scalar() == "ARCHIVED"  # nothing changed
        conn.execute(text("UPDATE assignments SET status = 'PUBLISHED', archived_at = NULL"))
    command.downgrade(cfg, "0002")  # allowed once nothing is archived
    with engine.connect() as conn:
        labels = {r[0] for r in conn.execute(text("SELECT unnest(enum_range(NULL::assignment_status))::text"))}
        assert labels == {"DRAFT", "PUBLISHED"}
        assert conn.execute(text("SELECT title, status::text FROM assignments")).one() == ("Existing", "PUBLISHED")


def test_0004_existing_assignments_become_file_assignments_and_downgrade_refuses_while_a_quiz_exists(empty_db):
    url, engine = empty_db
    cfg = alembic_config(url)
    command.upgrade(cfg, "0003")
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO sections (semester, name, label) VALUES (5, 'A', 'CSE-5A')"))
        conn.execute(text("INSERT INTO subjects (code, name, semester) VALUES ('CS503', 'Database Systems', 5)"))
        conn.execute(text("INSERT INTO users (login_id, full_name, role, password_hash) VALUES ('FAC001', 'T', 'FACULTY', 'x')"))
        conn.execute(
            text(
                "INSERT INTO assignments (title, instructions, subject_id, section_id, created_by, status, original_deadline, "
                "deadline, allowed_types, max_file_mb) SELECT 'Existing', 'i', su.id, se.id, u.id, 'PUBLISHED', now(), now(), "
                "ARRAY['pdf'], 5 FROM subjects su, sections se, users u"
            )
        )
    command.upgrade(cfg, "head")
    with engine.begin() as conn:
        assert conn.execute(text("SELECT assignment_type, description, duration_minutes FROM assignments")).one() == (
            "FILE",
            None,
            None,
        )
        conn.execute(text("UPDATE assignments SET assignment_type = 'QUIZ'"))
        with pytest.raises(IntegrityError):
            with conn.begin_nested():
                conn.execute(text("UPDATE assignments SET assignment_type = 'ESSAY'"))
    with pytest.raises(RuntimeError, match="quiz assignment"):
        command.downgrade(cfg, "0003")
    with engine.begin() as conn:
        conn.execute(text("UPDATE assignments SET assignment_type = 'FILE'"))
    command.downgrade(cfg, "0003")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT title FROM assignments")).scalar() == "Existing"
        assert "quiz_questions" not in inspect(engine).get_table_names()
