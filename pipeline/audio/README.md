# Weekly Thing Audio Pipeline

This stage runs after `pipeline/content/content.py build` and consumes the
canonical archive markdown in `site/archive/`. It does not read raw Buttondown
bodies and does not depend on the Librarian service.

## Two-stage rendering

Each issue's audio is built in two stages so that bumper/normalization changes
don't trigger another paid round of TTS.

1. **Body** — TTS the script chunks and concat them into `body.mp3`. Uploaded
   to `s3://files.thingelstad.com/weekly-thing/<issue>/body-<issue>.mp3`.
2. **Final** — concat `intro.mp3 + body.mp3 + outro.mp3`, run two-pass
   `loudnorm` (Apple Podcasts target: I=-16 LUFS, TP=-1.5 dBTP, LRA=11) plus
   an 80 Hz high-pass for low-end cleanup, and re-encode at 192k mono /
   44.1 kHz. Uploaded to
   `s3://files.thingelstad.com/weekly-thing/<issue>/weekly-thing-<issue>.mp3`.

When the body script and voice haven't changed, `audio.py build` only re-runs
stage 2 — fetching `body.mp3` from S3 if the local working tree no longer has
it. That makes bumper edits and `LOUDNORM_VERSION` bumps free.

## Bumpers

Intro and outro bumpers live in `data/audio/bumpers/intro.mp3` and
`data/audio/bumpers/outro.mp3` (tracked in git — they're tiny and committing
them means CI doesn't have to re-render them per build). Their text lives in
`pipeline/audio/bumpers.py`. The manifest tracks each bumper's
`hash`/`voice`/`generated_at` under the top-level `_bumpers` key so changes to
the text invalidate every issue's final MP3 (but not the body).

```bash
python pipeline/audio/audio.py bumpers build           # render any missing/changed bumper
python pipeline/audio/audio.py bumpers build --force   # re-render both bumpers
```

After updating bumper text, run `audio.py build --all` to reassemble. Issues
whose bodies are already in S3 will be reassembled with no TTS spend.

## Build commands

```bash
python pipeline/audio/audio.py build --latest
python pipeline/audio/audio.py build --issue 345
python pipeline/audio/audio.py build --all
python pipeline/audio/audio.py build --all --limit 50              # batch backfill
python pipeline/audio/audio.py build --all --reassemble-only       # no TTS, only stage 2
python pipeline/audio/audio.py build --issue 345 --dry-run
python pipeline/audio/audio.py build --issue 345 --force           # rebuild body + final
python pipeline/audio/audio.py status
python pipeline/audio/audio.py status --all
```

`audio.py build` decides per issue:

- Body fresh **and** final fresh → skip.
- Body fresh, final stale (bumper or `LOUDNORM_VERSION` changed) → reassemble
  only. No TTS.
- Body slot empty in S3 but the legacy published MP3 from the pre-bumper
  pipeline is still up there with a matching script hash → S3-copy it into the
  body slot, reassemble. No TTS. (`status` reports these as `promote`.)
- Body stale → render body, upload, reassemble. TTS billed.

`make audio` renders the latest issue. `make audio-issue ISSUE=345` renders a
specific issue.

## Artifacts

- `data/audio/manifest.json` — per-issue metadata plus the top-level
  `_bumpers` block.
- `data/audio/scripts/<issue>.txt` — the exact text sent to TTS for the body.
- `data/audio/bumpers/<name>.mp3` — committed intro/outro audio.
- `tmp/audio/<issue>/` — working directory (chunks, concat lists,
  `body.mp3`, `weekly-thing-<issue>.mp3`).
- `tmp/audio-script-<issue>.txt` — dry-run output.
- S3 keys:
  - `s3://files.thingelstad.com/weekly-thing/<issue>/body-<issue>.mp3` —
    bumper-less body audio (used to reassemble without TTS).
  - `s3://files.thingelstad.com/weekly-thing/<issue>/weekly-thing-<issue>.mp3` —
    the published MP3 with bumpers and loudnorm. This is what the on-page
    Listen button and the podcast feed both point at.

## Manifest invalidation knobs

- `synthesize.py:LOUDNORM_VERSION` — bump (e.g. `"v1"` → `"v2"`) to force every
  issue to reassemble with the current loudnorm/encoding settings. No TTS.
- `bumpers.py:INTRO_TEXT` / `OUTRO_TEXT` — edit, run `audio.py bumpers build`,
  then `audio.py build --all` to reassemble. Bumpers re-render once; bodies are
  reused.
- `synthesize.py:TTS_VOICE` — changing voice invalidates all body audio. Plan
  for the TTS spend before changing.

## Requirements

- `OPENAI_API_KEY` for OpenAI `tts-1-hd`.
- AWS credentials with S3 access to `files.thingelstad.com` and CloudFront
  invalidation rights on `E3AEA6KRKI2B7E`.
- `ffmpeg` and `ffprobe` available on `PATH`.

The voice is configured in `synthesize.py` as `echo` and persisted in the
manifest as `openai-tts-1-hd:echo`.
