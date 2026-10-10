"""Phase 7: Faculty Submission Health Board (count semantics, scope, filters) and in-app notifications."""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.seeds.seed_config import display_name
from app.services import notifications as notification_service
from tests.api.test_assignments import API, NOW
from tests.api.test_late_requests import AFTER, DECIDED, NO_ID, L
from tests.api.test_reviews_timeline import review, sub_id
from tests.api.test_submissions import DEADLINE
from tests.unit.test_file_validation import pdf


@pytest.fixture
def s(client, api_app, monkeypatch, test_password, freeze_time, s3_client, settings, seeded_engine, redis_client) -> L:
    monkeypatch.setattr(api_app.state, "settings", api_app.state.settings.model_copy(update={"jwt_expire_minutes": 60 * 24 * 30}))
    world = L(client, test_password, freeze_time, s3_client=s3_client, bucket=settings.s3_bucket, engine=seeded_engine)
    world.password, world.redis = test_password, redis_client
    return world


def tok(s, login: str) -> str:
    s.redis.flushdb()  # the login throttle (10/min per IP) would otherwise stop a test that logs in 11 users
    return s._login("STUDENT", login, s.password)


def overview(s, token=None, **params):
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return s.get(f"/faculty/overview?{query}", token or s.fac1)


def overview_students(s, token=None, **params):
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return s.get(f"/faculty/overview/students?{query}", token or s.fac1)


def unread(s, token) -> int:
    return s.get("/notifications", token).json()["unread_count"]


def inbox(s, token) -> list[dict]:
    return s.get("/notifications", token).json()["items"]


# --- the health board ------------------------------------------------------------------------------------------------------


@pytest.fixture
def board(s):
    """17 students in CSE-5A for one assignment, with a deliberately mixed state (see EXPECTED)."""
    s.upload(token=s.stu_5a, data=pdf(101))  # STU0101: two versions, on time
    s.upload(token=s.stu_5a, data=pdf(102))
    s.upload(token=s.stu_5a2, data=pdf(103))  # STU0102: on time, accepted
    t108 = tok(s, "STU0108")
    s.upload(token=t108, data=pdf(104))  # STU0108: v1 reviewed UNDER_REVIEW, then v2 -> current review is NOT_REVIEWED
    review(s, "UNDER_REVIEW", sid=sub_id(s, "STU0108"))
    s.at(NOW + timedelta(minutes=1))
    s.upload(token=t108, data=pdf(105))
    review(s, "UNDER_REVIEW", sid=sub_id(s, "STU0101"))  # on v2
    review(s, "ACCEPTED", "Fine.", sid=sub_id(s, "STU0102"))
    s.insert_first_version("STU0103", uploaded_at=AFTER, context="REGULAR")  # late (data only; no API path creates this)
    tokens = {login: tok(s, login) for login in ("STU0104", "STU0105", "STU0106", "STU0107")}
    s.at(AFTER)
    ids = {login: s.ask(token=t).json()["id"] for login, t in tokens.items()}
    s.at(DECIDED)
    assert s.decide(ids["STU0104"], window_hours=24).status_code == 200  # approved, will upload late
    assert s.decide(ids["STU0106"], decision="REJECT").status_code == 200
    assert s.decide(ids["STU0107"], window_hours=24).status_code == 200  # approved, unused
    s.at(DECIDED + timedelta(hours=1))
    assert s.upload(token=tokens["STU0104"], data=pdf(106)).json()["upload_context"] == "LATE_APPROVED"
    return s


EXPECTED = dict(
    expected=17,
    on_time=3,  # STU0101, STU0102, STU0108 (each counted once although two of them have two versions)
    late=2,  # STU0103 (data), STU0104 (approved late)
    late_approved=1,  # STU0104 only: a subset of late
    pending=0,
    missing=12,
    submitted=5,
    resubmitted=2,  # STU0101, STU0108
    under_review=1,  # STU0101 (STU0108's review belongs to the replaced version)
    accepted=1,
    revision_requested=0,
    not_reviewed=3,  # submitted but no current review: STU0103, STU0104, STU0108
    reviewed=1,  # accepted + revision_requested
    requests_pending=1,  # STU0105
)


def independent_counts(s) -> dict:
    """The same numbers from deliberately different SQL (no shared CTE), for comparison with the service."""
    q = lambda sql, **p: s.sql(sql, a=s.aid, **p)[0][0]  # noqa: E731
    first = "FROM submissions s JOIN submission_versions v ON v.submission_id = s.id AND v.version_no = 1 JOIN assignments a ON a.id = s.assignment_id WHERE s.assignment_id = :a"
    return dict(
        on_time=q(f"SELECT count(*) {first} AND v.uploaded_at <= a.deadline"),
        late=q(f"SELECT count(*) {first} AND v.uploaded_at > a.deadline"),
        late_approved=q(f"SELECT count(*) {first} AND v.uploaded_at > a.deadline AND v.upload_context = 'LATE_APPROVED'"),
        submitted=q("SELECT count(DISTINCT s.student_id) FROM submissions s JOIN submission_versions v ON v.submission_id = s.id WHERE s.assignment_id = :a"),
        resubmitted=q("SELECT count(*) FROM submissions WHERE assignment_id = :a AND latest_version_no > 1"),
        requests_pending=q("SELECT count(*) FROM late_requests WHERE assignment_id = :a AND status = 'PENDING'"),
        **{
            name.lower(): q(
                "SELECT count(DISTINCT s.id) FROM submissions s JOIN submission_versions lv ON lv.submission_id = s.id AND lv.version_no = s.latest_version_no "
                "JOIN reviews r ON r.version_id = lv.id WHERE s.assignment_id = :a AND r.status = CAST(:st AS review_status) "
                "AND r.reviewed_at = (SELECT max(r2.reviewed_at) FROM reviews r2 WHERE r2.version_id = lv.id)",
                st=name,
            )
            for name in ("UNDER_REVIEW", "ACCEPTED", "REVISION_REQUESTED")
        },
    )


def test_counts_match_the_scenario_exactly(board):
    s = board
    body = overview(s).json()
    assert body["totals"] == EXPECTED
    (row,) = body["assignments"]
    assert {k: v for k, v in row.items() if k in EXPECTED} == EXPECTED
    assert row["assignment"]["id"] == s.aid and row["assignment"]["subject"]["code"] and row["assignment"]["section"]["label"]


def test_counts_equal_independent_sql_and_buckets_add_up(board):
    s = board
    totals = overview(s).json()["totals"]
    expected_students = s.sql("SELECT count(*) FROM student_profiles sp JOIN assignments a ON a.section_id = sp.section_id WHERE a.id = :a", a=s.aid)[0][0]
    assert totals["expected"] == expected_students == 17
    for name, value in independent_counts(s).items():
        assert totals[name] == value, name
    assert totals["on_time"] + totals["late"] + totals["pending"] + totals["missing"] == totals["expected"]
    assert totals["late_approved"] <= totals["late"] and totals["submitted"] == totals["on_time"] + totals["late"]
    assert totals["reviewed"] == totals["accepted"] + totals["revision_requested"]
    assert totals["submitted"] == totals["under_review"] + totals["reviewed"] + totals["not_reviewed"]


def test_a_student_with_many_versions_is_counted_once(s):
    for i in range(4):
        s.upload(data=pdf(100 + i))
    totals = overview(s).json()["totals"]
    assert (totals["submitted"], totals["on_time"], totals["resubmitted"]) == (1, 1, 1)
    assert totals["on_time"] + totals["late"] + totals["pending"] + totals["missing"] == totals["expected"]
    assert s.count("submission_versions") == 4


def test_pending_becomes_missing_one_second_after_the_deadline(s):
    s.at(DEADLINE)
    t = overview(s).json()["totals"]
    assert (t["pending"], t["missing"]) == (17, 0)
    s.at(DEADLINE + timedelta(seconds=1))
    t = overview(s).json()["totals"]
    assert (t["pending"], t["missing"]) == (0, 17)


def test_the_student_list_comes_from_the_same_query_as_the_counts(board):
    s = board
    totals = overview(s).json()["totals"]
    for timing, key in (("ON_TIME", "on_time"), ("LATE", "late"), ("PENDING", "pending"), ("MISSING", "missing")):
        body = overview_students(s, timing=timing, limit=500).json()
        assert body["total"] == totals[key] == len(body["items"]) and body["truncated"] is False
        assert all(i["timing"] == timing for i in body["items"])
    late = {i["student"]["login_id"]: i for i in overview_students(s, timing="LATE").json()["items"]}
    assert set(late) == {"STU0103", "STU0104"}
    assert late["STU0104"]["late_approved"] is True and late["STU0103"]["late_approved"] is False
    assert late["STU0104"]["request_status"] == "USED"
    accepted = overview_students(s, review_status="ACCEPTED").json()["items"]
    assert [i["student"]["login_id"] for i in accepted] == ["STU0102"]
    both = overview_students(s, timing="ON_TIME", review_status="UNDER_REVIEW").json()["items"]
    assert [i["student"]["login_id"] for i in both] == ["STU0101"] and both[0]["is_resubmitted"] is True and both[0]["version_count"] == 2
    unreviewed = overview_students(s, review_status="NOT_REVIEWED", timing="ON_TIME").json()
    assert [i["student"]["login_id"] for i in unreviewed["items"]] == ["STU0108"]  # its review belongs to the replaced version
    requests = {i["student"]["login_id"]: i["request_status"] for i in overview_students(s, timing="MISSING", limit=500).json()["items"] if i["request_status"] != "NONE"}
    assert requests == {"STU0105": "PENDING", "STU0106": "REJECTED", "STU0107": "APPROVED"}


def test_student_list_limit_and_truncation(board):
    body = overview_students(board, timing="MISSING", limit=5).json()
    assert (body["total"], len(body["items"]), body["truncated"]) == (12, 5, True)
    assert overview_students(board, limit=0).status_code == 422 and overview_students(board, limit=501).status_code == 422


def test_filters_by_assignment_subject_and_section(s):
    second = s.create(title="Second", allowed_types=["pdf"]).json()
    draft = s.create(title="Hidden draft", allowed_types=["pdf"], publish=False).json()
    s.upload(aid=second["id"], data=pdf(500))
    both = overview(s).json()
    assert {a["assignment"]["title"] for a in both["assignments"]} == {"DBMS Lab 4", "Second"}  # drafts are not counted
    assert both["totals"]["expected"] == 34 and both["totals"]["on_time"] == 1
    only = overview(s, assignment_id=second["id"]).json()
    assert [a["assignment"]["id"] for a in only["assignments"]] == [second["id"]] and only["totals"]["expected"] == 17
    subject_id, section_id = s.slot1["subject"]["id"], s.slot1["section"]["id"]
    assert overview(s, subject_id=subject_id, section_id=section_id).json()["totals"]["expected"] == 34
    # A subject / section the teacher does not teach (or that does not exist) is denied, never silently counted as zero.
    for denied in (overview(s, subject_id=NO_ID), overview(s, section_id=NO_ID), overview(s, assignment_id=second["id"], section_id=NO_ID)):
        assert denied.status_code == 403 and denied.json()["error"]["code"] == "NOT_YOUR_CLASS"
    assert overview(s, assignment_id=draft["id"]).json()["assignments"] == []  # a draft has no submissions to count
    assert overview_students(s, assignment_id=second["id"], timing="ON_TIME").json()["total"] == 1


def test_counts_respect_the_faculty_members_scope(board):
    s = board
    for token in (s.fac2, s.fac49):
        body = overview(s, token=token).json()
        assert body["assignments"] == [] and body["totals"]["expected"] == 0 and body["totals"]["on_time"] == 0
        assert overview_students(s, token=token).json() == {"total": 0, "items": [], "truncated": False}
        assert overview(s, token=token, assignment_id=s.aid).status_code == 404  # not their assignment
        assert overview_students(s, token=token, assignment_id=s.aid).status_code == 404
    assert overview(s, token=s.stu_5a).status_code == 403 and overview_students(s, token=s.stu_5a).status_code == 403
    assert s.client.get(f"{API}/faculty/overview").status_code == 401
    assert overview(s, assignment_id="not-a-uuid").status_code == 422
    assert overview_students(s, timing="NOPE").status_code == 422 and overview_students(s, review_status="DONE").status_code == 422


def test_another_faculty_members_assignment_is_counted_for_them_only(s):
    theirs = s.create(token=s.fac2, slot=s.slot2, allowed_types=["pdf"]).json()
    mine = overview(s, token=s.fac2).json()
    assert [a["assignment"]["id"] for a in mine["assignments"]] == [theirs["id"]]
    assert [a["assignment"]["id"] for a in overview(s).json()["assignments"]] == [s.aid]  # and not for the first one


# --- notifications: creation, deduplication, privacy ----------------------------------------------------------------------------


def test_a_new_late_request_notifies_the_assignments_faculty_only(s):
    rid = s.pending()
    items = inbox(s, s.fac1)
    assert len(items) == 1 and unread(s, s.fac1) == 1
    n = items[0]
    assert (n["type"], n["ref_type"], n["ref_id"], n["read_at"]) == ("LATE_REQUEST_CREATED", "LATE_REQUEST", rid, None)
    assert display_name("STU0101") in n["body"] and "STU0101" in n["body"] and "hospital" not in n["body"]
    assert s.sql("SELECT dedup_key FROM notifications")[0][0] == f"LR_CREATED:{rid}"
    for token in (s.fac2, s.fac49, s.stu_5a, s.stu_5a2, s.stu_5b):
        assert inbox(s, token) == [] and unread(s, token) == 0




def test_retried_request_does_not_duplicate_the_notification(s):
    s.pending()
    assert s.ask().status_code == 409  # REQUEST_EXISTS
    assert s.ask().status_code == 409
    assert unread(s, s.fac1) == 1 and s.count("notifications") == 1


def test_a_decision_notifies_the_student_once(s):
    rid = s.pending()
    s.at(DECIDED)
    assert s.decide(rid, window_hours=2).status_code == 200
    (n,) = inbox(s, s.stu_5a)
    assert (n["type"], n["title"], n["ref_type"], n["ref_id"]) == ("LATE_REQUEST_DECIDED", "Late request approved", "ASSIGNMENT", s.aid)
    assert "IST" in n["body"] and unread(s, s.stu_5a) == 1
    assert s.decide(rid).status_code == 409 and s.decide(rid, decision="REJECT").status_code == 409  # ALREADY_DECIDED
    assert s.count("notifications") == 2 and unread(s, s.stu_5a) == 1  # request + one decision, nothing more
    assert s.sql("SELECT dedup_key FROM notifications WHERE user_id = :u", u=s.student_id("STU0101"))[0][0] == f"LR_DECIDED:{rid}"
    assert inbox(s, s.stu_5a2) == []


def test_a_rejection_notifies_the_student(s):
    rid = s.pending()
    s.at(DECIDED)
    s.decide(rid, decision="REJECT", note="No evidence.")
    (n,) = inbox(s, s.stu_5a)
    assert n["title"] == "Late request rejected" and "rejected" in n["body"]


def test_a_review_notifies_the_student_and_retries_do_not_duplicate(s):
    s.upload()
    assert review(s, "REVISION_REQUESTED", "SECRET feedback text").status_code == 201
    (n,) = inbox(s, s.stu_5a)
    assert (n["type"], n["title"], n["ref_type"], n["ref_id"]) == ("REVIEW_RECORDED", "Review: Revision requested", "ASSIGNMENT", s.aid)
    assert "SECRET" not in n["body"]  # feedback stays on the assignment page, not in the list
    assert review(s, "REVISION_REQUESTED", "SECRET feedback text").status_code == 409  # retry
    assert unread(s, s.stu_5a) == 1
    review(s, "ACCEPTED")
    assert unread(s, s.stu_5a) == 2
    assert inbox(s, s.stu_5a2) == []
    assert [n for n in inbox(s, s.fac1) if not n["type"].startswith("SUBMISSION_")] == []  # the upload itself notifies the teacher
    keys = {r[0] for r in s.sql("SELECT dedup_key FROM notifications WHERE type NOT LIKE 'SUBMISSION_%'")}
    assert all(k.startswith("REVIEW:") for k in keys) and len(keys) == 2


def test_a_deadline_change_notifies_every_student_of_the_section_once(s):
    new_deadline = DEADLINE + timedelta(days=1)
    assert s.patch(f"/faculty/assignments/{s.aid}/deadline", s.fac1, {"new_deadline": new_deadline.isoformat()}).status_code == 200
    assert s.count("notifications") == 17
    assert unread(s, s.stu_5a) == 1 and unread(s, s.stu_5a2) == 1
    assert unread(s, s.stu_5b) == 0 and unread(s, s.fac1) == 0  # other section, and not the teacher
    assert inbox(s, s.stu_5a)[0]["type"] == "DEADLINE_CHANGED" and "IST" in inbox(s, s.stu_5a)[0]["body"]
    assert s.sql("SELECT count(DISTINCT dedup_key) FROM notifications")[0][0] == 17
    s.patch(f"/faculty/assignments/{s.aid}/deadline", s.fac1, {"new_deadline": (new_deadline + timedelta(days=1)).isoformat()})
    assert s.count("notifications") == 34  # a second, real change is a second event


def test_the_same_event_cannot_notify_twice(s):
    with Session(s.engine) as db:
        uid = uuid.UUID(s.student_id("STU0101"))
        first = notification_service.notify(db, user_id=uid, type="T", title="t", body="b", ref_type=None, ref_id=None, dedup_key="X:1")
        second = notification_service.notify(db, user_id=uid, type="T", title="t", body="b", ref_type=None, ref_id=None, dedup_key="X:1")
        db.commit()
    assert (first, second) == (True, False) and s.count("notifications") == 1


# --- list, unread count, mark as read ------------------------------------------------------------------------------------------------


def test_list_is_newest_first_with_unread_count_and_a_50_item_cap(s):
    uid = s.student_id("STU0101")
    with Session(s.engine) as db:
        for i in range(60):
            db.execute(
                text("INSERT INTO notifications (user_id, type, title, body, dedup_key, created_at) VALUES (:u, 'T', :t, 'b', :k, :c)"),
                dict(u=uid, t=f"n{i}", k=f"BULK:{i}", c=NOW + timedelta(minutes=i)),
            )
        db.commit()
    body = s.get("/notifications", s.stu_5a).json()
    assert len(body["items"]) == 50 and body["unread_count"] == 60  # the count covers everything, the list is capped
    assert body["items"][0]["title"] == "n59" and body["items"][-1]["title"] == "n10"
    assert set(body) == {"alerts", "items", "unread_count"}


def test_mark_as_read_updates_only_read_at_and_is_idempotent(s):
    s.pending()
    s.at(DECIDED)
    n = inbox(s, s.fac1)[0]
    before = s.sql("SELECT id, type, title, body, dedup_key, created_at FROM notifications WHERE id = :i", i=n["id"])
    res = s.post(f"/notifications/{n['id']}/read", s.fac1)
    assert res.status_code == 204 and res.content == b""
    assert unread(s, s.fac1) == 0
    first_read = inbox(s, s.fac1)[0]["read_at"]
    assert first_read is not None
    s.at(DECIDED + timedelta(hours=1))
    assert s.post(f"/notifications/{n['id']}/read", s.fac1).status_code == 204  # again: harmless
    assert inbox(s, s.fac1)[0]["read_at"] == first_read  # the first time is kept
    assert s.sql("SELECT id, type, title, body, dedup_key, created_at FROM notifications WHERE id = :i", i=n["id"]) == before


def test_nobody_can_read_or_mark_someone_elses_notification(s):
    s.pending()
    n = inbox(s, s.fac1)[0]
    for token in (s.fac2, s.fac49, s.stu_5a, s.stu_5a2, s.stu_5b):
        res = s.post(f"/notifications/{n['id']}/read", token)
        assert res.status_code == 404, res.text
    assert s.sql("SELECT read_at FROM notifications")[0][0] is None and unread(s, s.fac1) == 1
    assert s.post(f"/notifications/{NO_ID}/read", s.fac1).status_code == 404
    assert s.post("/notifications/not-a-uuid/read", s.fac1).status_code == 422
    assert s.client.post(f"{API}/notifications/{n['id']}/read").status_code == 401
    assert s.client.get(f"{API}/notifications").status_code == 401


def test_students_never_see_each_others_notifications(s):
    s.upload()
    s.upload(token=s.stu_5a2, data=pdf(900))
    review(s, "ACCEPTED", "Private note", sid=sub_id(s, "STU0101"))
    mine, other = inbox(s, s.stu_5a), inbox(s, s.stu_5a2)
    assert [i["type"] for i in mine] == ["REVIEW_RECORDED"] and other == []
    assert s.post(f"/notifications/{mine[0]['id']}/read", s.stu_5a2).status_code == 404
    assert unread(s, s.stu_5a) == 1


# --- computed alerts -------------------------------------------------------------------------------------------------------------------------


def alerts(s, token=None) -> list[str]:
    return [a["type"] for a in s.get("/notifications", token or s.stu_5a).json()["alerts"]]


def test_due_alerts_follow_the_server_clock_at_exact_boundaries(s):
    expectations = [
        (DEADLINE - timedelta(hours=24, seconds=1), []),
        (DEADLINE - timedelta(hours=24), ["DUE_24H"]),
        (DEADLINE - timedelta(hours=3, seconds=1), ["DUE_24H"]),
        (DEADLINE - timedelta(hours=3), ["DUE_3H"]),
        (DEADLINE, ["DUE_3H"]),  # exactly at the deadline is still on time
        (DEADLINE + timedelta(seconds=1), ["MISSING"]),
    ]
    for moment, expected in expectations:
        s.at(moment)
        assert alerts(s) == expected, moment
    assert s.count("notifications") == 0  # computed, never stored


def test_a_submission_silences_the_due_and_missing_alerts(s):
    s.at(DEADLINE - timedelta(hours=2))
    assert alerts(s) == ["DUE_3H"]
    assert s.upload().status_code == 201
    assert alerts(s) == []
    s.at(DEADLINE + timedelta(days=1))
    assert alerts(s) == []


def test_alerts_are_for_the_students_own_section_only(s):
    s.at(DEADLINE - timedelta(hours=2))
    assert alerts(s, s.stu_5a2) == ["DUE_3H"] and alerts(s, s.stu_5b) == []
    assert alerts(s, s.fac1) == [] and s.get("/notifications", s.fac1).json()["alerts"] == []
    draft = s.create(publish=False, allowed_types=["pdf"]).json()
    assert draft["id"] and alerts(s, s.stu_5a) == ["DUE_3H"]  # drafts never alert


def test_window_alerts_and_missing_while_a_window_is_open(s):
    s.approved(hours=24)
    s.at(DECIDED + timedelta(hours=1))
    assert alerts(s) == []  # open window: neither MISSING nor closing yet
    s.at(DECIDED + timedelta(hours=21))
    assert alerts(s) == ["WINDOW_CLOSING"]
    s.at(DECIDED + timedelta(hours=24))
    assert alerts(s) == ["WINDOW_CLOSING"]  # inclusive end
    s.at(DECIDED + timedelta(hours=24, seconds=1))
    assert alerts(s) == ["MISSING", "WINDOW_EXPIRED"]
    assert alerts(s, s.stu_5a2) == ["MISSING"]


def test_using_the_window_silences_its_alerts(s):
    s.approved(hours=24)
    s.at(DECIDED + timedelta(hours=22))
    assert s.upload().status_code == 201
    assert alerts(s) == []
    s.at(DECIDED + timedelta(days=3))
    assert alerts(s) == []


def test_alerts_carry_the_assignment_and_time(s):
    s.at(DEADLINE - timedelta(hours=2))
    (alert,) = s.get("/notifications", s.stu_5a).json()["alerts"]
    assert alert["assignment_id"] == s.aid and alert["assignment_title"] == "DBMS Lab 4"
    assert alert["at"].startswith(DEADLINE.isoformat()[:19]) and "3 hours" in alert["message"]
