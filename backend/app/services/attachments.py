"""Reference materials of an assignment: add / remove (draft only), list, and authorised access."""

import uuid
from datetime import datetime

from botocore.client import BaseClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.db.models import (
    Assignment,
    AssignmentAttachment,
    AssignmentStatus,
    SubmissionVersion,
    User,
    UserRole,
)
from app.schemas.attachments import AttachmentOut
from app.services import file_validation, scope, storage

MAX_ATTACHMENTS = 5
KEY_PREFIX = "materials/"
FILE_TYPE_BY_MIME = {
    "application/pdf": "PDF",
    file_validation.PPT_MIME: "PPT",
    file_validation.PPTX_MIME: "PPTX",
}


def _not_found() -> AppError:
    return AppError("NOT_FOUND", 404, "The requested resource was not found.")


def attachment_out(a: AssignmentAttachment) -> AttachmentOut:
    return AttachmentOut(
        id=a.id,
        original_filename=a.original_filename,
        mime_type=a.mime_type,
        file_type=FILE_TYPE_BY_MIME.get(a.mime_type, "FILE"),
        size_bytes=a.size_bytes,
        uploaded_at=a.created_at,
        previewable=file_validation.is_previewable(a.mime_type),
    )


def list_for_assignment(db: Session, assignment_id: uuid.UUID) -> list[AttachmentOut]:
    rows = db.scalars(
        select(AssignmentAttachment)
        .where(AssignmentAttachment.assignment_id == assignment_id)
        .order_by(AssignmentAttachment.created_at, AssignmentAttachment.id)
    ).all()
    return [attachment_out(a) for a in rows]


def _require_draft(assignment: Assignment) -> None:
    if assignment.status != AssignmentStatus.DRAFT:
        raise AppError(
            "ATTACHMENTS_LOCKED",
            409,
            "Reference materials cannot be changed after the assignment is published: students rely on them.",
        )


def add_attachment(
    db: Session,
    s3: BaseClient,
    settings: Settings,
    faculty: User,
    assignment_id: uuid.UUID,
    filename: str | None,
    data: bytes,
    now: datetime,
) -> AttachmentOut:
    assignment = scope.get_faculty_assignment_or_404(db, faculty, assignment_id)
    _require_draft(assignment)
    validated = file_validation.validate_reference_file(filename, data, settings.max_upload_mb)
    count = db.scalar(
        select(func.count())
        .select_from(AssignmentAttachment)
        .where(AssignmentAttachment.assignment_id == assignment.id)
    )
    if count >= MAX_ATTACHMENTS:
        raise AppError(
            "TOO_MANY_ATTACHMENTS",
            422,
            f"An assignment can have at most {MAX_ATTACHMENTS} reference documents.",
        )

    key = f"{KEY_PREFIX}{assignment.id}/{uuid.uuid4()}.{validated.extension}"  # no user-supplied text in the key
    storage.put_object(s3, settings.s3_bucket, key, data, validated.mime_type)  # StorageUnavailable -> 503
    try:
        row = AssignmentAttachment(
            assignment_id=assignment.id,
            original_filename=validated.original_filename,
            storage_key=key,
            mime_type=validated.mime_type,
            size_bytes=validated.size_bytes,
            uploaded_by=faculty.id,
            created_at=now,
        )
        db.add(row)
        db.flush()
    except Exception:
        db.rollback()
        storage.delete_object_best_effort(s3, settings.s3_bucket, key)  # no object without a row
        raise
    return attachment_out(row)


def remove_attachment(
    db: Session,
    s3: BaseClient,
    settings: Settings,
    faculty: User,
    assignment_id: uuid.UUID,
    attachment_id: uuid.UUID,
) -> None:
    assignment = scope.get_faculty_assignment_or_404(db, faculty, assignment_id)
    row = db.get(AssignmentAttachment, attachment_id)
    if row is None or row.assignment_id != assignment.id:
        raise _not_found()
    _require_draft(assignment)
    key = row.storage_key
    db.delete(row)
    db.commit()  # the row is gone for good before the object is touched
    # Never delete an object that any record still references (keys are unique per upload; this is a guard).
    used_by_material = db.scalar(
        select(func.count()).select_from(AssignmentAttachment).where(AssignmentAttachment.storage_key == key)
    )
    used_by_version = db.scalar(
        select(func.count()).select_from(SubmissionVersion).where(SubmissionVersion.storage_key == key)
    )
    if not used_by_material and not used_by_version:
        storage.delete_object_best_effort(s3, settings.s3_bucket, key)


def get_for_user_or_404(db: Session, user: User, attachment_id: uuid.UUID) -> AssignmentAttachment:
    """Faculty: the assignment must be theirs and in their teaching scope (draft or published).
    Student: the assignment must be PUBLISHED and belong to the student's own section. Anything else is 404."""
    row = db.get(AssignmentAttachment, attachment_id)
    if row is None:
        raise _not_found()
    if user.role == UserRole.STUDENT:
        scope.get_student_assignment_or_404(db, user, row.assignment_id)
    else:
        scope.get_faculty_assignment_or_404(db, user, row.assignment_id)
    return row
