import os

import boto3
from botocore.exceptions import ClientError

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "documents")


def _client():
    return boto3.client(
        "s3",
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
    )


def ensure_bucket_exists() -> None:
    """Create the bucket if it doesn't exist. Call once at startup."""
    client = _client()
    try:
        client.head_bucket(Bucket=MINIO_BUCKET)
    except ClientError as e:
        if e.response["Error"]["Code"] == "404":
            client.create_bucket(Bucket=MINIO_BUCKET)
        else:
            raise


def upload_file(file_bytes: bytes, storage_key: str) -> None:
    """Upload raw bytes to MinIO under the given key."""
    _client().put_object(
        Bucket=MINIO_BUCKET,
        Key=storage_key,
        Body=file_bytes,
        ContentType="application/pdf",
    )


def delete_file(storage_key: str) -> None:
    """Delete an object from MinIO. No-ops if the key doesn't exist."""
    _client().delete_object(Bucket=MINIO_BUCKET, Key=storage_key)
