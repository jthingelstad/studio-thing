# Phase 2 — Publish

*Send it out.* — Overview: [`../publishing-process.md`](../publishing-process.md)

**Owner:** Scout + the `pipeline/`, with Eddy owning the shared editorial envelope.
**Channel:** `#production`. **Question:** *"Is it out the door, per channel?"*

Build is uniform; **Publish fans out per channel, and that divergence is the feature.** Each
channel renders the same body its own way and ships its own way. Some inputs are shared across all
channels; some are unique to one.

## The channel matrix

| Channel | Render artifact | Shared inputs | Channel-unique | Ship mechanic | Gate |
|---|---|---|---|---|---|
| **Email** (Buttondown) | `buttondown.md` | subject, description, body | membership **CTA** (Liquid, audience-aware); tinylytics pixel | POST/PATCH Buttondown API | `REQUIRED_FOR_BUTTONDOWN` = haiku + metadata + intro + cover, **and** subject + description set |
| **Website** (archive) | `archive.md` | subject, description, body | YAML front matter; no CTA, no pixel | atomic GitHub commit to `data/issues/{N}/` | Email shipped (so `absolute_url` is stamped) |
| **Podcast** (audio) | `transcript/*.txt` + MP3 | body | per-block transcript (uniquely shaped); a **CTA audio slot — not yet built** | per-block TTS + concat + S3 upload + manifest | transcripts present (always, post-Build) |

**Render-then-ship:** every leg renders exactly the artifacts it ships, from current DB state, at
ship time — nothing assumes a prior render.

## The shared envelope

Five pieces of shipping work that every channel draws on, all produced here (not in Build):

| Piece | Source | Triggered |
|---|---|---|
| **Thesis** | `thesis.md` content row — Eddy's 1–3 sentence editorial framing | **Auto** on `mark built` (one-shot, no picker). Anchors subject/description/haiku/CTA prompts downstream so the four shipping jobs land on one read. Refine in the web editor. |
| **Subject** | `metadata.json` — one-line, all channels | `compose-meta:subject` — Eddy returns 5 options, Jamie picks. |
| **Description** | `metadata.json` — comma-separated topic line; email preview + website front-matter | `compose-meta:description` — one-shot, no picker. |
| **Haiku** | `haiku.md` — bold tercet at the foot of the issue, all channels | `compose-haiku` — Eddy writes (3 options, Jamie picks). Haiku is shipping work, not authored content — Eddy produces it, Jamie just picks. |
| **CTA / thanks** | `cta-N.md` / `thanks-N.md` — audience-aware (email-only Liquid) | `compose-cta` (Patty) — **auto-fired on `mark built`** so a framing is waiting. Jamie picks. |

`metadata.json` also carries the deterministic `number`/`slug`/`image`/`publish_date` plus the
publish-stamped `buttondown_id`/`absolute_url`.

## Gates

- **Entry:** `/scout issue built` / `mark built`. On entry the ship flow runs **`compose-thesis`** (Eddy reads the
  now-frozen content and writes the framing every other Publish job will anchor on) and
  **auto-requests the CTA from Patty** (see [`../programs/membership.md`](../programs/membership.md))
  so a framing is waiting — Jamie only *picks* the CTA, never triggers it. Subject, description,
  and haiku come from the operator's buttons on the production page (slash escape hatches exist).
- **Exit:** `/scout issue put-to-bed` — files the issue into the `issues` table, closes the window
  (`is_active = 0`). The issue is now *published* and becomes the [Share](share.md) target.

The **production page** (`/productions/WT{n}`) is the live surface: **Eddy's thesis at the top**
(the read that anchors everything below), then the shared-envelope status (subject + description +
haiku + CTA), then the per-channel publish buttons — a destination's button stays gated until its
gate passes — with each leg's outcome reported back on the page.
