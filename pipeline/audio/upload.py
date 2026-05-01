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


def body_s3_key(issue: str) -> str:
    return f"weekly-thing/{issue}/body-{issue}.mp3"


def public_url(issue: str, bucket: str = BUCKET) -> str:
    return f"https://{bucket}/{s3_key(issue)}"


def body_public_url(issue: str, bucket: str = BUCKET) -> str:
    return f"https://{bucket}/{body_s3_key(issue)}"


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


def _head_exists(key: str, bucket: str) -> bool:
    try:
        from botocore.exceptions import ClientError
    except ImportError as exc:
        raise RuntimeError("The botocore package is required for audio S3 checks.") from exc

    try:
        s3_client().head_object(Bucket=bucket, Key=key)
        return True
    except ClientError as exc:
        code = str(exc.response.get("Error", {}).get("Code", ""))
        if code in {"404", "NoSuchKey", "NotFound"}:
            return False
        raise


def object_exists(issue: str, bucket: str = BUCKET) -> bool:
    return _head_exists(s3_key(issue), bucket)


def body_object_exists(issue: str, bucket: str = BUCKET) -> bool:
    return _head_exists(body_s3_key(issue), bucket)


def download_body_if_present(issue: str, dest_path: Path, bucket: str = BUCKET) -> bool:
    """Fetch the persisted body MP3 from S3 into dest_path. Returns True if downloaded."""
    if dest_path.exists():
        return True
    if not body_object_exists(issue, bucket):
        return False
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    s3_client().download_file(bucket, body_s3_key(issue), str(dest_path))
    return True


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


def _upload(path: Path, key: str, bucket: str) -> int:
    extra_args = {
        "ContentType": "audio/mpeg",
        "CacheControl": CACHE_CONTROL,
        "ACL": "public-read",
    }
    s3_client().upload_file(str(path), bucket, key, ExtraArgs=extra_args)
    try:
        invalidate_path(key)
    except Exception as exc:  # noqa: BLE001 — invalidation is best-effort
        print(f"  warning: CloudFront invalidation skipped ({exc})")
    return os.path.getsize(path)


def upload_audio(issue: str, path: Path, bucket: str = BUCKET) -> tuple[str, int]:
    size = _upload(path, s3_key(issue), bucket)
    return public_url(issue, bucket), size


def upload_body(issue: str, path: Path, bucket: str = BUCKET) -> tuple[str, int]:
    size = _upload(path, body_s3_key(issue), bucket)
    return body_public_url(issue, bucket), size


def copy_legacy_audio_to_body(issue: str, bucket: str = BUCKET) -> str | None:
    """Promote the existing published MP3 to the body slot (server-side copy).

    Returns the new body public URL on success, or None if the legacy object
    isn't present. Useful for backfilling issues whose original render predates
    the body/final split — those legacy files ARE the body."""
    if not object_exists(issue, bucket):
        return None
    s3_client().copy_object(
        Bucket=bucket,
        Key=body_s3_key(issue),
        CopySource={"Bucket": bucket, "Key": s3_key(issue)},
        ContentType="audio/mpeg",
        CacheControl=CACHE_CONTROL,
        ACL="public-read",
        MetadataDirective="REPLACE",
    )
    try:
        invalidate_path(body_s3_key(issue))
    except Exception as exc:  # noqa: BLE001
        print(f"  warning: CloudFront invalidation skipped ({exc})")
    return body_public_url(issue, bucket)
