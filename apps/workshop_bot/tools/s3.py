"""S3 helper for the per-issue file workspace.

Every read and write goes through ``_resolve_key`` which forces the path
into ``weekly-thing/issues/{N}/{filename}`` — no traversal, no other
prefixes, no other buckets. The agents have read/write power over a
single tightly-scoped namespace. Anything else is rejected.

Bucket name comes from ``WEEKLY_THING_ASSETS_BUCKET`` (defaults to
``files.thingelstad.com``). Auth via the standard boto3 chain (env vars,
shared credentials file, instance role).
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Optional

logger = logging.getLogger("workshop.s3")

DEFAULT_BUCKET = "files.thingelstad.com"
ROOT_PREFIX = "weekly-thing/issues"

# Single path component, allowed extension set, no traversal. Must be
# strict — these names go into S3 keys without further escaping.
FILENAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$")
ALLOWED_EXTENSIONS = {
    ".md", ".markdown", ".txt", ".json", ".yaml", ".yml", ".csv", ".html",
}
WRITE_MAX_BYTES = 256 * 1024  # 256 KB
READ_MAX_BYTES = 512 * 1024


class S3PathError(ValueError):
    """The supplied issue/filename pair is not a valid scoped path."""


def _bucket() -> str:
    return (
        os.environ.get("WEEKLY_THING_ASSETS_BUCKET")
        or DEFAULT_BUCKET
    ).strip()


def _client():
    # Imported lazily so the module loads in environments without boto3.
    import boto3

    return boto3.client("s3")


def _resolve_key(issue_number: int, filename: str) -> str:
    if not isinstance(issue_number, int) or issue_number <= 0:
        raise S3PathError(f"issue_number must be a positive integer; got {issue_number!r}")
    name = (filename or "").strip()
    if not FILENAME_RE.match(name):
        raise S3PathError(
            "filename must be a single path component using "
            "letters, digits, '.', '_' or '-'"
        )
    if "/" in name or "\\" in name or ".." in name:
        raise S3PathError("filename may not contain path separators or '..'")
    suffix = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if suffix and suffix not in ALLOWED_EXTENSIONS:
        raise S3PathError(
            f"extension {suffix!r} is not allowed; allowed: {sorted(ALLOWED_EXTENSIONS)}"
        )
    return f"{ROOT_PREFIX}/{issue_number}/{name}"


def list_workspaces() -> dict[str, Any]:
    """List every per-issue workspace folder under
    ``weekly-thing/issues/``. Used to figure out which issue is currently
    being assembled — the highest folder number is the working issue.

    Returns each issue's number, file count, and most-recent modification
    time across its files.
    """
    bucket = _bucket()
    prefix = f"{ROOT_PREFIX}/"
    client = _client()
    by_issue: dict[int, dict[str, Any]] = {}
    token: Optional[str] = None
    while True:
        kw: dict[str, Any] = {"Bucket": bucket, "Prefix": prefix, "MaxKeys": 1000}
        if token:
            kw["ContinuationToken"] = token
        resp = client.list_objects_v2(**kw)
        for obj in resp.get("Contents", []) or []:
            key: str = obj["Key"]
            tail = key[len(prefix):]
            num_str = tail.split("/", 1)[0]
            if not num_str.isdigit():
                continue
            n = int(num_str)
            entry = by_issue.setdefault(
                n, {"issue_number": n, "file_count": 0, "latest_modified": None}
            )
            entry["file_count"] += 1
            ts = obj.get("LastModified")
            if ts is not None:
                iso = ts.isoformat()
                if entry["latest_modified"] is None or iso > entry["latest_modified"]:
                    entry["latest_modified"] = iso
        if resp.get("IsTruncated"):
            token = resp.get("NextContinuationToken")
        else:
            break
    issues = sorted(by_issue.values(), key=lambda r: r["issue_number"])
    logger.info("s3.list_workspaces() -> %d issue folder(s)", len(issues))
    return {
        "bucket": bucket,
        "prefix": prefix,
        "issues": issues,
        "current_issue_number": issues[-1]["issue_number"] if issues else None,
    }


def list_issue(issue_number: int) -> dict[str, Any]:
    """List objects stored under ``weekly-thing/issues/{N}/``."""
    if not isinstance(issue_number, int) or issue_number <= 0:
        raise S3PathError(f"issue_number must be a positive integer; got {issue_number!r}")
    bucket = _bucket()
    prefix = f"{ROOT_PREFIX}/{issue_number}/"
    client = _client()
    out: list[dict[str, Any]] = []
    token: Optional[str] = None
    while True:
        kw: dict[str, Any] = {"Bucket": bucket, "Prefix": prefix, "MaxKeys": 200}
        if token:
            kw["ContinuationToken"] = token
        resp = client.list_objects_v2(**kw)
        for obj in resp.get("Contents", []) or []:
            key = obj["Key"]
            out.append(
                {
                    "filename": key[len(prefix):] if key.startswith(prefix) else key,
                    "key": key,
                    "size": obj.get("Size"),
                    "last_modified": (
                        obj["LastModified"].isoformat()
                        if obj.get("LastModified") else None
                    ),
                    "etag": obj.get("ETag"),
                }
            )
        if resp.get("IsTruncated"):
            token = resp.get("NextContinuationToken")
        else:
            break
    logger.info("s3.list_issue(%d) -> %d objects", issue_number, len(out))
    return {
        "bucket": bucket,
        "issue_number": issue_number,
        "prefix": prefix,
        "objects": out,
    }


def read_issue_file(issue_number: int, filename: str, *, max_bytes: int = READ_MAX_BYTES) -> dict[str, Any]:
    """Read a text-ish file for an issue. Binary content is reported but not returned."""
    key = _resolve_key(issue_number, filename)
    bucket = _bucket()
    client = _client()
    try:
        resp = client.get_object(Bucket=bucket, Key=key)
    except client.exceptions.NoSuchKey:
        return {"key": key, "found": False}
    body = resp["Body"].read(max_bytes + 1)
    if len(body) > max_bytes:
        return {
            "key": key,
            "found": True,
            "error": f"object exceeds {max_bytes:,} bytes; read aborted",
            "size": resp.get("ContentLength"),
        }
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        return {
            "key": key,
            "found": True,
            "binary": True,
            "size": resp.get("ContentLength"),
            "content_type": resp.get("ContentType"),
        }
    logger.info("s3.read_issue_file(%d, %s) -> %d bytes", issue_number, filename, len(body))
    return {
        "key": key,
        "found": True,
        "text": text,
        "size": len(body),
        "content_type": resp.get("ContentType"),
        "last_modified": (
            resp["LastModified"].isoformat() if resp.get("LastModified") else None
        ),
    }


def write_issue_file(
    issue_number: int,
    filename: str,
    content: str,
    *,
    content_type: Optional[str] = None,
) -> dict[str, Any]:
    """Write a text file under the issue's scoped prefix."""
    key = _resolve_key(issue_number, filename)
    if not isinstance(content, str):
        raise S3PathError("content must be a string")
    body = content.encode("utf-8")
    if len(body) > WRITE_MAX_BYTES:
        raise S3PathError(
            f"content is {len(body):,} bytes; max is {WRITE_MAX_BYTES:,}"
        )
    if content_type is None:
        suffix = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        content_type = {
            ".md": "text/markdown; charset=utf-8",
            ".markdown": "text/markdown; charset=utf-8",
            ".txt": "text/plain; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".yaml": "application/yaml; charset=utf-8",
            ".yml": "application/yaml; charset=utf-8",
            ".csv": "text/csv; charset=utf-8",
            ".html": "text/html; charset=utf-8",
        }.get(suffix, "text/plain; charset=utf-8")
    bucket = _bucket()
    client = _client()
    client.put_object(Bucket=bucket, Key=key, Body=body, ContentType=content_type)
    logger.info("s3.write_issue_file(%d, %s) -> %d bytes", issue_number, filename, len(body))
    return {
        "key": key,
        "bucket": bucket,
        "size": len(body),
        "content_type": content_type,
        "written": True,
    }
