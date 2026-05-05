# Weekly Thing Audio Pipeline

This stage runs after `pipeline/content/content.py build` and consumes the
canonical archive markdown in `apps/site/archive/`. It does not read raw Buttondown
bodies and does not depend on the Librarian service.

## Three stages

```
scripts build       → render data/audio/scripts/<N>.txt (committed)
scripts validate    → static checks; writes data/audio/script_status.json
audio build         → reads committed scripts; refuses --all on validation errors
```

`scripts build` produces the script that will be spoken. The committed file is
the source of truth — `audio build` reads it from disk rather than regenerating
from `script.py` on every run, so changes to the script transform don't
silently invalidate every issue's audio.

`scripts validate` runs static checks (no LLM, no API calls) for transformation
residue (markdown leakage, template tags, bare URLs, HTML tags, …) and
structural anomalies (chunks too long for the TTS limit, empty sections, etc.).
Findings are written to `data/audio/script_status.json` with severity
`error` or `warning`. Errors block `audio build --all`; warnings always print.

`audio build` is gated by validation status:

- `--all` hard-fails up front if any selected issue has unresolved errors,
  missing scripts, or stale validation. Pass `--allow-unvalidated` to override.
- `--issue N` / `--latest` warn but proceed.

If `scripts validate` flags an issue, the fix goes in `script.py`. Hand-editing
generated scripts is not supported — `scripts build` would overwrite them.

```bash
python pipeline/audio/audio.py scripts build --all
python pipeline/audio/audio.py scripts build --issue 100 --latest    # also accepted: --issue or --latest
python pipeline/audio/audio.py scripts validate --all                # exits non-zero if any errors
python pipeline/audio/audio.py scripts validate --issue 345
```

## Two-stage audio rendering

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

## Backfill workflow

Backfilling 300+ archived issues uses the three-stage flow to keep TTS spend
deliberate:

```bash
# 1. Generate every script. Cheap, fast, deterministic.
python pipeline/audio/audio.py scripts build --all

# 2. Validate. Free.
python pipeline/audio/audio.py scripts validate --all
# ... finds N errors across M issues

# 3. Triage:
#    - Common pattern (e.g. emoji-suffixed MailChimp section labels)?
#      Patch script.py, repeat 1+2.
#    - One-off historical format? Still patch script.py with a narrow
#      special-case — no hand-editing of generated scripts.

# 4. Once validate is clean for the issues you want, commit script.py
#    + data/audio/scripts/*.txt + data/audio/script_status.json.

# 5. TTS in batches:
python pipeline/audio/audio.py build --all --limit 50
```

## Artifacts

- `data/audio/manifest.json` — per-issue audio metadata plus the top-level
  `_bumpers` block.
- `data/audio/scripts/<issue>.txt` — the exact text sent to TTS for the body
  (committed; source of truth for `audio build`).
- `data/audio/script_status.json` — validation results per issue, schema
  version, and validator version.
- `data/audio/bumpers/<name>.mp3` — committed intro/outro audio.
- `tmp/audio/<issue>/` — working directory (chunks, concat lists,
  `body.mp3`, `weekly-thing-<issue>.mp3`).
- `tmp/audio/synthesize/<name>/` — per-render TTS workfiles for short clips
  (bumpers, ad-hoc one-shots).
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
- `script_validate.py:VALIDATOR_VERSION` — bump to make `scripts validate`
  refresh every issue's record on the next run, even when the script content
  hasn't changed.
- `script.py` — any change to the transform produces different scripts on the
  next `scripts build`. Diffs land in `data/audio/scripts/*.txt` for review.
  Once committed, the next `audio build` will detect the script-hash
  mismatch and re-render the affected bodies.

## Requirements

- `OPENAI_API_KEY` for OpenAI `tts-1-hd`.
- AWS credentials with S3 access to `files.thingelstad.com` and CloudFront
  invalidation rights on `E3AEA6KRKI2B7E`.
- `ffmpeg` and `ffprobe` available on `PATH`.

The voice is configured in `synthesize.py` as `echo` and persisted in the
manifest as `openai-tts-1-hd:echo`.
