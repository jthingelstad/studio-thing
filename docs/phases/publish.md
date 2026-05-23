# Phase 2 — Publish

*Send it out.* — Overview: [`../publishing-process.md`](../publishing-process.md)

**Owner:** Eddy + the `pipeline/`. **Channel:** `#editorial`. **Question:** *"Is it out the door,
per channel?"*

Build is uniform; **Publish fans out per channel, and that divergence is the feature.** Each
channel renders the same body its own way and ships its own way. Some inputs are shared across all
channels; some are unique to one.

## The channel matrix

| Channel | Render artifact | Shared inputs | Channel-unique | Ship mechanic | Gate |
|---|---|---|---|---|---|
| **Email** (Buttondown) | `buttondown.md` | subject, description, body | membership **CTA** (Liquid, audience-aware); tinylytics pixel | POST/PATCH Buttondown API | `REQUIRED_FOR_BUTTONDOWN` = haiku + metadata + intro + cover, **and** subject + description set |
| **Website** (archive) | `archive.md` | subject, description, body | YAML front matter; no CTA, no pixel | atomic GitHub commit to `data/issues/{N}/` | Email shipped (so `absolute_url` is stamped) |
| **Podcast** (audio) | `transcript/*.txt` + MP3 | body | per-block transcript (uniquely shaped); a **CTA audio slot — not yet built** | per-block TTS + concat + S3 upload + manifest | transcripts present (always, post-Build) |

## The shared envelope

*Subject* (one line, all channels) and *description* (comma-separated topic line; email preview +
website front-matter) are set **here**, not in Build. They live in `metadata.json` alongside the
deterministic `number`/`slug`/`image`/`publish_date` and the publish-stamped
`buttondown_id`/`absolute_url`.

## Gates

- **Entry:** `mark built`. On entry the ship flow **auto-requests the CTA from Patty** (see
  [`../programs/membership.md`](../programs/membership.md)) so a framing is waiting — Jamie only
  *picks* it, never triggers it.
- **Exit:** `put-to-bed` — files the issue into the `issues` table, closes the window
  (`is_active = 0`). The issue is now *published* and becomes the [Share](share.md) target.

The **Publish card** (`#editorial`) is the live surface: the shared envelope + CTA pick, then the
per-channel rows with gated 🚀 buttons (a destination's button stays disabled until its gate
passes), and each leg's outcome reported back on the card.
