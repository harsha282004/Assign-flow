"""24-hour deadline reminders: timing, recipients, duplicates, deadline changes, completed work, time zones."""

from datetime import timedelta

import pytest
from sqlalchemy.orm import Session

from app.services import reminders
from tests.api.test_assignments import API, auth
from tests.api.test_submissions import DEADLINE, S
from tests.unit.test_file_validation import pdf

H = timedelta(hours=1)


@pytest.fixture
def s(client, api_app, monkeypatch, test_password, freeze_time, s3_client, settings, seeded_engine) -> S:
    monkeypatch.setattr(api_app.state, "settings", api_app.state.settings.model_copy(update={"jwt_expire_minutes": 60 * 24 * 30}))
    return S(client, test_password, freeze_time, s3_client=s3_client, bucket=settings.s3_bucket, engine=seeded_engine)


def run(s: S, at) -> int:
    with Session(s.engine) as db:
        return reminders.send_due_reminders(db, at)


def reminder_count(s: S) -> int:
    return s.sql("SELECT count(*) FROM notifications WHERE type = 'DEADLINE_REMINDER_24H'")[0][0]


def test_reminder_is_sent_about_24_hours_before_and_not_earlier_or_much_later(s: S):
    assert run(s, DEADLINE - 25 * H) == 0  # too early
    assert run(s, DEADLINE - 22 * H + timedelta(minutes=1)) == 0  # under 22 h left: outside the catch-up window
    assert run(s, DEADLINE - 24 * H) == 17  # exactly 24 h before: every student of CSE-5A
    assert run(s, DEADLINE - 3 * H) == 0  # later runs add nothing


def test_catch_up_after_a_missed_tick_still_sends_once(s: S):
    assert run(s, DEADLINE - 23 * H) == 17
    assert run(s, DEADLINE - 22 * H - timedelta(minutes=30)) == 0


def test_only_students_of_the_assignments_section_are_notified(s: S):
    run(s, DEADLINE - 24 * H)
    assert s.sql("SELECT count(*) FROM notifications WHERE user_id = :u", u=s.student_id("STU0101"))[0][0] == 1
    assert s.sql("SELECT count(*) FROM notifications WHERE user_id = :u", u=s.student_id("STU0118"))[0][0] == 0  # CSE-5B
    for token in (s.fac1, s.fac2, s.stu_5b):
        res = s.client.get(f"{API}/notifications", headers=auth(token)).json()
        assert [n for n in res["items"] if n["type"] == "DEADLINE_REMINDER_24H"] == []


def test_message_has_title_subject_section_and_the_deadline_in_ist(s: S):
    run(s, DEADLINE - 24 * H)
    n = next(i for i in s.client.get(f"{API}/notifications", headers=auth(s.stu_5a)).json()["items"] if i["type"] == "DEADLINE_REMINDER_24H")
    # DEADLINE = 2026-10-13 12:00 UTC = 17:30 IST
    assert 'DBMS Lab 4' in n["body"] and "CS503" in n["body"] and "CSE-5A" in n["body"]
    assert "13 Oct 2026, 05:30 PM IST" in n["body"] and "submit on time" in n["body"]
    assert n["ref_type"] == "ASSIGNMENT" and n["ref_id"] == s.aid and n["read_at"] is None
    assert n["created_at"].endswith(("Z", "+00:00"))
    count = s.client.get(f"{API}/notifications/unread-count", headers=auth(s.stu_5a)).json()["unread_count"]
    assert count == 1  # it feeds the existing unread badge


def test_repeated_runs_and_restarts_never_duplicate(s: S):
    assert run(s, DEADLINE - 24 * H) == 17
    for minutes in (0, 1, 2, 30, 90):  # scheduler ticks / a restarted process
        assert run(s, DEADLINE - 24 * H + timedelta(minutes=minutes)) == 0
    assert reminder_count(s) == 17


def test_a_deadline_moved_later_before_the_window_gets_no_reminder_for_the_old_deadline(s: S):
    new_deadline = DEADLINE + timedelta(days=2)
    s.client.patch(f"{API}/faculty/assignments/{s.aid}/deadline", json={"new_deadline": new_deadline.isoformat()}, headers=auth(s.fac1))
    assert run(s, DEADLINE - 24 * H) == 0  # the old deadline is obsolete
    assert run(s, new_deadline - 24 * H) == 17  # the effective deadline earns its own reminder
    assert reminder_count(s) == 17


def test_a_deadline_extended_after_a_reminder_gets_one_more_for_the_new_deadline(s: S):
    assert run(s, DEADLINE - 24 * H) == 17
    new_deadline = DEADLINE + timedelta(days=1)
    s.client.patch(f"{API}/faculty/assignments/{s.aid}/deadline", json={"new_deadline": new_deadline.isoformat()}, headers=auth(s.fac1))
    assert run(s, DEADLINE - 24 * H + timedelta(minutes=5)) == 0  # 48 h before the new deadline: nothing
    assert run(s, new_deadline - 24 * H) == 17
    assert run(s, new_deadline - 24 * H + timedelta(minutes=5)) == 0
    assert reminder_count(s) == 34


def test_students_who_already_submitted_are_not_reminded(s: S):
    assert s.upload().status_code == 201  # STU0101 submits
    s.client.post(f"{API}/notifications/read-all", headers=auth(s.fac1))
    assert run(s, DEADLINE - 24 * H) == 16
    assert s.sql("SELECT count(*) FROM notifications WHERE type = 'DEADLINE_REMINDER_24H' AND user_id = :u", u=s.student_id("STU0101"))[0][0] == 0
    # uploading again later does not matter either; a resubmission needs no reminder
    assert s.upload(data=pdf(300)).status_code == 201
    assert run(s, DEADLINE - 23 * H) == 0


def test_drafts_and_archived_assignments_are_never_reminded(s: S):
    draft = s.create(publish=False).json()
    assert draft["status"] == "DRAFT"
    s.client.post(f"{API}/faculty/assignments/{s.aid}/archive", headers=auth(s.fac1))
    assert run(s, DEADLINE - 24 * H) == 0


def test_a_quiz_reminder_skips_students_who_submitted_it(s: S):
    from tests.api.test_quiz import answers_for, publish, quiz_body

    body = quiz_body(s, deadline=(DEADLINE + timedelta(days=3)).isoformat(), questions=[quiz_body(s)["questions"][2]])
    quiz = s.client.post(f"{API}/faculty/quizzes", json=body, headers=auth(s.fac1)).json()
    assert publish(s, quiz["id"]).status_code == 200
    attempt = s.client.post(f"{API}/student/quizzes/{quiz['id']}/attempts", headers=auth(s.stu_5a)).json()["attempt"]["id"]
    s.client.post(f"{API}/student/quiz-attempts/{attempt}/submit", json={"answers": answers_for(quiz, {0: [1]})}, headers=auth(s.stu_5a))
    quiz_deadline = DEADLINE + timedelta(days=3)
    assert run(s, quiz_deadline - 24 * H) == 16
