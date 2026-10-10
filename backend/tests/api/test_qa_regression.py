"""Phase 8 QA: cross-cutting regression guards that do not belong to one feature.

* an authorization matrix generated from the application's own route table (a new route cannot be forgotten),
* a cross-section isolation matrix,
* session lifecycle on the Phase 6-7 endpoints (expiry, logout, Redis outage),
* the 500 envelope,
* a seeded randomized workflow checked against independent SQL and database/storage invariants.
"""

import random
from datetime import timedelta

import pytest
from sqlalchemy.orm import Session

from app.services import orphans
from tests.api.test_assignments import API, NOW, auth
from tests.api.test_late_requests import AFTER, L
from tests.api.test_overview_notifications import (
    independent_counts,
    overview,
    overview_students,
    tok,
)
from tests.api.test_reviews_timeline import review, sub_id
from tests.unit.test_file_validation import pdf

ANY_ID = "00000000-0000-0000-0000-000000000000"
PUBLIC = {"/api/v1/health", "/api/v1/auth/login"}


@pytest.fixture
def s(client, api_app, monkeypatch, test_password, freeze_time, s3_client, settings, seeded_engine, redis_client) -> L:
    monkeypatch.setattr(api_app.state, "settings", api_app.state.settings.model_copy(update={"jwt_expire_minutes": 60 * 24 * 400}))
    world = L(client, test_password, freeze_time, s3_client=s3_client, bucket=settings.s3_bucket, engine=seeded_engine)
    world.password, world.redis = test_password, redis_client
    return world


def api_routes(app):
    """Every (method, path) under /api/v1, read from the generated OpenAPI document (the route table itself is
    nested in this FastAPI version)."""
    out = []
    for path, item in app.openapi()["paths"].items():
        if path.startswith("/api/v1") and path not in PUBLIC:
            for method in item:
                if method.upper() not in ("HEAD", "OPTIONS"):
                    out.append((method.upper(), path))
    return sorted(out)


def concrete(path: str) -> str:
    out = path
    while "{" in out:
        start = out.index("{")
        out = out[:start] + ANY_ID + out[out.index("}") + 1 :]
    return out


def call(s, method, path, token=None):
    headers = auth(token) if token else {}
    return s.client.request(method, concrete(path), headers=headers, json={} if method in ("POST", "PATCH", "PUT") else None)


# --- authorization matrix ------------------------------------------------------------------------------------------


def test_the_route_table_is_what_the_matrix_expects(api_app):
    routes = api_routes(api_app)
    assert len(routes) >= 22  # a sanity floor so the matrix cannot silently become empty
    prefixes = {p.split("/")[3] for _, p in routes}
    assert prefixes <= {"auth", "student", "faculty", "files", "notifications"}, prefixes


def test_every_endpoint_rejects_anonymous_callers_with_401(s, api_app):
    failures = []
    for method, path in api_routes(api_app):
        res = call(s, method, path)
        if res.status_code != 401 or res.json()["error"]["code"] not in ("UNAUTHENTICATED", "TOKEN_EXPIRED", "INVALID_TOKEN", "UNAUTHORIZED"):
            failures.append((method, path, res.status_code, res.text[:80]))
    assert not failures, failures


def test_every_role_restricted_endpoint_refuses_the_other_role_with_403(s, api_app):
    failures = []
    for method, path in api_routes(api_app):
        area = path.split("/")[3]
        if area == "student":
            res = call(s, method, path, s.fac1)
        elif area == "faculty":
            res = call(s, method, path, s.stu_5a)
        else:
            continue
        if res.status_code != 403:
            failures.append((method, path, res.status_code))
    assert not failures, failures


def test_shared_endpoints_accept_both_roles_but_never_leak_unknown_ids(s, api_app):
    for token in (s.fac1, s.stu_5a):
        assert call(s, "GET", "/api/v1/auth/me", token).status_code == 200
        assert call(s, "GET", "/api/v1/notifications", token).status_code == 200
        assert call(s, "GET", f"/api/v1/files/versions/{ANY_ID}", token).status_code == 404
        assert call(s, "POST", f"/api/v1/notifications/{ANY_ID}/read", token).status_code == 404


def test_unknown_ids_on_every_scoped_endpoint_are_404_not_500(s, api_app):
    failures = []
    for method, path in api_routes(api_app):
        if "{" not in path:
            continue
        area = path.split("/")[3]
        token = {"student": s.stu_5a, "faculty": s.fac1}.get(area, s.fac1)
        res = call(s, method, path, token)
        if res.status_code >= 500 or res.status_code == 200:
            failures.append((method, path, res.status_code))
    assert not failures, failures


# --- cross-section isolation ----------------------------------------------------------------------------------------


def test_a_student_of_another_section_sees_nothing_of_this_assignment(s):
    s.upload()
    review(s, "REVISION_REQUESTED", "private feedback")
    s.at(AFTER)
    rid = s.ask(token=s.stu_5a2).json()["id"]
    version_id = s.sql("SELECT id FROM submission_versions")[0][0]
    other = s.stu_5b
    assert s.get("/student/assignments", other).json() == []
    assert s.get(f"/student/assignments/{s.aid}", other).status_code == 404
    assert s.upload(token=other).status_code == 404
    assert s.ask(token=other).status_code == 404
    assert s.get(f"/files/versions/{version_id}", other).status_code == 404
    assert s.get("/notifications", other).json() == {"alerts": [], "items": [], "unread_count": 0}
    for path in (f"/faculty/assignments/{s.aid}", f"/faculty/late-requests/{rid}", f"/faculty/assignments/{s.aid}/roster"):
        assert s.get(path, other).status_code == 403  # a student has no faculty access at all
    # ...and faculty of other classes see none of it either.
    for token in (s.fac2, s.fac49):
        assert s.get(f"/files/versions/{version_id}", token).status_code == 404
        assert s.get(f"/faculty/assignments/{s.aid}", token).status_code == 404
        assert s.get(f"/faculty/assignments/{s.aid}/roster", token).status_code == 404
        assert s.get(f"/faculty/late-requests/{rid}", token).status_code == 404
        assert s.post(f"/faculty/submissions/{sub_id(s)}/reviews", token, {"status": "ACCEPTED"}).status_code == 404
        assert s.patch(f"/faculty/assignments/{s.aid}/deadline", token, {"new_deadline": (AFTER + timedelta(days=1)).isoformat()}).status_code == 404
    assert s.get("/notifications", s.fac2).json()["items"] == []


def test_classmates_cannot_read_each_others_files_reviews_or_requests(s):
    s.upload(data=pdf(100))
    review(s, "ACCEPTED", "classmate-secret")
    version_id = s.sql("SELECT id FROM submission_versions")[0][0]
    assert s.get(f"/files/versions/{version_id}", s.stu_5a2).status_code == 404
    other = s.detail(token=s.stu_5a2)
    assert "classmate-secret" not in str(other) and other["reviews"] == [] and other["versions"] == []
    assert s.get(f"/files/versions/{version_id}", s.stu_5a).status_code == 200  # the owner can


# --- session lifecycle on the newer endpoints ------------------------------------------------------------------------


def test_logout_revokes_access_to_notifications_and_the_faculty_board(s):
    assert s.get("/notifications", s.stu_5a).status_code == 200
    assert s.client.post(f"{API}/auth/logout", headers=auth(s.stu_5a)).status_code == 204
    assert s.get("/notifications", s.stu_5a).status_code == 401
    assert s.client.post(f"{API}/auth/logout", headers=auth(s.fac1)).status_code == 204
    assert overview(s).status_code == 401 and s.get("/faculty/late-requests", s.fac1).status_code == 401
    assert s.get("/notifications", s.stu_5a2).status_code == 200  # other sessions are untouched


def test_expired_tokens_are_refused_everywhere_including_the_new_endpoints(s, api_app, monkeypatch):
    short = api_app.state.settings.model_copy(update={"jwt_expire_minutes": 1})
    monkeypatch.setattr(api_app.state, "settings", short)
    token = s._login("STUDENT", "STU0101", s.password)
    assert s.get("/notifications", token).status_code == 200
    s.at(NOW + timedelta(minutes=2))
    for path in ("/notifications", "/student/assignments", "/auth/me"):
        res = s.get(path, token)
        assert res.status_code == 401, path


def test_the_new_endpoints_fail_closed_when_redis_is_down(s, api_app, monkeypatch):
    import redis as redis_lib

    def down(*args, **kwargs):
        raise redis_lib.exceptions.ConnectionError("down")

    monkeypatch.setattr(api_app.state.redis, "get", down, raising=False)
    monkeypatch.setattr(api_app.state.redis, "exists", down, raising=False)
    for path in ("/notifications", "/faculty/overview", "/faculty/late-requests"):
        token = s.stu_5a if path == "/notifications" else s.fac1
        res = s.get(path, token)
        assert res.status_code in (401, 503), (path, res.status_code)  # never served without the revocation check
    assert s.count("notifications") == 0


# --- error envelope --------------------------------------------------------------------------------------------------------


def test_unexpected_errors_return_a_generic_500_without_internals(s, api_app):
    def boom():
        raise RuntimeError("secret internal detail: password=hunter2")

    api_app.add_api_route("/_test/boom", boom, methods=["GET"])
    res = s.client.get("/_test/boom")
    assert res.status_code == 500 and res.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "hunter2" not in res.text and "Traceback" not in res.text and "RuntimeError" not in res.text


def test_validation_errors_use_the_envelope_and_never_echo_submitted_secrets(s):
    res = s.client.post(f"{API}/auth/login", json={"role": "STUDENT", "login_id": "STU0101", "password": 12345})
    assert res.status_code == 422 and res.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "12345" not in res.text


# --- randomized workflow: invariants and independent SQL ---------------------------------------------------------------------


def invariants(s, step):
    t = overview(s).json()["totals"]
    assert t["on_time"] + t["late"] + t["pending"] + t["missing"] == t["expected"] == 17, step
    assert t["late_approved"] <= t["late"] and t["submitted"] == t["on_time"] + t["late"], step
    assert t["resubmitted"] <= t["submitted"] and t["reviewed"] == t["accepted"] + t["revision_requested"], step
    assert t["submitted"] == t["under_review"] + t["reviewed"] + t["not_reviewed"], step
    for name, value in independent_counts(s).items():
        assert t[name] == value, (step, name, t[name], value)
    for timing, key in (("ON_TIME", "on_time"), ("LATE", "late"), ("PENDING", "pending"), ("MISSING", "missing")):
        assert overview_students(s, timing=timing, limit=500).json()["total"] == t[key], (step, timing)
    # Database rules that must hold after any sequence of actions.
    assert s.sql("SELECT count(*) FROM submission_versions WHERE (upload_context = 'LATE_APPROVED') <> (late_request_id IS NOT NULL)")[0][0] == 0
    assert s.sql("SELECT count(*) FROM submissions s WHERE s.latest_version_no <> (SELECT count(*) FROM submission_versions v WHERE v.submission_id = s.id)")[0][0] == 0
    assert s.sql("SELECT count(*) - count(DISTINCT dedup_key) FROM notifications")[0][0] == 0
    assert s.sql("SELECT count(*) FROM late_requests WHERE status = 'APPROVED' AND window_end <= window_start")[0][0] == 0


@pytest.mark.parametrize("seed", [7, 2026])
def test_random_workflows_keep_every_invariant(s, seed):
    rnd = random.Random(seed)
    logins = ["STU0101", "STU0102", "STU0103", "STU0104", "STU0105", "STU0106"]
    tokens = {login: tok(s, login) for login in logins}
    clock = NOW
    payloads = iter(range(1000, 100000))
    for step in range(45):
        # Phase 1 (before the original deadline): uploads, reviews, an occasional extension. Phase 2 (after a jump of
        # ten days): late requests, decisions, late uploads, reviews and the odd extension.
        clock += timedelta(days=10) if step == 12 else timedelta(minutes=rnd.choice([1, 5, 30, 120, 360]) if step < 12 else rnd.choice([5, 60, 720, 1800]))
        s.at(clock)
        if step < 12:
            action = rnd.choice(["upload", "upload", "review", "extend"] if step % 5 == 4 else ["upload", "upload", "review"])
        else:
            action = rnd.choice(["ask", "ask", "decide", "decide", "upload", "upload", "review", "extend"])
        login = rnd.choice(logins[:3] if step < 12 else logins)  # three students never submit before the deadline
        if action == "upload":
            res = s.upload(token=tokens[login], data=pdf(next(payloads)))
            assert res.status_code in (201, 409), (step, res.status_code, res.text)
        elif action == "ask":
            res = s.ask(token=tokens[login])
            assert res.status_code in (201, 409), (step, res.status_code, res.text)
        elif action == "decide":
            pending = s.sql("SELECT id FROM late_requests WHERE status = 'PENDING'")
            if pending:
                body = {"decision": rnd.choice(["APPROVE", "REJECT"])}
                if body["decision"] == "APPROVE":
                    body["window_hours"] = rnd.randint(1, 72)
                res = s.post(f"/faculty/late-requests/{pending[0][0]}/decision", s.fac1, body)
                assert res.status_code == 200, (step, res.text)
        elif action == "review":
            has = s.sql("SELECT s.id FROM submissions s JOIN users u ON u.id = s.student_id WHERE u.login_id = :l AND s.assignment_id = :a", l=login, a=s.aid)
            if has:
                status = rnd.choice(["UNDER_REVIEW", "ACCEPTED", "REVISION_REQUESTED"])
                res = review(s, status, "feedback" if status == "REVISION_REQUESTED" else None, sid=str(has[0][0]))
                assert res.status_code in (201, 409), (step, res.status_code, res.text)
        else:
            res = s.patch(f"/faculty/assignments/{s.aid}/deadline", s.fac1, {"new_deadline": (clock + timedelta(hours=rnd.randint(1, 100))).isoformat()})
            assert res.status_code == 200, (step, res.text)
        invariants(s, step)
    # Storage and database agree after everything, refused uploads left nothing behind.
    with Session(s.engine) as db:
        assert orphans.find_orphans(s.s3, s.bucket, db) == [] and orphans.find_dangling(s.s3, s.bucket, db) == []
    assert s.count("submission_versions") == len(s.objects())
    # The run really exercised the workflow (fixed seeds, so this is deterministic).
    assert s.count("submission_versions") > 0 and s.count("late_requests") > 0 and s.count("reviews") > 0
    assert s.count("deadline_changes") > 0 and s.count("notifications") > 0
