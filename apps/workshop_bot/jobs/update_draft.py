"""``update-draft`` — project upstream state into ``draft.md``.

A *pure projection*: re-run it and you get the same output (modulo
upstream changes). The draft is rebuilt from ``templates/draft_starter.md``
every run — so the layout / section order always tracks the template — and
each block is filled wholesale from its source. No additive merge; nothing
on the existing ``draft.md`` is preserved. Real authoring lives upstream
(Pinboard for the Notable / Briefly links, micro.blog for the Journal,
Drafts → Shortcut for ``intro.md`` / ``cover.json`` / ``currently.json``);
the haiku is a composed asset (``compose-haiku``). The cover caption and
the ``Currently`` section each come from a structured ``cover.json`` /
``currently.json`` (preferred) or a legacy verbatim ``cover.md`` /
``currently.md`` — see ``_cover.render`` / ``_currently.render``. The shape mirrors a
delivered issue: ``---``-fenced blocks, the Notable "discuss on Reddit"
line, ``### [Title](url)`` link headings, the ``→ **[Title](url)**``
Briefly form, elevated (titled) Journal posts, the ``A haiku to leave you
with…`` close.

After the fills the job writes ``draft.md`` back, records a ``draft_digests``
row (so Eddy's review can compute the delta), and — on Tue–Fri — runs
Eddy's post-update review and posts it to ``#editorial``. Sat/Sun/Mon it
stays silent. If ``final.md`` exists the issue is locked and the job
refuses (re-firing would silently produce a stale ``draft.md``).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from datetime import datetime

from html import escape as _html_escape

from ..personas.base import is_pass_response
from ..systems.pinboard import client as pinboard
from ..tools import (
    alt_text, context, db, draft as draft_mod, journal_images,
    microblog, render, s3,
)
from ..tools.llm import anthropic_client
from . import _base, _cover, _currently

logger = logging.getLogger("workshop.jobs.update_draft")

NAME = "update-draft"

# Block fill order is irrelevant (each replace_block is independent); the
# *layout* order lives in templates/draft_starter.md. Listed here in the
# published section order for readability (intro → Currently → cover → …).
SECTION_BLOCKS = ("intro", "currently", "cover", "notable", "journal", "brief", "haiku")
# Blocks that are just a verbatim copy of an authored asset file. (``cover``
# and ``currently`` are handled separately — see ``_cover.render`` /
# ``_currently.render`` — since they prefer structured ``.json`` forms.)
_ASSET_FILE = {"intro": "intro.md", "haiku": "haiku.md"}
_COVER_IMAGE = "https://files.thingelstad.com/weekly-thing/{n}/cover.jpg"

# Eddy posts a review only Tue–Fri (weekday 1..4, Mon=0). Sat/Sun/Mon the
# job runs but Eddy stays silent — issues just shipped Saturday and the
# early-week draft is too thin to comment on usefully.
_EDDY_REVIEW_WEEKDAYS = (1, 2, 3, 4)


# ---------- fills ----------

def _read_asset(issue_number: int, filename: str) -> str:
    res = s3.read_issue_file(issue_number, filename)
    if res.get("found") and isinstance(res.get("text"), str):
        return res["text"].strip()
    return ""


# ---- Notable ----
# H3-link headings, two blank lines apart, prefaced by the "discuss these
# links on Reddit" line. That line carries the issue number, so it's
# generated here rather than baked into the template.

def _reddit_tag_line(issue_number: int) -> str:
    return (
        f"_You can discuss any of these links at the "
        f"[Weekly Thing {issue_number} tag in r/WeeklyThing]"
        f"(https://www.reddit.com/r/weeklything/?f=flair_name%3A%22Weekly%20Thing%20{issue_number}%22)._"
    )


def _render_notable(items: list[dict], issue_number: int) -> str:
    blocks: list[str] = []
    for it in items:
        url = (it.get("url") or "").strip()
        title = (it.get("title") or url or "(untitled)").strip()
        commentary = (it.get("description") or "").strip()
        block = f"### [{title}]({url})"
        if commentary:
            block += f"\n\n{commentary}"
        blocks.append(block)
    if not blocks:
        return ""
    # Reddit line · one blank line · items two blank lines apart.
    return _reddit_tag_line(issue_number) + "\n\n" + "\n\n\n".join(blocks)


# ---- Briefly ----
# Each item is "<commentary> → **[Title](url)**" — commentary first, then
# the arrow, then the bolded link. One blank line between items; no headings.

def _render_brief(items: list[dict]) -> str:
    out: list[str] = []
    for it in items:
        url = (it.get("url") or "").strip()
        title = (it.get("title") or url or "(untitled)").strip()
        commentary = (it.get("description") or "").strip()
        link = f"**[{title}]({url})**"
        out.append(f"{commentary} → {link}" if commentary else link)
    return "\n\n".join(out)


# ---- Journal ----

def _journal_label(published_iso) -> str:
    """Render a journal entry's timestamp as ``Sunday @ 4:16 PM`` — the
    shape used in the published newsletter. Day-of-week + 12-hour clock,
    no calendar date: every journal entry in an issue is within the
    seven-day window, so the weekday already identifies it. (Double-issue
    windows do produce one duplicated weekday name; the body context
    around the entry disambiguates.)"""
    dt = microblog.published_local(published_iso)
    if dt is None:
        return str(published_iso or "").strip()
    hour12 = dt.hour % 12 or 12
    ampm = "AM" if dt.hour < 12 else "PM"
    return f"{dt.strftime('%A')} @ {hour12}:{dt.minute:02d} {ampm}"


def _render_journal(posts: list[dict]) -> str:
    """micro.blog posts in window, two blank lines apart. A status update
    (no title) leads with the date as a link; a titled post is *elevated* —
    an H3 link with a markdown hard break, the date plain on the next line.
    Photos already live inside ``content_md`` (rehosted), each on its own
    paragraph, so nothing extra is appended here."""
    out: list[str] = []
    for p in posts:
        url = (p.get("url") or "").strip()
        title = (p.get("title") or "").strip()
        label = _journal_label(p.get("published"))
        body = (p.get("content_md") or "").strip()
        if title and url:
            head = f"### [{title}]({url})  \n{label}"
        elif url:
            head = f"[{label}]({url})"
        else:
            head = label
        out.append(f"{head}\n\n{body}" if body else head)
    return "\n\n\n".join(out)


def _gather_fills(window: dict) -> dict[str, str]:
    """Pull every section's content once. Source pulls (Pinboard,
    micro.blog) that fail degrade to a placeholder line rather than
    breaking the run."""
    n = int(window["issue_number"])
    # Reset the per-run vision-call cap so a single ``update-draft`` can't
    # fan out to dozens of vision calls (cover + every journal image).
    alt_text.begin_run()
    fills: dict[str, str] = {block: _read_asset(n, _ASSET_FILE[block]) for block in _ASSET_FILE}
    # Cover (caption/date/location) — structured cover.json (preferred) or
    # legacy cover.md; Currently — structured currently.json or legacy currently.md.
    fills["cover"] = _cover.render(n)
    fills["currently"] = _currently.render(n)
    # The haiku ships bold-wrapped with hard breaks; normalize whatever the
    # composed haiku.md holds.
    fills["haiku"] = _base.format_haiku(fills.get("haiku", ""))
    # The cover block leads with the issue's cover image (a derived URL),
    # then the caption / date / location below it. Use a native <img> tag
    # so the alt attribute has an explicit home (cover.json.alt overrides;
    # else vision-generated; else "").
    if fills.get("cover"):
        cover_alt = _cover.alt(n)
        cover_img = (
            f'<img src="{_COVER_IMAGE.format(n=n)}" '
            f'alt="{_html_escape(cover_alt, quote=True)}" />'
        )
        fills["cover"] = f"{cover_img}\n\n{fills['cover']}"

    try:
        cand = pinboard.issue_window_candidates(window["start_date"], window["end_date"])
        fills["notable"] = _render_notable(cand.get("notable", []), n)
        fills["brief"] = _render_brief(cand.get("brief", []))
    except Exception as exc:  # noqa: BLE001
        logger.warning("update-draft: Pinboard pull failed for #%d: %s", n, exc)
        fills["notable"] = f"_Notable — couldn't pull from Pinboard ({type(exc).__name__})._"
        fills["brief"] = f"_Briefly — couldn't pull from Pinboard ({type(exc).__name__})._"

    try:
        posts = microblog.posts_in_window(window["start_date"], window["end_date"])
        for p in posts:
            try:
                p["content_md"] = journal_images.rehost_in_markdown(p.get("content_md") or "", n)
            except Exception as exc:  # noqa: BLE001
                logger.warning("update-draft: journal image rehost failed for %s: %s", p.get("url"), exc)
        fills["journal"] = _render_journal(posts)
    except Exception as exc:  # noqa: BLE001
        logger.warning("update-draft: micro.blog pull failed for #%d: %s", n, exc)
        fills["journal"] = f"_Journal — couldn't pull from micro.blog ({type(exc).__name__})._"

    return fills


def _final_exists(issue_number: int) -> bool:
    res = s3.read_issue_file(issue_number, "final.md")
    return bool(res.get("found"))


# ---------- Eddy's post-update review ----------

# Default model for the HTML drawer review (`_draft_review`) — the
# substantive editorial pass that lands on `draft.html`. Tunable via
# ``WORKSHOP_EDDY_DRAFT_REVIEW_MODEL`` so a deployment can swap to
# Opus for a richer pass or Haiku to save tokens. Separate from the
# weekday-scaled `_review_model` below (that one drives the lighter
# `#editorial` Discord card).
_DRAFT_REVIEW_DEFAULT_MODEL = "sonnet"


def _draft_review_model() -> str:
    override = (os.environ.get("WORKSHOP_EDDY_DRAFT_REVIEW_MODEL") or "").strip()
    return override or _DRAFT_REVIEW_DEFAULT_MODEL


# Model for the Tue–Fri `#editorial` post-update card, keyed by Python
# ``date.weekday()`` (Mon=0, …, Sun=6). Tue/Wed (1/2) get Haiku because
# the card is mostly the readiness checklist; Thu/Fri (3/4) get Sonnet
# for the substantive end-of-week pass. Sat/Sun/Mon don't run (gated
# above this function). Tweak by editing the dict; override the whole
# selection via ``WORKSHOP_EDDY_REVIEW_MODEL`` (matches the existing
# convention).
_REVIEW_MODEL_BY_WEEKDAY: dict[int, str] = {1: "haiku", 2: "haiku", 3: "sonnet", 4: "sonnet"}
_REVIEW_MODEL_FALLBACK = "haiku"


def _review_model(weekday: int) -> str:
    override = (os.environ.get("WORKSHOP_EDDY_REVIEW_MODEL") or "").strip()
    if override:
        return override
    return _REVIEW_MODEL_BY_WEEKDAY.get(weekday, _REVIEW_MODEL_FALLBACK)


async def _draft_review(
    ctx: "_base.JobContext", window: dict, st: dict, prev_digest, today, draft_text: str,
) -> str:
    """A solid editorial pass for the shareable ``draft.html`` — suggestions
    only, embedded behind a "Show review" toggle (hidden by default). Runs
    on every ``update-draft`` (not weekday-gated like the ``#editorial``
    card — the shareable preview should always carry the latest pass).
    Returns the review markdown, or ``""`` when there's no Eddy / the
    prompt is missing / Eddy responds ``PASS`` (an empty draft)."""
    team = getattr(getattr(ctx, "deps", None), "team", None)
    if team is None:
        return ""
    eddy = team.bots.get("eddy")
    if eddy is None or getattr(eddy, "user", None) is None:
        return ""
    try:
        prompt = anthropic_client.load_prompt("eddy-draft-review")
    except OSError as exc:
        logger.warning("update-draft: draft-review prompt missing: %s", exc)
        return ""
    n = int(window["issue_number"])
    eddy_ctx = context.build_eddy_context(ref_date=today, section_status=st, prev_digest=prev_digest)
    user_msg = (
        f"{context.render_block(eddy_ctx)}\n\n{prompt}\n\n"
        f"---\n\nThe current draft (WT{n}):\n\n```markdown\n{draft_text}\n```"
    )
    with db.AgentRun("eddy", trigger="update-draft:html-review") as run:
        answer, _m = await eddy.core(latest=user_msg, history=[], model=_draft_review_model())
        run.records_written = 0 if (not answer or is_pass_response(answer)) else 1
    if not answer or is_pass_response(answer):
        return ""
    return answer.strip()


async def _maybe_eddy_review(
    ctx: "_base.JobContext", window: dict, st: dict, prev_digest, today, *, view_url=None
) -> str:
    if today.weekday() not in _EDDY_REVIEW_WEEKDAYS:
        logger.info("update-draft: %s — Eddy stays silent", today.strftime("%a"))
        return "Eddy is silent Sat/Sun/Mon."
    team = getattr(getattr(ctx, "deps", None), "team", None)
    if team is None:
        logger.info("update-draft: no team registry; Eddy review skipped")
        return "(no Discord — Eddy review skipped)"
    eddy = team.bots.get("eddy")
    if eddy is None or getattr(eddy, "user", None) is None:
        logger.info("update-draft: Eddy unavailable; review skipped")
        return "(Eddy unavailable — review skipped)"

    eddy_ctx = context.build_eddy_context(ref_date=today, section_status=st, prev_digest=prev_digest)
    try:
        review_prompt = anthropic_client.load_prompt("eddy-update-review")
    except OSError as exc:
        logger.warning("update-draft: review prompt missing: %s", exc)
        return "(Eddy review prompt missing)"
    user_msg = f"{context.render_block(eddy_ctx)}\n\n{review_prompt}"
    model = _review_model(today.weekday())
    with db.AgentRun("eddy", trigger="update-draft:editorial-card") as run:
        answer, _meta = await eddy.core(latest=user_msg, history=[], model=model)
        run.records_written = 0 if (not answer or is_pass_response(answer)) else 1
    if not answer or is_pass_response(answer):
        return "Eddy: PASS (nothing to flag)."
    if view_url:
        answer = answer.rstrip() + f"\n\n📄 [view draft]({view_url})"
    posted = await ctx.post("DISCORD_CHANNEL_EDITORIAL", answer, persona="eddy")
    return "Eddy posted a review to #editorial." if posted else "(couldn't post Eddy's review)"


# ---------- the job ----------

async def run(ctx: "_base.JobContext") -> "_base.JobResult":
    window = db.get_active_issue_window()
    if window is None:
        return _base.JobResult(
            False,
            "❌ no active issue window — run `/workshop issue start <n> <pub-date> <days>` first.",
        )
    n = int(window["issue_number"])

    if _final_exists(n):
        return _base.JobResult(
            False,
            f"❌ issue #{n} is locked — `final.md` exists. Delete it to unlock `update-draft`.",
        )

    asset = f"{n}/draft.md"
    try:
        with _base.job_lock([asset], NAME):
            # Rebuild from the template every run so the section layout
            # always matches templates/draft_starter.md (the draft is a
            # pure projection — nothing on the old draft.md is preserved).
            text = _base.starter_template()
            # _gather_fills does blocking HTTP (Pinboard, micro.blog,
            # journal-image download/resize/upload) — off the event loop.
            fills = await asyncio.to_thread(_gather_fills, window)
            for block in SECTION_BLOCKS:
                text = _base.replace_block(text, block, fills.get(block, ""))
            try:
                s3.write_issue_file(n, "draft.md", text)
            except Exception as exc:  # noqa: BLE001
                logger.exception("update-draft: write failed for #%d", n)
                return _base.JobResult(
                    False, f"❌ couldn't write `draft.md` for #{n}: `{type(exc).__name__}: {exc}`"
                )

            source_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
            try:
                listing = s3.list_issue(n)
                files = {o.get("filename") for o in listing.get("objects", []) if o.get("filename")}
            except Exception:  # noqa: BLE001
                files = set()
            st = draft_mod.section_status(n, draft_text=text, list_objects=files)
            prev_digest = db.latest_draft_digest(n)
            today = datetime.now().date()

            # Solid editorial pass for the shareable HTML preview — embedded
            # behind a "Show review" toggle, hidden by default. Best-effort.
            review_md = ""
            try:
                review_md = await _draft_review(ctx, window, st, prev_digest, today, text)
            except Exception:  # noqa: BLE001
                logger.exception("update-draft: HTML draft review failed for #%d", n)

            # Browser-viewable preview (no-cache + CDN invalidation); best-effort.
            html_url = await asyncio.to_thread(
                render.render_and_upload_html, n, "draft", text,
                title=f"WT{n} — draft",
                subtitle=f"DRAFT · WT{n} · refreshed {today} · ~{st['word_count']} words · not the final issue",
                strip_block_markers=True, review_md=review_md,
            )

            review_note = ""
            try:
                review_note = await _maybe_eddy_review(ctx, window, st, prev_digest, today, view_url=html_url)
            except Exception:  # noqa: BLE001
                logger.exception("update-draft: Eddy review failed for #%d", n)
                review_note = "(Eddy review errored — see logs)"

            try:
                db.insert_draft_digest(
                    issue=n,
                    word_count=st["word_count"],
                    notable_count=st["sections"]["notable"]["item_count"],
                    brief_count=st["sections"]["brief"]["item_count"],
                    journal_count=st["sections"]["journal"]["item_count"],
                    intro_present=st["intro_present"],
                    currently_present=st["currently_present"],
                    haiku_present=st["haiku_present"],
                    cover_present=st["cover_present"],
                    source_hash=source_hash,
                )
            except Exception:  # noqa: BLE001
                logger.exception("update-draft: digest write failed for #%d", n)
    except _base.JobLocked as exc:
        return _base.JobResult(
            False, f"⏳ `update-draft` is already running ({exc.holder_desc}) — try again shortly."
        )

    missing = ", ".join(st["required_missing"]) or "nothing"
    view = (f" · 📄 {html_url}" + (" (with review — hit “Show review”)" if review_md else "")) if html_url else ""
    return _base.JobResult(
        True,
        f"refreshed `draft.md` for #{n} (~{st['word_count']} words; "
        f"{st['sections']['notable']['item_count']} Notable / "
        f"{st['sections']['brief']['item_count']} Briefly / "
        f"{st['sections']['journal']['item_count']} Journal){view}. "
        f"Still missing for ship: {missing}. {review_note}".strip(),
        data={"issue_number": n, "section_status": st, "review": review_note,
              "preview_url": html_url, "html_review": bool(review_md)},
    )
