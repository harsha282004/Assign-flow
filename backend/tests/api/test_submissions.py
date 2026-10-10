"""Phase 5: submission engine, version history, status, downloads, storage failures and consistency."""

import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from botocore.exceptions import ClientError, EndpointConnectionError
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from app.services import orphans, submissions
from app.services.storage import assert_bucket_private
from tests.api.test_assignments import API, NOW, World, auth, iso
from tests.unit.test_file_validation import jpeg, office, pdf, png, zip_bytes

MB = 1024 * 1024
ALL_TYPES = ["pdf", "docx", "pptx", "zip", "png", "jpg"]
DEADLINE = NOW + timedelta(days=2)


class S(World):
    """World plus one published assignment (CS503 / CSE-5A) accepting every file type up to 1 MB."""

    def __init__(self, *args, s3_client, bucket, engine):
        super().__init__(*args)
        self.s3, self.bucket, self.engine = s3_client, bucket, engine
        self.assignment = self.create(allowed_types=ALL_TYPES, max_file_mb=1).json()
        self.aid = self.assignment["id"]

    def upload(self, token=None, aid=None, name="report.pdf", data=None, content_type="application/octet-stream", **form):
        files = {"file": (name, pdf() if data is None else data, content_type)}
        return self.client.post(
            f"{API}/student/assignments/{aid or self.aid}/submissions",
            files=files,
            data=form or None,
            headers=auth(token or self.stu_5a),
        )

    def objects(self) -> list[str]:
        return [o["Key"] for o in self.s3.list_objects_v2(Bucket=self.bucket).get("Contents", [])]

    def sql(self, query: str, **params):
        with Session(self.engine) as s:
            return s.execute(text(query), params).all()

    def count(self, table: str) -> int:
        return self.sql(f"SELECT count(*) FROM {table}")[0][0]

    def student_id(self, login_id: str) -> str:
        return str(self.sql("SELECT id FROM users WHERE login_id = :l", l=login_id)[0][0])

    def insert_first_version(self, login_id="STU0101", uploaded_at=None, deadline_at_upload=None, context="REGULAR"):
        """Write a submission + version straight into the database (simulates data other phases will create)."""
        sid = self.student_id(login_id)
        with Session(self.engine) as s:
            sub_id = s.execute(
                text("INSERT INTO submissions (assignment_id, student_id, latest_version_no) VALUES (:a, :s, 1) RETURNING id"),
                dict(a=self.aid, s=sid),
            ).scalar()
            s.execute(
                text(
                    "INSERT INTO submission_versions (submission_id, version_no, storage_key, original_filename, mime_type, "
                    "size_bytes, sha256, uploaded_at, uploaded_by, deadline_at_upload, upload_context) "
                    "VALUES (:sub, 1, :key, 'seed.pdf', 'application/pdf', 5, :sha, :up, :by, :dl, CAST(:ctx AS upload_context))"
                ),
                dict(sub=sub_id, key=f"submissions/seed/{uuid.uuid4()}.pdf", sha="c" * 64, up=uploaded_at or NOW,
                     by=sid, dl=deadline_at_upload or DEADLINE, ctx=context),
            )
            s.commit()
            return str(sub_id)

    def insert_review(self, submission_id, review_status, login="FAC001"):
        with Session(self.engine) as s:
            version_id = s.execute(text("SELECT id FROM submission_versions WHERE submission_id = :s ORDER BY version_no DESC LIMIT 1"), dict(s=submission_id)).scalar()
            s.execute(
                text("INSERT INTO reviews (submission_id, version_id, reviewer_id, status) VALUES (:s, :v, :r, CAST(:st AS review_status))"),
                dict(s=submission_id, v=version_id, r=self.student_id(login), st=review_status),
            )
            s.commit()


@pytest.fixture
def s(client, api_app, monkeypatch, test_password, freeze_time, s3_client, settings, seeded_engine) -> S:
    monkeypatch.setattr(api_app.state, "settings", api_app.state.settings.model_copy(update={"jwt_expire_minutes": 60 * 24 * 30}))
    return S(client, test_password, freeze_time, s3_client=s3_client, bucket=settings.s3_bucket, engine=seeded_engine)


# --- valid uploads -------------------------------------------------------------------------------------------

def test_valid_upload_creates_version_one_with_server_timestamp_and_private_object(s):
    data = pdf(500)
    res = s.upload(data=data)
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["version_no"] == 1 and body["upload_context"] == "REGULAR"
    assert datetime.fromisoformat(body["uploaded_at"]) == NOW  # server clock
    assert datetime.fromisoformat(body["deadline_at_upload"]) == DEADLINE
    assert (body["version_timing"], body["submission_timing"], body["is_resubmitted"]) == ("ON_TIME", "ON_TIME", False)

    (row,) = s.sql("SELECT storage_key, original_filename, mime_type, size_bytes, sha256, uploaded_by FROM submission_versions")
    key = row[0]
    assert re.fullmatch(rf"submissions/{s.aid}/{s.student_id('STU0101')}/[0-9a-f-]{{36}}\.pdf", key)
    assert row[1:5] == ("report.pdf", "application/pdf", len(data), __import__("hashlib").sha256(data).hexdigest())
    assert s.objects() == [key]
    assert s.s3.get_object(Bucket=s.bucket, Key=key)["Body"].read() == data
    assert s.sql("SELECT latest_version_no FROM submissions")[0][0] == 1


def test_client_supplied_timestamps_and_status_are_ignored(s):
    res = s.upload(uploaded_at="2000-01-01T00:00:00Z", deadline_at_upload="2999-01-01T00:00:00Z",
                   upload_context="LATE_APPROVED", version_no="99", status="ON_TIME")
    assert res.status_code == 201
    assert datetime.fromisoformat(res.json()["uploaded_at"]) == NOW
    assert res.json()["upload_context"] == "REGULAR" and res.json()["version_no"] == 1
    assert datetime.fromisoformat(s.sql("SELECT uploaded_at FROM submission_versions")[0][0].isoformat()) == NOW


@pytest.mark.parametrize(
    "name, data",
    [("a.png", png()), ("a.jpg", jpeg()), ("a.jpeg", jpeg()), ("a.zip", zip_bytes({"x.txt": b"hi"})),
     ("a.docx", office("docx")), ("a.pptx", office("pptx")), ("a.PDF", pdf())],
)
def test_every_approved_type_is_accepted(s, name, data):
    assert s.upload(name=name, data=data).status_code == 201


# --- invalid uploads ----------------------------------------------------------------------------------------------

@pytest.mark.parametrize(
    "name, data, ctype",
    [
        ("malware.exe", b"MZ" + b"\x00" * 100, "application/octet-stream"),
        ("noextension", pdf(), "application/pdf"),
        ("fake.pdf", png(), "application/pdf"),  # PNG content under a .pdf name, with a lying Content-Type
        ("fake.png", pdf(), "image/png"),
        ("notes.pdf", b"plain text pretending to be a pdf" * 10, "application/pdf"),
        ("a.docx", zip_bytes({"readme.txt": b"x"}), "application/octet-stream"),  # plain zip as docx
        ("a.pptx", zip_bytes({"word/document.xml": b"x"}), "application/octet-stream"),  # wrong office part
        ("a.docx", b"PK\x03\x04 broken archive", "application/octet-stream"),
        ("a.xlsx", zip_bytes({"xl/workbook.xml": b"x"}), "application/octet-stream"),
    ],
)
def test_wrong_type_or_content_is_rejected_with_415_and_nothing_is_stored(s, name, data, ctype):
    res = s.upload(name=name, data=data, content_type=ctype)
    assert res.status_code == 415 and res.json()["error"]["code"] == "UNSUPPORTED_TYPE", res.text
    assert s.objects() == [] and s.count("submissions") == 0 and s.count("submission_versions") == 0


def test_client_content_type_is_not_trusted(s):
    assert s.upload(name="real.pdf", data=pdf(), content_type="image/png").status_code == 201


def test_type_must_be_allowed_by_the_assignment(s):
    pdf_only = s.create(allowed_types=["pdf"]).json()
    res = s.upload(aid=pdf_only["id"], name="a.png", data=png())
    assert res.status_code == 415 and "PDF" in res.json()["error"]["message"]
    assert s.upload(aid=pdf_only["id"], name="a.pdf").status_code == 201


def test_empty_file_missing_file_and_bad_form_are_422(s):
    assert s.upload(data=b"").status_code == 422
    res = s.client.post(f"{API}/student/assignments/{s.aid}/submissions", data={"note": "x"}, headers=auth(s.stu_5a))
    assert res.status_code == 422 and res.json()["error"]["code"] == "VALIDATION_ERROR"
    assert s.count("submissions") == 0


def test_size_limit_is_enforced_exactly(s):
    exact = b"%PDF-1.4\n" + b"x" * (1 * MB - 9)  # assignment limit is 1 MB
    assert len(exact) == MB
    assert s.upload(data=exact).status_code == 201
    res = s.upload(data=exact + b"y")
    assert res.status_code == 413 and res.json()["error"]["code"] == "FILE_TOO_LARGE"
    assert s.count("submission_versions") == 1 and len(s.objects()) == 1  # the oversized file left no trace


def test_global_limit_rejects_huge_bodies_before_they_are_parsed(s):
    res = s.upload(data=b"%PDF-1.4\n" + b"x" * (11 * MB))
    assert res.status_code == 413 and res.json()["error"]["code"] == "FILE_TOO_LARGE"
    assert s.objects() == []


def test_body_without_content_length_is_refused(s):
    boundary = "xBOUNDARYx"
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"a.pdf\"\r\n\r\n").encode() + pdf() + f"\r\n--{boundary}--\r\n".encode()
    res = s.client.post(
        f"{API}/student/assignments/{s.aid}/submissions",
        content=iter([body]),  # streamed -> chunked, no Content-Length
        headers={**auth(s.stu_5a), "Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    assert res.status_code == 411 and res.json()["error"]["code"] == "LENGTH_REQUIRED"


def test_filenames_never_become_storage_paths(s):
    for raw in ("../../etc/passwd.pdf", "C:\\fakepath\\r.pdf", "a" * 400 + ".pdf"):
        data = pdf(50 + len(raw))
        assert s.upload(name=raw, data=data).status_code == 201
    names = [r[0] for r in s.sql("SELECT original_filename FROM submission_versions ORDER BY version_no")]
    assert names[0] == "passwd.pdf" and names[1] == "r.pdf" and len(names[2]) == 200 and names[2].endswith(".pdf")
    assert all(re.fullmatch(rf"submissions/{s.aid}/[0-9a-f-]{{36}}/[0-9a-f-]{{36}}\.pdf", k) for k in s.objects())
    assert not any("passwd" in k or "fakepath" in k for k in s.objects())


# --- authorization and scope ----------------------------------------------------------------------------------------

def test_cross_section_draft_faculty_and_anonymous_uploads_are_refused(s):
    assert s.upload(token=s.stu_5b).status_code == 404  # other section
    draft = s.create(publish=False, allowed_types=["pdf"]).json()
    assert s.upload(aid=draft["id"]).status_code == 404  # drafts accept nothing
    assert s.upload(aid="00000000-0000-0000-0000-000000000000").status_code == 404
    assert s.upload(token=s.fac1).status_code == 403
    res = s.client.post(f"{API}/student/assignments/{s.aid}/submissions", files={"file": ("a.pdf", pdf(), "application/pdf")})
    assert res.status_code == 401
    assert s.objects() == [] and s.count("submissions") == 0


# --- versions -------------------------------------------------------------------------------------------------------

def test_resubmission_keeps_every_earlier_version_and_file(s):
    v1, v2, v3 = pdf(300), png(300), jpeg(300)
    r1, r2 = s.upload(name="one.pdf", data=v1), s.upload(name="two.png", data=v2)
    assert (r1.json()["version_no"], r2.json()["version_no"]) == (1, 2)
    assert r2.json()["is_resubmitted"] is True and r2.json()["submission_timing"] == "ON_TIME"
    rows_before = s.sql("SELECT version_no, storage_key, sha256, uploaded_at FROM submission_versions ORDER BY version_no")

    s.freeze_time(NOW + timedelta(minutes=5))
    assert s.upload(name="three.jpg", data=v3).json()["version_no"] == 3
    rows_after = s.sql("SELECT version_no, storage_key, sha256, uploaded_at FROM submission_versions ORDER BY version_no")
    assert rows_after[:2] == rows_before  # earlier versions are untouched
    assert len(s.objects()) == 3 and {r[1] for r in rows_after} == set(s.objects())
    for (vid,), data in zip(s.sql("SELECT id FROM submission_versions ORDER BY version_no"), (v1, v2, v3), strict=True):
        dl = s.get(f"/files/versions/{vid}", s.stu_5a)
        assert dl.status_code == 200 and dl.content == data


def test_identical_to_latest_is_a_duplicate_but_identical_to_an_older_version_is_allowed(s):
    a, b = pdf(100), pdf(200)
    s.upload(data=a)
    s.upload(data=b)
    dup = s.upload(data=b)
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "DUPLICATE_UPLOAD"
    assert s.count("submission_versions") == 2 and len(s.objects()) == 2  # no extra row and no extra object
    assert s.upload(data=a).json()["version_no"] == 3  # only the latest version is compared


def test_student_detail_lists_own_versions_without_storage_keys(s):
    s.upload(name="one.pdf", data=pdf(100))
    s.upload(name="two.pdf", data=pdf(200))
    res = s.get(f"/student/assignments/{s.aid}", s.stu_5a)
    d = res.json()
    assert [v["version_no"] for v in d["versions"]] == [1, 2]
    assert d["versions"][0]["original_filename"] == "one.pdf" and d["versions"][0]["size_bytes"] == len(pdf(100))
    assert d["timing"] == "ON_TIME" and d["is_resubmitted"] is True and d["can_upload"] is True
    assert "storage_key" not in res.text and "submissions/" not in res.text
    assert s.get(f"/student/assignments/{s.aid}", s.stu_5a2).json()["versions"] == []  # a classmate sees nothing of it


# --- status engine: boundaries ----------------------------------------------------------------------------------------

def test_upload_one_second_before_and_exactly_at_the_deadline_are_on_time(s):
    s.freeze_time(DEADLINE - timedelta(seconds=1))
    assert s.upload(token=s.stu_5a).json()["version_timing"] == "ON_TIME"
    s.freeze_time(DEADLINE)
    res = s.upload(token=s.stu_5a2)
    assert res.status_code == 201 and res.json()["version_timing"] == "ON_TIME"
    assert s.get("/student/assignments", s.stu_5a2).json()[0]["timing"] == "ON_TIME"


def test_upload_after_the_deadline_is_refused_and_leaves_no_trace(s):
    s.freeze_time(DEADLINE + timedelta(seconds=1))
    res = s.upload()
    assert res.status_code == 409 and res.json()["error"]["code"] == "DEADLINE_PASSED"
    assert s.objects() == [] and s.count("submissions") == 0
    detail = s.get(f"/student/assignments/{s.aid}", s.stu_5a).json()
    assert detail["timing"] == "MISSING" and detail["can_upload"] is False and detail["upload_blocked_reason"] == "DEADLINE_PASSED"


def test_pending_and_missing_without_a_submission(s):
    assert s.get("/student/assignments", s.stu_5a).json()[0]["timing"] == "PENDING"
    s.freeze_time(DEADLINE)
    assert s.get("/student/assignments", s.stu_5a).json()[0]["timing"] == "PENDING"
    s.freeze_time(DEADLINE + timedelta(seconds=1))
    assert s.get("/student/assignments", s.stu_5a).json()[0]["timing"] == "MISSING"


def test_resubmission_after_the_deadline_is_refused_and_the_first_version_stays_on_time(s):
    s.upload(data=pdf(100))
    s.freeze_time(DEADLINE + timedelta(minutes=1))
    assert s.upload(data=pdf(200)).status_code == 409
    d = s.get(f"/student/assignments/{s.aid}", s.stu_5a).json()
    assert d["timing"] == "ON_TIME" and len(d["versions"]) == 1 and d["can_upload"] is False
    assert s.count("submission_versions") == 1 and len(s.objects()) == 1


def test_late_timing_is_derived_from_the_first_version(s):
    # A first version received after the deadline (created by later phases, e.g. an approved late request).
    s.insert_first_version(uploaded_at=DEADLINE + timedelta(hours=1), context="REGULAR")
    s.freeze_time(DEADLINE + timedelta(days=1))
    assert s.get("/student/assignments", s.stu_5a).json()[0]["timing"] == "LATE"
    v = s.get(f"/student/assignments/{s.aid}", s.stu_5a).json()["versions"][0]
    assert (v["timing_at_upload"], v["timing_now"]) == ("LATE", "LATE")
    roster = {r["student"]["login_id"]: r for r in s.get(f"/faculty/assignments/{s.aid}/roster", s.fac1).json()}
    assert roster["STU0101"]["timing"] == "LATE" and roster["STU0102"]["timing"] == "MISSING"
    # Extending the deadline past that upload recomputes it against the current deadline.
    s.freeze_time(DEADLINE + timedelta(hours=1, minutes=30))
    assert s.patch(f"/faculty/assignments/{s.aid}/deadline", s.fac1, {"new_deadline": iso(DEADLINE + timedelta(days=3))}).status_code == 200
    v = s.get(f"/student/assignments/{s.aid}", s.stu_5a).json()["versions"][0]
    assert (v["timing_at_upload"], v["timing_now"]) == ("LATE", "ON_TIME")  # snapshot vs current deadline
    assert s.get("/student/assignments", s.stu_5a).json()[0]["timing"] == "ON_TIME"


# --- deadline changes and per-version snapshots ------------------------------------------------------------------------------

def test_each_version_keeps_the_deadline_that_applied_when_it_was_received(s):
    s.upload(data=pdf(100))
    s.freeze_time(NOW + timedelta(hours=1))
    new_deadline = NOW + timedelta(days=6)
    assert s.patch(f"/faculty/assignments/{s.aid}/deadline", s.fac1, {"new_deadline": iso(new_deadline)}).status_code == 200
    s.freeze_time(NOW + timedelta(hours=2))
    r2 = s.upload(data=pdf(200)).json()
    assert datetime.fromisoformat(r2["deadline_at_upload"]) == new_deadline
    versions = s.get(f"/student/assignments/{s.aid}", s.stu_5a).json()["versions"]
    assert datetime.fromisoformat(versions[0]["deadline_at_upload"]) == DEADLINE  # v1 keeps its snapshot
    assert datetime.fromisoformat(versions[1]["deadline_at_upload"]) == new_deadline
    assert all(v["timing_now"] == "ON_TIME" for v in versions)


def test_extending_a_passed_deadline_reopens_uploads_with_the_new_snapshot(s):
    s.freeze_time(DEADLINE + timedelta(hours=1))
    assert s.upload().status_code == 409
    new_deadline = DEADLINE + timedelta(days=2)
    assert s.patch(f"/faculty/assignments/{s.aid}/deadline", s.fac1, {"new_deadline": iso(new_deadline)}).status_code == 200
    res = s.upload()
    assert res.status_code == 201 and res.json()["upload_context"] == "REGULAR" and res.json()["version_timing"] == "ON_TIME"
    assert datetime.fromisoformat(res.json()["deadline_at_upload"]) == new_deadline


# --- review state is read (never written) by the eligibility rules ----------------------------------------------------------------

def test_accepted_submission_blocks_further_uploads(s):
    s.upload(data=pdf(100))
    (sub_id,) = [str(r[0]) for r in s.sql("SELECT id FROM submissions")]
    s.insert_review(sub_id, "ACCEPTED")
    res = s.upload(data=pdf(200))
    assert res.status_code == 409 and res.json()["error"]["code"] == "SUBMISSION_ACCEPTED"
    d = s.get(f"/student/assignments/{s.aid}", s.stu_5a).json()
    assert d["can_upload"] is False and d["upload_blocked_reason"] == "SUBMISSION_ACCEPTED"


def test_revision_request_allows_an_after_deadline_upload_without_changing_first_version_timing(s):
    s.upload(data=pdf(100))
    (sub_id,) = [str(r[0]) for r in s.sql("SELECT id FROM submissions")]
    s.insert_review(sub_id, "REVISION_REQUESTED")
    s.freeze_time(DEADLINE + timedelta(days=1))
    res = s.upload(data=pdf(200))
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["upload_context"] == "REVISION" and body["version_timing"] == "LATE"
    assert body["submission_timing"] == "ON_TIME"  # timing of the first version (Q1): a revision never makes it late
    assert s.get("/student/assignments", s.stu_5a).json()[0]["timing"] == "ON_TIME"


# --- faculty views ----------------------------------------------------------------------------------------------------------------------

def test_roster_lists_every_student_with_real_status_and_filters(s):
    s.upload(token=s.stu_5a, data=pdf(100))
    s.upload(token=s.stu_5a, data=pdf(200))
    s.upload(token=s.stu_5a2, data=pdf(300))
    rows = s.get(f"/faculty/assignments/{s.aid}/roster", s.fac1).json()
    assert len(rows) == 17 and [r["student"]["login_id"] for r in rows] == sorted(r["student"]["login_id"] for r in rows)
    by_id = {r["student"]["login_id"]: r for r in rows}
    assert (by_id["STU0101"]["timing"], by_id["STU0101"]["is_resubmitted"], by_id["STU0101"]["version_count"]) == ("ON_TIME", True, 2)
    assert (by_id["STU0102"]["timing"], by_id["STU0102"]["is_resubmitted"], by_id["STU0102"]["version_count"]) == ("ON_TIME", False, 1)
    assert by_id["STU0103"] == {**by_id["STU0103"], "timing": "PENDING", "version_count": 0, "latest_uploaded_at": None}
    assert datetime.fromisoformat(by_id["STU0101"]["latest_uploaded_at"]) == NOW
    assert "STU0118" not in by_id  # a student of another section is not expected here

    counts = {k: len(s.get(f"/faculty/assignments/{s.aid}/roster?status={k}", s.fac1).json()) for k in ("ON_TIME", "PENDING", "LATE", "MISSING")}
    assert counts == {"ON_TIME": 2, "PENDING": 15, "LATE": 0, "MISSING": 0}
    s.freeze_time(DEADLINE + timedelta(seconds=1))
    assert len(s.get(f"/faculty/assignments/{s.aid}/roster?status=MISSING", s.fac1).json()) == 15
    assert s.get(f"/faculty/assignments/{s.aid}/roster?status=BOGUS", s.fac1).status_code == 422


def test_roster_and_student_submission_authorization(s):
    path = f"/faculty/assignments/{s.aid}/roster"
    assert s.get(path, s.fac2).status_code == 404 and s.get(path, s.fac49).status_code == 404
    assert s.get(path, s.stu_5a).status_code == 403
    assert s.client.get(f"{API}{path}").status_code == 401
    draft = s.create(publish=False).json()
    res = s.get(f"/faculty/assignments/{draft['id']}/roster", s.fac1)
    assert res.status_code == 409 and res.json()["error"]["code"] == "NOT_PUBLISHED"


def test_faculty_sees_a_students_versions_and_can_download_them(s):
    first, second = pdf(111), png(222)
    s.upload(name="one.pdf", data=first)
    s.upload(name="two.png", data=second)
    sid = s.student_id("STU0101")
    res = s.get(f"/faculty/assignments/{s.aid}/students/{sid}/timeline", s.fac1)
    assert res.status_code == 200
    body = res.json()
    assert body["student"]["login_id"] == "STU0101" and body["timing"] == "ON_TIME" and body["is_resubmitted"] is True
    assert [v["original_filename"] for v in body["versions"]] == ["one.pdf", "two.png"]
    assert "storage_key" not in res.text
    dl = s.get(f"/files/versions/{body['versions'][1]['id']}", s.fac1)
    assert dl.status_code == 200 and dl.content == second

    assert s.get(f"/faculty/assignments/{s.aid}/students/{sid}/timeline", s.fac2).status_code == 404
    assert s.get(f"/faculty/assignments/{s.aid}/students/{sid}/timeline", s.stu_5a).status_code == 403
    other_section_student = s.student_id("STU0118")
    assert s.get(f"/faculty/assignments/{s.aid}/students/{other_section_student}/timeline", s.fac1).status_code == 404
    assert s.get(f"/faculty/assignments/{s.aid}/students/{uuid.uuid4()}/timeline", s.fac1).status_code == 404


# --- downloads and private storage -------------------------------------------------------------------------------------------------------------

def test_download_headers_and_scope(s):
    data = pdf(400)
    s.upload(name='my "report"; é.pdf', data=data)
    (vid,) = [str(r[0]) for r in s.sql("SELECT id FROM submission_versions")]
    ok = s.get(f"/files/versions/{vid}", s.stu_5a)
    assert ok.status_code == 200 and ok.content == data
    h = ok.headers
    assert h["content-disposition"].startswith("attachment;") and "filename*=UTF-8''" in h["content-disposition"]
    assert h["x-content-type-options"] == "nosniff" and h["content-type"] == "application/octet-stream"
    assert h["cache-control"] == "private, no-store" and h["content-length"] == str(len(data))

    assert s.get(f"/files/versions/{vid}", s.fac1).status_code == 200  # the assignment's teacher
    for token in (s.stu_5a2, s.stu_5b, s.fac2, s.fac49):  # classmate, other section, other faculty, unassigned faculty
        assert s.get(f"/files/versions/{vid}", token).status_code == 404
    assert s.client.get(f"{API}/files/versions/{vid}").status_code == 401
    assert s.get(f"/files/versions/{uuid.uuid4()}", s.stu_5a).status_code == 404
    s.client.post(f"{API}/auth/logout", headers=auth(s.stu_5a))
    assert s.get(f"/files/versions/{vid}", s.stu_5a).status_code == 401  # revoked token


def test_objects_are_private_and_no_json_exposes_storage_details(s, settings):
    res = s.upload(data=pdf(100))
    (key,) = s.objects()
    assert_bucket_private(s.s3, s.bucket)
    anon = httpx.get(f"{settings.s3_endpoint_url.rstrip('/')}/{s.bucket}/{key}", timeout=5)
    assert anon.status_code in (401, 403)
    texts = [res.text, s.get(f"/student/assignments/{s.aid}", s.stu_5a).text, s.get("/student/assignments", s.stu_5a).text,
             s.get(f"/faculty/assignments/{s.aid}/roster", s.fac1).text, s.get(f"/faculty/assignments/{s.aid}", s.fac1).text]
    for t in texts:
        assert key not in t and "storage_key" not in t and s.bucket not in t and "http://minio" not in t


# --- storage failures and database / storage consistency -----------------------------------------------------------------------------------------------

class FailingS3:
    """Delegates to the real client, failing selected operations."""

    def __init__(self, real, fail=()):
        self.real, self.fail = real, set(fail)

    def __getattr__(self, name):
        if name in self.fail:
            def boom(*a, **k):
                if name == "get_object":
                    raise EndpointConnectionError(endpoint_url="http://minio:9000")
                raise ClientError({"Error": {"Code": "InternalError", "Message": "down"}}, name)
            return boom
        return getattr(self.real, name)


def test_storage_down_during_upload_returns_503_and_writes_nothing(s, api_app, monkeypatch):
    monkeypatch.setattr(api_app.state, "s3", FailingS3(s.s3, {"put_object"}))
    res = s.upload()
    assert res.status_code == 503 and res.json()["error"]["code"] == "STORAGE_UNAVAILABLE"
    monkeypatch.undo()
    assert s.count("submissions") == 0 and s.count("submission_versions") == 0 and s.objects() == []
    assert s.upload().status_code == 201  # and it recovers


def test_storage_down_during_download_returns_503_and_a_missing_object_returns_404(s, api_app, monkeypatch):
    s.upload(data=pdf(100))
    (vid,) = [str(r[0]) for r in s.sql("SELECT id FROM submission_versions")]
    monkeypatch.setattr(api_app.state, "s3", FailingS3(s.s3, {"get_object"}))
    res = s.get(f"/files/versions/{vid}", s.stu_5a)
    assert res.status_code == 503 and res.json()["error"]["code"] == "STORAGE_UNAVAILABLE"
    monkeypatch.undo()
    s.s3.delete_object(Bucket=s.bucket, Key=s.objects()[0])  # database row without an object (should never happen)
    assert s.get(f"/files/versions/{vid}", s.stu_5a).status_code == 404
    assert orphans.find_dangling(s.s3, s.bucket, Session(s.engine)) != []


def test_database_failure_after_storing_removes_the_object(s, monkeypatch):
    def explode(*a, **k):
        raise RuntimeError("database went away")

    monkeypatch.setattr(submissions, "_lock_submission", explode)
    res = s.upload()
    assert res.status_code == 500 and res.json()["error"]["code"] == "INTERNAL_ERROR"
    assert s.objects() == []  # compensation deleted the stored file
    assert s.count("submission_versions") == 0 and s.count("submissions") == 0


def test_failed_compensation_leaves_only_an_unreferenced_orphan_that_is_reported(s, api_app, monkeypatch):
    def explode(*a, **k):
        raise RuntimeError("database went away")

    monkeypatch.setattr(submissions, "_lock_submission", explode)
    monkeypatch.setattr(api_app.state, "s3", FailingS3(s.s3, {"delete_object"}))
    assert s.upload().status_code == 500
    monkeypatch.undo()
    assert s.count("submission_versions") == 0  # nothing references the object
    (key,) = s.objects()
    with Session(s.engine) as db:
        assert orphans.find_orphans(s.s3, s.bucket, db) == [key]
        assert orphans.find_dangling(s.s3, s.bucket, db) == []


def test_committed_rows_always_reference_stored_objects(s):
    for i in range(3):
        s.upload(data=pdf(100 + i))
    with Session(s.engine) as db:
        assert orphans.find_orphans(s.s3, s.bucket, db) == [] and orphans.find_dangling(s.s3, s.bucket, db) == []


def test_concurrent_different_uploads_get_distinct_version_numbers(s, api_app):
    def post(i):
        with TestClient(api_app, raise_server_exceptions=False) as c:
            return c.post(f"{API}/student/assignments/{s.aid}/submissions",
                          files={"file": (f"f{i}.pdf", pdf(100 + i), "application/pdf")}, headers=auth(s.stu_5a))

    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(post, range(4)))
    assert all(r.status_code == 201 for r in results), [r.text for r in results]
    assert sorted(r.json()["version_no"] for r in results) == [1, 2, 3, 4]
    assert s.count("submissions") == 1 and len(s.objects()) == 4


def test_concurrent_identical_uploads_create_one_version(s, api_app):
    data = pdf(777)

    def post(_):
        with TestClient(api_app, raise_server_exceptions=False) as c:
            return c.post(f"{API}/student/assignments/{s.aid}/submissions",
                          files={"file": ("same.pdf", data, "application/pdf")}, headers=auth(s.stu_5a))

    with ThreadPoolExecutor(3) as pool:
        results = list(pool.map(post, range(3)))
    assert sorted(r.status_code for r in results) == [201, 409, 409], [r.text for r in results]
    assert s.count("submission_versions") == 1 and len(s.objects()) == 1  # duplicates were compensated away


# --- earlier phases ---------------------------------------------------------------------------------------------------------------------------------

def test_phase_1_to_4_behaviour_is_intact(s):
    assert s.client.get(f"{API}/health").json() == {"status": "ok", "db": "ok", "redis": "ok", "storage": "ok"}
    assert s.client.get(f"{API}/auth/me", headers=auth(s.stu_5a)).json()["login_id"] == "STU0101"
    listing = s.get("/student/assignments", s.stu_5a).json()
    assert listing[0]["timing"] == "PENDING" and listing[0]["is_resubmitted"] is False
    assert s.get("/faculty/assignments", s.fac1).json()[0]["id"] == s.aid
    assert s.get("/student/assignments", s.stu_5b).json() == []


def test_database_checks_still_reject_inconsistent_version_rows(s, seeded_engine: Engine):
    sub_id = s.insert_first_version()
    with Session(seeded_engine) as db, pytest.raises(Exception):  # noqa: B017 - DB constraint error type varies
        db.execute(text("UPDATE submissions SET latest_version_no = -1 WHERE id = :i"), dict(i=sub_id))
        db.commit()
    now = datetime.now(UTC)
    assert now.tzinfo is not None
