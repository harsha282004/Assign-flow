"""Phase 7: faculty reviews (permissions, transitions, privacy) and the Deadline Integrity Timeline."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from tests.api.test_assignments import API, NOW, auth, iso
from tests.api.test_late_requests import DECIDED, NO_ID, REASON, L
from tests.api.test_submissions import DEADLINE
from tests.unit.test_file_validation import pdf, png


@pytest.fixture
def s(client, api_app, monkeypatch, test_password, freeze_time, s3_client, settings, seeded_engine) -> L:
    monkeypatch.setattr(api_app.state, "settings", api_app.state.settings.model_copy(update={"jwt_expire_minutes": 60 * 24 * 30}))
    return L(client, test_password, freeze_time, s3_client=s3_client, bucket=settings.s3_bucket, engine=seeded_engine)


def sub_id(s, login="STU0101") -> str:
    return str(s.sql("SELECT s.id FROM submissions s JOIN users u ON u.id = s.student_id WHERE u.login_id = :l AND s.assignment_id = :a", l=login, a=s.aid)[0][0])


def review(s, status="ACCEPTED", feedback=None, token=None, sid=None, **extra):
    body = {"status": status, **({"feedback": feedback} if feedback is not None else {}), **extra}
    return s.post(f"/faculty/submissions/{sid or sub_id(s)}/reviews", token or s.fac1, body)


def faculty_view(s, login="STU0101", token=None):
    return s.get(f"/faculty/assignments/{s.aid}/students/{s.student_id(login)}/timeline", token or s.fac1)


def reviews_in_db(s):
    return s.sql("SELECT r.status, r.feedback, r.reviewed_at, r.reviewer_id, v.version_no FROM reviews r JOIN submission_versions v ON v.id = r.version_id ORDER BY r.reviewed_at, r.id")


# --- recording reviews -----------------------------------------------------------------------------------------------


def test_review_is_recorded_for_the_latest_version_with_server_set_fields(s):
    s.upload(data=pdf(100))
    s.upload(data=pdf(200))
    s.at(NOW + timedelta(minutes=5))
    res = review(s, "ACCEPTED", "Well done.")
    assert res.status_code == 201, res.text
    body = res.json()
    assert (body["status"], body["feedback"], body["version_no"], body["is_current"]) == ("ACCEPTED", "Well done.", 2, True)
    assert datetime.fromisoformat(body["reviewed_at"]) == NOW + timedelta(minutes=5)  # the server clock
    ((status, feedback, reviewed_at, reviewer, version_no),) = reviews_in_db(s)
    assert (status, feedback, version_no) == ("ACCEPTED", "Well done.", 2)
    assert str(reviewer) == s.student_id("FAC001") and reviewed_at == NOW + timedelta(minutes=5)


def test_feedback_is_optional_except_for_a_revision_request(s):
    s.upload()
    assert review(s, "UNDER_REVIEW").status_code == 201
    assert review(s, "ACCEPTED").json()["feedback"] is None
    assert review(s, "REVISION_REQUESTED").status_code == 422
    assert review(s, "REVISION_REQUESTED", "   ").status_code == 422
    assert review(s, "REVISION_REQUESTED", "Please add the ER diagram.").status_code == 201


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"status": "NOT_REVIEWED"},  # derived, never recorded
        {"status": "accepted"},
        {"status": "DONE"},
        {"status": None},
        {"status": "ACCEPTED", "feedback": "f" * 2001},
        {"status": "ACCEPTED", "feedback": "bad\x00nul"},
        {"status": "ACCEPTED", "reviewer_id": "x"},
        {"status": "ACCEPTED", "reviewed_at": "2000-01-01T00:00:00Z"},
        {"status": "ACCEPTED", "version_id": "x"},
        {"status": "ACCEPTED", "expected_version_no": 0},
        {"status": "ACCEPTED", "expected_version_no": "1"},
        {"status": "ACCEPTED", "expected_version_no": True},
    ],
)
def test_invalid_review_bodies_are_rejected_and_nothing_is_recorded(s, body):
    s.upload()
    res = s.post(f"/faculty/submissions/{sub_id(s)}/reviews", s.fac1, body)
    assert res.status_code == 422, res.text
    assert s.count("reviews") == 0 and s.sql("SELECT count(*) FROM notifications WHERE type NOT LIKE 'SUBMISSION_%'")[0][0] == 0


def test_feedback_boundary_and_trimming(s):
    s.upload()
    assert review(s, "UNDER_REVIEW", "x" * 2000).status_code == 201
    assert review(s, "ACCEPTED", "  padded  ").json()["feedback"] == "padded"


def test_only_the_owning_faculty_member_can_review(s):
    s.upload()
    for token in (s.fac2, s.fac49):
        assert review(s, token=token).status_code == 404  # other classes: not visible
    assert review(s, token=s.stu_5a).status_code == 403  # the student themselves
    assert review(s, token=s.stu_5b).status_code == 403
    assert s.client.post(f"{API}/faculty/submissions/{sub_id(s)}/reviews", json={"status": "ACCEPTED"}).status_code == 401
    assert review(s, sid=NO_ID).status_code == 404
    assert s.post("/faculty/submissions/not-a-uuid/reviews", s.fac1, {"status": "ACCEPTED"}).status_code == 422
    assert s.count("reviews") == 0 and s.sql("SELECT count(*) FROM notifications WHERE type NOT LIKE 'SUBMISSION_%'")[0][0] == 0
    assert review(s).status_code == 201  # the owner still can


def test_history_cannot_be_rewritten_through_the_api(s):
    s.upload()
    review(s, "UNDER_REVIEW")
    sid = sub_id(s)
    for method in ("PATCH", "PUT", "DELETE"):
        res = s.client.request(method, f"{API}/faculty/submissions/{sid}/reviews", headers=auth(s.fac1), json={"status": "ACCEPTED"})
        assert res.status_code == 405, method
    version_id = s.sql("SELECT id FROM submission_versions")[0][0]
    assert s.client.delete(f"{API}/files/versions/{version_id}", headers=auth(s.stu_5a)).status_code == 405
    tl = f"/faculty/assignments/{s.aid}/students/{s.student_id('STU0101')}/timeline"
    for method in ("PATCH", "PUT", "DELETE", "POST"):
        assert s.client.request(method, f"{API}{tl}", headers=auth(s.fac1)).status_code == 405, method
    assert s.count("reviews") == 1 and s.count("submission_versions") == 1


# --- transitions, independence from timing ----------------------------------------------------------------------------


def test_review_status_is_not_reviewed_until_a_review_exists(s):
    assert s.detail()["review_status"] == "NOT_REVIEWED"
    s.upload()
    assert s.detail()["review_status"] == "NOT_REVIEWED" and s.detail()["reviews"] == []
    roster = {r["student"]["login_id"]: r for r in s.get(f"/faculty/assignments/{s.aid}/roster", s.fac1).json()}
    assert roster["STU0101"]["review_status"] == "NOT_REVIEWED" and roster["STU0102"]["review_status"] == "NOT_REVIEWED"


def test_every_status_can_follow_every_other_and_history_is_append_only(s):
    s.upload()
    for status, feedback in (("UNDER_REVIEW", None), ("ACCEPTED", "Good."), ("REVISION_REQUESTED", "Redo section 2."), ("UNDER_REVIEW", None), ("ACCEPTED", "Fine now.")):
        assert review(s, status, feedback).status_code == 201, status
    assert [r[0] for r in reviews_in_db(s)] == ["UNDER_REVIEW", "ACCEPTED", "REVISION_REQUESTED", "UNDER_REVIEW", "ACCEPTED"]
    detail = s.detail()
    assert detail["review_status"] == "ACCEPTED" and detail["latest_feedback"] == "Fine now."
    assert [r["is_current"] for r in detail["reviews"]] == [False, False, False, False, True]
    assert all(r["reviewer_name"] for r in detail["reviews"])


def test_reviews_under_one_frozen_instant_still_have_a_strict_order(s):
    s.upload()
    for status in ("UNDER_REVIEW", "ACCEPTED", "REVISION_REQUESTED"):
        review(s, status, "x")
    times = [r[2] for r in reviews_in_db(s)]
    assert times == sorted(set(times)) and len(times) == 3
    assert s.detail()["review_status"] == "REVISION_REQUESTED"  # the last one decided, not a random tie


def test_late_and_accepted_are_shown_together(s):
    s.approved(hours=24)
    s.at(DECIDED + timedelta(hours=1))
    assert s.upload(data=pdf(100)).status_code == 201
    assert review(s, "ACCEPTED", "Accepted despite being late.").status_code == 201
    d = s.detail()
    assert (d["timing"], d["late_approved"], d["review_status"]) == ("LATE", True, "ACCEPTED")
    roster = {r["student"]["login_id"]: r for r in s.get(f"/faculty/assignments/{s.aid}/roster", s.fac1).json()}
    assert (roster["STU0101"]["timing"], roster["STU0101"]["review_status"]) == ("LATE", "ACCEPTED")
    item = s.get("/student/assignments", s.stu_5a).json()[0]
    assert (item["timing"], item["review_status"], item["latest_feedback"]) == ("LATE", "ACCEPTED", "Accepted despite being late.")


def test_on_time_with_a_revision_request_is_valid_too(s):
    s.upload()
    review(s, "REVISION_REQUESTED", "Needs more detail.")
    d = s.detail()
    assert (d["timing"], d["review_status"]) == ("ON_TIME", "REVISION_REQUESTED")


def test_accepted_blocks_uploads_before_and_after_the_deadline(s):
    s.upload(data=pdf(100))
    review(s, "ACCEPTED")
    for moment in (NOW + timedelta(minutes=1), DEADLINE + timedelta(hours=1)):
        s.at(moment)
        res = s.upload(data=pdf(200))
        assert res.status_code == 409 and res.json()["error"]["code"] == "SUBMISSION_ACCEPTED"
        d = s.detail()
        assert d["can_upload"] is False and d["upload_blocked_reason"] == "SUBMISSION_ACCEPTED"
    assert s.count("submission_versions") == 1 and len(s.objects()) == 1


def test_accepted_can_be_reopened_by_a_new_review(s):
    s.upload(data=pdf(100))
    review(s, "ACCEPTED")
    assert s.upload(data=pdf(200)).status_code == 409
    review(s, "REVISION_REQUESTED", "I accepted too early; please add references.")
    assert s.upload(data=pdf(200)).status_code == 201  # before the deadline: a regular upload again


def test_revision_request_after_the_deadline_allows_exactly_one_revision_upload(s):
    s.upload(data=pdf(100))
    review(s, "REVISION_REQUESTED", "Fix the figures.")
    s.at(DEADLINE + timedelta(hours=2))
    d = s.detail()
    assert d["can_upload"] is True and d["timing"] == "ON_TIME"
    res = s.upload(data=pdf(200))
    assert res.status_code == 201 and res.json()["upload_context"] == "REVISION"
    assert res.json()["version_timing"] == "LATE" and res.json()["submission_timing"] == "ON_TIME"  # first version rules
    # The new version starts as NOT_REVIEWED; the earlier review stays in history attached to version 1.
    d = s.detail()
    assert d["review_status"] == "NOT_REVIEWED" and d["latest_feedback"] is None
    assert [(r["version_no"], r["status"], r["is_current"]) for r in d["reviews"]] == [(1, "REVISION_REQUESTED", False)]
    # So a second after-deadline upload needs a new revision request.
    again = s.upload(data=pdf(300))
    assert again.status_code == 409 and again.json()["error"]["code"] == "DEADLINE_PASSED"
    review(s, "REVISION_REQUESTED", "One more fix.")
    assert s.upload(data=pdf(300)).json()["upload_context"] == "REVISION"
    assert s.detail()["timing"] == "ON_TIME" and s.count("submission_versions") == 3


def test_a_new_version_resets_the_current_review_in_every_view(s):
    s.upload(data=pdf(100))
    review(s, "UNDER_REVIEW")
    s.upload(data=pdf(200))
    roster = {r["student"]["login_id"]: r for r in s.get(f"/faculty/assignments/{s.aid}/roster", s.fac1).json()}
    assert roster["STU0101"]["review_status"] == "NOT_REVIEWED"
    view = faculty_view(s).json()
    assert view["review_status"] == "NOT_REVIEWED" and view["reviews"][0]["version_no"] == 1


def test_a_retried_review_is_not_recorded_twice(s):
    s.upload()
    assert review(s, "ACCEPTED", "Good.").status_code == 201
    again = review(s, "ACCEPTED", "Good.")
    assert again.status_code == 409 and again.json()["error"]["code"] == "REVIEW_UNCHANGED"
    assert len(reviews_in_db(s)) == 1
    assert review(s, "ACCEPTED", "Good, with a small note.").status_code == 201  # different feedback is a new review
    assert len(reviews_in_db(s)) == 2


def test_concurrent_identical_reviews_create_one_row(s, api_app):
    s.upload()
    sid = sub_id(s)

    def post(_):
        with TestClient(api_app, raise_server_exceptions=False) as c:
            return c.post(f"{API}/faculty/submissions/{sid}/reviews", json={"status": "ACCEPTED", "feedback": "ok"}, headers=auth(s.fac1))

    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(post, range(4)))
    assert sorted(r.status_code for r in results) == [201, 409, 409, 409], [r.text for r in results]
    assert len(reviews_in_db(s)) == 1 and s.sql("SELECT count(*) FROM notifications WHERE type NOT LIKE 'SUBMISSION_%'")[0][0] == 1


def test_expected_version_guard_rejects_a_stale_review(s):
    s.upload(data=pdf(100))
    s.upload(data=pdf(200))
    stale = review(s, "ACCEPTED", expected_version_no=1)
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "STALE_VERSION"
    assert review(s, "ACCEPTED", expected_version_no=2).json()["version_no"] == 2
    assert len(reviews_in_db(s)) == 1


def test_review_racing_an_upload_never_leaves_accepted_work_replaced(s, api_app):
    s.upload(data=pdf(100))
    sid = sub_id(s)

    def accept(_):
        with TestClient(api_app, raise_server_exceptions=False) as c:
            return c.post(f"{API}/faculty/submissions/{sid}/reviews", json={"status": "ACCEPTED"}, headers=auth(s.fac1))

    def upload(_):
        with TestClient(api_app, raise_server_exceptions=False) as c:
            return c.post(f"{API}/student/assignments/{s.aid}/submissions", files={"file": ("b.pdf", pdf(300), "application/pdf")}, headers=auth(s.stu_5a))

    with ThreadPoolExecutor(2) as pool:
        a, u = pool.submit(accept, 0), pool.submit(upload, 0)
        accepted, uploaded = a.result(), u.result()
    assert accepted.status_code == 201 and uploaded.status_code in (201, 409)
    latest = s.sql("SELECT max(version_no) FROM submission_versions")[0][0]
    # The ACCEPTED review is always attached to the version that is current, never to a version that was replaced.
    assert reviews_in_db(s)[0][4] == latest
    assert s.detail()["review_status"] == "ACCEPTED"
    assert s.upload(data=pdf(999)).status_code == 409


# --- privacy -----------------------------------------------------------------------------------------------------------


def test_a_student_sees_only_their_own_review_details(s):
    s.upload(data=pdf(100))
    s.upload(token=s.stu_5a2, data=pdf(150))
    review(s, "REVISION_REQUESTED", "PRIVATE feedback for the first student only.")
    mine = s.detail()
    assert mine["latest_feedback"].startswith("PRIVATE") and mine["reviews"][0]["feedback"].startswith("PRIVATE")
    other = s.detail(token=s.stu_5a2)
    assert other["review_status"] == "NOT_REVIEWED" and other["reviews"] == [] and other["latest_feedback"] is None
    assert "PRIVATE" not in str(other) and "PRIVATE" not in str(s.get("/student/assignments", s.stu_5a2).json())
    assert s.get(f"/student/assignments/{s.aid}", s.stu_5b).status_code == 404  # other section
    # Students and unrelated faculty cannot read the faculty view of someone else's submission.
    assert faculty_view(s, token=s.stu_5a2).status_code == 403
    for token in (s.fac2, s.fac49):
        assert faculty_view(s, token=token).status_code == 404
    assert "PRIVATE" in str(faculty_view(s).json())  # the teacher can


# --- the Deadline Integrity Timeline --------------------------------------------------------------------------------------------


def types(view):
    return [e["type"] for e in view["events"]]


def test_timeline_contains_every_real_event_in_order_with_actors_and_timestamps(s):
    t_change = NOW + timedelta(hours=1)
    s.at(t_change)
    new_deadline = DEADLINE + timedelta(days=1)
    assert s.patch(f"/faculty/assignments/{s.aid}/deadline", s.fac1, {"new_deadline": iso(new_deadline), "reason": "Lab outage"}).status_code == 200
    t_req = new_deadline + timedelta(hours=1)
    s.at(t_req)
    rid = s.ask().json()["id"]
    t_dec = t_req + timedelta(minutes=10)
    s.at(t_dec)
    assert s.decide(rid, window_hours=24, note="Certificate seen.").status_code == 200
    t_up = t_dec + timedelta(hours=2)
    s.at(t_up)
    assert s.upload(data=pdf(100)).status_code == 201
    t_rev = t_up + timedelta(hours=1)
    s.at(t_rev)
    assert review(s, "ACCEPTED", "Accepted with thanks.").status_code == 201

    view = faculty_view(s).json()
    assert types(view) == [
        "ASSIGNMENT_CREATED", "ASSIGNMENT_PUBLISHED", "DEADLINE_CHANGED", "LATE_REQUESTED",
        "REQUEST_APPROVED", "VERSION_UPLOADED", "REVIEW_RECORDED",
    ]
    ev = {e["type"]: e for e in view["events"]}
    at = {k: datetime.fromisoformat(v["at"]) for k, v in ev.items()}
    assert at["ASSIGNMENT_CREATED"] == NOW and at["ASSIGNMENT_PUBLISHED"] == NOW
    assert at["DEADLINE_CHANGED"] == t_change and at["LATE_REQUESTED"] == t_req
    assert at["REQUEST_APPROVED"] == t_dec and at["VERSION_UPLOADED"] == t_up and at["REVIEW_RECORDED"] == t_rev
    assert [datetime.fromisoformat(e["at"]) for e in view["events"]] == sorted(at.values())  # chronological
    assert ev["ASSIGNMENT_CREATED"]["actor"] == ev["DEADLINE_CHANGED"]["actor"] == ev["REQUEST_APPROVED"]["actor"] == ev["REVIEW_RECORDED"]["actor"]
    assert ev["LATE_REQUESTED"]["actor"] == ev["VERSION_UPLOADED"]["actor"] == s.get("/auth/me", s.stu_5a).json()["full_name"]
    d = ev["DEADLINE_CHANGED"]["data"]
    assert (d["old_deadline"], d["new_deadline"], d["reason"]) == (iso(DEADLINE), iso(new_deadline), "Lab outage")
    assert ev["LATE_REQUESTED"]["data"]["reason"] == REASON and ev["LATE_REQUESTED"]["data"]["deadline_at_request"] == iso(new_deadline)
    a = ev["REQUEST_APPROVED"]["data"]
    assert (a["window_hours"], a["note"]) == (24, "Certificate seen.") and a["window_start"] == iso(t_dec)
    v = ev["VERSION_UPLOADED"]["data"]
    assert (v["version_no"], v["upload_context"], v["timing_at_upload"], v["timing_now"]) == (1, "LATE_APPROVED", "LATE", "LATE")
    assert v["deadline_at_upload"] == iso(new_deadline) and v["late_request_id"] == rid and len(v["sha256"]) == 64
    r = ev["REVIEW_RECORDED"]["data"]
    assert (r["status"], r["version_no"], r["feedback"]) == ("ACCEPTED", 1, "Accepted with thanks.")
    assert all(e["derived"] is False for e in view["events"]) and all("IST" in e["summary"] for e in view["events"] if e["type"] not in ("REQUEST_REJECTED", "REVIEW_RECORDED"))

    # "Why this status" uses the same status functions and names the approver.
    why = view["why_this_status"]
    assert (why["timing"], why["headline"]) == ("LATE", "Late (approved)")
    assert any("window approved by" in line for line in why["lines"]) and any("Accepted" in line for line in why["lines"])


def test_the_student_sees_the_same_timeline_and_only_their_own(s):
    s.upload(data=pdf(100))
    review(s, "UNDER_REVIEW")
    mine = s.detail()
    assert types(mine) == types(faculty_view(s).json()) == ["ASSIGNMENT_CREATED", "ASSIGNMENT_PUBLISHED", "VERSION_UPLOADED", "REVIEW_RECORDED"]
    assert mine["events"] == faculty_view(s).json()["events"] and mine["why_this_status"]["headline"] == "On time"
    other = s.detail(token=s.stu_5a2)  # another student: no versions, no review, no foreign events
    assert types(other) == ["ASSIGNMENT_CREATED", "ASSIGNMENT_PUBLISHED"]
    assert "report.pdf" not in str(other["events"])


def test_timeline_is_read_only_and_reflects_the_database(s):
    s.upload(data=pdf(100))
    tables = ("reviews", "submission_versions", "late_requests", "deadline_changes", "notifications", "submissions")
    before = {t: s.count(t) for t in tables}
    first = faculty_view(s).json()
    assert faculty_view(s).json() == first and {t: s.count(t) for t in tables} == before
    # A review written straight into the database shows up: events come from real records, not from a side log.
    s.insert_review(sub_id(s), "ACCEPTED")
    assert "REVIEW_RECORDED" in types(faculty_view(s).json())  # (its DB-default timestamp is real time, not the frozen one)
    assert "REVIEW_RECORDED" not in types(first)


def test_equal_timestamps_are_ordered_by_event_order_then_version(s):
    s.upload(data=pdf(100))  # created, published and v1 all happen at NOW
    s.upload(data=pdf(200))
    view = faculty_view(s).json()
    assert types(view) == ["ASSIGNMENT_CREATED", "ASSIGNMENT_PUBLISHED", "VERSION_UPLOADED", "VERSION_UPLOADED"]
    assert [e["data"]["version_no"] for e in view["events"] if e["type"] == "VERSION_UPLOADED"] == [1, 2]


def test_deadline_snapshot_and_current_deadline_are_both_in_the_version_event(s):
    s.upload(data=pdf(100))
    s.at(DEADLINE + timedelta(minutes=1))
    review(s, "REVISION_REQUESTED", "Revise.")
    assert s.upload(data=pdf(200)).json()["upload_context"] == "REVISION"
    s.patch(f"/faculty/assignments/{s.aid}/deadline", s.fac1, {"new_deadline": iso(DEADLINE + timedelta(days=5))})
    view = faculty_view(s).json()
    v2 = [e for e in view["events"] if e["type"] == "VERSION_UPLOADED"][1]["data"]
    assert (v2["upload_context"], v2["timing_at_upload"], v2["timing_now"]) == ("REVISION", "LATE", "ON_TIME")
    assert v2["deadline_at_upload"] == iso(DEADLINE)
    assert "late at upload" in [e for e in view["events"] if e["type"] == "VERSION_UPLOADED"][1]["summary"]


def test_rejection_and_derived_markers_for_a_missing_student(s):
    rid = s.pending()
    s.at(DECIDED)
    s.decide(rid, decision="REJECT", note="No evidence.")
    s.at(DECIDED + timedelta(days=1))
    view = faculty_view(s).json()
    assert types(view) == ["ASSIGNMENT_CREATED", "ASSIGNMENT_PUBLISHED", "DEADLINE_PASSED_NO_SUBMISSION", "LATE_REQUESTED", "REQUEST_REJECTED"]
    marker = view["events"][2]
    assert marker["derived"] is True and datetime.fromisoformat(marker["at"]) == DEADLINE and marker["actor"] is None
    assert view["events"][4]["data"]["note"] == "No evidence."
    assert view["why_this_status"]["headline"] == "Missing" and any("rejected" in line for line in view["why_this_status"]["lines"])


def test_expired_window_marker_and_missing_explanation(s):
    s.approved(hours=1)
    s.at(DECIDED + timedelta(hours=1, seconds=1))
    view = faculty_view(s).json()
    assert types(view)[-1] == "REQUEST_WINDOW_EXPIRED" and view["events"][-1]["derived"] is True
    assert datetime.fromisoformat(view["events"][-1]["at"]) == DECIDED + timedelta(hours=1)
    assert any("closed without an upload" in line for line in view["why_this_status"]["lines"])
    s.at(DECIDED + timedelta(minutes=30))  # inside the window: no expiry marker yet
    assert "REQUEST_WINDOW_EXPIRED" not in types(faculty_view(s).json())


def test_why_this_status_for_on_time_pending_and_resubmission(s):
    pending = faculty_view(s).json()["why_this_status"]
    assert (pending["timing"], pending["headline"]) == ("PENDING", "Pending") and "No submission yet" in pending["lines"][0]
    s.at(DEADLINE)
    s.upload(data=pdf(100))
    assert "exactly at the deadline" in faculty_view(s).json()["why_this_status"]["lines"][0]
    s.upload(name="b.png", data=png(100))
    why = faculty_view(s).json()["why_this_status"]
    assert why["headline"] == "On time" and any("2 versions" in line for line in why["lines"])
    assert why["lines"][-1].startswith("Review status is separate from timing")


def test_timeline_scope_and_privacy(s):
    s.upload()
    path = f"/faculty/assignments/{s.aid}/students/{s.student_id('STU0101')}/timeline"
    assert s.get(path, s.fac1).status_code == 200
    for token in (s.fac2, s.fac49):
        assert s.get(path, token).status_code == 404
    assert s.get(path, s.stu_5a).status_code == 403
    assert s.client.get(f"{API}{path}").status_code == 401
    # A student of another section is not part of this assignment.
    assert s.get(f"/faculty/assignments/{s.aid}/students/{s.student_id('STU0118')}/timeline", s.fac1).status_code == 404
    assert s.get(f"/faculty/assignments/{s.aid}/students/{NO_ID}/timeline", s.fac1).status_code == 404
