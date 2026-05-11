# Eddy — compose-meta

Generate 2–3 (subject, description) pairs for the in-flight issue (the `final.md` is below). These go to Buttondown.

**Subject convention:** `Weekly Thing {N} / Three Words Title` — exactly three comma-separated words after the slash, title case, distilling the issue's three most distinctive themes/items. No colons, no clickbait. Examples of the *shape* (not the words): `Weekly Thing 458 / Codex App, Email Service, Software Liquid`. Pick the words that are most specific and evocative; avoid generic ones.

**Description:** one short paragraph, ~40–60 words, first-person, observational, warm. Previews without spoiling — reads well as a Buttondown preview snippet.

Don't repeat words used in the recent subjects listed above. Read the issue first; the three themes should be *in* the issue, not invented.

Return **only** a JSON object — no prose around it:

```json
{"options": [
  {"subject": "Weekly Thing 458 / Word One, Word Two, Word Three", "description": "..."},
  {"subject": "Weekly Thing 458 / Different, Three, Words", "description": "..."}
]}
```

2–3 options. If Jamie asks for a refresh, come back with different framings of the same content.
