"""Archive / restore of published assignments: history preserved, no new work, visibility, counts, concurrency."""

import hashlib
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from tests.api.test_assignments import API, NOW, auth, iso
from tests.api.test_attachments import attach, draft, pdf, publish
from tests.api.test_submissions import S


@pytest.fixture
def m(client, api_app, monkeypatch, test_password, freeze_time, s3_client, settings, seeded_engine) -> S:
    monkeypatch.setattr(
        api_app.state, "settings", api_app.state.settings.model_copy(update={"jwt_expire_minutes": 60 * 24 * 30})
    )
    return S(client, test_password, freeze_time, s3_client=s3_client, bucket=settings.s3_bucket, engine=seeded_engine)


def archive(m: S, aid=None, token=None, reason=None):
    return m.client.post(
        f"{API}/faculty/assignments/{aid or m.aid}/archive",
        json={"reason": reason} if reason else None,
        headers=auth(token or m.fac1),
    )


def restore(m: S, aid=None, token=None):
    return m.client.post(f"{API}/faculty/assignments/{aid or m.aid}/restore", headers=auth(token or m.fac1))


def status_of(m: S, aid=None) -> str:
    return m.sql("SELECT status::text FROM assignments WHERE id = :a", a=aid or m.aid)[0][0]


def history_fingerprint(m: S) -> str:
    h = hashlib.sha256()
    for table in ("submissions", "submission_versions", "reviews", "late_requests", "deadline_changes", "notifications"):
        h.update(repr(m.sql(f'SELECT * FROM "{table}" ORDER BY id')).encode())
    return h.hexdigest()


def with_history(m: S) -> dict:
    """STU0101: submission + review; STU0102: nothing; a late request by STU0103 after a deadline change."""
    assert m.upload().status_code == 201
    sub = m.sql("SELECT id FROM submissions")[0][0]
    res = m.client.post(
        f"{API}/faculty/submissions/{sub}/reviews", json={"status": "REVISION_REQUESTED", "feedback": "Please add more detail."}, headers=auth(m.fac1)
    )
    assert res.status_code == 201, res.text
    key = m.sql("SELECT storage_key FROM submission_versions")[0][0]
    vid = str(m.sql("SELECT id FROM submission_versions")[0][0])
    return {"sub": str(sub), "key": key, "vid": vid}


# --- who may archive ---------------------------------------------------------------------------------------------


def test_only_the_owner_can_archive_or_restore(m):
    assert archive(m, token=m.stu_5a).status_code == 403
    assert m.client.post(f"{API}/faculty/assignments/{m.aid}/archive").status_code == 401
    for token in (m.fac2, m.fac49):
        assert archive(m, token=token).status_code == 404
    assert status_of(m) == "PUBLISHED"
    assert archive(m).status_code == 200
    for token in (m.stu_5a, ):
        assert restore(m, token=token).status_code == 403
    for token in (m.fac2, m.fac49):
        assert restore(m, token=token).status_code == 404
    assert status_of(m) == "ARCHIVED"


def test_state_rules_draft_archived_and_repeats(m):
    d = draft(m)
    res = archive(m, d)
    assert res.status_code == 409 and res.json()["error"]["code"] == "NOT_PUBLISHED"  # a draft is deleted, not archived
    assert restore(m).status_code == 409 and restore(m).json()["error"]["code"] == "NOT_ARCHIVED"
    assert archive(m).status_code == 200
    again = archive(m)
    assert again.status_code == 409 and again.json()["error"]["code"] == "ALREADY_ARCHIVED"
    assert m.count("assignment_state_changes") == 1


# --- history is preserved ---------------------------------------------------------------------------------------------


def test_archiving_an_assignment_with_history_preserves_every_record_and_file(m):
    h = with_history(m)
    assert m.patch(f"/faculty/assignments/{m.aid}/deadline", m.fac1, {"new_deadline": iso(NOW + timedelta(days=4))}).status_code == 200
    before = history_fingerprint(m)
    counts = {t: m.count(t) for t in ("submissions", "submission_versions", "reviews", "deadline_changes", "notifications")}
    objects = m.objects()
    chk = m.get(f"/faculty/assignments/{m.aid}/deletion-check", m.fac1).json()
    assert chk["student_history"] is True and chk["can_delete"] is False and chk["action"] == "ARCHIVE" and chk["can_archive"] is True
    res = archive(m, reason="Superseded by the new brief")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ARCHIVED" and body["archived_at"] is not None and body["deadline"] == iso(NOW + timedelta(days=4)).replace("+00:00", "Z")
    assert status_of(m) == "ARCHIVED"
    assert history_fingerprint(m) == before  # byte-identical history rows
    assert {t: m.count(t) for t in counts} == counts and m.objects() == objects and h["key"] in m.objects()
    row = m.sql("SELECT from_status, to_status, reason FROM assignment_state_changes")[0]
    assert tuple(row) == ("PUBLISHED", "ARCHIVED", "Superseded by the new brief")
    # an archived assignment can never be deleted
    res = m.client.delete(f"{API}/faculty/assignments/{m.aid}", headers=auth(m.fac1))
    assert res.status_code == 409 and res.json()["error"]["code"] == "NOT_A_DRAFT" and status_of(m) == "ARCHIVED"


def test_archive_does_not_touch_the_deadline_or_review_status(m):
    with_history(m)
    deadline = m.sql("SELECT deadline FROM assignments")[0][0]
    archive(m)
    assert m.sql("SELECT deadline FROM assignments")[0][0] == deadline
    assert m.sql("SELECT status::text FROM reviews")[0][0] == "REVISION_REQUESTED"


# --- students ---------------------------------------------------------------------------------------------------------


def test_an_archived_assignment_leaves_the_students_active_work_but_stays_readable_for_their_own_history(m):
    h = with_history(m)  # STU0101 submitted and was reviewed
    assert m.aid in {a["id"] for a in m.get("/student/assignments", m.stu_5a).json()}
    archive(m)
    for token in (m.stu_5a, m.stu_5a2):
        assert m.aid not in {a["id"] for a in m.get("/student/assignments", token).json()}  # not active work
    # alerts and the upcoming-work counts no longer include it
    assert m.get("/notifications", m.stu_5a).json()["alerts"] == []
    # the student with history still sees it, read-only
    mine = m.get("/student/assignments/archived", m.stu_5a).json()
    assert [a["id"] for a in mine] == [m.aid] and mine[0]["assignment_state"] == "ARCHIVED"
    detail = m.get(f"/student/assignments/{m.aid}", m.stu_5a)
    assert detail.status_code == 200
    d = detail.json()
    assert d["assignment_state"] == "ARCHIVED" and d["can_upload"] is False and d["upload_blocked_reason"] == "ARCHIVED"
    assert d["can_request_late"] is False and len(d["versions"]) == 1
    assert d["review_status"] == "REVISION_REQUESTED" and d["latest_feedback"] == "Please add more detail."  # feedback kept
    assert d["reviews"][0]["feedback"] == "Please add more detail."
    # a classmate without any history cannot see it at all
    assert m.get("/student/assignments/archived", m.stu_5a2).json() == []
    assert m.get(f"/student/assignments/{m.aid}", m.stu_5a2).status_code == 404
    # another section never could
    assert m.get(f"/student/assignments/{m.aid}", m.stu_5b).status_code == 404
    # own file access still works: download and preview
    dl = m.get(f"/files/versions/{h['vid']}", m.stu_5a)
    assert dl.status_code == 200 and dl.content == pdf()
    assert m.get(f"/files/versions/{h['vid']}/preview", m.stu_5a).status_code == 200
    assert m.get(f"/files/versions/{h['vid']}", m.stu_5a2).status_code == 404  # privacy rules unchanged


def test_new_submissions_and_late_requests_are_rejected_after_archiving(m):
    m.upload()  # STU0101 has a version
    objects = m.objects()
    archive(m)
    res = m.upload(data=pdf(555))  # a new version by the student with history
    assert res.status_code == 409 and res.json()["error"]["code"] == "ASSIGNMENT_ARCHIVED"
    assert m.count("submission_versions") == 1 and m.objects() == objects  # nothing stored, nothing left behind
    res = m.upload(token=m.stu_5a2)  # a student without history cannot even see it
    assert res.status_code == 404 and m.count("submissions") == 1
    # a student with an earlier late request gets the archived error, not a second request
    restore(m)
    other = m.create(title="Late one", deadline=iso(NOW + timedelta(days=1))).json()["id"]
    m.freeze_time(NOW + timedelta(days=1, minutes=5))
    ask = lambda aid, token: m.client.post(f"{API}/student/assignments/{aid}/late-request", json={"reason": "r" * 30}, headers=auth(token))  # noqa: E731
    assert ask(other, m.stu_5a2).status_code == 201
    archive(m, other)
    res = ask(other, m.stu_5a2)
    assert res.status_code == 409 and res.json()["error"]["code"] == "ASSIGNMENT_ARCHIVED"
    assert ask(other, m.stu_5a).status_code == 404  # no history: invisible
    assert m.count("late_requests") == 1


# --- faculty ---------------------------------------------------------------------------------------------------------


def test_faculty_keep_the_history_but_cannot_change_an_archived_assignment(m):
    h = with_history(m)
    assert m.upload(token=m.stu_5a2, data=pdf(900)).status_code == 201  # a second submission, not yet reviewed
    archive(m)
    # history stays available
    assert m.get(f"/faculty/assignments/{m.aid}", m.fac1).json()["status"] == "ARCHIVED"
    roster = m.get(f"/faculty/assignments/{m.aid}/roster", m.fac1)
    assert roster.status_code == 200 and sum(1 for r in roster.json() if r["version_count"]) == 2
    sid = m.student_id("STU0101")
    detail = m.get(f"/faculty/assignments/{m.aid}/students/{sid}/timeline", m.fac1)
    assert detail.status_code == 200 and detail.json()["review_status"] == "REVISION_REQUESTED"
    assert m.get(f"/files/versions/{h['vid']}", m.fac1).content == pdf()
    # but nothing can be changed
    sub2 = m.sql("SELECT id FROM submissions WHERE student_id = :s", s=m.student_id("STU0102"))[0][0]
    res = m.client.post(f"{API}/faculty/submissions/{sub2}/reviews", json={"status": "ACCEPTED"}, headers=auth(m.fac1))
    assert res.status_code == 409 and res.json()["error"]["code"] == "ASSIGNMENT_ARCHIVED" and m.count("reviews") == 1
    res = m.patch(f"/faculty/assignments/{m.aid}/deadline", m.fac1, {"new_deadline": iso(NOW + timedelta(days=9))})
    assert res.status_code == 409 and res.json()["error"]["code"] == "ASSIGNMENT_ARCHIVED"
    # another teacher still sees nothing
    assert m.get(f"/faculty/assignments/{m.aid}/roster", m.fac2).status_code == 404


def test_a_pending_late_request_on_an_archived_assignment_cannot_be_decided_and_is_not_counted_as_waiting(m):
    other = m.create(title="Late two", deadline=iso(NOW + timedelta(days=1))).json()["id"]
    m.freeze_time(NOW + timedelta(days=1, minutes=5))
    r = m.client.post(f"{API}/student/assignments/{other}/late-request", json={"reason": "r" * 30}, headers=auth(m.stu_5a2))
    assert r.status_code == 201
    pending = lambda: m.get("/faculty/late-requests?status=PENDING", m.fac1).json()  # noqa: E731
    assert len(pending()) == 1 and m.client.get(f"{API}/faculty/overview", headers=auth(m.fac1)).json()["totals"]["requests_pending"] == 1
    archive(m, other)
    assert pending() == []  # nothing can be decided, so nothing is waiting
    assert m.client.get(f"{API}/faculty/overview", headers=auth(m.fac1)).json()["totals"]["requests_pending"] == 0
    assert len(m.get("/faculty/late-requests", m.fac1).json()) == 1  # but the request is still listed in the history
    rid = r.json()["id"]
    res = m.post(f"/faculty/late-requests/{rid}/decision", m.fac1, {"decision": "APPROVE", "window_hours": 24})
    assert res.status_code == 409 and res.json()["error"]["code"] == "ASSIGNMENT_ARCHIVED"
    assert m.sql("SELECT status::text FROM late_requests")[0][0] == "PENDING"


def test_lists_and_dashboard_numbers_distinguish_active_from_archived(m):
    second = m.create(title="Second").json()["id"]
    d = draft(m)
    ids = lambda state: {a["id"] for a in m.client.get(f"{API}/faculty/assignments", params={"state": state}, headers=auth(m.fac1)).json()}  # noqa: E731
    assert ids("active") == {m.aid, second, d} and ids("archived") == set() and ids("all") == {m.aid, second, d}
    totals = lambda: m.client.get(f"{API}/faculty/overview", headers=auth(m.fac1)).json()  # noqa: E731
    assert totals()["totals"]["expected"] == 34 and len(totals()["assignments"]) == 2
    archive(m, second)
    assert ids("active") == {m.aid, d} and ids("archived") == {second} and ids("all") == {m.aid, second, d}
    assert totals()["totals"]["expected"] == 17 and [a["assignment"]["id"] for a in totals()["assignments"]] == [m.aid]
    row = next(a for a in m.get("/faculty/assignments?state=archived", m.fac1).json())
    assert row["status"] == "ARCHIVED" and row["archived_at"] is not None
    # the section filter still validates and still counts only active work
    sec = m.slot1["section"]["id"]
    assert m.client.get(f"{API}/faculty/overview", params={"section_id": sec}, headers=auth(m.fac1)).json()["totals"]["expected"] == 17
    assert m.client.get(f"{API}/faculty/assignments", params={"state": "bogus"}, headers=auth(m.fac1)).status_code == 422


def test_restore_makes_the_assignment_active_again_with_the_same_deadline_and_history(m):
    with_history(m)
    deadline = m.sql("SELECT deadline FROM assignments")[0][0]
    before = history_fingerprint(m)
    archive(m)
    res = restore(m)
    assert res.status_code == 200 and res.json()["status"] == "PUBLISHED" and res.json()["archived_at"] is None
    assert m.sql("SELECT deadline, archived_at, archived_by FROM assignments")[0] == (deadline, None, None)
    assert history_fingerprint(m) == before
    assert m.aid in {a["id"] for a in m.get("/student/assignments", m.stu_5a).json()}
    assert m.get("/student/assignments/archived", m.stu_5a).json() == []
    assert m.client.get(f"{API}/faculty/overview", headers=auth(m.fac1)).json()["totals"]["expected"] == 17
    assert m.upload(data=pdf(321)).status_code == 201  # accepts work again


def test_the_timeline_shows_who_archived_and_restored_and_when(m):
    m.upload()
    archive(m, reason="Wrong brief")
    m.freeze_time(NOW + timedelta(hours=2))
    restore(m)
    sid = m.student_id("STU0101")
    for events in (
        m.get(f"/faculty/assignments/{m.aid}/students/{sid}/timeline", m.fac1).json()["events"],
        m.get(f"/student/assignments/{m.aid}", m.stu_5a).json()["events"],
    ):
        kinds = [e["type"] for e in events]
        assert kinds.index("ASSIGNMENT_ARCHIVED") < kinds.index("ASSIGNMENT_RESTORED")
        arch = next(e for e in events if e["type"] == "ASSIGNMENT_ARCHIVED")
        assert arch["actor"] and "Wrong brief" in arch["summary"] and "All submissions and reviews are kept" in arch["summary"]
        assert not arch["derived"] and arch["at"].startswith("2026-10-")


# --- concurrency ------------------------------------------------------------------------------------------------------


def test_an_upload_racing_an_archive_is_either_stored_before_it_or_refused_after_it(m):
    """The archive holds the assignment row; the upload waits, then sees ARCHIVED, is refused and leaves nothing."""
    with Session(m.engine) as a:
        a.execute(
            text("UPDATE assignments SET status = 'ARCHIVED', archived_at = now() WHERE id = :i"), {"i": m.aid}
        )  # takes the row lock, not yet committed
        with ThreadPoolExecutor(max_workers=1) as pool:
            fut = pool.submit(lambda: m.upload(data=pdf(777)))
            time.sleep(1.0)
            assert not fut.done()  # the upload is waiting for the archive to finish
            a.commit()
            res = fut.result(timeout=15)
    assert res.status_code == 409 and res.json()["error"]["code"] == "ASSIGNMENT_ARCHIVED"
    assert m.count("submissions") == 0 and m.count("submission_versions") == 0 and m.objects() == []


def test_an_archive_after_an_upload_keeps_that_upload(m):
    assert m.upload().status_code == 201
    assert archive(m).status_code == 200
    assert m.count("submission_versions") == 1 and len(m.objects()) == 1


# --- reference documents stay with the assignment ----------------------------------------------------------------------


def test_reference_documents_remain_downloadable_by_students_with_history_and_faculty(m):
    aid = draft(m)
    att = attach(m, aid).json()["id"]
    publish(m, aid)
    sub = m.client.post(f"{API}/student/assignments/{aid}/submissions", files={"file": ("w.pdf", pdf(), "application/pdf")}, headers=auth(m.stu_5a))
    assert sub.status_code == 201
    archive(m, aid)
    assert m.get(f"/files/materials/{att}", m.fac1).status_code == 200
    assert m.get(f"/files/materials/{att}", m.stu_5a).status_code == 200  # has history
    assert m.get(f"/files/materials/{att}", m.stu_5a2).status_code == 404  # no history: invisible
    assert m.count("assignment_attachments") == 1 and len(m.objects()) == 2
