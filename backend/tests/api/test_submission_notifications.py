"""Teacher notifications for student submissions (created in the same transaction as the version)."""

import pytest

from app.services import submissions
from tests.api.test_assignments import API, auth
from tests.api.test_submissions import S
from tests.unit.test_file_validation import pdf


@pytest.fixture
def s(client, api_app, monkeypatch, test_password, freeze_time, s3_client, settings, seeded_engine) -> S:
    monkeypatch.setattr(api_app.state, "settings", api_app.state.settings.model_copy(update={"jwt_expire_minutes": 60 * 24 * 30}))
    return S(client, test_password, freeze_time, s3_client=s3_client, bucket=settings.s3_bucket, engine=seeded_engine)


def notes(s: S, token: str) -> list[dict]:
    return s.client.get(f"{API}/notifications", headers=auth(token)).json()["items"]


def unread(s: S, token: str) -> int:
    return s.client.get(f"{API}/notifications/unread-count", headers=auth(token)).json()["unread_count"]


def test_first_submission_notifies_the_owning_teacher_with_real_details(s: S):
    assert unread(s, s.fac1) == 0
    assert s.upload().status_code == 201
    assert unread(s, s.fac1) == 1
    n = notes(s, s.fac1)[0]
    assert n["title"] == "New assignment submission" and n["type"] == "SUBMISSION_NEW"
    name, login = s.sql("SELECT full_name, login_id FROM users WHERE login_id = 'STU0101'")[0]
    assert f"{name} ({login}) submitted \"DBMS Lab 4\" for " in n["body"] and "CSE-5A" in n["body"]
    assert "IST" in n["body"]  # shown in IST
    assert n["created_at"].endswith(("Z", "+00:00"))  # stored and sent in UTC
    assert n["ref_type"] == "SUBMISSION" and n["read_at"] is None


def test_new_version_has_its_own_message_and_resubmission_counts_again(s: S):
    s.upload(data=pdf(200))
    assert s.upload(data=pdf(300)).status_code == 201
    titles = sorted(n["title"] for n in notes(s, s.fac1))
    assert titles == ["New assignment submission", "New submission version"]
    version = next(n for n in notes(s, s.fac1) if n["type"] == "SUBMISSION_VERSION")
    assert "uploaded version 2 of" in version["body"] and unread(s, s.fac1) == 2


def test_failed_uploads_create_no_notification(s: S, monkeypatch):
    assert s.upload(name="x.exe", data=b"MZ" + b"x" * 50).status_code == 415
    s.upload(data=pdf(100))
    assert s.upload(data=pdf(100)).status_code == 409  # identical to the latest version
    assert unread(s, s.fac1) == 1  # only the first, successful upload

    def explode(*a, **k):
        raise RuntimeError("database went away")

    monkeypatch.setattr(submissions, "_lock_submission", explode)
    assert s.upload(token=s.stu_5a2).status_code == 500
    assert s.count("notifications") == 1


def test_only_the_owning_teacher_is_notified_and_students_never_are(s: S):
    s.upload()
    assert unread(s, s.fac2) == 0 and unread(s, s.fac49) == 0
    assert unread(s, s.stu_5a) == 0 and unread(s, s.stu_5a2) == 0
    assert s.count("notifications") == 1


def test_teacher_reads_it_count_drops_and_it_persists(s: S, test_password):
    s.upload()
    s.upload(data=pdf(250))
    first = notes(s, s.fac1)[0]["id"]
    assert s.client.post(f"{API}/notifications/{first}/read", headers=auth(s.fac1)).status_code == 204
    assert unread(s, s.fac1) == 1
    s.client.post(f"{API}/notifications/{first}/read", headers=auth(s.fac1))  # reading again changes nothing
    assert unread(s, s.fac1) == 1
    again = s.client.post(f"{API}/auth/login", json={"role": "FACULTY", "login_id": "FAC001", "password": test_password})
    assert unread(s, again.json()["access_token"]) == 1  # persisted across a new login


def test_another_teacher_cannot_read_it_or_open_the_submission(s: S):
    s.upload()
    n = notes(s, s.fac1)[0]
    assert s.client.post(f"{API}/notifications/{n['id']}/read", headers=auth(s.fac2)).status_code == 404
    assert s.client.get(f"{API}/faculty/submissions/{n['ref_id']}/locator", headers=auth(s.fac2)).status_code == 404
    ok = s.client.get(f"{API}/faculty/submissions/{n['ref_id']}/locator", headers=auth(s.fac1))
    assert ok.status_code == 200 and ok.json()["assignment_id"] == s.aid
    assert s.client.get(f"{API}/faculty/submissions/{n['ref_id']}/locator", headers=auth(s.stu_5a)).status_code == 403


def test_a_retried_event_never_duplicates_the_notification(s: S):
    from sqlalchemy.orm import Session

    from app.db.models import Submission, SubmissionVersion, User

    s.upload()
    with Session(s.engine) as db:
        v = db.query(SubmissionVersion).one()
        sub = db.get(Submission, v.submission_id)
        a = sub.assignment_id
        from app.db.models import Assignment

        assignment = db.get(Assignment, a)
        student = db.get(User, sub.student_id)
        submissions._notify_faculty(db, assignment, student, sub, v)  # same event again
        db.commit()
    assert s.count("notifications") == 1


def test_existing_student_notifications_are_unchanged(s: S):
    # a deadline change still notifies students exactly as before
    r = s.client.patch(
        f"{API}/faculty/assignments/{s.aid}/deadline",
        json={"new_deadline": "2026-10-20T10:00:00+05:30"},
        headers=auth(s.fac1),
    )
    assert r.status_code == 200
    assert any(n["type"] == "DEADLINE_CHANGED" for n in notes(s, s.stu_5a))
