"""Enhancement round 2, Phase B: reference materials (PDF / PPT / PPTX), inline preview and download."""

import pytest
from sqlalchemy.orm import Session

from app.services import orphans
from tests.api.test_assignments import API, auth
from tests.api.test_submissions import S
from tests.unit.test_file_validation import jpeg, office, pdf, png

MB = 1024 * 1024


def ppt(n: int = 600) -> bytes:
    """Smallest content the detector accepts as a legacy PowerPoint (OLE header + PowerPoint signature)."""
    data = bytearray(n)
    data[0:8] = b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1"
    data[512:516] = b"\xA0\x46\x1D\xF0"
    return bytes(data)


@pytest.fixture
def m(client, api_app, monkeypatch, test_password, freeze_time, s3_client, settings, seeded_engine) -> S:
    monkeypatch.setattr(
        api_app.state, "settings", api_app.state.settings.model_copy(update={"jwt_expire_minutes": 60 * 24 * 30})
    )
    return S(client, test_password, freeze_time, s3_client=s3_client, bucket=settings.s3_bucket, engine=seeded_engine)


def draft(m: S, token=None, slot=None) -> str:
    res = m.create(token=token, slot=slot, publish=False)
    assert res.status_code == 201, res.text
    return res.json()["id"]


def attach(m: S, aid: str, name="notes.pdf", data=None, token=None, content_type="application/pdf"):
    return m.client.post(
        f"{API}/faculty/assignments/{aid}/attachments",
        files={"file": (name, pdf() if data is None else data, content_type)},
        headers=auth(token or m.fac1),
    )


def publish(m: S, aid: str):
    res = m.post(f"/faculty/assignments/{aid}/publish", m.fac1)
    assert res.status_code == 200, res.text


# --- upload validation -------------------------------------------------------------------------------------

@pytest.mark.parametrize(
    "name, data, mime, label",
    [
        ("questions.pdf", pdf(), "application/pdf", "PDF"),
        ("slides.pptx", office("pptx"), "application/vnd.openxmlformats-officedocument.presentationml.presentation", "PPTX"),
        ("old.ppt", ppt(), "application/vnd.ms-powerpoint", "PPT"),
    ],
)
def test_pdf_ppt_and_pptx_reference_documents_are_accepted_and_typed_from_content(m, name, data, mime, label):
    aid = draft(m)
    # The browser's Content-Type is irrelevant: it is deliberately wrong here.
    res = attach(m, aid, name=name, data=data, content_type="text/html")
    assert res.status_code == 201, res.text
    body = res.json()
    assert (body["original_filename"], body["mime_type"], body["file_type"], body["size_bytes"]) == (name, mime, label, len(data))
    assert body["previewable"] is (label == "PDF")
    assert "storage_key" not in body and "url" not in str(body).lower()
    key = m.sql("SELECT storage_key FROM assignment_attachments WHERE id = :i", i=body["id"])[0][0]
    assert key.startswith(f"materials/{aid}/") and key.endswith(f".{name.rsplit('.', 1)[1]}") and name not in key
    assert key in m.objects()


@pytest.mark.parametrize(
    "name, data",
    [
        ("evil.html", b"<html><script>alert(1)</script></html>"),
        ("report.docx", office("docx")),  # a real document, but not an allowed reference type
        ("photo.png", png()),
        ("archive.zip", b"PK\x03\x04" + b"0" * 50),
        ("script.exe", b"MZ" + b"0" * 100),
        ("noext", pdf()),
    ],
)
def test_other_types_are_refused_by_extension(m, name, data):
    aid = draft(m)
    res = attach(m, aid, name=name, data=data)
    assert res.status_code == 415 and res.json()["error"]["code"] == "UNSUPPORTED_TYPE"
    assert m.count("assignment_attachments") == 0 and m.objects() == []


@pytest.mark.parametrize(
    "name, data",
    [
        ("fake.pdf", b"<html>not a pdf</html>"),
        ("fake.pptx", b"%PDF-1.4 pretending"),
        ("empty-structure.pptx", b"PK\x03\x04" + b"0" * 40),
        ("nodoc.pptx", office("docx")),  # a zip, but a Word package
        ("fake.ppt", pdf()),
    ],
)
def test_content_must_match_the_extension(m, name, data):
    aid = draft(m)
    assert attach(m, aid, name=name, data=data).status_code == 415
    assert m.count("assignment_attachments") == 0 and m.objects() == []


def test_empty_and_oversized_files_are_refused(m):
    aid = draft(m)
    assert attach(m, aid, data=b"").status_code == 422
    big = attach(m, aid, data=b"%PDF-1.4\n" + b"x" * (10 * MB))
    assert big.status_code in (413,) and m.count("assignment_attachments") == 0


def test_at_most_five_reference_documents(m):
    aid = draft(m)
    for i in range(5):
        assert attach(m, aid, name=f"n{i}.pdf", data=pdf(100 + i)).status_code == 201
    res = attach(m, aid, name="sixth.pdf")
    assert res.status_code == 422 and res.json()["error"]["code"] == "TOO_MANY_ATTACHMENTS"
    assert m.count("assignment_attachments") == 5 and len(m.objects()) == 5


def test_filenames_are_sanitised_and_never_used_in_keys(m):
    aid = draft(m)
    body = attach(m, aid, name="../../etc/pass wd\x00.pdf").json()
    assert "/" not in body["original_filename"] and "\x00" not in body["original_filename"]
    key = m.sql("SELECT storage_key FROM assignment_attachments")[0][0]
    assert ".." not in key and "etc" not in key


# --- ownership, scope and the draft lock ----------------------------------------------------------------------

def test_only_the_owning_faculty_can_attach_or_remove(m):
    aid = draft(m)
    assert attach(m, aid, token=m.fac2).status_code == 404  # another teacher
    assert attach(m, aid, token=m.fac49).status_code == 404  # a teacher without classes
    assert m.client.post(f"{API}/faculty/assignments/{aid}/attachments", files={"file": ("a.pdf", pdf())}).status_code == 401
    assert attach(m, aid, token=m.stu_5a).status_code == 403  # students cannot
    att = attach(m, aid).json()["id"]
    for token in (m.fac2, m.fac49):
        res = m.client.delete(f"{API}/faculty/assignments/{aid}/attachments/{att}", headers=auth(token))
        assert res.status_code == 404
    assert m.client.delete(f"{API}/faculty/assignments/{aid}/attachments/{att}", headers=auth(m.stu_5a)).status_code == 403
    assert m.count("assignment_attachments") == 1


def test_an_attachment_id_cannot_be_used_through_another_assignment(m):
    a, b = draft(m), draft(m)
    att = attach(m, a).json()["id"]
    res = m.client.delete(f"{API}/faculty/assignments/{b}/attachments/{att}", headers=auth(m.fac1))
    assert res.status_code == 404 and m.count("assignment_attachments") == 1


def test_removing_a_draft_attachment_deletes_row_and_object(m):
    aid = draft(m)
    att = attach(m, aid).json()["id"]
    assert len(m.objects()) == 1
    res = m.client.delete(f"{API}/faculty/assignments/{aid}/attachments/{att}", headers=auth(m.fac1))
    assert res.status_code == 204
    assert m.count("assignment_attachments") == 0 and m.objects() == []
    assert m.client.delete(f"{API}/faculty/assignments/{aid}/attachments/{att}", headers=auth(m.fac1)).status_code == 404


def test_materials_are_locked_after_publication(m):
    aid = draft(m)
    att = attach(m, aid).json()["id"]
    publish(m, aid)
    res = attach(m, aid, name="late-addition.pdf")
    assert res.status_code == 409 and res.json()["error"]["code"] == "ATTACHMENTS_LOCKED"
    res = m.client.delete(f"{API}/faculty/assignments/{aid}/attachments/{att}", headers=auth(m.fac1))
    assert res.status_code == 409 and res.json()["error"]["code"] == "ATTACHMENTS_LOCKED"
    assert m.count("assignment_attachments") == 1 and len(m.objects()) == 1


def test_an_assignment_created_published_cannot_get_materials(m):
    res = attach(m, m.aid)  # the fixture assignment was created as PUBLISHED
    assert res.status_code == 409 and res.json()["error"]["code"] == "ATTACHMENTS_LOCKED"


# --- what each side sees ----------------------------------------------------------------------------------------

def test_faculty_detail_lists_attachments_and_students_see_them_only_when_published(m):
    aid = draft(m)
    first = attach(m, aid, name="a.pdf").json()
    second = attach(m, aid, name="b.pptx", data=office("pptx")).json()
    detail = m.get(f"/faculty/assignments/{aid}", m.fac1).json()
    # (the frozen test clock gives both the same timestamp, so compare as a set)
    assert {a["original_filename"] for a in detail["attachments"]} == {"a.pdf", "b.pptx"}
    assert first["id"] in {a["id"] for a in detail["attachments"]}
    # A draft is invisible to students (detail and files).
    assert m.get(f"/student/assignments/{aid}", m.stu_5a).status_code == 404
    assert m.get(f"/files/materials/{first['id']}", m.stu_5a).status_code == 404
    publish(m, aid)
    seen = m.get(f"/student/assignments/{aid}", m.stu_5a).json()
    assert {a["original_filename"] for a in seen["attachments"]} == {"a.pdf", "b.pptx"}
    assert seen["instructions"] and {a["id"] for a in seen["attachments"]} == {first["id"], second["id"]}
    for a in seen["attachments"]:
        assert set(a) == {"id", "original_filename", "mime_type", "file_type", "size_bytes", "uploaded_at", "previewable"}


def test_assignments_without_materials_have_an_empty_list(m):
    assert m.get(f"/student/assignments/{m.aid}", m.stu_5a).json()["attachments"] == []
    assert m.get(f"/faculty/assignments/{m.aid}", m.fac1).json()["attachments"] == []


# --- downloads and previews ---------------------------------------------------------------------------------------

def published_with(m, name="notes.pdf", data=None):
    aid = draft(m)
    att = attach(m, aid, name=name, data=data).json()["id"]
    publish(m, aid)
    return aid, att


def test_download_serves_the_original_bytes_as_an_attachment(m):
    data = pdf(777)
    _, att = published_with(m, data=data)
    for token in (m.fac1, m.stu_5a, m.stu_5a2):
        res = m.get(f"/files/materials/{att}", token)
        assert res.status_code == 200 and res.content == data
        assert res.headers["content-disposition"].startswith("attachment;") and "notes.pdf" in res.headers["content-disposition"]
        assert res.headers["content-type"] == "application/octet-stream"
        assert res.headers["x-content-type-options"] == "nosniff" and "no-store" in res.headers["cache-control"]
        assert "content-security-policy" not in res.headers


def test_pdf_preview_is_inline_with_the_detected_type_and_a_locked_down_csp(m):
    data = pdf(500)
    _, att = published_with(m, data=data)
    for token in (m.fac1, m.stu_5a):
        res = m.get(f"/files/materials/{att}/preview", token)
        assert res.status_code == 200 and res.content == data
        assert res.headers["content-type"] == "application/pdf"
        assert res.headers["content-disposition"].startswith("inline;")
        assert res.headers["content-security-policy"] == "default-src 'none'; sandbox"
        assert res.headers["x-content-type-options"] == "nosniff"


@pytest.mark.parametrize("name, data", [("slides.pptx", office("pptx")), ("old.ppt", ppt())])
def test_powerpoint_is_never_pretended_to_be_previewable(m, name, data):
    _, att = published_with(m, name=name, data=data)
    res = m.get(f"/files/materials/{att}/preview", m.stu_5a)
    assert res.status_code == 415 and res.json()["error"]["code"] == "PREVIEW_UNAVAILABLE"
    assert m.get(f"/files/materials/{att}", m.stu_5a).content == data  # the Download action still works


def test_materials_are_private_to_authorised_users(m):
    aid, att = published_with(m)
    for path in (f"/files/materials/{att}", f"/files/materials/{att}/preview"):
        assert m.client.get(f"{API}{path}").status_code == 401
        assert m.get(path, m.stu_5b).status_code == 404  # a student of another section
        assert m.get(path, m.fac2).status_code == 404  # another teacher
        assert m.get(path, m.fac49).status_code == 404  # a teacher without classes
    assert m.get(f"/files/materials/{'0' * 8}-0000-0000-0000-{'0' * 12}", m.fac1).status_code == 404
    assert m.get("/files/materials/not-a-uuid", m.fac1).status_code == 422


def test_a_draft_material_is_visible_to_its_teacher_only(m):
    aid = draft(m)
    att = attach(m, aid).json()["id"]
    assert m.get(f"/files/materials/{att}/preview", m.fac1).status_code == 200
    assert m.get(f"/files/materials/{att}", m.stu_5a).status_code == 404
    assert m.get(f"/files/materials/{att}", m.fac2).status_code == 404


# --- submission previews (faculty View + Download) -----------------------------------------------------------------

@pytest.mark.parametrize(
    "name, data, mime",
    [("work.pdf", pdf(300), "application/pdf"), ("pic.png", png(300), "image/png"), ("pic.jpg", jpeg(300), "image/jpeg")],
)
def test_submission_versions_preview_inline_and_download_the_original(m, name, data, mime):
    assert m.upload(name=name, data=data).status_code == 201
    vid = m.sql("SELECT id FROM submission_versions")[0][0]
    pre = m.get(f"/files/versions/{vid}/preview", m.fac1)
    assert pre.status_code == 200 and pre.content == data and pre.headers["content-type"] == mime
    assert pre.headers["content-disposition"].startswith("inline;")
    assert pre.headers["content-security-policy"] == "default-src 'none'; sandbox"
    dl = m.get(f"/files/versions/{vid}", m.fac1)
    assert dl.status_code == 200 and dl.content == data and dl.headers["content-disposition"].startswith("attachment;")
    assert dl.headers["content-type"] == "application/octet-stream"
    assert m.get(f"/files/versions/{vid}/preview", m.stu_5a).status_code == 200  # the owner may preview too


@pytest.mark.parametrize("name, data", [("deck.pptx", office("pptx")), ("doc.docx", office("docx")), ("a.zip", b"PK\x03\x04" + b"1" * 60)])
def test_non_previewable_submissions_answer_415_but_still_download(m, name, data):
    assert m.upload(name=name, data=data).status_code == 201
    vid = m.sql("SELECT id FROM submission_versions")[0][0]
    res = m.get(f"/files/versions/{vid}/preview", m.fac1)
    assert res.status_code == 415 and res.json()["error"]["code"] == "PREVIEW_UNAVAILABLE"
    assert m.get(f"/files/versions/{vid}", m.fac1).content == data


def test_submission_previews_respect_scope(m):
    m.upload()
    vid = m.sql("SELECT id FROM submission_versions")[0][0]
    path = f"/files/versions/{vid}/preview"
    assert m.client.get(f"{API}{path}").status_code == 401
    assert m.get(path, m.stu_5a2).status_code == 404  # a classmate
    assert m.get(path, m.stu_5b).status_code == 404
    assert m.get(path, m.fac2).status_code == 404  # another teacher
    assert m.get(path, m.fac49).status_code == 404


# --- storage consistency ---------------------------------------------------------------------------------------------

def test_orphan_tools_know_about_reference_materials(m):
    from sqlalchemy import create_engine  # noqa: F401

    aid = draft(m)
    attach(m, aid)
    with Session(m.engine) as db:
        assert orphans.find_orphans(m.s3, m.bucket, db) == []  # referenced, so not an orphan
        assert orphans.find_dangling(m.s3, m.bucket, db) == []
    m.s3.put_object(Bucket=m.bucket, Key="materials/stray/unreferenced.pdf", Body=b"x")
    with Session(m.engine) as db:
        assert orphans.find_orphans(m.s3, m.bucket, db) == ["materials/stray/unreferenced.pdf"]
    m.s3.delete_object(Bucket=m.bucket, Key="materials/stray/unreferenced.pdf")


def test_a_failed_database_write_removes_the_stored_object(m, monkeypatch):
    from app.services import attachments

    aid = draft(m)
    real_flush = Session.flush

    def boom(self, *a, **k):
        if any(type(o).__name__ == "AssignmentAttachment" for o in self.new):
            raise RuntimeError("database write failed")
        return real_flush(self, *a, **k)

    monkeypatch.setattr(Session, "flush", boom)
    monkeypatch.setattr(attachments, "MAX_ATTACHMENTS", 5)
    res = attach(m, aid)
    assert res.status_code == 500
    monkeypatch.setattr(Session, "flush", real_flush)
    assert m.objects() == [] and m.count("assignment_attachments") == 0


def test_existing_submission_and_version_rows_are_untouched_by_attachments(m):
    m.upload()
    before = m.sql("SELECT id, storage_key, original_filename FROM submission_versions")
    aid = draft(m)
    att = attach(m, aid).json()["id"]
    m.client.delete(f"{API}/faculty/assignments/{aid}/attachments/{att}", headers=auth(m.fac1))
    assert m.sql("SELECT id, storage_key, original_filename FROM submission_versions") == before
    assert before[0][1] in m.objects()


def test_cors_preflight_allows_the_delete_used_by_the_browser(m, settings):
    """A browser DELETE of a draft document needs DELETE in the CORS allow-list (found in the browser run)."""
    res = m.client.options(
        f"{API}/faculty/assignments/{m.aid}/attachments/{m.aid}",
        headers={
            "Origin": settings.frontend_origin,
            "Access-Control-Request-Method": "DELETE",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert res.status_code == 200 and "DELETE" in res.headers["access-control-allow-methods"]
    assert res.headers["access-control-allow-origin"] == settings.frontend_origin
    foreign = m.client.options(
        f"{API}/faculty/assignments/{m.aid}/attachments/{m.aid}",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "DELETE"},
    )
    assert "access-control-allow-origin" not in foreign.headers
