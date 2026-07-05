# Eddy — compose the email envelope (subject + description + haiku)

Jamie just marked WT<NUM> built. The issue's content is frozen and now
in **Publish**. Compose the shipping **envelope** for it in one pass:
**5 subject options**, **1 meta description**, and **3 haiku options**.

You're seeing the whole assembled draft below (intro, sections in their
final order, outro). Read it as one issue, not a list — the throughline
you find is the anchor for all three deliverables, so the subject, the
description, and the haiku read as expressions of the same idea. Compose
them together on purpose.

Return **only** a single JSON object, no prose around it:

```json
{
  "subjects": ["WT<NUM> — Option One", "WT<NUM> — Option Two", "WT<NUM> — Option Three", "WT<NUM> — Option Four", "WT<NUM> — Option Five"],
  "description": "comma, separated, topics, lifted, from, the, body.",
  "haikus": ["line one\nline two\nline three", "another\nhaiku\nhere", "a third\noption\nhere"]
}
```

`subjects` is exactly 5 strings, `description` is one string, `haikus`
is exactly 3 strings (each haiku's three lines joined by `\n`).

---

## `subjects` — 5 email subject options

The canonical format is `WT<NUM> — <Theme>` with an em-dash and a 3–6-word
title-case theme phrase.

- The prefix `WT<NUM> — ` is always identical across all 5 options. Never
  use `/` or any other separator after the issue number.
- Capture the intellectual center of gravity of the issue, not just the
  headline of one link. Favor concrete nouns and specific ideas.
- Match Jamie's voice: thoughtful, calm, direct, no hype, no clickbait,
  no exclamation points, no emoji, no buzzwords. Use title case.
- Work when truncated to 40 characters on mobile (aim for the full line
  under 50 characters).
- Aim for **variety** across the 5 — different thematic angles (the essay
  vs. a Notable thread vs. a connective idea), different framings
  (declarative vs. concrete noun phrase vs. named concept). At least one
  option should be the comma-separated token fallback style (3
  distinctive, surprising nouns from the issue).
- If the issue is a special issue (travel, anniversary, sponsored
  nonprofit reveal, family content, guest-heavy, somber/single-theme),
  weight the options toward the special-topic framing:
  `WT<NUM> — <Special Topic>` (e.g. "Ireland", "Nine Year Anniversary").
  For somber or crisis-centered issues, stay plain and literal.

Voice guardrails — do NOT produce:
- Marketing phrases ("Don't miss", "You need to read", "The secret to")
- Question-mark subjects ("Is Scrum Dead?")
- Vague abstractions ("Thoughts on the Week", "This Week in Tech")
- All-caps words (except established acronyms like AI, MCP, RSS)
- Subtitles or colons inside the theme phrase

## `description` — the meta description

A single line — a comma-separated list of concrete topics lifted from
the body, ending in a single period. It appears in social card previews
(OG metadata), the issue page header, and the issue index in llms.txt.

- Target 130–150 characters, absolute max 160. Typically 5–8 items.
- Include named things (products, projects, people, places, companies,
  technologies, events) and concrete concepts that anchor a Notable or
  Featured section (e.g. "agentic coding", "death of Scrum"). Lift from
  Notable, Featured, and Briefly — the editorial core.
- Exclude/de-prioritize Journal/micropost content (family, daily life,
  photos) unless it's the dominant content, membership/housekeeping
  notes, and generic words ("technology", "AI", "the web") without a
  specific anchor.
- Lead with the strongest or most distinctive item — usually the
  Featured essay, the central theme, or the most unusual named thing.
  Order the rest roughly by prominence.
- Use words/short phrases lifted from the body; light rewording for
  compactness is allowed ("Death of Scrum" not "The Death of Scrum — An
  Interactive Essay") but don't invent topics not in the body.
- No sentences, no verbs or connecting phrases, no intro/prefix/emoji/
  hashtags/quotation marks/brackets. Title case for proper nouns,
  lowercase for common nouns and concepts. End with a single period.

## `haikus` — 3 haiku options

The haiku closes the issue.

- Read the issue. Find the dominant theme / tension / one-liner — the
  thing the week was *about* — and let the haiku echo it.
- Each is a complete haiku. Jamie's convention is haiku-shaped, not
  strictly 5-7-5 — three short lines, the third turning or landing.
- Plain, observational, mildly wry — the Weekly Thing voice. Concrete
  nouns from the actual issue body, no abstractions like "the future"
  or "technology". Not precious, not greeting-card.
- The dash (`—`) at end-of-line-two is a common Weekly Thing pattern but
  not required. Don't repeat a haiku Jamie has used in a recent issue.

Three real archive examples (shape, voice, the third-line landing):

```
Hand-drawn QR dreams,
Redis arrays tell stories —
Dads learn to listen
```
```
Coffee stirs the gut
While AI dreams in the night
Both keep us awake
```
```
Wiki of my own,
Clouds of email drift in play —
Agents sip the sky.
```

---

Few-shot subject example (issue content summarized, then ideal output):

Issue: Death of Scrum essay, agentic coding, AI company learning,
workplace productivity, watchOS maps, Redis arrays, hand-drawn QR codes,
FilamentHound, DO_NOT_TRACK.
Subjects:
  WT347 — The Death of Scrum
  WT347 — Value Over Token Consumption
  WT347 — How Companies Learn With AI
  WT347 — Agentic Coding Is a Trap
  WT347 — Scrum, FilamentHound, DO_NOT_TRACK
Description: Claude personal guidance, Redis array type, watchOS maps, AI company learning, agentic coding, workplace productivity, Death of Scrum.

---

The assembled draft for WT<NUM>:

<<<ISSUE_TEXT>>>
