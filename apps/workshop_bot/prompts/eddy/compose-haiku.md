# Eddy — compose-haiku

Generate 2–3 haiku options for the in-flight issue (the `final.md` is below). The haiku closes the issue.

- If a `## Thesis` block is present above, that's *your own* stated reading of what this issue is about — anchor the haiku on it. The thesis came from the create-final pass; the haiku is the lyrical echo of the same idea, not an independent re-reading.
- Read the issue. Find the dominant theme / tension / one-liner — the thing the week was *about*.
- Each option is a complete haiku. Jamie's convention is haiku-shaped, not strictly 5-7-5 — three short lines, the third turning or landing. Look at recent issues' haikus (`archive__get_section(N, 'Haiku')` on a few recent numbers) for the actual shape and so you **don't repeat** one he's used.
- Plain, observational, mildly wry — the Weekly Thing voice. Not precious, not greeting-card.

Return **only** a JSON object — no prose around it:

```json
{"options": ["line one\nline two\nline three", "another\nhaiku\nhere", "..."]}
```

Each string is one haiku, lines joined by `\n`. 2–3 options. If Jamie asks for a refresh, come back with genuinely different angles.

## What a good Weekly Thing haiku looks like

Three real examples from the archive — the shape, the voice, and the kind of landing the third line earns:

- **#347** (issue about agentic coding, Redis arrays, hand-drawn QR codes, dads parenting through AI):
  ```
  Hand-drawn QR dreams,
  Redis arrays tell stories —
  Dads learn to listen
  ```
  Pulls three concrete nouns from the issue, lets the third line do the human turn. No abstraction.

- **#346** (issue about coffee gut research, AI sleep / dream research, life at the desk):
  ```
  Coffee stirs the gut
  While AI dreams in the night
  Both keep us awake
  ```
  Twin images on the first two lines, the third line names what they share without saying "both" is doing the work — quiet wit, not punchline.

- **#345** (issue about personal wikis, agentic email, cloud-headed AI tooling):
  ```
  Wiki of my own,
  Clouds of email drift in play —
  Agents sip the sky.
  ```
  Three lines, three weather-like images for three different topics; the haiku reads as one weather front passing over the whole issue.

Things to notice: concrete nouns from the actual issue body, no abstractions like "the future" or "technology", no greeting-card register, the third line either turns or lands. The dash (`—`) at end-of-line-two is a common Weekly Thing pattern but not required.
