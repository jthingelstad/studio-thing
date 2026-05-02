"""Read and write tracked audio metadata."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
AUDIO_DIR = REPO / "data" / "audio"
MANIFEST_PATH = AUDIO_DIR / "manifest.json"
SCRIPT_DIR = AUDIO_DIR / "scripts"
SCRIPT_STATUS_PATH = AUDIO_DIR / "script_status.json"
BUMPERS_DIR = AUDIO_DIR / "bumpers"
BUMPERS_KEY = "_bumpers"
BUMPER_NAMES = ("intro", "outro")
SCRIPT_STATUS_SCHEMA_VERSION = 1


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def issue_key(issue: Any) -> str:
    return str(issue)


def issue_sort_key(value: Any) -> tuple[int, str]:
    text = str(value)
    prefix = ""
    for char in text:
        if not char.isdigit():
            break
        prefix += char
    if not prefix:
        return (10**9, text)
    return (int(prefix), text)


def hash_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_manifest(path: Path = MANIFEST_PATH) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError(f"{path} must contain a JSON object")
    return {str(key): value for key, value in data.items()}


def write_manifest(data: dict[str, dict[str, Any]], path: Path = MANIFEST_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    bumpers = data.get(BUMPERS_KEY)
    issue_keys = sorted(
        (str(key) for key in data.keys() if key != BUMPERS_KEY),
        key=issue_sort_key,
    )
    ordered: dict[str, Any] = {}
    if isinstance(bumpers, dict):
        ordered[BUMPERS_KEY] = bumpers
    for key in issue_keys:
        ordered[key] = data[key]
    path.write_text(json.dumps(ordered, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def script_path(issue: Any) -> Path:
    return SCRIPT_DIR / f"{issue_key(issue)}.txt"


def bumper_path(name: str) -> Path:
    return BUMPERS_DIR / f"{name}.mp3"


def bumpers_state(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    state = manifest.get(BUMPERS_KEY)
    if not isinstance(state, dict):
        return {}
    return {name: state[name] for name in BUMPER_NAMES if isinstance(state.get(name), dict)}


def set_bumper_state(manifest: dict[str, Any], name: str, hash_: str, voice: str) -> None:
    block = manifest.setdefault(BUMPERS_KEY, {})
    block[name] = {"hash": hash_, "voice": voice, "generated_at": now_iso()}


def issue_entries(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        key: value
        for key, value in manifest.items()
        if key != BUMPERS_KEY and isinstance(value, dict)
    }


def script_status_path() -> Path:
    return SCRIPT_STATUS_PATH


def read_script_status(path: Path = SCRIPT_STATUS_PATH) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": SCRIPT_STATUS_SCHEMA_VERSION, "validator_version": "", "issues": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError(f"{path} must contain a JSON object")
    issues = data.get("issues") or {}
    if not isinstance(issues, dict):
        raise RuntimeError(f"{path}: 'issues' must be an object")
    data["issues"] = {str(key): value for key, value in issues.items()}
    return data


def write_script_status(data: dict[str, Any], path: Path = SCRIPT_STATUS_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    issues = data.get("issues") or {}
    ordered_issues = {
        key: issues[key]
        for key in sorted((str(key) for key in issues.keys()), key=issue_sort_key)
    }
    payload = {
        "schema_version": data.get("schema_version", SCRIPT_STATUS_SCHEMA_VERSION),
        "validator_version": data.get("validator_version", ""),
        "issues": ordered_issues,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
