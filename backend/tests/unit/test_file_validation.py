"""File validation: extension, content detection, archive structure, size, filename sanitising."""

import io
import zipfile

import pytest

from app.core.errors import AppError
from app.services.file_validation import MB, effective_max_bytes, sanitize_filename, validate_file

ALL = ["pdf", "docx", "pptx", "zip", "png", "jpg"]


def pdf(n: int = 100) -> bytes:
    return b"%PDF-1.4\n" + b"x" * n


def png(n: int = 100) -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + b"y" * n


def jpeg(n: int = 100) -> bytes:
    return b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"z" * n


def zip_bytes(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, content in entries.items():
            z.writestr(name, content)
    return buf.getvalue()


def office(kind: str) -> bytes:
    main = "word/document.xml" if kind == "docx" else "ppt/presentation.xml"
    return zip_bytes({"[Content_Types].xml": b"<Types/>", main: b"<x/>"})


def check(name, data, allowed=ALL, max_mb=10):
    return validate_file(name, data, allowed, max_mb, 10)


@pytest.mark.parametrize(
    "name, data, mime",
    [
        ("a.pdf", pdf(), "application/pdf"),
        ("a.PNG", png(), "image/png"),
        ("a.jpg", jpeg(), "image/jpeg"),
        ("a.jpeg", jpeg(), "image/jpeg"),
        ("a.zip", zip_bytes({"x.txt": b"hello"}), "application/zip"),
    ],
)
def test_valid_files(name, data, mime):
    result = check(name, data)
    assert result.mime_type == mime and result.size_bytes == len(data)


@pytest.mark.parametrize("kind", ["docx", "pptx"])
def test_office_documents_need_their_main_part(kind):
    assert check(f"a.{kind}", office(kind)).extension == kind
    for bad in (zip_bytes({"readme.txt": b"x"}), zip_bytes({"[Content_Types].xml": b"<Types/>"}), b"PK\x03\x04 broken"):
        with pytest.raises(AppError) as err:
            check(f"a.{kind}", bad)
        assert err.value.http_status == 415


def test_extension_must_be_allowed_for_the_assignment():
    with pytest.raises(AppError) as err:
        check("a.png", png(), allowed=["pdf"])
    assert (err.value.http_status, err.value.code) == (415, "UNSUPPORTED_TYPE")
    for name in ("malware.exe", "noextension", "a.pdf.exe", "a."):
        with pytest.raises(AppError):
            check(name, pdf())


def test_content_must_match_the_extension_not_the_client():
    for name, data in (("fake.pdf", png()), ("fake.png", pdf()), ("fake.jpg", pdf()), ("notes.pdf", b"just text" * 20)):
        with pytest.raises(AppError) as err:
            check(name, data)
        assert err.value.http_status == 415


def test_empty_and_oversized_files():
    with pytest.raises(AppError) as err:
        check("a.pdf", b"")
    assert (err.value.http_status, err.value.code) == (422, "EMPTY_FILE")
    exact = b"%PDF-1.4\n" + b"x" * (1 * MB - 9)
    assert len(exact) == 1 * MB and check("a.pdf", exact, max_mb=1).size_bytes == MB
    with pytest.raises(AppError) as err:
        check("a.pdf", exact + b"x", max_mb=1)
    assert (err.value.http_status, err.value.code) == (413, "FILE_TOO_LARGE")


def test_global_cap_wins_over_a_larger_assignment_limit():
    assert effective_max_bytes(10, 5) == 5 * MB and effective_max_bytes(2, 10) == 2 * MB


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("report.pdf", "report.pdf"),
        ("../../etc/passwd.pdf", "passwd.pdf"),
        ("C:\\fakepath\\r.pdf", "r.pdf"),
        ("a\x00b\x1f.pdf", "ab.pdf"),
        ("  spaced name.pdf  ", "spaced name.pdf"),
        ("", "upload"),
        (None, "upload"),
        ("...", "upload"),
        ("é-ünï.pdf", "é-ünï.pdf"),
    ],
)
def test_sanitize_filename(raw, expected):
    assert sanitize_filename(raw) == expected


def test_long_filenames_are_truncated_but_keep_their_extension():
    name = sanitize_filename("a" * 500 + ".pdf")
    assert len(name) == 200 and name.endswith(".pdf")
    assert check(name.replace("pdf", "pdf"), pdf()).extension == "pdf"
    assert len(sanitize_filename("b" * 500)) == 200
