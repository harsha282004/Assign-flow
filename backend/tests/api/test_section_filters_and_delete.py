"""Section / subject filtering of the faculty dashboard and board, and safe deletion of assignments."""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services import assignment_deletion, orphans
from tests.api.test_assignments import API, NOW, World, auth, iso
from tests.api.test_attachments import attach, draft, pdf, publish
from tests.api.test_submissions import S

# --- section filtering ------------------------------------------------------------------------------------
# FAC002 teaches CS501 in CSE-5A and CS504 in CSE-5C; FAC007 teaches CS501 in CSE-5B (see seed_config).
# CSE-5A has STU0101-STU0117 (17), CSE-5B STU0118-STU0134 (17), CSE-5C STU0135-STU0150 (16).


class F(World):
    def __init__(self, client, password, freeze_time):
        super().__init__(client, password, freeze_time)
        self.fac2_5a_5c = self._login("FACULTY", "FAC002", password)
        self.fac_5b = self._login("FACULTY", "FAC007", password)
        self.stu_5c = self._login("STUDENT", "STU0135", password)
        me = self.client.get(f"{API}/auth/me", headers=auth(self.fac2_5a_5c)).json()
        self.slots = {t["section"]["label"]: t for t in me["teaching"]}
        assert set(self.slots) == {"CSE-5A", "CSE-5C"}

    def make(self, label, token=None, **over):
        res = self.create(token=token or self.fac2_5a_5c, slot=self.slots[label], **over)
        assert res.status_code == 201, res.text
        return res.json()

    def ov(self, token=None, **params):
        return self.client.get(f"{API}/faculty/overview", params=params, headers=auth(token or self.fac2_5a_5c))

    def ov_students(self, token=None, **params):
        return self.client.get(f"{API}/faculty/overview/students", params=params, headers=auth(token or self.fac2_5a_5c))

    def sec(self, label):
        return self.slots[label]["section"]["id"]

    def subj(self, label):
        return self.slots[label]["subject"]["id"]


@pytest.fixture
def f(client, api_app, monkeypatch, test_password, freeze_time) -> F:
    monkeypatch.setattr(
        api_app.state, "settings", api_app.state.settings.model_copy(update={"jwt_expire_minutes": 60 * 24 * 30})
    )
    return F(client, test_password, freeze_time)


def test_each_section_has_its_own_counts_and_the_combined_total_is_their_sum(f):
    f.make("CSE-5A")
    f.make("CSE-5C")
    a, c = f.ov(section_id=f.sec("CSE-5A")).json(), f.ov(section_id=f.sec("CSE-5C")).json()
    both = f.ov().json()
    assert a["totals"]["expected"] == 17 and c["totals"]["expected"] == 16
    assert [x["assignment"]["section"]["label"] for x in a["assignments"]] == ["CSE-5A"]
    assert [x["assignment"]["section"]["label"] for x in c["assignments"]] == ["CSE-5C"]
    assert both["totals"]["expected"] == 33
    for field in ("expected", "pending", "missing", "submitted", "on_time", "late", "requests_pending"):
        assert both["totals"][field] == a["totals"][field] + c["totals"][field], field
    assert a["totals"]["pending"] == 17 and c["totals"]["pending"] == 16 and both["totals"]["missing"] == 0


def test_subject_and_section_filters_apply_together(f):
    f.make("CSE-5A")  # CS501 in 5A
    f.make("CSE-5C")  # CS504 in 5C
    right = f.ov(subject_id=f.subj("CSE-5C"), section_id=f.sec("CSE-5C")).json()
    assert right["totals"]["expected"] == 16 and len(right["assignments"]) == 1
    only_subject = f.ov(subject_id=f.subj("CSE-5A")).json()
    assert only_subject["totals"]["expected"] == 17  # CS501 is taught to 5A only
    crossed = f.ov(subject_id=f.subj("CSE-5A"), section_id=f.sec("CSE-5C")).json()  # I teach both, never together
    assert crossed["totals"]["expected"] == 0 and crossed["assignments"] == []
    students = f.ov_students(subject_id=f.subj("CSE-5C"), section_id=f.sec("CSE-5C")).json()
    assert students["total"] == 16 and {i["assignment"]["section"]["label"] for i in students["items"]} == {"CSE-5C"}
    assert {i["student"]["login_id"] for i in students["items"]} == {f"STU{n:04d}" for n in range(135, 151)}


def test_versions_never_inflate_the_counts(f):
    asg = f.make("CSE-5A")
    for n in (1, 2, 3):
        up = f.client.post(
            f"{API}/student/assignments/{asg['id']}/submissions",
            files={"file": ("w.pdf", pdf(100 + n), "application/pdf")},
            headers=auth(f.stu_5a),
        )
        assert up.status_code == 201, up.text
    t = f.ov(section_id=f.sec("CSE-5A")).json()["totals"]
    assert (t["expected"], t["submitted"], t["on_time"], t["pending"], t["resubmitted"]) == (17, 1, 1, 16, 1)
    assert f.ov_students(section_id=f.sec("CSE-5A"), timing="ON_TIME").json()["total"] == 1


def test_a_section_with_assignments_but_no_submissions_and_one_with_no_assignments(f):
    asg = f.make("CSE-5C", deadline=iso(NOW + timedelta(days=1)))
    t = f.ov(section_id=f.sec("CSE-5C")).json()["totals"]
    assert (t["expected"], t["submitted"], t["pending"], t["missing"]) == (16, 0, 16, 0)
    # no assignment in CSE-5A: authorised, valid, empty - zeros and no records, not an error
    empty = f.ov(section_id=f.sec("CSE-5A"))
    assert empty.status_code == 200 and empty.json()["assignments"] == [] and empty.json()["totals"]["expected"] == 0
    assert f.ov_students(section_id=f.sec("CSE-5A")).json() == {"total": 0, "items": [], "truncated": False}
    f.freeze_time(NOW + timedelta(days=1, seconds=1))  # the deadline passes: the same 16 students are now missing
    t = f.ov(section_id=f.sec("CSE-5C")).json()["totals"]
    assert (t["expected"], t["pending"], t["missing"]) == (16, 0, 16)
    assert asg["expected_students"] == 16


def test_late_request_counts_follow_the_section_filter(f):
    f.make("CSE-5A", deadline=iso(NOW + timedelta(days=1)))
    f.make("CSE-5C", deadline=iso(NOW + timedelta(days=1)))
    f.freeze_time(NOW + timedelta(days=1, minutes=5))
    asg_c = f.client.get(f"{API}/student/assignments", headers=auth(f.stu_5c)).json()[0]["id"]
    res = f.client.post(f"{API}/student/assignments/{asg_c}/late-request", json={"reason": "x" * 30}, headers=auth(f.stu_5c))
    assert res.status_code == 201, res.text
    assert f.ov(section_id=f.sec("CSE-5C")).json()["totals"]["requests_pending"] == 1
    assert f.ov(section_id=f.sec("CSE-5A")).json()["totals"]["requests_pending"] == 0
    assert f.ov().json()["totals"]["requests_pending"] == 1
    for label, n in (("CSE-5C", 1), ("CSE-5A", 0)):
        got = f.client.get(f"{API}/faculty/late-requests", params={"section_id": f.sec(label), "status": "PENDING"}, headers=auth(f.fac2_5a_5c)).json()
        assert len(got) == n, label


def test_assignment_list_filters_by_subject_and_section(f):
    f.make("CSE-5A")
    f.make("CSE-5C")
    lst = lambda **p: f.client.get(f"{API}/faculty/assignments", params=p, headers=auth(f.fac2_5a_5c)).json()  # noqa: E731
    assert len(lst()) == 2
    assert [a["section"]["label"] for a in lst(section_id=f.sec("CSE-5C"))] == ["CSE-5C"]
    assert [a["section"]["label"] for a in lst(section_id=f.sec("CSE-5A"), subject_id=f.subj("CSE-5A"))] == ["CSE-5A"]
    assert lst(section_id=f.sec("CSE-5A"), subject_id=f.subj("CSE-5C")) == []


def test_unauthorised_sections_and_subjects_are_denied_everywhere(f):
    f.make("CSE-5A")
    sec_5b = str(uuid.UUID(f.client.get(f"{API}/auth/me", headers=auth(f.fac_5b)).json()["teaching"][0]["section"]["id"]))
    for path in ("/faculty/overview", "/faculty/overview/students", "/faculty/assignments", "/faculty/late-requests"):
        for params in ({"section_id": sec_5b}, {"subject_id": str(uuid.uuid4())}, {"section_id": str(uuid.uuid4())}):
            res = f.client.get(f"{API}{path}", params=params, headers=auth(f.fac2_5a_5c))
            assert res.status_code == 403 and res.json()["error"]["code"] == "NOT_YOUR_CLASS", (path, params)
    # the owner of that section can use it, and sees nothing of FAC002's students
    assert f.ov(token=f.fac_5b, section_id=sec_5b).json()["totals"]["expected"] == 0
    # students never reach these endpoints
    assert f.client.get(f"{API}/faculty/overview", params={"section_id": sec_5b}, headers=auth(f.stu_5a)).status_code == 403
    assert f.client.get(f"{API}/faculty/overview", params={"section_id": sec_5b}).status_code == 401


def test_a_teacher_without_classes_gets_empty_data_and_denial_for_any_filter(f):
    f.make("CSE-5A")
    for path in ("/faculty/overview", "/faculty/overview/students", "/faculty/assignments", "/faculty/late-requests"):
        assert f.client.get(f"{API}{path}", headers=auth(f.fac49)).status_code == 200
        res = f.client.get(f"{API}{path}", params={"section_id": f.sec("CSE-5A")}, headers=auth(f.fac49))
        assert res.status_code == 403
    assert f.ov(token=f.fac49).json()["totals"]["expected"] == 0
    assert f.client.get(f"{API}/faculty/assignments", headers=auth(f.fac49)).json() == []


# --- deletion -----------------------------------------------------------------------------------------------------


@pytest.fixture
def m(client, api_app, monkeypatch, test_password, freeze_time, s3_client, settings, seeded_engine) -> S:
    monkeypatch.setattr(
        api_app.state, "settings", api_app.state.settings.model_copy(update={"jwt_expire_minutes": 60 * 24 * 30})
    )
    return S(client, test_password, freeze_time, s3_client=s3_client, bucket=settings.s3_bucket, engine=seeded_engine)


def delete(m: S, aid, token=None):
    return m.client.delete(f"{API}/faculty/assignments/{aid}", headers=auth(token or m.fac1))


def check_(m: S, aid, token=None):
    return m.get(f"/faculty/assignments/{aid}/deletion-check", token or m.fac1)


def exists(m: S, aid) -> bool:
    return m.sql("SELECT count(*) FROM assignments WHERE id = :a", a=aid)[0][0] == 1


def test_the_owner_can_delete_an_eligible_draft_and_a_repeat_is_safe(m):
    aid = draft(m)
    chk = check_(m, aid).json()
    assert chk["can_delete"] is True and chk["blockers"] == {} and chk["status"] == "DRAFT" and chk["action"] == "DELETE"
    res = delete(m, aid)
    assert res.status_code == 200
    assert res.json() == {"deleted": True, "assignment_id": aid, "title": "DBMS Lab 4", "files_removed": 0, "files_left": 0}
    assert not exists(m, aid)
    again = delete(m, aid)  # a double click / repeated request
    assert again.status_code == 404 and again.json()["error"]["code"] == "NOT_FOUND"
    assert m.get(f"/faculty/assignments/{aid}", m.fac1).status_code == 404


def test_a_draft_with_reference_documents_is_deleted_with_them(m):
    aid = draft(m)
    attach(m, aid, name="a.pdf", data=pdf(200))
    attach(m, aid, name="b.pdf", data=pdf(300))
    assert len(m.objects()) == 2 and check_(m, aid).json()["can_delete"] is True
    res = delete(m, aid).json()
    assert (res["files_removed"], res["files_left"]) == (2, 0)
    assert m.count("assignment_attachments") == 0 and m.objects() == [] and not exists(m, aid)


def test_students_and_other_faculty_cannot_delete(m):
    aid = draft(m)
    assert m.client.delete(f"{API}/faculty/assignments/{aid}").status_code == 401
    assert delete(m, aid, m.stu_5a).status_code == 403
    for token in (m.fac2, m.fac49):
        res = delete(m, aid, token)
        assert res.status_code == 404 and res.json()["error"]["code"] == "NOT_FOUND"
        assert check_(m, aid, token).status_code == 404
    assert exists(m, aid)
    assert check_(m, aid, m.stu_5a).status_code == 403


def test_a_published_assignment_is_never_deleted_it_is_archived_instead(m):
    pub = m.create(title="Fresh").json()["id"]
    chk = check_(m, pub).json()
    assert chk["can_delete"] is False and chk["action"] == "ARCHIVE" and chk["can_archive"] is True
    assert chk["student_history"] is False
    res = delete(m, pub)
    assert res.status_code == 409 and res.json()["error"]["code"] == "NOT_A_DRAFT"
    assert res.json()["error"]["details"] == {"action": "ARCHIVE"}
    assert exists(m, pub) and pub in {a["id"] for a in m.get("/student/assignments", m.stu_5a).json()}


def test_an_assignment_with_a_submission_is_protected(m):
    assert m.upload().status_code == 201
    key = m.sql("SELECT storage_key FROM submission_versions")[0][0]
    chk = check_(m, m.aid).json()
    assert chk["can_delete"] is False and chk["blockers"] == {"submissions": 1, "versions": 1}
    assert chk["student_history"] is True and chk["action"] == "ARCHIVE" and chk["can_archive"] is True
    res = delete(m, m.aid)
    assert res.status_code == 409 and res.json()["error"]["code"] == "NOT_A_DRAFT"
    assert exists(m, m.aid) and m.count("submissions") == 1 and m.count("submission_versions") == 1 and key in m.objects()


def test_review_late_request_deadline_change_and_notification_history_each_block_deletion(m):
    sid = m.insert_first_version("STU0101")
    m.insert_review(sid, "ACCEPTED")
    chk = check_(m, m.aid).json()["blockers"]
    assert chk["reviews"] == 1 and chk["submissions"] == 1
    other = m.create(title="Other").json()["id"]
    assert m.patch(f"/faculty/assignments/{other}/deadline", m.fac1, {"new_deadline": iso(NOW + timedelta(days=5))}).status_code == 200
    blockers = check_(m, other).json()["blockers"]
    assert blockers["deadline_changes"] == 1 and blockers["notifications"] == 17  # every student of the section was told
    assert delete(m, other).status_code == 409 and exists(m, other)
    third = m.create(title="Third", deadline=iso(NOW + timedelta(days=1))).json()["id"]
    m.freeze_time(NOW + timedelta(days=1, minutes=1))
    assert m.client.post(f"{API}/student/assignments/{third}/late-request", json={"reason": "r" * 30}, headers=auth(m.stu_5a)).status_code == 201
    only = check_(m, third).json()["blockers"]
    assert only == {"late_requests": 1}
    assert delete(m, third).status_code == 409 and exists(m, third)


def test_published_reference_documents_block_deletion_and_their_objects_survive(m):
    aid = draft(m)
    attach(m, aid)
    publish(m, aid)
    chk = check_(m, aid).json()
    assert chk["can_delete"] is False and chk["blockers"] == {"reference_files": 1}
    assert delete(m, aid).status_code == 409
    assert exists(m, aid) and m.count("assignment_attachments") == 1 and len(m.objects()) == 1


def test_a_referenced_object_is_never_deleted(m):
    """A draft's document whose key is (somehow) still used by another record keeps its object."""
    aid = draft(m)
    attach(m, aid, name="shared.pdf")
    key = m.sql("SELECT storage_key FROM assignment_attachments")[0][0]
    sid = m.insert_first_version("STU0101")
    with Session(m.engine) as db:
        db.execute(text("UPDATE submission_versions SET storage_key = :k WHERE submission_id = :s"), {"k": key, "s": sid})
        db.commit()
    res = delete(m, aid).json()
    assert (res["files_removed"], res["files_left"]) == (0, 1)
    assert key in m.objects() and not exists(m, aid)


def test_a_dependent_row_that_slips_in_is_stopped_by_the_foreign_keys(m, monkeypatch):
    """Even if the history check were bypassed (a race), RESTRICT keeps the data and the delete answers 409."""
    aid = draft(m)
    sid = m.student_id("STU0101")
    with Session(m.engine) as db:
        db.execute(
            text("INSERT INTO submissions (assignment_id, student_id, latest_version_no) VALUES (:a, :s, 0)"),
            {"a": aid, "s": sid},
        )
        db.commit()
    monkeypatch.setattr(assignment_deletion, "blockers", lambda db, a: ({}, 0))
    res = delete(m, aid)
    assert res.status_code == 409 and res.json()["error"]["code"] == "ASSIGNMENT_HAS_HISTORY"
    assert exists(m, aid) and m.count("submissions") == 1


def test_a_database_failure_rolls_everything_back_and_keeps_the_files(m, monkeypatch):
    aid = draft(m)
    attach(m, aid, name="keep.pdf")
    real_commit = Session.commit
    calls = {"n": 0}

    def failing_commit(self):
        calls["n"] += 1
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(Session, "commit", failing_commit)
    res = delete(m, aid)
    monkeypatch.setattr(Session, "commit", real_commit)
    assert res.status_code == 500 and calls["n"] >= 1
    assert exists(m, aid) and m.count("assignment_attachments") == 1 and len(m.objects()) == 1  # nothing was removed


def test_a_storage_failure_after_commit_leaves_a_harmless_orphan(m, monkeypatch):
    aid = draft(m)
    attach(m, aid)
    monkeypatch.setattr(assignment_deletion.storage, "delete_object_best_effort", lambda *a, **k: False)
    res = delete(m, aid)
    assert res.status_code == 200 and (res.json()["files_removed"], res.json()["files_left"]) == (0, 1)
    assert not exists(m, aid) and m.count("assignment_attachments") == 0  # the database is consistent
    with Session(m.engine) as db:
        assert len(orphans.find_orphans(m.s3, m.bucket, db)) == 1  # reported, never referenced by any row
        assert orphans.find_dangling(m.s3, m.bucket, db) == []


def test_a_deleted_draft_leaves_the_active_numbers_alone_and_leaves_the_list(m):
    extra = draft(m)
    before = m.client.get(f"{API}/faculty/overview", headers=auth(m.fac1)).json()
    assert extra in {a["id"] for a in m.get("/faculty/assignments", m.fac1).json()}
    assert delete(m, extra).status_code == 200
    after = m.client.get(f"{API}/faculty/overview", headers=auth(m.fac1)).json()
    assert after == before  # drafts were never part of the counts
    assert extra not in {a["id"] for a in m.get("/faculty/assignments", m.fac1).json()}


def test_deleting_a_draft_does_not_touch_other_assignments_or_their_files(m):
    other = draft(m)
    attach(m, other, name="other.pdf")
    publish(m, other)
    mine = draft(m)
    attach(m, mine, name="mine.pdf", data=pdf(333))
    delete(m, mine)
    assert exists(m, other) and m.count("assignment_attachments") == 1 and len(m.objects()) == 1
    assert m.sql("SELECT original_filename FROM assignment_attachments")[0][0] == "other.pdf"
