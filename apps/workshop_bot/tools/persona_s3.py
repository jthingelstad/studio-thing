"""S3 helper for the per-persona workshop scratchpad.

Each persona has a private prefix on the workshop bucket where it can
keep arbitrary files — campaign ledgers, drafts, multi-step thinking
notes, anything that needs to survive across hosts and process restarts.
The structure under each persona's prefix is up to the persona; we
recommend ``notes/`` for free-form Markdown and (for Marky)
``campaigns/`` for one JSON per ref tag.

Every read and write goes through ``_resolve_key`` which forces the path
into ``personas/{persona}/{relative}`` — no traversal, no other
prefixes, no other personas, no other buckets. The persona name is
*not* a model-supplied parameter; it comes from the
``active_persona`` ContextVar set by the agent loop, so a tool call
always lands inside the calling persona's namespace.

Bucket name comes from ``WORKSHOP_BUCKET`` (defaults to
``weekly-thing-workshop``). Auth via the standard boto3 chain.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Optional

logger = logging.getLogger("workshop.persona_s3")

DEFAULT_BUCKET = "weekly-thing-workshop"
ROOT_PREFIX = "personas"

# Persona name: lowercase identifier used as a path component.
PERSONA_RE = re.compile(r"^[a-z][a-z0-9_-]{0,30}$")
# Each path component (between the slashes the model supplies) follows
# the same single-component rule we use for issue files: starts with an
# alphanumeric, allowed inner chars, max 80 long.
COMPONENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$")
ALLOWED_EXTENSIONS = {
    ".md", ".markdown", ".txt", ".json", ".yaml", ".yml", ".csv", ".html",
}
WRITE_MAX_BYTES = 256 * 1024  # 256 KB
READ_MAX_BYTES = 512 * 1024


class S3PathError(ValueError):
    """The supplied persona/path pair is not a valid scoped path."""


def _bucket() -> str:
    return (os.environ.get("WORKSHOP_BUCKET") or DEFAULT_BUCKET).strip()


def _client():
    # Imported lazily so the module loads in environments without boto3.
    import boto3

    return boto3.client("s3")


def _validate_persona(persona: str) -> str:
    if not isinstance(persona, str):
        raise S3PathError(f"persona must be a string; got {type(persona).__name__}")
    name = persona.strip().lower()
    if not name or name == "unknown":
        raise S3PathError("persona is empty or unset; tool was called outside the agent loop")
    if not PERSONA_RE.match(name):
        raise S3PathError(
            "persona must be lowercase letters/digits/'_'/'-' starting with a letter"
        )
    return name


def _validate_path(path: str) -> str:
    """Validate a relative path the model supplied. Returns the normalized
    relative path (no leading/trailing slashes, no consecutive slashes).
    """
    if not isinstance(path, str):
        raise S3PathError(f"path must be a string; got {type(path).__name__}")
    raw = path.strip()
    if not raw:
        raise S3PathError("path is required")
    if raw.startswith("/") or raw.startswith("\\"):
        raise S3PathError("path must be relative (no leading slash)")
    if raw.endswith("/") or raw.endswith("\\"):
        raise S3PathError("path must end in a filename, not a slash")
    if "\\" in raw:
        raise S3PathError("backslashes are not allowed in paths")
    components = raw.split("/")
    if any(c == "" for c in components):
        raise S3PathError("path must not contain consecutive slashes")
    if any(c == ".." or c == "." for c in components):
        raise S3PathError("path may not contain '..' or '.' components")
    for c in components:
        if not COMPONENT_RE.match(c):
            raise S3PathError(
                f"path component {c!r} must match {COMPONENT_RE.pattern}"
            )
    leaf = components[-1]
    suffix = "." + leaf.rsplit(".", 1)[-1].lower() if "." in leaf else ""
    if not suffix or suffix not in ALLOWED_EXTENSIONS:
        raise S3PathError(
            f"leaf extension {suffix or '(none)'!r} is not allowed; "
            f"allowed: {sorted(ALLOWED_EXTENSIONS)}"
        )
    return raw


def _resolve_key(persona: str, path: str) -> str:
    """Combine validated persona + relative path into a bucket-relative key."""
    p = _validate_persona(persona)
    rel = _validate_path(path)
    return f"{ROOT_PREFIX}/{p}/{rel}"


def list_persona(persona: str, prefix: Optional[str] = None) -> dict[str, Any]:
    """List the files in ``personas/{persona}/{prefix}``.

    ``prefix`` is optional; if supplied it scopes the listing to a
    subdirectory the persona uses (e.g. ``"campaigns"``). The prefix is
    validated as a sequence of legal path components — no traversal.
    """
    name = _validate_persona(persona)
    bucket = _bucket()
    base = f"{ROOT_PREFIX}/{name}/"
    if prefix:
        # Allow a sub-prefix that's a sequence of components, no leaf-extension
        # requirement (it's a directory).
        sub = prefix.strip().strip("/")
        for c in sub.split("/"):
            if not c or c in ("..", ".") or not COMPONENT_RE.match(c):
                raise S3PathError(f"prefix component {c!r} is not a valid path component")
        base = base + sub + "/"
    client = _client()
    out: list[dict[str, Any]] = []
    token: Optional[str] = None
    while True:
        kw: dict[str, Any] = {"Bucket": bucket, "Prefix": base, "MaxKeys": 1000}
        if token:
            kw["ContinuationToken"] = token
        resp = client.list_objects_v2(**kw)
        for obj in resp.get("Contents", []) or []:
            key: str = obj["Key"]
            out.append(
                {
                    "path": key[len(f"{ROOT_PREFIX}/{name}/"):],
                    "key": key,
                    "size": obj.get("Size"),
                    "last_modified": (
                        obj["LastModified"].isoformat()
                        if obj.get("LastModified") else None
                    ),
                }
            )
        if resp.get("IsTruncated"):
            token = resp.get("NextContinuationToken")
        else:
            break
    logger.info("persona_s3.list(%s, prefix=%r) -> %d objects", name, prefix, len(out))
    return {"bucket": bucket, "persona": name, "prefix": base, "objects": out}


def read_persona_file(
    persona: str, path: str, *, max_bytes: int = READ_MAX_BYTES
) -> dict[str, Any]:
    """Read a text-ish file under the persona's scratchpad."""
    key = _resolve_key(persona, path)
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
    logger.info("persona_s3.read(%s, %s) -> %d bytes", persona, path, len(body))
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


def write_persona_file(
    persona: str,
    path: str,
    content: str,
    *,
    content_type: Optional[str] = None,
) -> dict[str, Any]:
    """Write a text file under the persona's scoped prefix."""
    key = _resolve_key(persona, path)
    if not isinstance(content, str):
        raise S3PathError("content must be a string")
    body = content.encode("utf-8")
    if len(body) > WRITE_MAX_BYTES:
        raise S3PathError(
            f"content is {len(body):,} bytes; max is {WRITE_MAX_BYTES:,}"
        )
    if content_type is None:
        leaf = path.rsplit("/", 1)[-1]
        suffix = "." + leaf.rsplit(".", 1)[-1].lower() if "." in leaf else ""
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
    logger.info("persona_s3.write(%s, %s) -> %d bytes", persona, path, len(body))
    return {
        "key": key,
        "bucket": bucket,
        "size": len(body),
        "content_type": content_type,
        "written": True,
    }
