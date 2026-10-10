"""Upload validation (architecture §18): extension, content type, archive structure, size, filename.

A file must pass all three type checks: (1) its extension is among the assignment's allowed types,
(2) content-based detection (`filetype`, not the client's Content-Type) matches an allowed MIME,
(3) for docx/pptx (ZIP containers) the archive contains word/document.xml / ppt/presentation.xml.
"""

import io
import re
import zipfile
from dataclasses import dataclass

import filetype

from app.core.errors import AppError

MB = 1024 * 1024

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"

# extension -> content MIMEs accepted for it
ALLOWED_MIMES: dict[str, set[str]] = {
    "pdf": {"application/pdf"},
    "png": {"image/png"},
    "jpg": {"image/jpeg"},
    "zip": {"application/zip"},
    "docx": {DOCX_MIME, "application/zip"},
    "pptx": {PPTX_MIME, "application/zip"},
}
REQUIRED_ZIP_ENTRY = {"docx": "word/document.xml", "pptx": "ppt/presentation.xml"}
EXTENSION_ALIASES = {"jpeg": "jpg"}  # same format, different spelling

MAX_NAME_LENGTH = 200
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


@dataclass(frozen=True)
class ValidatedFile:
    original_filename: str  # sanitised, display only: it is never used as a storage path
    extension: str
    mime_type: str  # detected from the content
    size_bytes: int


def sanitize_filename(raw: str | None) -> str:
    """Basename only, control characters stripped, at most 200 characters (display use only)."""
    name = (raw or "").replace("\\", "/").split("/")[-1]
    name = _CONTROL_CHARS.sub("", name).strip().strip(".")
    if len(name) > MAX_NAME_LENGTH:
        # Shorten the stem, never the extension: the extension is validated on this sanitised name.
        stem, dot, ext = name.rpartition(".")
        name = (stem[: MAX_NAME_LENGTH - len(ext) - 1] + "." + ext) if dot and len(ext) < 20 else name[:MAX_NAME_LENGTH]
    return name or "upload"


def _extension(name: str) -> str:
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return EXTENSION_ALIASES.get(ext, ext)


def _unsupported(message: str) -> AppError:
    return AppError("UNSUPPORTED_TYPE", 415, message)


def effective_max_bytes(assignment_max_mb: int, global_max_mb: int) -> int:
    return min(assignment_max_mb, global_max_mb) * MB


def validate_file(
    filename: str | None,
    data: bytes,
    allowed_types: list[str],
    assignment_max_mb: int,
    global_max_mb: int,
) -> ValidatedFile:
    limit = effective_max_bytes(assignment_max_mb, global_max_mb)
    if len(data) == 0:
        raise AppError("EMPTY_FILE", 422, "The uploaded file is empty.")
    if len(data) > limit:
        raise AppError(
            "FILE_TOO_LARGE",
            413,
            f"The file is larger than the {limit // MB} MB limit for this assignment.",
        )

    name = sanitize_filename(filename)
    ext = _extension(name)
    allowed = ", ".join(t.upper() for t in allowed_types)
    if ext not in allowed_types:
        raise _unsupported(f"This assignment accepts only these file types: {allowed}.")

    detected = filetype.guess(data)
    mime = detected.mime if detected else None
    if mime not in ALLOWED_MIMES[ext]:
        raise _unsupported(f"The file content does not match a valid .{ext} file.")

    required = REQUIRED_ZIP_ENTRY.get(ext)
    if required:
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                if required not in archive.namelist():
                    raise _unsupported(f"The file is not a valid .{ext} document.")
        except zipfile.BadZipFile as exc:
            raise _unsupported(f"The file is not a valid .{ext} document.") from exc

    return ValidatedFile(original_filename=name, extension=ext, mime_type=mime, size_bytes=len(data))


# --- Reference materials (faculty-attached documents) ----------------------------------------------------

PPT_MIME = "application/vnd.ms-powerpoint"
REFERENCE_MIMES: dict[str, set[str]] = {
    "pdf": {"application/pdf"},
    "ppt": {PPT_MIME},
    "pptx": {PPTX_MIME, "application/zip"},
}
# The only detected types the server will ever send with an inline Content-Disposition.
PREVIEWABLE_MIMES = {"application/pdf", "image/png", "image/jpeg"}


def is_previewable(mime_type: str) -> bool:
    return mime_type in PREVIEWABLE_MIMES


def validate_reference_file(filename: str | None, data: bytes, global_max_mb: int) -> ValidatedFile:
    """PDF, PPT or PPTX: extension, content-detected type (never the browser's Content-Type) and size."""
    limit = global_max_mb * MB
    if len(data) == 0:
        raise AppError("EMPTY_FILE", 422, "The uploaded file is empty.")
    if len(data) > limit:
        raise AppError("FILE_TOO_LARGE", 413, f"The file is larger than the {global_max_mb} MB limit.")
    name = sanitize_filename(filename)
    ext = _extension(name)
    if ext not in REFERENCE_MIMES:
        raise _unsupported("Reference documents must be PDF, PPT or PPTX files.")
    detected = filetype.guess(data)
    mime = detected.mime if detected else None
    if mime not in REFERENCE_MIMES[ext]:
        raise _unsupported(f"The file content does not match a valid .{ext} file.")
    if ext == "pptx":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                if REQUIRED_ZIP_ENTRY["pptx"] not in archive.namelist():
                    raise _unsupported("The file is not a valid .pptx document.")
        except zipfile.BadZipFile as exc:
            raise _unsupported("The file is not a valid .pptx document.") from exc
        mime = PPTX_MIME
    return ValidatedFile(original_filename=name, extension=ext, mime_type=mime, size_bytes=len(data))
