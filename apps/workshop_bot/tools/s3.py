"""S3 helper for the per-issue file workspace.

Every read and write goes through ``_resolve_key`` which forces the path
into ``weekly-thing/{N}/{filename}`` — no traversal, no other prefixes,
no other buckets. The agents have read/write power over a single
tightly-scoped namespace. Anything else is rejected.

The published archive shares this prefix (e.g. ``weekly-thing/100/cover.jpg``),
so the helper's extension allowlist excludes image and binary types to
keep agent writes from clobbering shipped assets.

Bucket name comes from ``WEEKLY_THING_ASSETS_BUCKET`` (defaults to
``files.thingelstad.com``). Auth via the standard boto3 chain (env vars,
shared credentials file, instance role).
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Optional

logger = logging.getLogger("workshop.s3")

DEFAULT_BUCKET = "files.thingelstad.com"
ROOT_PREFIX = "weekly-thing"

# Single path component, allowed extension set, no traversal. Must be
# strict — these names go into S3 keys without further escaping.
FILENAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$")
ALLOWED_EXTENSIONS = {
    ".md", ".markdown", ".txt", ".json", ".yaml", ".yml", ".csv", ".html",
}
WRITE_MAX_BYTES = 256 * 1024  # 256 KB
READ_MAX_BYTES = 512 * 1024

# Journal images live one level deeper (weekly-thing/{N}/journal/{name})
# and are binary (resized photos rehosted from micro.blog). This is *not*
# an agent-callable surface — only update-draft's journal fill uses it —
# so a separate, image-only allowlist is fine here.
JOURNAL_PREFIX = "journal"
JOURNAL_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
JOURNAL_IMAGE_MAX_BYTES = 4 * 1024 * 1024  # 4 MB — a resized image should be far under this

# Per-block audio transcripts also live one level deeper
# (weekly-thing/{N}/transcript/{NNN-slug}.txt) so they don't clash with the
# flat asset namespace. Written by ``compose-transcript`` only.
TRANSCRIPT_PREFIX = "transcript"
TRANSCRIPT_EXTENSIONS = {".txt"}
_JOURNAL_CONTENT_TYPES = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".gif": "image/gif", ".webp": "image/webp",
}


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
    """List every per-issue workspace folder under ``weekly-thing/``.
    Used to figure out which issue is currently being assembled — the
    highest folder number is the working issue.

    Folders whose first path component is not an integer (e.g.
    ``weekly-thing/forum/``, ``weekly-thing/2017/``) are skipped, so
    historical year buckets and other non-issue prefixes don't show up.

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
    """List objects stored under ``weekly-thing/{N}/``."""
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


def issue_file_url(issue_number: int, filename: str) -> str:
    """Public URL for a file in the issue workspace (the bucket is a
    CDN-fronted domain, so ``https://{bucket}/{key}``)."""
    return f"https://{_bucket()}/{_resolve_key(int(issue_number), filename)}"


def write_issue_file(
    issue_number: int,
    filename: str,
    content: str,
    *,
    content_type: Optional[str] = None,
    cache_control: Optional[str] = None,
) -> dict[str, Any]:
    """Write a text file under the issue's scoped prefix. ``cache_control``,
    if given, is set on the object (used for the HTML previews, which are
    overwritten frequently and want ``no-cache``)."""
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
    put_kwargs: dict[str, Any] = {"Bucket": bucket, "Key": key, "Body": body, "ContentType": content_type}
    if cache_control:
        put_kwargs["CacheControl"] = cache_control
    _client().put_object(**put_kwargs)
    logger.info("s3.write_issue_file(%d, %s) -> %d bytes", issue_number, filename, len(body))
    return {
        "key": key,
        "bucket": bucket,
        "url": f"https://{bucket}/{key}",
        "size": len(body),
        "content_type": content_type,
        "written": True,
    }


def delete_issue_file(issue_number: int, filename: str) -> dict[str, Any]:
    """Delete a text/JSON file from an issue's workspace. Idempotent on
    the S3 side (``DeleteObject`` is a 204 whether the key existed or
    not), but ``reset-issue`` wants to know what was actually there
    before the call — so callers should ``list_issue`` first and only
    call this for keys they saw. Returns ``{key, bucket, deleted: True}``.

    Used by ``jobs/reset_issue.py``. The agent tool surface
    deliberately does not expose this: agents can write, can't delete.
    """
    key = _resolve_key(int(issue_number), filename)
    bucket = _bucket()
    _client().delete_object(Bucket=bucket, Key=key)
    logger.info("s3.delete_issue_file(%d, %s)", issue_number, filename)
    return {"key": key, "bucket": bucket, "deleted": True}


# Pointer file at the top of the weekly-thing/ namespace (NOT inside an issue
# folder) — iOS Shortcuts fetch this URL to know the current in-flight issue
# (number, dates, predictable workspace URLs). Written by `jobs/start_issue.py`
# every time the issue window is set.
WORKSHOP_POINTER_KEY = f"{ROOT_PREFIX}/workshop.json"


def write_workshop_pointer(data: dict[str, Any]) -> dict[str, Any]:
    """Write the workshop pointer JSON to
    ``s3://{bucket}/weekly-thing/workshop.json`` (no-cache + CloudFront
    invalidation, so Shortcuts always see the latest). ``data`` is serialised
    verbatim — callers shape the schema."""
    bucket = _bucket()
    body = (json.dumps(data, indent=2, sort_keys=False) + "\n").encode("utf-8")
    _client().put_object(
        Bucket=bucket, Key=WORKSHOP_POINTER_KEY, Body=body,
        ContentType="application/json; charset=utf-8",
        # `no-store` — browsers must not cache. Stronger than `no-cache`
        # (which allows caching with revalidation). We need this because
        # CloudFront's Response Headers Policy doesn't apply to 304 Not
        # Modified responses; a cached entry that goes through conditional
        # revalidation would come back without the CORS header. `no-store`
        # keeps the browser from ever caching it, so every fetch from
        # weekly.thingelstad.com gets a fresh 200 with the CORS header.
        CacheControl="no-store",
    )
    logger.info("s3.write_workshop_pointer -> %d bytes", len(body))
    try:
        from . import cdn
        cdn.invalidate([f"/{WORKSHOP_POINTER_KEY}"])
    except Exception as exc:  # noqa: BLE001 — invalidation is best-effort
        logger.warning("s3.write_workshop_pointer: CDN invalidation skipped (%s)", exc)
    return {
        "key": WORKSHOP_POINTER_KEY, "bucket": bucket,
        "url": f"https://{bucket}/{WORKSHOP_POINTER_KEY}",
        "size": len(body), "written": True,
    }


def write_issue_html(issue_number: int, filename: str, html_text: str) -> dict[str, Any]:
    """Write an ``.html`` preview to the issue workspace with
    ``Cache-Control: no-cache`` and then invalidate the CloudFront path for
    it (best-effort). Returns the same dict as :func:`write_issue_file`,
    including ``url``."""
    if not filename.endswith(".html"):
        raise S3PathError("write_issue_html expects an .html filename")
    res = write_issue_file(
        int(issue_number), filename, html_text,
        content_type="text/html; charset=utf-8", cache_control="no-cache, max-age=0",
    )
    try:
        from . import cdn
        cdn.invalidate([f"/{res['key']}"])
    except Exception as exc:  # noqa: BLE001 — invalidation is best-effort
        logger.warning("s3.write_issue_html: CDN invalidation skipped (%s)", exc)
    return res


# ---------- journal images (binary; update-draft rehosting only) ----------


def _resolve_journal_key(issue_number: int, filename: str) -> str:
    if not isinstance(issue_number, int) or issue_number <= 0:
        raise S3PathError(f"issue_number must be a positive integer; got {issue_number!r}")
    name = (filename or "").strip()
    if not FILENAME_RE.match(name) or "/" in name or "\\" in name or ".." in name:
        raise S3PathError("journal image filename must be a single safe path component")
    suffix = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if suffix not in JOURNAL_IMAGE_EXTENSIONS:
        raise S3PathError(
            f"journal image extension {suffix or '(none)'!r} not allowed; "
            f"allowed: {sorted(JOURNAL_IMAGE_EXTENSIONS)}"
        )
    return f"{ROOT_PREFIX}/{issue_number}/{JOURNAL_PREFIX}/{name}"


def journal_image_url(issue_number: int, filename: str) -> str:
    """Public URL for a rehosted journal image (the bucket is a CDN-fronted
    domain, so ``https://{bucket}/{key}``)."""
    key = _resolve_journal_key(int(issue_number), filename)
    return f"https://{_bucket()}/{key}"


def journal_image_exists(issue_number: int, filename: str) -> bool:
    """True if the journal image is already in the workspace (a cheap HEAD —
    lets update-draft skip re-downloading/resizing on daily re-runs)."""
    key = _resolve_journal_key(int(issue_number), filename)
    client = _client()
    try:
        client.head_object(Bucket=_bucket(), Key=key)
        return True
    except client.exceptions.NoSuchKey:
        return False
    except Exception as exc:  # noqa: BLE001 — botocore 404 is a ClientError, not NoSuchKey, on head
        code = getattr(getattr(exc, "response", {}), "get", lambda *_a: {})("Error", {}).get("Code", "")
        if code in ("404", "NoSuchKey", "NotFound"):
            return False
        raise


def write_journal_image(
    issue_number: int, filename: str, body: bytes, *, content_type: Optional[str] = None
) -> dict[str, Any]:
    """Upload a (resized) journal image to ``weekly-thing/{N}/journal/{name}``.
    Binary; not exposed as an agent tool."""
    key = _resolve_journal_key(int(issue_number), filename)
    if not isinstance(body, (bytes, bytearray)):
        raise S3PathError("journal image body must be bytes")
    if len(body) > JOURNAL_IMAGE_MAX_BYTES:
        raise S3PathError(f"journal image is {len(body):,} bytes; max is {JOURNAL_IMAGE_MAX_BYTES:,}")
    if content_type is None:
        suffix = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        content_type = _JOURNAL_CONTENT_TYPES.get(suffix, "application/octet-stream")
    bucket = _bucket()
    _client().put_object(Bucket=bucket, Key=key, Body=bytes(body), ContentType=content_type)
    logger.info("s3.write_journal_image(%d, %s) -> %d bytes", issue_number, filename, len(body))
    return {"key": key, "url": f"https://{bucket}/{key}", "size": len(body), "content_type": content_type}


# ---------- per-block transcript files (text; compose-transcript only) ----------


def _resolve_transcript_key(issue_number: int, basename: str) -> str:
    """``basename`` is the file name within ``transcript/`` — must be a single
    safe path component with a ``.txt`` suffix."""
    if not isinstance(issue_number, int) or issue_number <= 0:
        raise S3PathError(f"issue_number must be a positive integer; got {issue_number!r}")
    name = (basename or "").strip()
    if not FILENAME_RE.match(name) or "/" in name or "\\" in name or ".." in name:
        raise S3PathError("transcript filename must be a single safe path component")
    suffix = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if suffix not in TRANSCRIPT_EXTENSIONS:
        raise S3PathError(
            f"transcript extension {suffix or '(none)'!r} not allowed; "
            f"allowed: {sorted(TRANSCRIPT_EXTENSIONS)}"
        )
    return f"{ROOT_PREFIX}/{issue_number}/{TRANSCRIPT_PREFIX}/{name}"


def write_transcript_file(issue_number: int, basename: str, content: str) -> dict[str, Any]:
    """Write a per-block transcript file to ``weekly-thing/{N}/transcript/{basename}``."""
    key = _resolve_transcript_key(int(issue_number), basename)
    if not isinstance(content, str):
        raise S3PathError("transcript content must be a string")
    body = content.encode("utf-8")
    if len(body) > WRITE_MAX_BYTES:
        raise S3PathError(f"transcript content is {len(body):,} bytes; max is {WRITE_MAX_BYTES:,}")
    bucket = _bucket()
    _client().put_object(
        Bucket=bucket, Key=key, Body=body,
        ContentType="text/plain; charset=utf-8",
    )
    logger.info("s3.write_transcript_file(%d, %s) -> %d bytes", issue_number, basename, len(body))
    return {
        "key": key, "bucket": bucket,
        "url": f"https://{bucket}/{key}", "size": len(body), "written": True,
    }


def delete_transcript_file(issue_number: int, basename: str) -> dict[str, Any]:
    """Delete a transcript block. ``compose-transcript`` uses this to clean up
    stale files when a re-run produces fewer blocks than the previous run."""
    key = _resolve_transcript_key(int(issue_number), basename)
    bucket = _bucket()
    _client().delete_object(Bucket=bucket, Key=key)
    logger.info("s3.delete_transcript_file(%d, %s)", issue_number, basename)
    return {"key": key, "bucket": bucket, "deleted": True}


def list_transcript_files(issue_number: int) -> list[str]:
    """List basenames of transcript files in the workspace."""
    issue_data = list_issue(int(issue_number))
    prefix = f"{TRANSCRIPT_PREFIX}/"
    return [
        o["filename"][len(prefix):]
        for o in issue_data.get("objects", [])
        if isinstance(o.get("filename"), str) and o["filename"].startswith(prefix)
    ]
