"""Find storage objects that no submission version or reference material references (architecture §18: DB/storage consistency).

A committed database row always points to an object that was stored successfully; the reverse can fail
(for example if deleting a stored object after a database error also failed). Such orphans are harmless
because nothing references them. This module lists them; deletion is an explicit, separate step.
"""

from botocore.client import BaseClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AssignmentAttachment, SubmissionVersion

KEY_PREFIXES = ("submissions/", "materials/")  # submission versions and assignment reference materials


def referenced_keys(db: Session) -> set[str]:
    return set(db.scalars(select(SubmissionVersion.storage_key))) | set(
        db.scalars(select(AssignmentAttachment.storage_key))
    )


def stored_keys(client: BaseClient, bucket: str) -> set[str]:
    keys: set[str] = set()
    for prefix in KEY_PREFIXES:
        for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
            keys.update(obj["Key"] for obj in page.get("Contents", []))
    return keys


def find_orphans(client: BaseClient, bucket: str, db: Session) -> list[str]:
    """Objects present in the bucket but referenced by no version or attachment row, sorted."""
    return sorted(stored_keys(client, bucket) - referenced_keys(db))


def find_dangling(client: BaseClient, bucket: str, db: Session) -> list[str]:
    """Referenced keys missing from the bucket (should always be empty)."""
    return sorted(referenced_keys(db) - stored_keys(client, bucket))
