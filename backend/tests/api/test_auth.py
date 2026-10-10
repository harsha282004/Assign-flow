"""Authentication API tests: login, /me, logout, revocation, expiry, throttling, Redis outages."""

import logging
from datetime import UTC, datetime, timedelta

import jwt
import pytest
import redis
from redis.exceptions import ConnectionError as RedisConnectionError

from app.core.config import get_settings
from app.core.security import create_access_token
from app.db.models import UserRole
from app.services import ratelimit

API = "/api/v1"
NOW = datetime(2026, 10, 11, 12, 0, tzinfo=UTC)


def login(client, role, login_id, password):
    return client.post(f"{API}/auth/login", json={"role": role, "login_id": login_id, "password": password})


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def token_for(client, role, login_id, password):
    res = login(client, role, login_id, password)
    assert res.status_code == 200, res.text
    return res.json()["access_token"]


# --- successful login -----------------------------------------------------------------------

def test_faculty_login_succeeds(client, test_password):
    res = login(client, "FACULTY", "FAC001", test_password)
    assert res.status_code == 200
    body = res.json()
    assert body["token_type"] == "bearer" and body["access_token"]
    assert body["user"]["login_id"] == "FAC001" and body["user"]["role"] == "FACULTY"
    assert "password" not in str(body).lower() and "hash" not in str(body).lower()
    assert res.headers["cache-control"] == "no-store"


def test_student_login_succeeds_and_login_id_is_case_insensitive(client, test_password):
    res = login(client, "STUDENT", " stu0101 ", test_password)
    assert res.status_code == 200
    assert res.json()["user"]["login_id"] == "STU0101"
    assert res.json()["user"]["role"] == "STUDENT"


def test_token_has_expected_claims_and_two_hour_lifetime(client, test_password, freeze_time):
    freeze_time(NOW)
    res = login(client, "STUDENT", "STU0101", test_password)
    claims = jwt.decode(res.json()["access_token"], get_settings().jwt_secret, algorithms=["HS256"], options={"verify_exp": False, "verify_iat": False})
    assert claims["role"] == "STUDENT" and claims["jti"] and claims["sub"] == res.json()["user"]["id"]
    assert claims["exp"] - claims["iat"] == 7200
    assert res.json()["expires_at"].startswith("2026-10-11T14:00:00")


# --- failed login: generic, identical responses -----------------------------------------------

def test_all_failure_causes_return_identical_generic_401(client, test_password, make_account):
    make_account("TMPINACT", UserRole.STUDENT, "pw-inactive-1", is_active=False)
    attempts = [
        ("FACULTY", "FAC001", "wrong-password"),  # wrong password
        ("FACULTY", "NOSUCHID", test_password),  # unknown ID
        ("FACULTY", "STU0101", test_password),  # student ID on the faculty form (role mismatch)
        ("STUDENT", "FAC001", test_password),  # faculty ID on the student form
        ("STUDENT", "TMPINACT", "pw-inactive-1"),  # inactive account, correct password
    ]
    bodies = []
    for role, login_id, password in attempts:
        res = login(client, role, login_id, password)
        assert res.status_code == 401, (role, login_id)
        bodies.append(res.json())
    assert all(b == bodies[0] for b in bodies)
    assert bodies[0]["error"]["code"] == "INVALID_CREDENTIALS"
    assert bodies[0]["error"]["message"] == "Invalid ID or password."


def test_validation_errors_do_not_echo_the_password(client):
    res = client.post(f"{API}/auth/login", json={"role": "STUDENT", "password": "super-secret-value"})
    assert res.status_code == 422 and res.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "super-secret-value" not in res.text
    res = client.post(f"{API}/auth/login", json={"role": "ADMIN", "login_id": "X", "password": "super-secret-value"})
    assert res.status_code == 422 and "super-secret-value" not in res.text


def test_nothing_sensitive_is_logged(client, test_password, caplog):
    caplog.set_level(logging.DEBUG)
    ok = login(client, "STUDENT", "STU0101", test_password)
    login(client, "STUDENT", "STU0101", "wrong-password-xyz")
    client.get(f"{API}/auth/me", headers=bearer(ok.json()["access_token"]))
    logged = "\n".join(r.getMessage() for r in caplog.records)
    for secret in (test_password, "wrong-password-xyz", ok.json()["access_token"], "$argon2"):
        assert secret not in logged


# --- /auth/me -----------------------------------------------------------------------------------

def test_me_for_student_returns_section_and_subjects_with_faculty(client, test_password):
    token = token_for(client, "STUDENT", "STU0101", test_password)
    res = client.get(f"{API}/auth/me", headers=bearer(token))
    assert res.status_code == 200
    me = res.json()
    assert me["login_id"] == "STU0101" and me["role"] == "STUDENT"
    assert {k: me["section"][k] for k in ("label", "semester", "name")} == {"label": "CSE-5A", "semester": 5, "name": "A"}
    assert me["section"]["id"] and all(s["id"] for s in me["subjects"])
    assert [s["code"] for s in me["subjects"]] == [f"CS50{i}" for i in range(1, 7)]
    assert next(s for s in me["subjects"] if s["code"] == "CS503")["faculty_name"]
    assert me["teaching"] is None


def test_me_for_faculty_returns_teaching_mappings(client, test_password):
    me = client.get(f"{API}/auth/me", headers=bearer(token_for(client, "FACULTY", "FAC001", test_password))).json()
    assert [(t["subject"]["code"], t["subject"]["name"], t["section"]["label"]) for t in me["teaching"]] == [
        ("CS503", "Database Systems", "CSE-5A")
    ]
    assert me["teaching"][0]["subject"]["id"] and me["teaching"][0]["section"]["id"]
    assert me["section"] is None and me["subjects"] is None


def test_me_for_faculty_without_classes_is_empty(client, test_password):
    me = client.get(f"{API}/auth/me", headers=bearer(token_for(client, "FACULTY", "QAFAC01", test_password))).json()
    assert me["teaching"] == []


# --- token validation ---------------------------------------------------------------------------

def test_missing_or_malformed_authorization_is_401(client):
    assert client.get(f"{API}/auth/me").status_code == 401
    assert client.get(f"{API}/auth/me").json()["error"]["code"] == "UNAUTHENTICATED"
    for header in ("Bearer", "Basic abc", "Bearer not.a.jwt", "Bearer "):
        res = client.get(f"{API}/auth/me", headers={"Authorization": header})
        assert res.status_code == 401, header


def test_expired_token_is_rejected(client, test_password, freeze_time):
    freeze_time(NOW)
    token = token_for(client, "STUDENT", "STU0101", test_password)
    freeze_time(NOW + timedelta(hours=2) - timedelta(seconds=1))
    assert client.get(f"{API}/auth/me", headers=bearer(token)).status_code == 200
    freeze_time(NOW + timedelta(hours=2))
    res = client.get(f"{API}/auth/me", headers=bearer(token))
    assert res.status_code == 401 and res.json()["error"]["code"] == "TOKEN_EXPIRED"


def test_tampered_and_foreign_signed_tokens_are_rejected(client, test_password):
    token = token_for(client, "STUDENT", "STU0101", test_password)
    head, payload, sig = token.split(".")
    assert client.get(f"{API}/auth/me", headers=bearer(f"{head}.{payload}.{sig[:-2]}xx")).status_code == 401
    forged = jwt.encode(
        {"sub": "00000000-0000-0000-0000-000000000000", "role": "FACULTY", "jti": "j", "iat": 1, "exp": 9999999999},
        "an-attacker-chosen-secret-of-sufficient-length",
        algorithm="HS256",
    )
    assert client.get(f"{API}/auth/me", headers=bearer(forged)).status_code == 401


def test_token_for_unknown_user_is_rejected(client):
    import uuid

    token, _, _ = create_access_token(get_settings(), uuid.uuid4(), "FACULTY", datetime.now(UTC))
    res = client.get(f"{API}/auth/me", headers=bearer(token))
    assert res.status_code == 401 and res.json()["error"]["code"] == "INVALID_TOKEN"


def test_deactivated_account_loses_access_immediately(client, make_account, set_active):
    make_account("TMPUSER1", UserRole.STUDENT, "pw-temp-user-1")
    token = token_for(client, "STUDENT", "TMPUSER1", "pw-temp-user-1")
    assert client.get(f"{API}/auth/me", headers=bearer(token)).status_code == 200
    set_active("TMPUSER1", False)
    assert client.get(f"{API}/auth/me", headers=bearer(token)).status_code == 401
    assert login(client, "STUDENT", "TMPUSER1", "pw-temp-user-1").status_code == 401


def test_role_comes_from_database_not_token_claim(client, test_password):
    # A student's token claiming FACULTY must still be treated as a student.
    token = token_for(client, "STUDENT", "STU0101", test_password)
    claims = jwt.decode(token, options={"verify_signature": False})
    claims["role"] = "FACULTY"
    forged_role = jwt.encode(claims, get_settings().jwt_secret, algorithm="HS256")
    assert client.get("/_test/faculty-only", headers=bearer(forged_role)).status_code == 403
    assert client.get("/_test/student-only", headers=bearer(forged_role)).status_code == 200


# --- logout / revocation ---------------------------------------------------------------------

def test_logout_revokes_token_with_matching_ttl(client, test_password, redis_client, freeze_time):
    freeze_time(NOW)
    res = login(client, "FACULTY", "FAC001", test_password)
    token = res.json()["access_token"]
    claims = jwt.decode(token, options={"verify_signature": False})
    assert client.post(f"{API}/auth/logout", headers=bearer(token)).status_code == 204
    ttl = redis_client.ttl(f"deny:jti:{claims['jti']}")
    assert 7190 <= ttl <= 7200
    res = client.get(f"{API}/auth/me", headers=bearer(token))
    assert res.status_code == 401 and res.json()["error"]["code"] == "TOKEN_REVOKED"
    # Logging out again with the revoked token is also 401, and a fresh login still works.
    assert client.post(f"{API}/auth/logout", headers=bearer(token)).status_code == 401
    assert login(client, "FACULTY", "FAC001", test_password).status_code == 200


def test_logout_requires_authentication(client):
    assert client.post(f"{API}/auth/logout").status_code == 401


def test_logout_revokes_only_the_current_session(client, test_password):
    first = token_for(client, "STUDENT", "STU0101", test_password)
    second = token_for(client, "STUDENT", "STU0101", test_password)
    client.post(f"{API}/auth/logout", headers=bearer(first))
    assert client.get(f"{API}/auth/me", headers=bearer(first)).status_code == 401
    assert client.get(f"{API}/auth/me", headers=bearer(second)).status_code == 200


# --- role guards -----------------------------------------------------------------------------------

def test_role_guards(client, test_password):
    student = token_for(client, "STUDENT", "STU0101", test_password)
    faculty = token_for(client, "FACULTY", "FAC001", test_password)
    assert client.get("/_test/faculty-only").status_code == 401
    assert client.get("/_test/faculty-only", headers=bearer(student)).status_code == 403
    assert client.get("/_test/faculty-only", headers=bearer(student)).json()["error"]["code"] == "FORBIDDEN"
    assert client.get("/_test/student-only", headers=bearer(faculty)).status_code == 403
    assert client.get("/_test/faculty-only", headers=bearer(faculty)).status_code == 200
    assert client.get("/_test/student-only", headers=bearer(student)).status_code == 200


def test_unknown_route_uses_error_envelope(client):
    res = client.get(f"{API}/does-not-exist")
    assert res.status_code == 404 and res.json()["error"]["code"] == "NOT_FOUND"


# --- throttling ---------------------------------------------------------------------------------------

def test_sixth_failed_attempt_for_one_id_is_429_even_with_correct_password(client, test_password):
    for _ in range(5):
        assert login(client, "FACULTY", "FAC002", "bad-password").status_code == 401
    res = login(client, "FACULTY", "FAC002", test_password)
    assert res.status_code == 429 and res.json()["error"]["code"] == "RATE_LIMITED"
    assert 1 <= int(res.headers["retry-after"]) <= 600
    # Other IDs (and the same ID on the other role form) are unaffected.
    assert login(client, "FACULTY", "FAC003", test_password).status_code == 200
    assert login(client, "STUDENT", "FAC002", "bad-password").status_code == 401


def test_successful_login_resets_the_failure_counter(client, test_password):
    for _ in range(4):
        login(client, "FACULTY", "FAC004", "bad-password")
    assert login(client, "FACULTY", "FAC004", test_password).status_code == 200
    for _ in range(4):
        assert login(client, "FACULTY", "FAC004", "bad-password").status_code == 401
    assert login(client, "FACULTY", "FAC004", test_password).status_code == 200


def test_failure_counter_expires_after_ten_minutes(client, redis_client):
    login(client, "FACULTY", "FAC005", "bad-password")
    key = "rl:loginfail:FACULTY:FAC005"
    assert 590 <= redis_client.ttl(key) <= 600
    login(client, "FACULTY", "FAC005", "bad-password")
    assert redis_client.ttl(key) <= 600 and int(redis_client.get(key)) == 2  # TTL not extended by later failures


def test_per_ip_limit_is_ten_logins_per_minute(client):
    for i in range(10):
        assert login(client, "STUDENT", f"NOPE{i}", "x").status_code == 401
    res = login(client, "STUDENT", "NOPE11", "x")
    assert res.status_code == 429 and res.json()["error"]["code"] == "RATE_LIMITED"
    assert res.headers["retry-after"]


# --- fail closed when Redis is unavailable ---------------------------------------------------------------

@pytest.fixture
def broken_redis():
    return redis.Redis(host="127.0.0.1", port=1, decode_responses=True, socket_connect_timeout=0.5)


def test_login_fails_closed_when_redis_is_down(client, api_app, monkeypatch, broken_redis, test_password):
    monkeypatch.setattr(api_app.state, "redis", broken_redis)
    res = login(client, "FACULTY", "FAC001", test_password)
    assert res.status_code == 503 and res.json()["error"]["code"] == "SERVICE_UNAVAILABLE"
    assert "access_token" not in res.text


def test_ip_limiter_fails_closed_when_its_storage_is_down(client, monkeypatch, test_password):
    class Down:
        def hit(self, *a, **k):
            raise RedisConnectionError("down")

        def test(self, *a, **k):
            raise RedisConnectionError("down")

    monkeypatch.setattr(ratelimit.limiter, "_limiter", Down())
    res = login(client, "FACULTY", "FAC001", test_password)
    assert res.status_code == 503 and res.json()["error"]["code"] == "SERVICE_UNAVAILABLE"


def test_authenticated_requests_and_logout_fail_closed_when_redis_is_down(client, api_app, monkeypatch, broken_redis, test_password):
    token = token_for(client, "STUDENT", "STU0101", test_password)
    monkeypatch.setattr(api_app.state, "redis", broken_redis)
    assert client.get(f"{API}/auth/me", headers=bearer(token)).status_code == 503
    assert client.get("/_test/student-only", headers=bearer(token)).status_code == 503
    assert client.post(f"{API}/auth/logout", headers=bearer(token)).status_code == 503
    monkeypatch.undo()
    # The failed logout did not silently revoke or pretend to: the token still works once Redis is back.
    assert client.get(f"{API}/auth/me", headers=bearer(token)).status_code == 200


# --- Phase 1 regression -------------------------------------------------------------------------------------

def test_health_endpoint_still_reports_real_dependencies(client):
    res = client.get(f"{API}/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "db": "ok", "redis": "ok", "storage": "ok"}
