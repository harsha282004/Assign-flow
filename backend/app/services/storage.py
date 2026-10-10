"""S3-compatible object storage (MinIO): client, private-bucket initialisation, object operations.

The bucket is private and no public policy is ever set. Files are only ever served by the backend after
authorisation (architecture §18); no presigned or public URLs exist.
"""

import logging

import boto3
from botocore.client import BaseClient, Config
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import Settings

logger = logging.getLogger("assignflow.storage")


class StorageUnavailable(Exception):
    """The object store could not be reached or rejected the operation."""


class StorageObjectMissing(Exception):
    """The database references an object that is not in the bucket."""


def make_s3_client(settings: Settings) -> BaseClient:
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            connect_timeout=5,
            read_timeout=15,
            retries={"max_attempts": 2},
        ),
    )


def ensure_bucket(client: BaseClient, bucket: str) -> bool:
    """Create the bucket if absent. Returns True if it was created. Never sets a public policy."""
    try:
        client.head_bucket(Bucket=bucket)
        return False
    except ClientError as exc:
        if exc.response["Error"]["Code"] not in ("404", "NoSuchBucket", "NotFound"):
            raise
    try:
        client.create_bucket(Bucket=bucket)
    except ClientError as exc:
        # Lost a race with another starter: that is fine.
        if exc.response["Error"]["Code"] not in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
            raise
        return False
    return True


def assert_bucket_private(client: BaseClient, bucket: str) -> None:
    """Fail if the bucket has any bucket policy (we never set one) or a public ACL grant."""
    try:
        client.get_bucket_policy(Bucket=bucket)
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "NoSuchBucketPolicy":
            raise
    else:
        raise RuntimeError(f"Bucket '{bucket}' has a bucket policy; expected a private bucket")

    acl = client.get_bucket_acl(Bucket=bucket)
    for grant in acl.get("Grants", []):
        uri = grant.get("Grantee", {}).get("URI", "")
        if uri.endswith("/global/AllUsers") or uri.endswith("/global/AuthenticatedUsers"):
            raise RuntimeError(f"Bucket '{bucket}' grants public access via ACL")


def put_object(client: BaseClient, bucket: str, key: str, body: bytes, content_type: str) -> None:
    try:
        client.put_object(Bucket=bucket, Key=key, Body=body, ContentType=content_type)
    except (ClientError, BotoCoreError) as exc:
        logger.error("storage put failed (%s)", type(exc).__name__)
        raise StorageUnavailable from exc


def get_object(client: BaseClient, bucket: str, key: str):
    """Return the boto3 response (Body is a streaming body the caller must close)."""
    try:
        return client.get_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        if exc.response["Error"]["Code"] in ("NoSuchKey", "404"):
            logger.error("object referenced by the database is missing from storage")
            raise StorageObjectMissing from exc
        logger.error("storage get failed (%s)", type(exc).__name__)
        raise StorageUnavailable from exc
    except BotoCoreError as exc:
        logger.error("storage get failed (%s)", type(exc).__name__)
        raise StorageUnavailable from exc


def delete_object_best_effort(client: BaseClient, bucket: str, key: str) -> bool:
    """Compensation after a failed database write. A leftover object is an unreferenced orphan."""
    try:
        client.delete_object(Bucket=bucket, Key=key)
        return True
    except (ClientError, BotoCoreError) as exc:
        logger.error("orphaned object could not be deleted (%s); see scripts/find_orphans.py", type(exc).__name__)
        return False
