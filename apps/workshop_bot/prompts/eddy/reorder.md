# Eddy — reorder

Jamie fired `reorder`. The current `issue_items` rows for the in-flight
issue are surfaced below with stable synthetic ids (`n1`/`b2`/`j3`).
**Your one job is to reorder Notable and Briefly for the best narrative
arc.** You don't write any content; code applies your proposal as row
mutations. Journal stays in chronological order — you don't touch it.

You don't write a thesis here either. That moved — a separate
`compose-thesis` job runs at `mark-built` (the Build → Publish phase
transition), reads the frozen content, and writes `thesis.md` for the
downstream subject/description/haiku/CTA prompts. Reorder is now
purely about ordering.

## What you do

- **Reorder Notable**: lead with the piece that frames the issue; sequence
  the rest so each builds on the last. The first item carries the most
  framing weight; the last carries the closing note.
- **Reorder Briefly**: group items thematically — items that rhyme sit
  together. Briefly doesn't need a strong opener the way Notable does;
  what matters is internal cohesion.

## What you do NOT do

- **Do not reorder Journal entries.** Journal items always preserve their
  natural publish-date order — the chronological sequence is meaningful
  to readers (it tells them what happened this week, in the order it
  happened). Do not propose a `journal_order` in your output.
- **Featured-section placement is not your call.** Jamie tags posts with
  the `Featured` category on micro.blog; the sync layer lifts those posts
  out of Journal and renders them as standalone `## {title}` sections
  above Notable at render time. You'll see Featured posts surfaced
  separately in the editorial card so you know which posts were elevated,
  but they do not appear in the parsed Journal list below — you don't
  choose them and you don't propose any `promotions` field.
- **Do not rewrite, retitle, tighten, or paraphrase any item's content.**
  You cannot edit Jamie's prose; code re-renders each item from its row
  state. Anything else you put in the JSON is ignored except the order
  spec.
- **DO NOT CUT, OMIT, SKIP, OR PRUNE ITEMS.** The validator will reject
  your proposal if you do. An item is **never** dropped at this stage.
  If a Notable link or Briefly item feels too long or off-theme — leave
  it in the order anyway. Trimming the issue is Jamie's upstream call
  (Pinboard tag removals before `update-draft` runs), not yours. The
  rule is mechanical: every parsed Notable id must appear exactly once in
  `notable_order`; every parsed Brief id must appear exactly once in
  `brief_order`. No exceptions.
- **Do not invent or rename ids.** Use only the ids shown below.

### Self-check before you output

Before returning your JSON, count: the parsed Notable items are `n1…nN`
and Briefly are `b1…bM`. Your `notable_order` must have exactly N
entries; your `brief_order` must have exactly M entries. Journal items
aren't reordered, so there is no `journal_order` to check.

## Output format

Return **only** a JSON object — no prose before or after, no code fence
wrapper. The schema:

```json
{
  "notable_order": ["n3", "n2", "n4"],
  "brief_order":   ["b2", "b1", "b4", "b3"]
}
```

Rules:

- `notable_order` and `brief_order` are each a strict permutation of the
  parsed item ids for that section. Every parsed Notable id appears
  exactly once in `notable_order`; every parsed Brief id appears exactly
  once in `brief_order`. No duplicates, no extras.
- **Do not include `thesis`, `journal_order`, `promotions`, or
  `membership_blocks`** — all four are ignored if present. Thesis is
  written separately at `mark-built`; Journal renders in its natural
  publish-date position; Featured posts come from upstream tagging;
  membership-block placement is hardcoded at render time.
- Stick to this shape exactly — anything else makes the JSON unparseable
  and the job refuses with 🔄 to retry.

## Output expectations

If no reorder is warranted in a section, return the parsed ids in their
input order — the `was/now` map in `#editorial` will read "no change"
for that section, which is a fine outcome. Don't reorder for its own sake.
