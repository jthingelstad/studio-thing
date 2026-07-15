# Publish

Publish packages and ships the current newsletter issue.

**Owner:** Jamie, with Eddy assisting on issue envelope and editorial notes.
**Surface:** Studio web app.

The same DB-backed issue body renders into channel-specific artifacts at ship
time. Nothing in Publish should create a second source of truth.

## Channel Matrix

| Channel | Render Artifact | Ship Mechanic | Gate |
|---|---|---|---|
| Email | `buttondown.md` | Create or update a Buttondown draft | subject, description, haiku, intro, cover, and required sections present |
| Website | `archive.md` plus metadata | Commit generated issue files downstream | Buttondown publish record exists |
| Audio | transcript + MP3 assets | TTS, concatenate, upload, update manifest | transcript/audio inputs present |

Audio production remains part of the newsletter issue path. Podcast production
as a separate product is out of scope.

## Eddy Work In Scope

- `compose-envelope` creates or refreshes the issue subject and description.
- `compose-haiku` creates haiku options when Jamie wants them.
- `compose-echoes` writes the Echoes note from the archive context.
- Eddy review remains suggestions-only. Jamie writes every word.

CTA, membership-program copy, syndication, campaign tracking, blog posts,
podcast episodes, projects, seeds, and gardening are not active Studio work.

## Exit

When the issue has shipped, Put to bed files it into the archive tables, closes
the active issue window, and leaves Studio ready for the next newsletter issue.
