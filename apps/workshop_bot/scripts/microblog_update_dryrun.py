#!/usr/bin/env python3
"""Hand-runnable integration check for the Micropub update path.

One-time sanity test before turning on the auto-write alt-fill flow. Run
against one micro.blog post you don't mind touching (a recent throwaway,
or a post where you want a real alt added):

  python -m apps.workshop_bot.scripts.microblog_update_dryrun <post-url>
  python -m apps.workshop_bot.scripts.microblog_update_dryrun <post-url> --preview

What it does:

  1. Fetches the post via `q=source&url=…` and prints every mf2 property.
  2. Computes a candidate new ``content`` string:
       - If the body has at least one ``<img>`` or ``![]()`` with an empty
         alt, fills the *first* one with a placeholder alt
         ``"alt fill smoke test"`` so we can see the round-trip.
       - Otherwise rewrites the body to itself (a no-op replace) so we
         can still verify the server preserves other properties when the
         content stays byte-identical.
  3. With ``--preview``, stops here and prints the diff that *would*
     be sent. Default behaviour: POSTs the Micropub update.
  4. Re-fetches the post and prints a per-property diff. Loud about any
     field that changed besides ``content``.

Exits non-zero if any non-content property diverges. Requires
``MICROBLOG_API_KEY`` (and optionally ``MICROBLOG_MICROPUB_URL``) in env.
"""

from __future__ import annotations

import argparse
import difflib
import json
import logging
import re
import sys
from pathlib import Path

# Make `apps.workshop_bot...` importable when run as a script.
_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

# Line-buffered output so progress shows up under tee / pipes.
try:
    sys.stdout.reconfigure(line_buffering=True)  # type: ignore[attr-defined]
except Exception:  # noqa: BLE001
    pass

from apps.workshop_bot.tools.content import microblog  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")

_PLACEHOLDER_ALT = "alt fill smoke test"

# Match an <img …> tag with alt="" (or missing alt). We splice an alt
# in once, on the first match. The exact splice is "add alt=… after src=…".
_IMG_TAG_RE = re.compile(r"<img\b[^>]*?>", re.IGNORECASE | re.DOTALL)
_IMG_ALT_RE = re.compile(r'\balt\s*=\s*["\']([^"\']*)["\']', re.IGNORECASE)
_IMG_SRC_RE = re.compile(r'(\bsrc\s*=\s*["\'][^"\']+["\'])', re.IGNORECASE)

# Markdown image with empty alt: ![](url). Adds the placeholder inside [].
_MD_IMG_EMPTY_RE = re.compile(r"!\[\]\(([^)]+)\)")


def _splice_alt_into_first_img(body: str) -> tuple[str, str] | None:
    """If the body has an `<img>` or `![]()` with an empty alt, return
    (new_body, description-of-change). Otherwise return None.
    """
    # Try HTML <img> tags first.
    for m in _IMG_TAG_RE.finditer(body):
        tag = m.group(0)
        alt_m = _IMG_ALT_RE.search(tag)
        if alt_m is None:
            # No alt attribute at all — splice one in after src.
            new_tag = _IMG_SRC_RE.sub(
                lambda sm: f'{sm.group(1)} alt="{_PLACEHOLDER_ALT}"',
                tag, count=1,
            )
            if new_tag != tag:
                return (
                    body[: m.start()] + new_tag + body[m.end():],
                    f"<img> at offset {m.start()}: added alt='{_PLACEHOLDER_ALT}'",
                )
        elif alt_m.group(1).strip() == "":
            # Empty alt — replace it.
            new_alt = f'alt="{_PLACEHOLDER_ALT}"'
            new_tag = tag[: alt_m.start()] + new_alt + tag[alt_m.end():]
            return (
                body[: m.start()] + new_tag + body[m.end():],
                f"<img> at offset {m.start()}: filled empty alt with '{_PLACEHOLDER_ALT}'",
            )
    # Then markdown images.
    md_m = _MD_IMG_EMPTY_RE.search(body)
    if md_m is not None:
        replacement = f"![{_PLACEHOLDER_ALT}]({md_m.group(1)})"
        return (
            body[: md_m.start()] + replacement + body[md_m.end():],
            f"![]() at offset {md_m.start()}: filled empty alt with '{_PLACEHOLDER_ALT}'",
        )
    return None


def _short(s: object, n: int = 120) -> str:
    text = json.dumps(s, ensure_ascii=False) if not isinstance(s, str) else s
    text = text.replace("\n", "↵")
    return text if len(text) <= n else text[: n - 1] + "…"


def _content_str(content_value: object) -> str:
    """Coerce mf2 content (str | dict | list) to a comparable string."""
    if isinstance(content_value, list) and content_value:
        return _content_str(content_value[0])
    if isinstance(content_value, dict):
        for k in ("markdown", "value", "html"):
            if isinstance(content_value.get(k), str):
                return content_value[k]
        return json.dumps(content_value, sort_keys=True, ensure_ascii=False)
    return str(content_value or "")


def _print_props(label: str, props: dict) -> None:
    print(f"\n=== {label} ===")
    for key in sorted(props.keys()):
        val = props[key]
        if key == "content":
            print(f"  content (len={len(_content_str(val))}):")
            for line in _content_str(val).splitlines()[:30]:
                print(f"    │ {line}")
            tail = _content_str(val).splitlines()[30:]
            if tail:
                print(f"    │ … ({len(tail)} more lines)")
        else:
            print(f"  {key}: {_short(val, 200)}")


def _diff_props(before: dict, after: dict) -> tuple[list[str], list[str]]:
    """Return (content_diff_lines, other_changed_keys)."""
    content_diff: list[str] = []
    before_content = _content_str(before.get("content"))
    after_content = _content_str(after.get("content"))
    if before_content != after_content:
        content_diff = list(difflib.unified_diff(
            before_content.splitlines(),
            after_content.splitlines(),
            fromfile="content (before)",
            tofile="content (after)",
            lineterm="",
        ))
    other_changed: list[str] = []
    keys = set(before.keys()) | set(after.keys())
    for key in sorted(keys):
        if key == "content":
            continue
        if before.get(key) != after.get(key):
            other_changed.append(key)
    return content_diff, other_changed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("post_url", help="The micro.blog post URL to update.")
    ap.add_argument(
        "--preview", action="store_true",
        help="Show what would be sent. Don't actually POST the update.",
    )
    args = ap.parse_args()

    print(f"Fetching {args.post_url} …")
    before = microblog.source_for_url(args.post_url)
    _print_props("BEFORE", before)

    body = _content_str(before.get("content"))
    splice = _splice_alt_into_first_img(body)
    if splice is None:
        print(
            "\nNo <img> / ![]() with empty alt found. Falling back to a "
            "no-op replace (sending the body back unchanged) to exercise "
            "the update path."
        )
        new_body = body
        mutation = "no-op (content byte-identical)"
    else:
        new_body, mutation = splice
        print(f"\nMutation: {mutation}")

    if args.preview:
        print("\n--- preview diff (not sent) ---")
        for line in difflib.unified_diff(
            body.splitlines(),
            new_body.splitlines(),
            fromfile="content (before)",
            tofile="content (proposed)",
            lineterm="",
        ):
            print(line)
        return 0

    print("\nSending Micropub update …")
    microblog.update_post_content(args.post_url, new_body)
    print("Update accepted by server.")

    print("\nRe-fetching to verify …")
    after = microblog.source_for_url(args.post_url)
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
            print(f"    before: {_short(before.get(key), 200)}")
            print(f"    after : {_short(after.get(key), 200)}")
        return 1
    print("Other properties: all preserved ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
