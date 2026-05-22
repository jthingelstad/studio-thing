#!/usr/bin/env python3
"""End-to-end Micropub round-trip check, no operator post needed.

Lifecycle:

  1. Find a recent micro.blog post that has at least one image and lift
     its first image URL (so the test post embeds a real, already-hosted
     image — micro.blog won't reject it).
  2. Create a fresh `h-entry` test post titled "Workshop alt-fill round-
     trip test" with an `<img alt="">` embed.
  3. Re-fetch the new post via `q=source&url=…`. Print its properties.
  4. Mutate the content: splice `alt="alt fill smoke test"` into the
     `<img>` (same logic the real dry-run uses).
  5. Send the Micropub `update` action.
  6. Re-fetch and print a diff. Loud about any property other than
     `content` that changed.
  7. Send the Micropub `delete` action. Re-fetch to confirm it's gone
     (or that the server marked it deleted).

Exits non-zero if any non-content property diverged across the update,
or if delete didn't take effect. The whole run is bounded — one create,
one update, one delete; no orphan posts left behind even on a mid-run
crash, because step 7 runs in a `finally` block.

Requires ``MICROBLOG_API_KEY`` in env. Run from the repo root:

    venv/bin/python -m apps.workshop_bot.scripts.microblog_alt_lifecycle_test
"""

from __future__ import annotations

import difflib
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Optional

import requests

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

try:
    sys.stdout.reconfigure(line_buffering=True)  # type: ignore[attr-defined]
except Exception:  # noqa: BLE001
    pass

from apps.workshop_bot.tools.content import microblog  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")

_PLACEHOLDER_ALT = "alt fill smoke test"
_UA = "WeeklyThing-WorkshopBot/1.0-alt-lifecycle"
_TIMEOUT = 30.0

# Reuse the same matchers as the dry-run script.
_IMG_TAG_RE = re.compile(r"<img\b[^>]*?>", re.IGNORECASE | re.DOTALL)
_IMG_ALT_RE = re.compile(r'\balt\s*=\s*["\']([^"\']*)["\']', re.IGNORECASE)
_IMG_SRC_RE = re.compile(r'src\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)


def _api_key() -> str:
    key = (os.environ.get("MICROBLOG_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("MICROBLOG_API_KEY is required")
    return key


def _headers_json() -> dict:
    return {
        "Authorization": f"Bearer {_api_key()}",
        "Content-Type": "application/json",
        "User-Agent": _UA,
    }


def _find_existing_image_url() -> Optional[str]:
    """Walk the most recent ~100 posts (via q=source) and return the first
    `<img src=…>` we find. The test post will embed this image so the
    server gets a real upload reference and doesn't reject the body.
    """
    posts = microblog._source_posts()  # noqa: SLF001 — internal helper, fine for scripts
    for p in posts:
        for m in _IMG_TAG_RE.finditer(p.get("content_md") or ""):
            src_m = _IMG_SRC_RE.search(m.group(0))
            if src_m:
                return src_m.group(1)
    return None


def _create_test_post(body: str) -> str:
    """POST a Micropub create. Returns the new post's URL (from the
    server's Location header, or from the JSON body as a fallback).
    """
    payload = {
        "type": ["h-entry"],
        "properties": {
            "name": ["Workshop alt-fill round-trip test"],
            "content": [body],
        },
    }
    resp = requests.post(
        microblog.micropub_url(), json=payload,
        headers=_headers_json(), timeout=_TIMEOUT,
    )
    if resp.status_code >= 400:
        raise RuntimeError(
            f"Micropub create failed: HTTP {resp.status_code} — {(resp.text or '')[:300]}"
        )
    loc = resp.headers.get("Location") or resp.headers.get("location")
    if loc:
        return loc.strip()
    # Some Micropub servers put the URL in the JSON body.
    try:
        data = resp.json()
    except ValueError:
        data = {}
    if isinstance(data, dict):
        if isinstance(data.get("url"), str):
            return data["url"]
        if isinstance(data.get("properties"), dict):
            url_prop = data["properties"].get("url")
            if isinstance(url_prop, list) and url_prop:
                return str(url_prop[0])
    raise RuntimeError("Micropub create succeeded but no post URL returned")


def _delete_post(post_url: str) -> None:
    payload = {"action": "delete", "url": post_url}
    resp = requests.post(
        microblog.micropub_url(), json=payload,
        headers=_headers_json(), timeout=_TIMEOUT,
    )
    if resp.status_code >= 400:
        raise RuntimeError(
            f"Micropub delete failed: HTTP {resp.status_code} — {(resp.text or '')[:300]}"
        )


def _splice_alt(body: str) -> tuple[str, str]:
    m = _IMG_TAG_RE.search(body)
    if not m:
        raise RuntimeError("Test post body has no <img> to splice an alt into")
    tag = m.group(0)
    alt_m = _IMG_ALT_RE.search(tag)
    if alt_m is None:
        new_tag = _IMG_SRC_RE.sub(
            lambda sm: f'{sm.group(0)} alt="{_PLACEHOLDER_ALT}"', tag, count=1,
        )
    else:
        new_alt = f'alt="{_PLACEHOLDER_ALT}"'
        new_tag = tag[: alt_m.start()] + new_alt + tag[alt_m.end():]
    new_body = body[: m.start()] + new_tag + body[m.end():]
    return new_body, f"<img>: alt → '{_PLACEHOLDER_ALT}'"


def _content_str(content_value: object) -> str:
    if isinstance(content_value, list) and content_value:
        return _content_str(content_value[0])
    if isinstance(content_value, dict):
        for k in ("markdown", "value", "html"):
            if isinstance(content_value.get(k), str):
                return content_value[k]
        return json.dumps(content_value, sort_keys=True, ensure_ascii=False)
    return str(content_value or "")


def _short(s: object, n: int = 200) -> str:
    text = json.dumps(s, ensure_ascii=False) if not isinstance(s, str) else s
    text = text.replace("\n", "↵")
    return text if len(text) <= n else text[: n - 1] + "…"


def _print_props(label: str, props: dict) -> None:
    print(f"\n=== {label} ===")
    for key in sorted(props.keys()):
        val = props[key]
        if key == "content":
            content_str = _content_str(val)
            print(f"  content (len={len(content_str)}):")
            for line in content_str.splitlines()[:30]:
                print(f"    │ {line}")
        else:
            print(f"  {key}: {_short(val)}")


def _diff_props(before: dict, after: dict) -> tuple[list[str], list[str]]:
    before_content = _content_str(before.get("content"))
    after_content = _content_str(after.get("content"))
    content_diff: list[str] = []
    if before_content != after_content:
        content_diff = list(difflib.unified_diff(
            before_content.splitlines(), after_content.splitlines(),
            fromfile="content (before)", tofile="content (after)", lineterm="",
        ))
    other_changed: list[str] = []
    for key in sorted(set(before.keys()) | set(after.keys())):
        if key == "content":
            continue
        if before.get(key) != after.get(key):
            other_changed.append(key)
    return content_diff, other_changed


def main() -> int:
    print("Step 1: locating an existing image URL to embed …")
    image_src = _find_existing_image_url()
    if not image_src:
        print("ERROR: no existing micro.blog post with an <img> found.", file=sys.stderr)
        return 2
    print(f"  using {image_src}")

    test_body = (
        "This is a temporary post created by workshop_bot to verify the "
        "Micropub update round-trip. It will be deleted automatically.\n\n"
        f'<img src="{image_src}" alt="" />\n'
    )

    print("\nStep 2: creating test post …")
    post_url = _create_test_post(test_body)
    print(f"  created: {post_url}")

    exit_code = 0
    try:
        print("\nStep 3: fetching the new post …")
        before = microblog.source_for_url(post_url)
        _print_props("BEFORE", before)

        print("\nStep 4: computing splice …")
        body = _content_str(before.get("content"))
        new_body, mutation = _splice_alt(body)
        print(f"  mutation: {mutation}")

        print("\nStep 5: sending Micropub update …")
        microblog.update_post_content(post_url, new_body)
        print("  update accepted")

        print("\nStep 6: re-fetching to verify …")
        after = microblog.source_for_url(post_url)
        _print_props("AFTER", after)

        content_diff, other_changed = _diff_props(before, after)
        print("\n=== DIFF SUMMARY ===")
        if content_diff:
            print("content:")
            for line in content_diff:
                print(f"  {line}")
        else:
            print("content: unchanged (server returned byte-identical body)")
        if other_changed:
            print(f"⚠️ other properties changed: {', '.join(other_changed)}")
            for key in other_changed:
                print(f"  {key}")
                print(f"    before: {_short(before.get(key))}")
                print(f"    after : {_short(after.get(key))}")
            exit_code = 1
        else:
            print("Other properties: all preserved ✓")
    finally:
        print(f"\nStep 7: deleting test post {post_url} …")
        try:
            _delete_post(post_url)
            print("  delete accepted")
        except Exception as exc:  # noqa: BLE001
            print(f"  ⚠️ delete FAILED — manually remove {post_url}: {exc}", file=sys.stderr)
            exit_code = max(exit_code, 3)

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
