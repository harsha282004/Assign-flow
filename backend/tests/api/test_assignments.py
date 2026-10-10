"""Phase 4: assignment management API (faculty + student), deadline policy and history."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

API = "/api/v1"
NOW = datetime(2026, 10, 11, 12, 0, tzinfo=UTC)


def iso(moment: datetime) -> str:
    return moment.isoformat()


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


class World:
    """Logged-in actors under a frozen clock: FAC001 (CS503/CSE-5A), FAC002 (other class), students."""

    def __init__(self, client, password, freeze_time):
        self.client, self.freeze_time = client, freeze_time
        freeze_time(NOW)
        self.fac1 = self._login("FACULTY", "FAC001", password)
        self.fac2 = self._login("FACULTY", "FAC013", password)  # teaches CSE-5C: no overlap with 5A / 5B
        self.fac49 = self._login("FACULTY", "QAFAC01", password)
        self.stu_5a = self._login("STUDENT", "STU0101", password)
        self.stu_5a2 = self._login("STUDENT", "STU0102", password)
        self.stu_5b = self._login("STUDENT", "STU0118", password)
        self.slot1 = self._slot(self.fac1)
        self.slot2 = self._slot(self.fac2)

    def _login(self, role, login_id, password) -> str:
        res = self.client.post(f"{API}/auth/login", json={"role": role, "login_id": login_id, "password": password})
        assert res.status_code == 200, res.text
        return res.json()["access_token"]

    def _slot(self, token) -> dict:
        return self.client.get(f"{API}/auth/me", headers=auth(token)).json()["teaching"][0]

    def payload(self, slot=None, **over) -> dict:
        slot = slot or self.slot1
        body = {
            "title": "DBMS Lab 4",
            "instructions": "Upload your normalisation report as a PDF.",
            "subject_id": slot["subject"]["id"],
            "section_id": slot["section"]["id"],
            "deadline": iso(NOW + timedelta(days=2)),
            "allowed_types": ["pdf"],
            "max_file_mb": 5,
            "publish": True,
        }
        body.update(over)
        return body

    def create(self, token=None, slot=None, **over):
        return self.client.post(f"{API}/faculty/assignments", json=self.payload(slot, **over), headers=auth(token or self.fac1))

    def get(self, path, token):
        return self.client.get(f"{API}{path}", headers=auth(token))

    def patch(self, path, token, body):
        return self.client.patch(f"{API}{path}", json=body, headers=auth(token))

    def post(self, path, token, body=None):
        return self.client.post(f"{API}{path}", json=body, headers=auth(token))


@pytest.fixture
def w(client, api_app, monkeypatch, test_password, freeze_time) -> World:
    # Long-lived tokens so tests can move the frozen clock days ahead without re-logging in.
    monkeypatch.setattr(api_app.state, "settings", api_app.state.settings.model_copy(update={"jwt_expire_minutes": 60 * 24 * 30}))
    return World(client, test_password, freeze_time)


# --- creating assignments ------------------------------------------------------------------------

def test_faculty_creates_and_publishes_assignment_in_own_class(w):
    res = w.create()
    assert res.status_code == 201, res.text
    a = res.json()
    assert a["status"] == "PUBLISHED" and a["title"] == "DBMS Lab 4"
    assert a["subject"]["code"] == "CS503" and a["section"]["label"] == "CSE-5A"
    assert a["deadline"] == a["original_deadline"]
    assert datetime.fromisoformat(a["deadline"]) == NOW + timedelta(days=2)
    assert datetime.fromisoformat(a["published_at"]) == NOW  # server clock, not client supplied
    assert a["allowed_types"] == ["pdf"] and a["max_file_mb"] == 5
    assert a["expected_students"] == 17 and a["deadline_history"] == []


def test_draft_is_hidden_from_students_until_published(w):
    draft = w.create(publish=False).json()
    assert draft["status"] == "DRAFT" and draft["published_at"] is None
    assert w.get("/student/assignments", w.stu_5a).json() == []
    assert w.get(f"/student/assignments/{draft['id']}", w.stu_5a).status_code == 404

    published = w.post(f"/faculty/assignments/{draft['id']}/publish", w.fac1)
    assert published.status_code == 200 and published.json()["status"] == "PUBLISHED"
    assert datetime.fromisoformat(published.json()["published_at"]) == NOW
    assert [a["id"] for a in w.get("/student/assignments", w.stu_5a).json()] == [draft["id"]]


def test_deadline_is_stored_in_utc_whatever_offset_is_sent(w):
    ist = datetime.fromisoformat("2026-10-13T18:00:00+05:30")
    a = w.create(deadline="2026-10-13T18:00:00+05:30").json()
    assert datetime.fromisoformat(a["deadline"]) == ist
    assert a["deadline"].endswith(("Z", "+00:00"))


def test_cannot_create_for_unauthorized_subject_or_section(w):
    res = w.create(slot=w.slot2)  # FAC001 using FAC002's class
    assert res.status_code == 403 and res.json()["error"]["code"] == "NOT_YOUR_CLASS"
    res = w.create(token=w.fac49)  # faculty with no classes
    assert res.status_code == 403 and res.json()["error"]["code"] == "NOT_YOUR_CLASS"
    # Right subject, wrong section (CS503 is taught to 5A by FAC001, but 5B belongs to someone else).
    other_section = w.get("/auth/me", w.stu_5b).json()["section"]["id"]
    res = w.create(section_id=other_section)
    assert res.status_code == 403
    # Unknown IDs get the same answer, so they cannot be used to probe.
    res = w.create(subject_id="00000000-0000-0000-0000-000000000000")
    assert res.status_code == 403


def test_students_and_anonymous_cannot_use_faculty_endpoints(w, client):
    assert client.post(f"{API}/faculty/assignments", json=w.payload()).status_code == 401
    assert client.get(f"{API}/faculty/assignments").status_code == 401
    res = w.create(token=w.stu_5a)
    assert res.status_code == 403 and res.json()["error"]["code"] == "FORBIDDEN"
    assert w.get("/faculty/assignments", w.stu_5a).status_code == 403


def test_faculty_cannot_use_student_endpoints(w):
    assert w.get("/student/assignments", w.fac1).status_code == 403


# --- input validation --------------------------------------------------------------------------------

@pytest.mark.parametrize(
    "override",
    [
        {"title": ""},
        {"title": "   "},
        {"title": "x" * 151},
        {"instructions": ""},
        {"instructions": "y" * 5001},
        {"allowed_types": []},
        {"allowed_types": ["exe"]},
        {"allowed_types": ["pdf"] * 7},
        {"max_file_mb": 0},
        {"max_file_mb": 11},
        {"deadline": "2026-10-13T18:00:00"},  # no timezone offset
        {"deadline": "not-a-date"},
        {"subject_id": "not-a-uuid"},
        {"status": "PUBLISHED"},  # unknown field: status is not client-controlled
        {"created_by": "00000000-0000-0000-0000-000000000000"},
        {"published_at": "2026-01-01T00:00:00Z"},
    ],
)
def test_invalid_create_input_is_rejected(w, override):
    res = w.create(**override)
    assert res.status_code == 422, (override, res.text)
    assert res.json()["error"]["code"] == "VALIDATION_ERROR"


def test_missing_required_fields_are_rejected(w):
    for field in ("title", "instructions", "subject_id", "section_id", "deadline", "allowed_types"):
        body = w.payload()
        del body[field]
        res = w.client.post(f"{API}/faculty/assignments", json=body, headers=auth(w.fac1))
        assert res.status_code == 422, field


def test_duplicate_types_are_collapsed_and_text_is_trimmed(w):
    a = w.create(allowed_types=["pdf", "zip", "pdf"], title="  Padded title  ").json()
    assert a["allowed_types"] == ["pdf", "zip"] and a["title"] == "Padded title"


def test_deadline_must_be_at_least_one_minute_in_the_future(w):
    too_soon = w.create(deadline=iso(NOW + timedelta(seconds=59)))
    assert too_soon.status_code == 422 and too_soon.json()["error"]["code"] == "DEADLINE_IN_PAST"
    assert w.create(deadline=iso(NOW)).status_code == 422
    assert w.create(deadline=iso(NOW - timedelta(days=1))).status_code == 422
    assert w.create(deadline=iso(NOW + timedelta(seconds=60))).status_code == 201  # boundary is allowed
    assert w.create(publish=False, deadline=iso(NOW + timedelta(seconds=30))).status_code == 422  # drafts too


# --- editing drafts -------------------------------------------------------------------------------------

def test_draft_can_be_edited_and_published_assignment_cannot(w):
    a = w.create(publish=False).json()
    res = w.patch(f"/faculty/assignments/{a['id']}", w.fac1, {"title": "Renamed", "max_file_mb": 8, "allowed_types": ["pdf", "docx"]})
    assert res.status_code == 200
    assert (res.json()["title"], res.json()["max_file_mb"], res.json()["allowed_types"]) == ("Renamed", 8, ["pdf", "docx"])

    new_deadline = NOW + timedelta(days=5)
    res = w.patch(f"/faculty/assignments/{a['id']}", w.fac1, {"deadline": iso(new_deadline)})
    body = res.json()
    assert datetime.fromisoformat(body["deadline"]) == new_deadline == datetime.fromisoformat(body["original_deadline"])
    assert body["deadline_history"] == []  # a draft has no history to preserve

    w.post(f"/faculty/assignments/{a['id']}/publish", w.fac1)
    res = w.patch(f"/faculty/assignments/{a['id']}", w.fac1, {"title": "Too late"})
    assert res.status_code == 409 and res.json()["error"]["code"] == "NOT_DRAFT"
    assert w.get(f"/faculty/assignments/{a['id']}", w.fac1).json()["title"] == "Renamed"


def test_draft_edit_validation_and_immutable_fields(w):
    a = w.create(publish=False).json()
    path = f"/faculty/assignments/{a['id']}"
    for bad in ({}, {"title": None}, {"title": ""}, {"max_file_mb": 99}, {"deadline": iso(NOW)}, {"deadline": "2026-10-13T18:00:00"},
                {"status": "PUBLISHED"}, {"subject_id": w.slot2["subject"]["id"]}, {"section_id": w.slot2["section"]["id"]},
                {"created_by": w.slot2["subject"]["id"]}):
        assert w.patch(path, w.fac1, bad).status_code == 422, bad
    unchanged = w.get(path, w.fac1).json()
    assert unchanged["title"] == "DBMS Lab 4" and unchanged["status"] == "DRAFT"


def test_faculty_cannot_edit_publish_or_view_another_facultys_assignment(w):
    own = w.create(publish=False).json()
    theirs = w.create(token=w.fac2, slot=w.slot2, publish=False).json()
    for token, assignment in ((w.fac2, own), (w.fac1, theirs), (w.fac49, own)):
        path = f"/faculty/assignments/{assignment['id']}"
        assert w.get(path, token).status_code == 404
        assert w.patch(path, token, {"title": "hijack"}).status_code == 404
        assert w.post(f"{path}/publish", token).status_code == 404
        assert w.patch(f"{path}/deadline", token, {"new_deadline": iso(NOW + timedelta(days=9))}).status_code == 404
    assert w.get(f"/faculty/assignments/{own['id']}", w.fac1).json()["title"] == "DBMS Lab 4"  # untouched
    assert w.get("/faculty/assignments/00000000-0000-0000-0000-000000000000", w.fac1).status_code == 404


# --- publishing ---------------------------------------------------------------------------------------------

def test_publish_rules(w):
    draft = w.create(publish=False, deadline=iso(NOW + timedelta(hours=1))).json()
    # By the time the faculty member tries to publish, the deadline has passed (or is < 1 minute away).
    w.freeze_time(NOW + timedelta(minutes=59, seconds=30))
    res = w.post(f"/faculty/assignments/{draft['id']}/publish", w.fac1)
    assert res.status_code == 422 and res.json()["error"]["code"] == "DEADLINE_IN_PAST"
    w.freeze_time(NOW)
    assert w.post(f"/faculty/assignments/{draft['id']}/publish", w.fac1).status_code == 200
    again = w.post(f"/faculty/assignments/{draft['id']}/publish", w.fac1)
    assert again.status_code == 409 and again.json()["error"]["code"] == "ALREADY_PUBLISHED"


# --- listing and viewing (faculty) -------------------------------------------------------------------------------

def test_faculty_lists_only_own_assignments_with_subject_section_and_real_counts(w):
    mine = w.create(title="Mine").json()
    w.create(token=w.fac2, slot=w.slot2, title="Theirs")
    listing = w.get("/faculty/assignments", w.fac1).json()
    assert [a["id"] for a in listing] == [mine["id"]]
    item = listing[0]
    assert item["subject"]["code"] == "CS503" and item["section"]["label"] == "CSE-5A"
    assert item["expected_students"] == 17
    assert "instructions" not in item
    assert w.get("/faculty/assignments", w.fac49).json() == []
    assert {a["title"] for a in w.get("/faculty/assignments", w.fac2).json()} == {"Theirs"}


def test_faculty_list_is_newest_first(w):
    first = w.create(title="First").json()
    w.freeze_time(NOW + timedelta(seconds=1))  # created_at is the server clock, which the tests freeze
    second = w.create(title="Second").json()
    assert [a["id"] for a in w.get("/faculty/assignments", w.fac1).json()] == [second["id"], first["id"]]


# --- students ------------------------------------------------------------------------------------------------------

def test_student_sees_own_section_assignment_with_pending_timing(w):
    a = w.create().json()
    listing = w.get("/student/assignments", w.stu_5a).json()
    assert len(listing) == 1
    item = listing[0]
    assert item["id"] == a["id"] and item["title"] == "DBMS Lab 4"
    assert item["subject"]["code"] == "CS503" and item["faculty_name"]
    assert item["timing"] == "PENDING"
    assert datetime.fromisoformat(item["deadline"]) == NOW + timedelta(days=2)
    detail = w.get(f"/student/assignments/{a['id']}", w.stu_5a).json()
    assert detail["instructions"] == "Upload your normalisation report as a PDF."
    assert detail["allowed_types"] == ["pdf"] and detail["section"]["label"] == "CSE-5A"
    # A classmate sees the same assignment.
    assert [x["id"] for x in w.get("/student/assignments", w.stu_5a2).json()] == [a["id"]]


def test_student_cannot_see_another_sections_assignments(w):
    a = w.create().json()
    assert w.get("/student/assignments", w.stu_5b).json() == []
    res = w.get(f"/student/assignments/{a['id']}", w.stu_5b)
    assert res.status_code == 404 and res.json()["error"]["code"] == "NOT_FOUND"
    other = w.create(token=w.fac2, slot=w.slot2).json()  # FAC002's class: a different semester entirely
    assert w.get(f"/student/assignments/{other['id']}", w.stu_5a).status_code == 404
    assert w.get("/student/assignments/00000000-0000-0000-0000-000000000000", w.stu_5a).status_code == 404


def test_student_list_is_ordered_by_deadline_and_timing_follows_server_clock(w):
    later = w.create(title="Later", deadline=iso(NOW + timedelta(days=5))).json()
    sooner = w.create(title="Sooner", deadline=iso(NOW + timedelta(days=1))).json()
    assert [a["id"] for a in w.get("/student/assignments", w.stu_5a).json()] == [sooner["id"], later["id"]]

    deadline = NOW + timedelta(days=1)
    w.freeze_time(deadline)  # exactly at the deadline: still pending
    items = {a["id"]: a for a in w.get("/student/assignments", w.stu_5a).json()}
    assert items[sooner["id"]]["timing"] == "PENDING"
    w.freeze_time(deadline + timedelta(seconds=1))
    items = {a["id"]: a for a in w.get("/student/assignments", w.stu_5a).json()}
    assert items[sooner["id"]]["timing"] == "MISSING" and items[later["id"]]["timing"] == "PENDING"


# --- deadline changes -------------------------------------------------------------------------------------------------

def change(w, assignment_id, new_deadline, token=None, reason=None):
    body = {"new_deadline": iso(new_deadline)}
    if reason is not None:
        body["reason"] = reason
    return w.patch(f"/faculty/assignments/{assignment_id}/deadline", token or w.fac1, body)


def test_deadline_change_records_history_and_keeps_original(w, seeded_engine: Engine):
    a = w.create().json()
    original = NOW + timedelta(days=2)
    w.freeze_time(NOW + timedelta(hours=3))
    new = NOW + timedelta(days=4)
    res = change(w, a["id"], new, reason="Lab server was down")
    assert res.status_code == 200, res.text
    body = res.json()
    assert datetime.fromisoformat(body["deadline"]) == new
    assert datetime.fromisoformat(body["original_deadline"]) == original  # never changes
    (entry,) = body["deadline_history"]
    assert datetime.fromisoformat(entry["old_deadline"]) == original
    assert datetime.fromisoformat(entry["new_deadline"]) == new
    assert datetime.fromisoformat(entry["changed_at"]) == NOW + timedelta(hours=3)  # server clock
    assert entry["changed_by_name"] and entry["reason"] == "Lab server was down"
    with Session(seeded_engine) as s:
        assert s.execute(text("SELECT count(*) FROM deadline_changes")).scalar() == 1


def test_history_is_preserved_in_order_across_several_changes(w):
    a = w.create().json()
    deadlines = [NOW + timedelta(days=d) for d in (3, 1, 6)]
    for i, d in enumerate(deadlines):
        w.freeze_time(NOW + timedelta(minutes=i + 1))
        assert change(w, a["id"], d, reason=f"change {i}").status_code == 200
    detail = w.get(f"/faculty/assignments/{a['id']}", w.fac1).json()
    history = detail["deadline_history"]
    assert [h["reason"] for h in history] == ["change 0", "change 1", "change 2"]
    olds = [datetime.fromisoformat(h["old_deadline"]) for h in history]
    news = [datetime.fromisoformat(h["new_deadline"]) for h in history]
    assert olds == [NOW + timedelta(days=2), deadlines[0], deadlines[1]]  # each old is the previous new
    assert news == deadlines
    assert datetime.fromisoformat(detail["deadline"]) == deadlines[-1]
    assert datetime.fromisoformat(detail["original_deadline"]) == NOW + timedelta(days=2)
    # Students see the current deadline and the original one.
    student = w.get(f"/student/assignments/{a['id']}", w.stu_5a).json()
    assert datetime.fromisoformat(student["deadline"]) == deadlines[-1]
    assert datetime.fromisoformat(student["original_deadline"]) == NOW + timedelta(days=2)


def test_deadline_can_be_extended_after_it_has_passed_but_not_moved_into_the_past(w):
    a = w.create().json()
    after_deadline = NOW + timedelta(days=3)
    w.freeze_time(after_deadline)
    assert w.get("/student/assignments", w.stu_5a).json()[0]["timing"] == "MISSING"
    res = change(w, a["id"], after_deadline)  # not after "now"
    assert res.status_code == 422 and res.json()["error"]["code"] == "DEADLINE_IN_PAST"
    assert change(w, a["id"], after_deadline - timedelta(seconds=1)).status_code == 422
    assert change(w, a["id"], after_deadline + timedelta(seconds=1)).status_code == 200  # extension after expiry
    assert w.get("/student/assignments", w.stu_5a).json()[0]["timing"] == "PENDING"  # recomputed
    assert len(w.get(f"/faculty/assignments/{a['id']}", w.fac1).json()["deadline_history"]) == 1  # failures left no rows


def test_deadline_change_requires_published_assignment(w):
    draft = w.create(publish=False).json()
    res = change(w, draft["id"], NOW + timedelta(days=9))
    assert res.status_code == 409 and res.json()["error"]["code"] == "NOT_PUBLISHED"


def test_deadline_change_authorization_and_validation(w):
    a = w.create().json()
    future = NOW + timedelta(days=9)
    assert change(w, a["id"], future, token=w.stu_5a).status_code == 403
    assert change(w, a["id"], future, token=w.fac2).status_code == 404
    assert w.client.patch(f"{API}/faculty/assignments/{a['id']}/deadline", json={"new_deadline": iso(future)}).status_code == 401
    path = f"/faculty/assignments/{a['id']}/deadline"
    for bad in ({}, {"new_deadline": "2026-10-20T10:00:00"}, {"new_deadline": "nope"},
                {"new_deadline": iso(future), "reason": "r" * 501},
                {"new_deadline": iso(future), "changed_at": iso(NOW)},  # timestamps are server controlled
                {"new_deadline": iso(future), "old_deadline": iso(NOW)}):
        assert w.patch(path, w.fac1, bad).status_code == 422, bad
    assert w.get(f"/faculty/assignments/{a['id']}", w.fac1).json()["deadline_history"] == []


def test_blank_reason_is_stored_as_none(w):
    a = w.create().json()
    res = change(w, a["id"], NOW + timedelta(days=9), reason="   ")
    assert res.json()["deadline_history"][0]["reason"] is None


# --- earlier phases keep working ------------------------------------------------------------------------------------------

def test_authentication_and_health_still_work(client, w):
    assert client.get(f"{API}/health").status_code == 200
    assert client.get(f"{API}/auth/me", headers=auth(w.fac1)).json()["login_id"] == "FAC001"
    assert client.post(f"{API}/auth/logout", headers=auth(w.fac1)).status_code == 204
    assert client.get(f"{API}/auth/me", headers=auth(w.fac1)).status_code == 401
