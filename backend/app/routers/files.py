"""Authenticated file access (architecture §18, §20.2 #19): download and in-app preview.

No presigned or public URLs exist: the backend checks ownership / academic scope, then streams the object.

* `/download` style endpoints always send `Content-Disposition: attachment` and `application/octet-stream`, so
  the original bytes are saved and nothing is ever rendered by the browser.
* `/preview` endpoints send `inline` ONLY for content-detected PDF, PNG and JPEG files, with the detected media
  type, `nosniff` and a CSP that forbids any active content. Every other type answers 415 PREVIEW_UNAVAILABLE.
"""

import logging
import uuid
from urllib.parse import quote

from botocore.client import BaseClient
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.deps import get_app_settings, get_current_user, get_db, get_s3
from app.core.errors import AppError
from app.db.models import User
from app.services import attachments, file_validation, scope, storage

logger = logging.getLogger("assignflow.files")
router = APIRouter(prefix="/files", tags=["files"])

PREVIEW_CSP = "default-src 'none'; sandbox"


def _disposition(kind: str, filename: str) -> str:
    ascii_name = "".join(c if 32 <= ord(c) < 127 and c not in '"\\;' else "_" for c in filename) or "download"
    return f"{kind}; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename, safe='')}"


def _stream(s3: BaseClient, settings: Settings, key: str, size: int, filename: str, *, preview: bool, mime: str):
    try:
        obj = storage.get_object(s3, settings.s3_bucket, key)
    except storage.StorageObjectMissing as exc:
        raise AppError("NOT_FOUND", 404, "The requested resource was not found.") from exc

    body = obj["Body"]

    def stream():
        try:
            yield from body.iter_chunks(64 * 1024)
        finally:
            body.close()

    headers = {
        "Content-Disposition": _disposition("inline" if preview else "attachment", filename),
        "Content-Length": str(size),
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, no-store",
    }
    if preview:
        headers["Content-Security-Policy"] = PREVIEW_CSP
    # Downloads never echo a browser-renderable type; previews use the content-detected type of a safe allow-list.
    return StreamingResponse(stream(), media_type=mime if preview else "application/octet-stream", headers=headers)


def _require_previewable(mime: str) -> None:
    if not file_validation.is_previewable(mime):
        raise AppError(
            "PREVIEW_UNAVAILABLE",
            415,
            "This file type cannot be previewed in AssignFlow. Download it to view it.",
        )


@router.get("/versions/{version_id}")
def download_version(
    version_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    s3: BaseClient = Depends(get_s3),
    settings: Settings = Depends(get_app_settings),
) -> StreamingResponse:
    # Own versions for a student; students of own assignments for faculty. Anything else is 404.
    version = scope.get_version_for_user_or_404(db, user, version_id)
    return _stream(
        s3, settings, version.storage_key, version.size_bytes, version.original_filename, preview=False, mime=""
    )


@router.get("/versions/{version_id}/preview")
def preview_version(
    version_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    s3: BaseClient = Depends(get_s3),
    settings: Settings = Depends(get_app_settings),
) -> StreamingResponse:
    version = scope.get_version_for_user_or_404(db, user, version_id)
    _require_previewable(version.mime_type)
    return _stream(
        s3,
        settings,
        version.storage_key,
        version.size_bytes,
        version.original_filename,
        preview=True,
        mime=version.mime_type,
    )


@router.get("/materials/{attachment_id}")
def download_material(
    attachment_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    s3: BaseClient = Depends(get_s3),
    settings: Settings = Depends(get_app_settings),
) -> StreamingResponse:
    row = attachments.get_for_user_or_404(db, user, attachment_id)
    return _stream(s3, settings, row.storage_key, row.size_bytes, row.original_filename, preview=False, mime="")


@router.get("/materials/{attachment_id}/preview")
def preview_material(
    attachment_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    s3: BaseClient = Depends(get_s3),
    settings: Settings = Depends(get_app_settings),
) -> StreamingResponse:
    row = attachments.get_for_user_or_404(db, user, attachment_id)
    _require_previewable(row.mime_type)
    return _stream(
        s3, settings, row.storage_key, row.size_bytes, row.original_filename, preview=True, mime=row.mime_type
    )
