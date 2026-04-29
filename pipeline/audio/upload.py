"""S3 upload helpers for generated audio."""

from __future__ import annotations

import os
import time
from pathlib import Path

from dotenv import load_dotenv

REPO = Path(__file__).resolve().parents[2]
BUCKET = "files.thingelstad.com"
CACHE_CONTROL = "public, max-age=31536000"
CLOUDFRONT_DISTRIBUTION_ID = "E3AEA6KRKI2B7E"

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


def cloudfront_client():
    try:
        import boto3
    except ImportError as exc:
        raise RuntimeError("The boto3 package is required for CloudFront invalidations.") from exc

    return boto3.client("cloudfront")


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


def invalidate_path(path: str) -> str | None:
    if not CLOUDFRONT_DISTRIBUTION_ID:
        return None
    full_path = path if path.startswith("/") else f"/{path}"
    response = cloudfront_client().create_invalidation(
        DistributionId=CLOUDFRONT_DISTRIBUTION_ID,
        InvalidationBatch={
            "Paths": {"Quantity": 1, "Items": [full_path]},
            "CallerReference": f"audio-{int(time.time() * 1000)}",
        },
    )
    return response.get("Invalidation", {}).get("Id")


def upload_audio(issue: str, path: Path, bucket: str = BUCKET) -> tuple[str, int]:
    extra_args = {
        "ContentType": "audio/mpeg",
        "CacheControl": CACHE_CONTROL,
        "ACL": "public-read",
    }
    key = s3_key(issue)
    s3_client().upload_file(str(path), bucket, key, ExtraArgs=extra_args)
    invalidate_path(key)
    return public_url(issue, bucket), os.path.getsize(path)
