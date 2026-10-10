"""Phase 6: late-submission requests, decisions, approved windows and LATE_APPROVED uploads."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.services import orphans
from tests.api.test_assignments import API, NOW, auth, iso
from tests.api.test_submissions import DEADLINE, S
from tests.unit.test_file_validation import pdf

AFTER = DEADLINE + timedelta(hours=1)  # the student is MISSING from here on
DECIDED = AFTER + timedelta(minutes=10)
REASON = "I was in hospital with a fever and could not submit before the deadline."
NO_ID = "00000000-0000-0000-0000-000000000000"


class L(S):
    """Submission world plus helpers for the late-request workflow."""

    def at(self, moment: datetime) -> None:
        self.freeze_time(moment)

    def ask(self, token=None, aid=None, reason=REASON, **extra):
        return self.post(f"/student/assignments/{aid or self.aid}/late-request", token or self.stu_5a, {"reason": reason, **extra})

    def decide(self, rid, token=None, decision="APPROVE", **extra):
        return self.post(f"/faculty/late-requests/{rid}/decision", token or self.fac1, {"decision": decision, **extra})

    def row(self, login="STU0101"):
        rows = self.sql(
            "SELECT lr.status, lr.decided_by, lr.decided_at, lr.decision_note, lr.window_start, lr.window_end, "
            "lr.requested_at, lr.deadline_at_request, lr.reason, lr.id FROM late_requests lr "
            "JOIN users u ON u.id = lr.student_id WHERE u.login_id = :l",
            l=login,
        )
        return rows[0] if rows else None

    def pending(self, token=None) -> str:
        """A PENDING request created after the deadline (the clock is left at AFTER)."""
        self.at(AFTER)
        res = self.ask(token)
        assert res.status_code == 201, res.text
        return res.json()["id"]

    def approved(self, hours=24, token=None, **extra) -> str:
        """An APPROVED request: decided at DECIDED, window [DECIDED, DECIDED + hours]."""
        rid = self.pending(token)
        self.at(DECIDED)
        res = self.decide(rid, window_hours=hours, **extra)
        assert res.status_code == 200, res.text
        return rid

    def detail(self, token=None):
        return self.get(f"/student/assignments/{self.aid}", token or self.stu_5a).json()

    def versions(self):
        return self.sql(
            "SELECT version_no, upload_context, late_request_id, uploaded_at, deadline_at_upload FROM submission_versions ORDER BY version_no"
        )


@pytest.fixture
def s(client, api_app, monkeypatch, test_password, freeze_time, s3_client, settings, seeded_engine) -> L:
    monkeypatch.setattr(api_app.state, "settings", api_app.state.settings.model_copy(update={"jwt_expire_minutes": 60 * 24 * 30}))
    return L(client, test_password, freeze_time, s3_client=s3_client, bucket=settings.s3_bucket, engine=seeded_engine)


# --- creating requests -------------------------------------------------------------------------------------


def test_missing_student_creates_a_pending_request_with_server_timestamps(s):
    s.at(AFTER)
    res = s.ask()
    assert res.status_code == 201, res.text
    body = res.json()
    assert (body["status"], body["state"], body["reason"]) == ("PENDING", "PENDING", REASON)
    assert datetime.fromisoformat(body["requested_at"]) == AFTER
    assert datetime.fromisoformat(body["deadline_at_request"]) == DEADLINE
    assert body["decided_at"] is None and body["window_start"] is None and body["window_end"] is None

    status, decided_by, *_ = s.row()
    assert status == "PENDING" and decided_by is None
    detail = s.detail()
    assert detail["late_request"]["id"] == body["id"] and detail["can_request_late"] is False
    assert detail["request_status"] == "PENDING" and detail["timing"] == "MISSING" and detail["can_upload"] is False
    assert s.get("/student/assignments", s.stu_5a).json()[0]["request_status"] == "PENDING"
    roster = {r["student"]["login_id"]: r for r in s.get(f"/faculty/assignments/{s.aid}/roster", s.fac1).json()}
    assert roster["STU0101"]["request_status"] == "PENDING" and roster["STU0102"]["request_status"] == "NONE"


def test_a_missing_student_is_offered_the_request_and_others_are_not(s):
    assert s.detail()["can_request_late"] is False  # before the deadline
    s.at(AFTER)
    assert s.detail()["can_request_late"] is True
    s.at(DEADLINE)
    assert s.detail()["can_request_late"] is False  # exactly at the deadline is still PENDING


def test_client_supplied_server_fields_are_rejected(s):
    s.at(AFTER)
    for extra in (
        {"status": "APPROVED"},
        {"student_id": s.student_id("STU0102")},
        {"requested_at": "2000-01-01T00:00:00Z"},
        {"window_end": "2999-01-01T00:00:00Z"},
        {"decided_by": s.student_id("STU0101")},
    ):
        res = s.ask(**extra)
        assert res.status_code == 422 and res.json()["error"]["code"] == "VALIDATION_ERROR", extra
    assert s.count("late_requests") == 0


@pytest.mark.parametrize(
    "reason",
    ["too short", "x" * 19, "   " + "y" * 19 + "   ", "z" * 1001, "", "   ", "bad\x00nul character in the reason text"],
)
def test_invalid_reasons_are_rejected(s, reason):
    s.at(AFTER)
    res = s.ask(reason=reason)
    assert res.status_code == 422 and res.json()["error"]["code"] == "VALIDATION_ERROR", res.text
    assert s.count("late_requests") == 0


def test_missing_null_and_non_string_reasons_are_rejected(s):
    s.at(AFTER)
    path = f"/student/assignments/{s.aid}/late-request"
    for body in ({}, {"reason": None}, {"reason": 12345678901234567890}, {"reason": ["a"] * 30}):
        assert s.post(path, s.stu_5a, body).status_code == 422, body
    assert s.client.post(f"{API}{path}", content=b"not json", headers={**auth(s.stu_5a), "Content-Type": "application/json"}).status_code == 422
    assert s.count("late_requests") == 0


def test_reason_length_boundaries_and_trimming(s):
    s.at(AFTER)
    assert s.ask(reason="a" * 20).status_code == 201
    assert s.ask(token=s.stu_5a2, reason="  " + "b" * 1000 + "  ").status_code == 201  # trimmed to exactly 1000
    assert s.row("STU0101")[8] == "a" * 20 and s.row("STU0102")[8] == "b" * 1000


def test_reason_is_stored_and_returned_as_plain_text(s):
    s.at(AFTER)
    html = "<script>alert('x')</script> my laptop broke down yesterday"
    assert s.ask(reason=html).json()["reason"] == html  # never interpreted; the UI renders it as text
    assert s.row()[8] == html


def test_requests_are_only_allowed_while_missing(s):
    path = f"/student/assignments/{s.aid}/late-request"
    for moment in (NOW, DEADLINE - timedelta(seconds=1), DEADLINE):  # before and exactly at the deadline
        s.at(moment)
        res = s.post(path, s.stu_5a, {"reason": REASON})
        assert res.status_code == 409 and res.json()["error"]["code"] == "NOT_MISSING", moment
    s.at(DEADLINE + timedelta(seconds=1))
    assert s.post(path, s.stu_5a, {"reason": REASON}).status_code == 201
    assert s.count("late_requests") == 1


def test_a_student_who_already_submitted_cannot_request(s):
    assert s.upload().status_code == 201  # on time
    s.at(AFTER)
    res = s.ask()
    assert res.status_code == 409 and res.json()["error"]["code"] == "NOT_MISSING"
    assert s.count("late_requests") == 0
    # The same holds for work that is itself late (inserted directly: LATE cannot arise otherwise for this student).
    s.insert_first_version("STU0102", uploaded_at=AFTER, context="REGULAR")
    assert s.ask(token=s.stu_5a2).status_code == 409


def test_only_one_request_per_student_per_assignment(s):
    rid = s.pending()
    again = s.ask()
    assert again.status_code == 409 and again.json()["error"]["code"] == "REQUEST_EXISTS"
    assert s.count("late_requests") == 1 and s.detail()["late_request"]["id"] == rid
    # Still one request after a rejection: a rejected student cannot ask again.
    s.decide(rid, decision="REJECT")
    assert s.ask().json()["error"]["code"] == "REQUEST_EXISTS"
    assert s.count("late_requests") == 1


def test_the_limit_is_per_assignment_not_per_student(s):
    other = s.create(allowed_types=["pdf"]).json()  # same deadline, so the student is MISSING in both
    s.at(AFTER)
    assert s.ask().status_code == 201
    assert s.ask(aid=other["id"]).status_code == 201
    assert s.ask().status_code == 409 and s.ask(aid=other["id"]).status_code == 409
    assert s.count("late_requests") == 2


def test_wrong_role_scope_and_authentication(s):
    draft = s.create(publish=False, allowed_types=["pdf"]).json()
    s.at(AFTER)
    path = f"/student/assignments/{s.aid}/late-request"
    assert s.post(path, s.fac1, {"reason": REASON}).status_code == 403  # faculty
    assert s.client.post(f"{API}{path}", json={"reason": REASON}).status_code == 401  # anonymous
    assert s.ask(token=s.stu_5b).status_code == 404  # student of another section
    assert s.ask(aid=draft["id"]).status_code == 404  # drafts are invisible
    assert s.ask(aid=NO_ID).status_code == 404
    assert s.post("/student/assignments/not-a-uuid/late-request", s.stu_5a, {"reason": REASON}).status_code == 422
    assert s.count("late_requests") == 0


def test_concurrent_identical_requests_create_exactly_one(s, api_app):
    s.at(AFTER)

    def post(_):
        with TestClient(api_app, raise_server_exceptions=False) as c:
            return c.post(f"{API}/student/assignments/{s.aid}/late-request", json={"reason": REASON}, headers=auth(s.stu_5a))

    with ThreadPoolExecutor(5) as pool:
        results = list(pool.map(post, range(5)))
    assert sorted(r.status_code for r in results) == [201, 409, 409, 409, 409], [r.text for r in results]
    assert {r.json()["error"]["code"] for r in results if r.status_code == 409} == {"REQUEST_EXISTS"}
    assert s.count("late_requests") == 1


# --- faculty: list and inspect -----------------------------------------------------------------------------


def test_faculty_lists_and_inspects_requests_on_own_assignments_only(s):
    rid = s.pending()
    s.ask(token=s.stu_5a2)
    listing = s.get("/faculty/late-requests", s.fac1)
    assert listing.status_code == 200
    items = listing.json()
    assert len(items) == 2 and {i["student"]["login_id"] for i in items} == {"STU0101", "STU0102"}
    item = next(i for i in items if i["id"] == rid)
    assert item["reason"] == REASON and item["state"] == "PENDING" and item["assignment"]["id"] == s.aid
    assert item["assignment"]["subject"]["code"] and item["assignment"]["section"]["label"]
    assert datetime.fromisoformat(item["current_deadline"]) == DEADLINE

    detail = s.get(f"/faculty/late-requests/{rid}", s.fac1)
    assert detail.status_code == 200
    d = detail.json()
    assert d["submission_timing"] == "MISSING" and d["versions"] == [] and d["reason"] == REASON

    # Other faculty see nothing and cannot inspect it; students cannot use the faculty endpoints at all.
    assert s.get("/faculty/late-requests", s.fac2).json() == []
    assert s.get("/faculty/late-requests", s.fac49).json() == []
    for token in (s.fac2, s.fac49):
        assert s.get(f"/faculty/late-requests/{rid}", token).status_code == 404
    assert s.get(f"/faculty/late-requests/{NO_ID}", s.fac1).status_code == 404
    assert s.get("/faculty/late-requests", s.stu_5a).status_code == 403
    assert s.get(f"/faculty/late-requests/{rid}", s.stu_5a).status_code == 403
    assert s.client.get(f"{API}/faculty/late-requests").status_code == 401


def test_list_filters_ordering_and_assignment_filter(s):
    first = s.pending()
    s.at(AFTER + timedelta(minutes=5))
    second = s.ask(token=s.stu_5a2).json()["id"]
    assert [i["id"] for i in s.get("/faculty/late-requests?status=PENDING", s.fac1).json()] == [first, second]  # oldest first
    s.at(DECIDED)
    assert s.decide(first, window_hours=1).status_code == 200
    assert [i["id"] for i in s.get("/faculty/late-requests", s.fac1).json()] == [second, first]  # pending before decided
    assert [i["id"] for i in s.get("/faculty/late-requests?status=APPROVED", s.fac1).json()] == [first]
    assert s.get("/faculty/late-requests?status=REJECTED", s.fac1).json() == []
    assert [i["id"] for i in s.get(f"/faculty/late-requests?assignment_id={s.aid}", s.fac1).json()] == [second, first]
    assert s.get(f"/faculty/late-requests?assignment_id={NO_ID}", s.fac1).json() == []
    assert s.get("/faculty/late-requests?status=NONSENSE", s.fac1).status_code == 422
    s.at(DECIDED + timedelta(hours=1, seconds=1))
    assert [i["id"] for i in s.get("/faculty/late-requests?status=EXPIRED", s.fac1).json()] == [first]
    assert s.get("/faculty/late-requests?status=APPROVED", s.fac1).json() == []


# --- faculty: decisions --------------------------------------------------------------------------------------


def test_approval_records_server_decision_time_and_default_24_hour_window(s):
    rid = s.pending()
    s.at(DECIDED)
    res = s.decide(rid, note="Medical certificate seen.")
    assert res.status_code == 200, res.text
    body = res.json()
    assert (body["status"], body["state"]) == ("APPROVED", "APPROVED")
    assert datetime.fromisoformat(body["decided_at"]) == DECIDED
    assert datetime.fromisoformat(body["window_start"]) == DECIDED
    assert datetime.fromisoformat(body["window_end"]) == DECIDED + timedelta(hours=24)
    assert body["decision_note"] == "Medical certificate seen." and body["decided_by_name"]

    status, decided_by, decided_at, note, w_start, w_end, *_ = s.row()
    assert status == "APPROVED" and str(decided_by) == s.student_id("FAC001")
    assert (decided_at, w_start, w_end) == (DECIDED, DECIDED, DECIDED + timedelta(hours=24)) and note == "Medical certificate seen."

    student_view = s.detail()["late_request"]
    assert student_view["state"] == "APPROVED" and datetime.fromisoformat(student_view["window_end"]) == DECIDED + timedelta(hours=24)
    assert student_view["decision_note"] == "Medical certificate seen."
    assert s.detail()["can_upload"] is True  # decided_at <= now <= window_end


@pytest.mark.parametrize("hours", [1, 2, 24, 72])
def test_window_hours_are_honoured_between_1_and_72(s, hours):
    rid = s.pending()
    s.at(DECIDED)
    res = s.decide(rid, window_hours=hours)
    assert datetime.fromisoformat(res.json()["window_end"]) == DECIDED + timedelta(hours=hours)


@pytest.mark.parametrize("hours", [0, -1, 73, 1000, 1.5, 24.0, "24", "x", True])
def test_invalid_window_hours_are_rejected_and_nothing_changes(s, hours):
    rid = s.pending()
    res = s.decide(rid, window_hours=hours)
    assert res.status_code == 422, (hours, res.text)
    assert s.row()[0] == "PENDING"


def test_invalid_decision_bodies_are_rejected(s):
    rid = s.pending()
    path = f"/faculty/late-requests/{rid}/decision"
    bad_bodies = [
        {},
        {"decision": "MAYBE"},
        {"decision": "approve"},
        {"decision": "REJECT", "window_hours": 24},  # a window only belongs to an approval
        {"decision": "APPROVE", "note": "n" * 501},
        {"decision": "APPROVE", "note": "bad\x00note"},
        {"decision": "APPROVE", "window_start": iso(AFTER)},  # window times are server-controlled
        {"decision": "APPROVE", "window_end": iso(AFTER + timedelta(days=90))},
        {"decision": "APPROVE", "decided_at": "2000-01-01T00:00:00Z"},
        {"decision": "APPROVE", "status": "APPROVED"},
        {"decision": "APPROVE", "decided_by": s.student_id("STU0101")},
    ]
    for body in bad_bodies:
        assert s.post(path, s.fac1, body).status_code == 422, body
    assert s.client.post(f"{API}{path}", content=b"{", headers={**auth(s.fac1), "Content-Type": "application/json"}).status_code == 422
    assert s.row()[0] == "PENDING"


def test_note_boundaries_and_blank_note(s):
    first = s.pending()
    s.ask(token=s.stu_5a2)
    assert s.decide(first, note="n" * 500).json()["decision_note"] == "n" * 500
    second = s.get("/faculty/late-requests?status=PENDING", s.fac1).json()[0]["id"]
    assert s.decide(second, decision="REJECT", note="   ").json()["decision_note"] is None


def test_rejection_is_final_and_leaves_the_student_missing(s):
    rid = s.pending()
    s.at(DECIDED)
    res = s.decide(rid, decision="REJECT", note="No evidence provided.")
    assert res.status_code == 200
    body = res.json()
    assert (body["status"], body["state"], body["window_start"], body["window_end"]) == ("REJECTED", "REJECTED", None, None)
    assert datetime.fromisoformat(body["decided_at"]) == DECIDED and body["decision_note"] == "No evidence provided."

    detail = s.detail()
    assert detail["timing"] == "MISSING" and detail["can_upload"] is False and detail["can_request_late"] is False
    assert detail["late_request"]["status"] == "REJECTED"
    upload = s.upload()
    assert upload.status_code == 409 and upload.json()["error"]["code"] == "DEADLINE_PASSED"
    assert s.objects() == [] and s.count("submissions") == 0


def test_unauthorized_faculty_and_students_cannot_decide(s):
    rid = s.pending()
    for token in (s.fac2, s.fac49):  # other classes
        res = s.decide(rid, token=token)
        assert res.status_code == 404, res.text
    assert s.decide(rid, token=s.stu_5a).status_code == 403  # the requester themselves
    assert s.decide(rid, token=s.stu_5b).status_code == 403
    assert s.client.post(f"{API}/faculty/late-requests/{rid}/decision", json={"decision": "APPROVE"}).status_code == 401
    assert s.decide(NO_ID).status_code == 404
    assert s.post("/faculty/late-requests/not-a-uuid/decision", s.fac1, {"decision": "APPROVE"}).status_code == 422
    status, decided_by, decided_at, *_ = s.row()
    assert status == "PENDING" and decided_by is None and decided_at is None
    assert s.decide(rid).status_code == 200  # the owning faculty still can


def test_a_decided_request_cannot_be_decided_again(s):
    rid = s.approved(hours=2)
    before = s.row()
    s.at(DECIDED + timedelta(minutes=30))
    for res in (s.decide(rid, window_hours=72), s.decide(rid, decision="REJECT")):
        assert res.status_code == 409 and res.json()["error"]["code"] == "ALREADY_DECIDED"
    assert s.row() == before  # the original decision is untouched

    other = s.ask(token=s.stu_5a2).json()["id"]
    assert s.decide(other, decision="REJECT").status_code == 200
    assert s.decide(other).json()["error"]["code"] == "ALREADY_DECIDED"
    assert s.row("STU0102")[0] == "REJECTED"


@pytest.mark.parametrize("decisions", [("APPROVE", "REJECT"), ("REJECT", "APPROVE"), ("APPROVE",) * 4])
def test_concurrent_decisions_have_exactly_one_winner(s, api_app, decisions):
    rid = s.pending()
    s.at(DECIDED)

    def post(decision):
        with TestClient(api_app, raise_server_exceptions=False) as c:
            return decision, c.post(f"{API}/faculty/late-requests/{rid}/decision", json={"decision": decision}, headers=auth(s.fac1))

    with ThreadPoolExecutor(len(decisions)) as pool:
        results = list(pool.map(post, decisions))
    winners = [(d, r) for d, r in results if r.status_code == 200]
    losers = [r for _, r in results if r.status_code != 200]
    assert len(winners) == 1, [(d, r.status_code, r.text) for d, r in results]
    assert all(r.status_code == 409 and r.json()["error"]["code"] == "ALREADY_DECIDED" for r in losers)
    status, _, decided_at, _, w_start, w_end, *_ = s.row()
    assert status == ("APPROVED" if winners[0][0] == "APPROVE" else "REJECTED")
    assert decided_at == DECIDED and ((w_start, w_end) == (DECIDED, DECIDED + timedelta(hours=24)) if status == "APPROVED" else (w_start, w_end) == (None, None))


# --- uploads: the approved window is enforced by the server ----------------------------------------------------


def test_no_upload_while_pending_or_without_any_request(s):
    s.at(AFTER)
    assert s.upload().json()["error"]["code"] == "DEADLINE_PASSED"  # no request at all
    s.ask()
    res = s.upload()  # request not decided yet
    assert res.status_code == 409 and res.json()["error"]["code"] == "DEADLINE_PASSED"
    assert s.objects() == [] and s.count("submissions") == 0


def test_upload_inside_the_window_is_late_approved_and_never_on_time(s):
    rid = s.approved(hours=24)
    s.at(DECIDED + timedelta(hours=5))
    res = s.upload(data=pdf(321))
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["upload_context"] == "LATE_APPROVED"
    assert (body["version_timing"], body["submission_timing"]) == ("LATE", "LATE")
    assert datetime.fromisoformat(body["uploaded_at"]) == DECIDED + timedelta(hours=5)  # the real time, never backdated
    assert datetime.fromisoformat(body["deadline_at_upload"]) == DEADLINE  # the deadline snapshot

    (version,) = s.versions()
    assert version[1] == "LATE_APPROVED" and str(version[2]) == rid
    assert version[3] == DECIDED + timedelta(hours=5) and version[4] == DEADLINE

    detail = s.detail()
    assert (detail["timing"], detail["late_approved"], detail["request_status"]) == ("LATE", True, "USED")
    assert detail["late_request"]["state"] == "USED" and detail["versions"][0]["upload_context"] == "LATE_APPROVED"
    assert detail["versions"][0]["timing_at_upload"] == "LATE"
    listing = s.get("/student/assignments", s.stu_5a).json()[0]
    assert (listing["timing"], listing["late_approved"]) == ("LATE", True)
    roster = {r["student"]["login_id"]: r for r in s.get(f"/faculty/assignments/{s.aid}/roster", s.fac1).json()}
    assert (roster["STU0101"]["timing"], roster["STU0101"]["late_approved"], roster["STU0101"]["request_status"]) == ("LATE", True, "USED")
    assert roster["STU0102"]["timing"] == "MISSING" and roster["STU0102"]["late_approved"] is False
    assert s.get(f"/faculty/assignments/{s.aid}/roster?status=LATE", s.fac1).json()[0]["student"]["login_id"] == "STU0101"
    faculty_view = s.get(f"/faculty/assignments/{s.aid}/students/{s.student_id('STU0101')}/timeline", s.fac1).json()
    assert faculty_view["timing"] == "LATE" and faculty_view["late_approved"] is True and faculty_view["request_status"] == "USED"
    assert s.get(f"/faculty/late-requests/{rid}", s.fac1).json()["state"] == "USED"


def test_window_boundaries_are_inclusive(s):
    s.approved(hours=2)
    # Exactly at window_start (the decision instant) and exactly at window_end are both inside the window.
    s.at(DECIDED)
    assert s.upload(data=pdf(111)).status_code == 201
    s.at(DECIDED + timedelta(hours=2))
    assert s.upload(data=pdf(222)).status_code == 201  # exactly window_end: a second LATE_APPROVED version
    s.at(DECIDED + timedelta(hours=2, seconds=1))
    res = s.upload(data=pdf(333))
    assert res.status_code == 409 and res.json()["error"]["code"] == "DEADLINE_PASSED"
    assert [v[1] for v in s.versions()] == ["LATE_APPROVED", "LATE_APPROVED"] and s.count("submission_versions") == 2


def test_expired_window_blocks_upload_and_request_shows_expired(s):
    rid = s.approved(hours=1)
    s.at(DECIDED + timedelta(hours=1))
    assert s.detail()["late_request"]["state"] == "APPROVED" and s.detail()["can_upload"] is True  # last instant
    s.at(DECIDED + timedelta(hours=1, seconds=1))
    detail = s.detail()
    assert detail["late_request"]["state"] == "EXPIRED" and detail["request_status"] == "EXPIRED"
    assert detail["timing"] == "MISSING" and detail["can_upload"] is False and detail["can_request_late"] is False
    res = s.upload()
    assert res.status_code == 409 and res.json()["error"]["code"] == "DEADLINE_PASSED"
    assert s.objects() == [] and s.count("submissions") == 0 and s.count("submission_versions") == 0
    assert s.ask().json()["error"]["code"] == "REQUEST_EXISTS"  # no second request after expiry
    assert s.get(f"/faculty/late-requests/{rid}", s.fac1).json()["state"] == "EXPIRED"
    assert s.row()[0] == "APPROVED"  # EXPIRED is derived; the stored status never changes


def test_further_uploads_in_the_window_are_late_approved_versions_and_timing_follows_the_first(s):
    rid = s.approved(hours=24)
    s.at(DECIDED + timedelta(hours=1))
    assert s.upload(data=pdf(100)).status_code == 201
    s.at(DECIDED + timedelta(hours=3))
    res = s.upload(data=pdf(200))
    assert res.status_code == 201 and res.json()["version_no"] == 2 and res.json()["upload_context"] == "LATE_APPROVED"
    assert s.upload(data=pdf(200)).status_code == 409  # identical to the latest version
    assert [(v[0], v[1], str(v[2])) for v in s.versions()] == [(1, "LATE_APPROVED", rid), (2, "LATE_APPROVED", rid)]
    detail = s.detail()
    assert detail["is_resubmitted"] is True and detail["timing"] == "LATE" and detail["late_approved"] is True
    s.at(DECIDED + timedelta(hours=24, seconds=1))
    assert s.upload(data=pdf(300)).status_code == 409  # window over: no more versions
    assert s.count("submission_versions") == 2


def test_late_request_does_not_let_a_student_replace_work_submitted_on_time(s):
    # Created while MISSING, then the deadline is extended and the student submits regularly.
    rid = s.pending()
    s.at(DECIDED)
    assert s.decide(rid, window_hours=72).status_code == 200
    new_deadline = DECIDED + timedelta(hours=2)
    assert s.patch(f"/faculty/assignments/{s.aid}/deadline", s.fac1, {"new_deadline": iso(new_deadline)}).status_code == 200
    s.at(DECIDED + timedelta(hours=1))
    first = s.upload(data=pdf(100))
    assert first.status_code == 201 and first.json()["upload_context"] == "REGULAR" and first.json()["version_timing"] == "ON_TIME"
    # The new deadline passes; the approved window is still open, but this is existing regular work (rule 6).
    s.at(new_deadline + timedelta(minutes=1))
    res = s.upload(data=pdf(200))
    assert res.status_code == 409 and res.json()["error"]["code"] == "DEADLINE_PASSED"
    d = s.detail()
    assert d["can_upload"] is False and d["timing"] == "ON_TIME" and d["late_approved"] is False
    assert s.count("submission_versions") == 1


def test_an_extended_deadline_takes_precedence_over_the_window(s):
    rid = s.approved(hours=24)
    new_deadline = DECIDED + timedelta(hours=6)
    assert s.patch(f"/faculty/assignments/{s.aid}/deadline", s.fac1, {"new_deadline": iso(new_deadline)}).status_code == 200
    s.at(DECIDED + timedelta(hours=1))  # inside both the window and the new deadline
    res = s.upload()
    assert res.status_code == 201 and res.json()["upload_context"] == "REGULAR" and res.json()["version_timing"] == "ON_TIME"
    assert s.versions()[0][2] is None  # a REGULAR version is not linked to the request
    assert s.get(f"/faculty/late-requests/{rid}", s.fac1).json()["state"] == "APPROVED"  # not "used"


def test_deadline_change_never_rewrites_the_request(s):
    rid = s.pending()
    before = s.row()
    s.at(AFTER + timedelta(minutes=1))
    new_deadline = AFTER + timedelta(days=3)
    assert s.patch(f"/faculty/assignments/{s.aid}/deadline", s.fac1, {"new_deadline": iso(new_deadline)}).status_code == 200
    assert s.row() == before and s.row()[7] == DEADLINE  # deadline_at_request keeps the deadline of that moment
    detail = s.get(f"/faculty/late-requests/{rid}", s.fac1).json()
    assert datetime.fromisoformat(detail["current_deadline"]) == new_deadline
    assert datetime.fromisoformat(detail["deadline_at_request"]) == DEADLINE
    # The student is PENDING again and may upload normally; the pending request can still be decided.
    assert s.detail()["timing"] == "PENDING" and s.detail()["can_upload"] is True
    assert s.upload().json()["upload_context"] == "REGULAR"
    assert s.decide(rid).status_code == 200


def test_the_client_cannot_claim_a_late_approved_upload(s):
    s.at(AFTER)
    rid = s.pending()
    res = s.upload(upload_context="LATE_APPROVED", late_request_id=rid, status="ON_TIME")
    assert res.status_code == 409  # not approved: the form fields are ignored
    s.at(DECIDED)
    s.decide(rid, decision="REJECT")
    assert s.upload(upload_context="LATE_APPROVED", late_request_id=rid).status_code == 409
    assert s.count("submission_versions") == 0 and s.objects() == []


def test_an_approval_only_helps_its_own_student_and_assignment(s):
    other = s.create(allowed_types=["pdf"], deadline=iso(DEADLINE)).json()  # created before the clock moves on
    s.approved(hours=24)
    s.at(DECIDED + timedelta(hours=1))
    assert s.upload(token=s.stu_5a2).status_code == 409  # a classmate cannot use it
    assert s.upload(aid=other["id"]).status_code == 409  # another assignment cannot use it
    assert s.upload(token=s.stu_5b).status_code == 404
    assert s.count("submission_versions") == 0 and s.objects() == []
    assert s.upload().status_code == 201  # the approved student still can


def test_accepted_work_cannot_be_replaced_inside_the_window(s):
    s.approved(hours=24)
    s.at(DECIDED + timedelta(hours=1))
    assert s.upload(data=pdf(100)).status_code == 201
    s.insert_review(str(s.sql("SELECT id FROM submissions")[0][0]), "ACCEPTED")
    res = s.upload(data=pdf(200))
    assert res.status_code == 409 and res.json()["error"]["code"] == "SUBMISSION_ACCEPTED"
    assert s.count("submission_versions") == 1


def test_revision_after_the_window_is_a_revision_upload(s):
    s.approved(hours=1)
    s.at(DECIDED + timedelta(minutes=10))
    assert s.upload(data=pdf(100)).status_code == 201
    sub_id = str(s.sql("SELECT id FROM submissions")[0][0])
    s.insert_review(sub_id, "REVISION_REQUESTED")
    s.at(DECIDED + timedelta(hours=5))  # well after window_end
    res = s.upload(data=pdf(200))
    assert res.status_code == 201 and res.json()["upload_context"] == "REVISION"
    assert [v[1] for v in s.versions()] == ["LATE_APPROVED", "REVISION"] and s.versions()[1][2] is None


def test_decision_racing_with_an_upload_is_always_consistent(s, api_app):
    rid = s.pending()
    s.at(DECIDED)

    def decide(_):
        with TestClient(api_app, raise_server_exceptions=False) as c:
            return c.post(f"{API}/faculty/late-requests/{rid}/decision", json={"decision": "APPROVE"}, headers=auth(s.fac1))

    def upload(_):
        with TestClient(api_app, raise_server_exceptions=False) as c:
            return c.post(
                f"{API}/student/assignments/{s.aid}/submissions",
                files={"file": ("late.pdf", pdf(500), "application/pdf")},
                headers=auth(s.stu_5a),
            )

    with ThreadPoolExecutor(2) as pool:
        d, u = pool.submit(decide, 0), pool.submit(upload, 0)
        decision, uploaded = d.result(), u.result()
    assert decision.status_code == 200
    if uploaded.status_code == 201:  # the approval landed first: a proper LATE_APPROVED version
        assert uploaded.json()["upload_context"] == "LATE_APPROVED" and s.count("submission_versions") == 1
    else:  # the upload was evaluated before the approval: refused, and nothing was written or left in storage
        assert uploaded.status_code == 409 and s.count("submission_versions") == 0 and s.objects() == []
    # Whatever happened, a retry now succeeds or is a duplicate, never an inconsistent state.
    retry = s.upload(data=pdf(500))
    assert retry.status_code in (201, 409)
    assert s.count("submission_versions") == 1 and len(s.objects()) == 1


def test_concurrent_uploads_in_the_window_get_distinct_late_approved_versions(s, api_app):
    rid = s.approved(hours=24)
    s.at(DECIDED + timedelta(hours=1))

    def post(i):
        with TestClient(api_app, raise_server_exceptions=False) as c:
            return c.post(
                f"{API}/student/assignments/{s.aid}/submissions",
                files={"file": (f"f{i}.pdf", pdf(100 + i), "application/pdf")},
                headers=auth(s.stu_5a),
            )

    with ThreadPoolExecutor(3) as pool:
        results = list(pool.map(post, range(3)))
    assert all(r.status_code == 201 for r in results), [r.text for r in results]
    assert sorted(v[0] for v in s.versions()) == [1, 2, 3]
    assert {v[1] for v in s.versions()} == {"LATE_APPROVED"} and {str(v[2]) for v in s.versions()} == {rid}


# --- consistency and earlier phases -----------------------------------------------------------------------------


def test_database_rejects_inconsistent_request_rows(s):
    rid = s.pending()
    for statement in (
        "UPDATE late_requests SET status = 'APPROVED' WHERE id = :i",  # decision and window fields missing
        "UPDATE late_requests SET status = 'REJECTED', decided_by = NULL, decided_at = NULL WHERE id = :i",
        "UPDATE late_requests SET reason = 'too short' WHERE id = :i",
    ):
        with Session(s.engine) as db, pytest.raises(IntegrityError):
            db.execute(text(statement), dict(i=rid))
            db.commit()
    assert s.row()[0] == "PENDING"


def test_storage_and_database_stay_consistent_around_late_uploads(s):
    s.approved(hours=24)
    s.at(DECIDED + timedelta(hours=1))
    s.upload(data=pdf(100))
    s.upload(data=pdf(200))
    assert s.upload(token=s.stu_5a2).status_code == 409  # refused uploads leave nothing behind
    with Session(s.engine) as db:
        assert orphans.find_orphans(s.s3, s.bucket, db) == [] and orphans.find_dangling(s.s3, s.bucket, db) == []


def test_seed_accounts_and_earlier_phases_are_untouched(s):
    s.approved(hours=24)
    assert s.sql("SELECT count(*) FROM users WHERE login_id LIKE 'STU%'")[0][0] == 50  # the configured dataset
    assert s.sql("SELECT count(*) FROM users WHERE login_id LIKE 'FAC%' AND role = 'FACULTY'")[0][0] == 15
    assert s.client.get(f"{API}/health").json() == {"status": "ok", "db": "ok", "redis": "ok", "storage": "ok"}
    assert s.client.get(f"{API}/auth/me", headers=auth(s.stu_5a)).json()["login_id"] == "STU0101"
