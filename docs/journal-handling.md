# Journal handling

How the `## Journal` section is built from micro.blog. The Journal is the issue's day-in-the-life
texture — it often carries an issue on its own. Formatting basics are in
[`sections.md`](sections.md); this is the detail.

> Draft — refine in your voice.

## Source + ordering

- Pulled from **micro.blog** for the issue's 7-day window (Micropub `q=source`; `MICROBLOG_API_KEY`
  required — no fallback). Posts arrive as the native markdown Jamie wrote.
- **Time-ordered by the sync, never reordered.** Eddy's reorder pass is *ordering-only* for
  Notable/Briefly and does **not** touch or cut Journal. If an issue feels too long, trim
  **upstream** — delete the post on micro.blog before the next draft refresh.

## Two entry shapes

- **Status update** (no title): `[Weekday @ H:MM AM/PM](url)` + content.
- **Titled post** (elevated): `### [Title](url)  \n{Weekday @ H:MM AM/PM}` + content.

The label is **weekday + 12-hour clock, no date** — every entry sits inside the same seven-day
window, so the weekday already identifies it.

## Photos

- Images on Jamie's upload hosts are **rehosted** into `weekly-thing/{N}/journal/`, resized
  (≤600px long side), and emitted as native `<img src … alt … />` tags — each on its own paragraph
  so gallery images don't run together.
- Empty alts are filled by a vision model (cached per content-addressed filename). Alt quality is
  one of the things the editorial review flags.

## Featured

A journal post in micro.blog's **`Featured` category** gets elevated to its own standalone H2
section in the issue — see [`featured-posts.md`](featured-posts.md).
