import boto3
from botocore.client import Config
from botocore.exceptions import ClientError, BotoCoreError
import os
from typing import BinaryIO

# Fast-fail S3 config: during a storage outage, surface a quick clean error instead
# of blocking a worker for the default 60s × retries (which exhausts the pool).
_S3_CONFIG = dict(
    connect_timeout=3,
    read_timeout=5,
    retries={"max_attempts": 2, "mode": "standard"},
)


class StorageUnavailable(Exception):
    """Raised when object storage can't be reached — callers map this to HTTP 503."""

S3_ENDPOINT  = os.getenv("S3_ENDPOINT", "http://localhost:9000")
# Endpoint used when signing URLs handed to the browser. Internally services reach
# MinIO at http://minio:9000, but the browser must use a host it can resolve
# (e.g. http://localhost:9000). The SigV4 signature is bound to this host, so we
# sign with a dedicated client configured for the public endpoint.
S3_PUBLIC_ENDPOINT = os.getenv("S3_PUBLIC_ENDPOINT", S3_ENDPOINT)
ACCESS_KEY   = os.getenv("S3_ACCESS_KEY", "minioadmin")
SECRET_KEY   = os.getenv("S3_SECRET_KEY", "minioadmin123")
BUCKET       = os.getenv("S3_BUCKET", "pdf-documents")

_client = None
_presign_client = None


def get_s3():
    global _client
    if _client is None:
        _client = boto3.client(
            "s3",
            endpoint_url=S3_ENDPOINT,
            aws_access_key_id=ACCESS_KEY,
            aws_secret_access_key=SECRET_KEY,
            config=Config(signature_version="s3v4", **_S3_CONFIG),
            region_name="us-east-1",
        )
        try:
            _client.head_bucket(Bucket=BUCKET)
        except Exception:
            _client.create_bucket(Bucket=BUCKET)
    return _client


def upload_file(key: str, data: BinaryIO, content_type: str = "application/pdf") -> str:
    try:
        get_s3().upload_fileobj(data, BUCKET, key, ExtraArgs={"ContentType": content_type})
    except (ClientError, BotoCoreError) as e:
        raise StorageUnavailable(str(e))
    return key


def download_file(key: str, dest_path: str) -> None:
    try:
        get_s3().download_file(BUCKET, key, dest_path)
    except (ClientError, BotoCoreError) as e:
        raise StorageUnavailable(str(e))


def get_presign_s3():
    global _presign_client
    if _presign_client is None:
        _presign_client = boto3.client(
            "s3",
            endpoint_url=S3_PUBLIC_ENDPOINT,
            aws_access_key_id=ACCESS_KEY,
            aws_secret_access_key=SECRET_KEY,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
            region_name="us-east-1",
        )
    return _presign_client


def generate_presigned_url(key: str, expiry: int = 3600) -> str:
    return get_presign_s3().generate_presigned_url(
        "get_object",
        Params={"Bucket": BUCKET, "Key": key},
        ExpiresIn=expiry,
    )


def delete_file(key: str) -> None:
    get_s3().delete_object(Bucket=BUCKET, Key=key)
