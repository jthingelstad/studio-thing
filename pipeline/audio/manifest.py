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
    ordered = {
        key: data[key]
        for key in sorted((str(key) for key in data.keys()), key=issue_sort_key)
    }
    path.write_text(json.dumps(ordered, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def script_path(issue: Any) -> Path:
    return SCRIPT_DIR / f"{issue_key(issue)}.txt"
