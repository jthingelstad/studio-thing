"""S3 upload helpers for generated audio."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

REPO = Path(__file__).resolve().parents[2]
BUCKET = "files.thingelstad.com"
CACHE_CONTROL = "public, max-age=31536000, immutable"

load_dotenv(REPO / ".env")


def s3_key(issue: str) -> str:
    return f"weekly-thing/{issue}/weekly-thing-{issue}.mp3"


def public_url(issue: str, bucket: str = BUCKET) -> str:
    return f"https://{bucket}/{s3_key(issue)}"


def s3_client():
    try:
        import boto3
    except ImportError as exc:
        raise RuntimeError("The boto3 package is required for audio S3 uploads.") from exc

    return boto3.client("s3")


def object_exists(issue: str, bucket: str = BUCKET) -> bool:
    try:
        from botocore.exceptions import ClientError
    except ImportError as exc:
        raise RuntimeError("The botocore package is required for audio S3 checks.") from exc

    try:
        s3_client().head_object(Bucket=bucket, Key=s3_key(issue))
        return True
    except ClientError as exc:
        code = str(exc.response.get("Error", {}).get("Code", ""))
        if code in {"404", "NoSuchKey", "NotFound"}:
            return False
        raise


def upload_audio(issue: str, path: Path, bucket: str = BUCKET) -> tuple[str, int]:
    extra_args = {
        "ContentType": "audio/mpeg",
        "CacheControl": CACHE_CONTROL,
        "ACL": "public-read",
    }
    s3_client().upload_file(str(path), bucket, s3_key(issue), ExtraArgs=extra_args)
    return public_url(issue, bucket), os.path.getsize(path)
