"""``compose-archive`` — assemble ``archive.md`` from ``final.md`` + assets.

The website-side sibling of ``build-publish``. Same source material (``final.md``
plus the assembled atoms), same body shape, but tuned for the public archive:

- **No editor-mode comment** — that's a Buttondown-specific preamble.
- **No Tinylytics tracking pixel** — that's email-only.
- **No audience-aware Liquid blocks** — and the ``<!-- cta:N -->`` /
  ``<!-- thanks:N -->`` markers are stripped entirely rather than substituted,
  because the website doesn't host supporter callouts inline (the dedicated
  ``/members/`` page does that work).
- **YAML front matter** carrying the editorial-facing fields (subject,
  publish_date, description, image, slug, absolute_url, buttondown_id,
  word_count, domains, links).

Also writes ``links.json`` next to ``archive.md`` — the structured link
extraction (notable_links / briefly_links / domains / word_count) that the
website's corpus chunker and per-issue link feeds consume.

Deterministic, no LLM calls. Re-runs are idempotent on identical ``final.md``.
Refuses (PASSes loudly) if any required asset is missing — same gate as
``build-publish``, minus the membership-block marker check (markers are
*expected* in ``final.md``; we strip them on the way to ``archive.md``).
"""

from __future__ import annotations

import json
import logging
import re

import yaml
from librarian_core.links import count_words, extract_domains, extract_links

from ..tools import s3
from . import _base

logger = logging.getLogger("workshop.jobs.compose_archive")

NAME = "compose-archive"

REQUIRED = ("final.md", "haiku.md", "metadata.json", "intro.md", "cover.jpg")

_FIX_HINT = {
    "haiku.md": "→ `/eddy issue haiku`",
    "metadata.json": "→ `/eddy issue subject`",
    "intro.md": "→ write it, push via Shortcut",
    "cover.jpg": "→ Shortcuts uploads this",
    "final.md": "→ `/eddy issue final`",
}

# Match the marker line plus a trailing blank line so removing the marker
# doesn't leave a doubled paragraph break.
_MARKER_RE = re.compile(r"\n?<!--\s*(?:cta|thanks):\d+\s*-->\n?")


def _read(issue_number: int, filename: str) -> str:
    res = s3.read_issue_file(issue_number, filename)
    if res.get("found") and isinstance(res.get("text"), str):
        return res["text"]
    return ""


def _load_metadata(issue_number: int) -> dict:
    raw = _read(issue_number, "metadata.json")
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (ValueError, TypeError):
        return {}


def _strip_membership_markers(body: str) -> str:
    """Drop ``<!-- cta:N -->`` / ``<!-- thanks:N -->`` lines and the blank
    lines around them. The website body shouldn't carry supporter-callout
    placeholders — those belong in the email only."""
    cleaned = _MARKER_RE.sub("\n", body)
    # The regex leaves a triple-newline where a marker had a blank line on
    # both sides; collapse so the helper is self-consistent.
    return re.sub(r"\n{3,}", "\n\n", cleaned)


def _build_archive_body(final_text: str) -> str:
    """Take the same block-stripped + marker-stripped body shape used in
    archive.md today. Reuses build-publish's block-marker stripper for
    section-collapse parity, then strips the cta/thanks markers."""
    from ..tools import issue_assembly  # local import — match build_publish style

    body = issue_assembly._strip_block_markers(final_text)
    body = _strip_membership_markers(body)
    # Normalize any blank-line bloat the marker removal left behind.
    body = re.sub(r"\n{3,}", "\n\n", body)
    return body.strip() + "\n"


def _build_front_matter(metadata: dict, body: str) -> dict:
    """Match the front-matter field order data/issues/{N}/archive.md uses today
    (see pipeline/one-shot/migrate_to_issues_canonical.py). Keeps the website
    build's read path identical regardless of whether an issue was migrated
    from data/buttondown/ or composed fresh by workshop_bot."""
    link_data = extract_links(body)
    all_curated = link_data["all_curated"]
    return {
        "buttondown_id": metadata.get("buttondown_id", "") or "",
        "number": int(metadata["number"]),
        "subject": metadata.get("subject", "") or "",
        "publish_date": metadata.get("publish_date", "") or "",
        "slug": str(metadata.get("slug", "") or ""),
        "description": metadata.get("description", "") or "",
        "image": metadata.get("image", "") or "",
        "absolute_url": metadata.get("absolute_url", "") or "",
        "domains": extract_domains(all_curated),
        "links": all_curated,
        "word_count": count_words(body),
    }, link_data


def _build_links_json(front_matter: dict, link_data: dict) -> dict:
    return {
        "notable_links": link_data["notable"],
        "briefly_links": link_data["briefly"],
        "domains": front_matter["domains"],
        "word_count": front_matter["word_count"],
    }


def _render_archive_md(front_matter: dict, body: str) -> str:
    fm_str = yaml.dump(
        front_matter,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
        width=1000,
    )
    return f"---\n{fm_str}---\n{body}"


async def run(ctx: "_base.JobContext") -> "_base.JobResult":
    """Build ``archive.md`` + ``links.json`` for the in-flight issue.

    Refuses with a missing-list (→ ``#editorial``) if any of REQUIRED isn't
    in the workspace. Holds a job lock on ``{N}/archive.md`` so a concurrent
    run can't race with us. Idempotent on identical ``final.md`` + metadata.
    """
    from ..tools import db

    window = db.get_active_issue_window()
    if window is None:
        return _base.JobResult(
            False, "❌ no active issue window — run `/eddy issue start` first."
        )
    n = int(window["issue_number"])

    asset = f"{n}/archive.md"
    try:
        with _base.job_lock([asset], NAME):
            try:
                listing = s3.list_issue(n)
                files = {o.get("filename") for o in listing.get("objects", []) if o.get("filename")}
            except Exception:  # noqa: BLE001
                files = set()
            missing = [r for r in REQUIRED if r not in files]
            if missing:
                lines = [f"⛔ `compose-archive` for **WT{n}** can't run yet — missing:"]
                for r in missing:
                    lines.append(f"  ❌ `{r}` {_FIX_HINT.get(r, '')}".rstrip())
                msg = "\n".join(lines)
                await ctx.post("DISCORD_CHANNEL_EDITORIAL", msg, persona="eddy")
                return _base.JobResult(
                    False, msg, data={"issue_number": n, "missing": missing}
                )

            final_text = _read(n, "final.md")
            metadata = _load_metadata(n)
            if not metadata.get("number"):
                metadata["number"] = n

            body = _build_archive_body(final_text)
            front_matter, link_data = _build_front_matter(metadata, body)
            archive_md = _render_archive_md(front_matter, body)
            links_json = _build_links_json(front_matter, link_data)

            s3.write_issue_file(n, "archive.md", archive_md)
            s3.write_issue_file(n, "links.json", json.dumps(links_json, indent=2) + "\n")
    except _base.JobLocked as exc:
        return _base.JobResult(
            False, f"⏳ `compose-archive` is already running ({exc.holder_desc})."
        )

    return _base.JobResult(
        True,
        f"archive.md + links.json written for #{n} "
        f"({front_matter['word_count']} words, "
        f"{len(front_matter['links'])} links, "
        f"{len(front_matter['domains'])} domains).",
        data={
            "issue_number": n,
            "word_count": front_matter["word_count"],
            "link_count": len(front_matter["links"]),
            "domain_count": len(front_matter["domains"]),
        },
    )
