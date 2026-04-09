import logging

import boto3
from botocore.exceptions import ClientError

from .config import settings

logger = logging.getLogger(__name__)

MINIO_ENDPOINT = settings.MINIO_ENDPOINT
MINIO_ACCESS_KEY = settings.MINIO_ACCESS_KEY
MINIO_SECRET_KEY = settings.MINIO_SECRET_KEY
MINIO_BUCKET = settings.MINIO_BUCKET


def _client():
    kwargs = {
        "aws_access_key_id": MINIO_ACCESS_KEY,
        "aws_secret_access_key": MINIO_SECRET_KEY,
        "region_name": "us-east-1",
    }
    if MINIO_ENDPOINT:
        kwargs["endpoint_url"] = MINIO_ENDPOINT
    return boto3.client("s3", **kwargs)


def ensure_bucket_exists() -> None:
    """Create the bucket if it doesn't exist. Call once at startup."""
    client = _client()
    try:
        client.head_bucket(Bucket=MINIO_BUCKET)
        logger.info("MinIO bucket '%s' exists", MINIO_BUCKET)
    except ClientError as e:
        if e.response["Error"]["Code"] in ("404", "NoSuchBucket"):
            client.create_bucket(Bucket=MINIO_BUCKET)
            logger.info("Created MinIO bucket '%s'", MINIO_BUCKET)
        else:
            raise


def upload_file(file_bytes: bytes, storage_key: str) -> None:
    """Upload raw bytes under the given key."""
    _client().put_object(
        Bucket=MINIO_BUCKET,
        Key=storage_key,
        Body=file_bytes,
        ContentType="application/pdf",
    )


def delete_file(storage_key: str) -> None:
    """Delete an object. No-ops if the key doesn't exist."""
    _client().delete_object(Bucket=MINIO_BUCKET, Key=storage_key)
