"""Push cached journal alt text from workshop.db back to micro.blog.

Before Phase 2, ``update-draft`` cached vision-generated alts in the
``image_alt_cache`` SQLite table, keyed by the rehosted image basename
(``428e3db12e.jpg``). Phase 2 flipped the model so micro.blog is the
source of truth, but the existing 25-ish journal alts only live in the
local cache — Jamie's blog still serves the same images alt-less.

This one-shot walks ``image_alt_cache`` rows whose key looks like a
journal image (not ``cover-*`` — those are dead now that
``cover.json.alt`` is the source of truth for the cover), reverse-maps
each to a micro.blog upload URL by scanning the last ~100 posts for
``<img src=".../<basename>" alt="">``, splices the cached alt in, and
fires one Micropub ``replace.content`` update per modified post.

Run from the repo root:

    venv/bin/python -m pipeline.one-shot.backfill_microblog_alts            # dry-run
    venv/bin/python -m pipeline.one-shot.backfill_microblog_alts --apply    # writes

Default behaviour is a dry-run — shows the proposed splices for every
post and exits without writing. ``--apply`` actually POSTs the updates.

Skips:
  - Cache rows whose key starts with ``cover-`` (the cover.json model
    handles those now).
  - Cache rows whose basename appears in no current micro.blog post
    (post deleted upstream / older than the q=source window). Logged.
  - Images that already have a non-empty alt on the live post (we don't
    overwrite operator edits).

Idempotent: re-running after ``--apply`` is a no-op (every image either
has an alt now or wasn't found).
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

try:
    sys.stdout.reconfigure(line_buffering=True)  # type: ignore[attr-defined]
except Exception:  # noqa: BLE001
    pass

from apps.workshop_bot.tools import db  # noqa: E402
from apps.workshop_bot.tools.content import microblog  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("backfill_alts")

# Match `<img …>` tags and pull out their src + alt.
_IMG_TAG_RE = re.compile(r"<img\b[^>]*?>", re.IGNORECASE | re.DOTALL)
# Quote-aware: the back-reference \1 makes the closing quote match the
# opener, so an apostrophe inside a double-quoted alt doesn't get read
# as a closing quote. Group 2 is the value.
_IMG_SRC_RE = re.compile(r'\bsrc\s*=\s*(["\'])(.*?)\1', re.IGNORECASE | re.DOTALL)
_IMG_ALT_RE = re.compile(r'\balt\s*=\s*(["\'])(.*?)\1', re.IGNORECASE | re.DOTALL)
_IMG_SRC_ATTR_RE = re.compile(r'(\bsrc\s*=\s*(["\']).*?\2)', re.IGNORECASE | re.DOTALL)


def _splice_alt_into_img(tag: str, alt: str) -> str:
    """Same shape as ``microblog._splice_alt_into_img`` — splice an alt
    attribute into an ``<img>`` tag (replacing empty or inserting after
    src). Local copy because this script doesn't want to depend on the
    internal helper.
    """
    safe = alt.replace('"', "")
    alt_m = _IMG_ALT_RE.search(tag)
    if alt_m is not None:
        return tag[: alt_m.start()] + f'alt="{safe}"' + tag[alt_m.end():]
    return _IMG_SRC_ATTR_RE.sub(
        lambda sm: f'{sm.group(1)} alt="{safe}"', tag, count=1,
    )


def _cached_journal_alts() -> dict[str, str]:
    """Return {basename: alt} for every journal cache entry. Returns an
    empty dict if the table has been dropped (this script ran once on
    2026-05-22 and the Phase 5 migration removed the cache afterwards;
    leaving the script as a no-op so re-runs are safe historical
    reference rather than errors)."""
    import sqlite3
    try:
        with db.connect() as conn:
            rows = conn.execute(
                "SELECT image_key, alt FROM image_alt_cache "
                "WHERE image_key NOT LIKE 'cover-%' AND alt <> '' "
                "ORDER BY image_key"
            ).fetchall()
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc).lower():
            return {}
        raise
    return {r["image_key"]: r["alt"] for r in rows}


def _basename_in_url(url: str, basename: str) -> bool:
    """True if ``url`` ends with /``basename`` or has it as the final
    path component (case-insensitive). We don't care which CDN host
    serves the image; only that the basename matches."""
    if not url:
        return False
    return url.lower().rsplit("/", 1)[-1] == basename.lower()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--apply", action="store_true",
        help="Actually POST Micropub updates. Default is a dry-run.",
    )
    args = ap.parse_args()

    print("Loading cached alts from workshop.db …")
    cache = _cached_journal_alts()
    print(f"  {len(cache)} journal cache row(s)")

    if not cache:
        print("Nothing to backfill.")
        return 0

    print("Fetching recent micro.blog posts via q=source …")
    posts = microblog._source_posts()  # noqa: SLF001 — internal, fine for scripts
    print(f"  {len(posts)} post(s) returned")

    # post_url → (post, new_content_md, [(basename, src, alt)])
    pending: dict[str, dict] = {}
    found_basenames: set[str] = set()

    for post in posts:
        body = post.get("content_md") or ""
        if not body:
            continue
        url = (post.get("url") or "").strip()
        if not url:
            continue
        new_body = body
        per_post: list[tuple[str, str, str]] = []
        # Walk every <img> in the post; if its basename matches a cache
        # entry AND its alt is empty, queue the splice.
        for m in _IMG_TAG_RE.finditer(body):
            tag = m.group(0)
            src_m = _IMG_SRC_RE.search(tag)
            if not src_m:
                continue
            src = src_m.group(2).strip()
            basename = src.rsplit("/", 1)[-1].lower()
            if basename not in (k.lower() for k in cache):
                continue
            # Resolve the exact cache key (case-sensitive in DB)
            cache_key = next(k for k in cache if k.lower() == basename)
            alt_m = _IMG_ALT_RE.search(tag)
            current_alt = (alt_m.group(2) if alt_m else "").strip()
            if current_alt:
                # Live post already has an alt — don't overwrite (operator
                # may have edited it). Still mark as found so we don't
                # report it as missing.
                found_basenames.add(cache_key)
                continue
            cached_alt = cache[cache_key]
            # Splice — re-compute against `new_body` since earlier matches
            # may have shifted offsets.
            try:
                idx = new_body.index(tag)
            except ValueError:
                # Tag was already mutated by a previous splice in this
                # post — re-match against the mutated body.
                continue
            new_tag = _splice_alt_into_img(tag, cached_alt)
            new_body = new_body[:idx] + new_tag + new_body[idx + len(tag):]
            per_post.append((cache_key, src, cached_alt))
            found_basenames.add(cache_key)
        if per_post:
            pending[url] = {
                "post": post,
                "new_body": new_body,
                "splices": per_post,
            }

    # Report.
    print()
    print(f"=== Backfill plan ({'APPLY' if args.apply else 'DRY-RUN'}) ===")
    print(f"Posts to update : {len(pending)}")
    print(f"Alts to fill    : {sum(len(p['splices']) for p in pending.values())}")
    print(f"Cache rows hit  : {len(found_basenames)}/{len(cache)}")
    missing = [k for k in cache if k not in found_basenames]
    if missing:
        print("Cache rows with no upstream match (will be left as-is):")
        for k in missing:
            print(f"  - {k}")

    for url, item in pending.items():
        post = item["post"]
        title = (post.get("title") or "").strip() or "(untitled)"
        print(f"\n→ {title}")
        print(f"  {url}")
        for basename, src, alt in item["splices"]:
            short_alt = alt if len(alt) <= 90 else alt[:87] + "…"
            print(f"    {basename}  src={src}")
            print(f"        alt='{short_alt}'")

    if not args.apply:
        print("\nDry-run — re-run with --apply to send the updates.")
        return 0

    print("\nWriting back to micro.blog …")
    succeeded = 0
    failed = 0
    for url, item in pending.items():
        try:
            microblog.update_post_content(url, item["new_body"])
            succeeded += 1
            print(f"  ✓ {url}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"  ✗ {url}: {exc}")
    print(f"\nDone. {succeeded} succeeded, {failed} failed.")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
