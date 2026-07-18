# pipeline/audio/ — project memory

Operational notes for the audio pipeline. Human-facing overview (what it is + quick start) is in [`README.md`](README.md). This file is the deep-dive on freshness gates, invalidation knobs, and the backfill workflow.

## Three stages

```
scripts build       → render data/audio/scripts/<N>.txt (committed)
scripts validate    → static checks; writes data/audio/script_status.json
audio build         → reads committed scripts; refuses --all on validation errors
```

`scripts build` produces the script that will be spoken. The committed file is the source of truth — `audio build` reads from disk rather than regenerating from the `script/` package on every run, so changes to the script transform don't silently invalidate every issue's audio.

`scripts validate` runs static checks (no LLM, no API calls) for transformation residue (markdown leakage, template tags, bare URLs, HTML tags, …) and structural anomalies (chunks too long for the TTS limit, empty sections, etc.). Findings land in `data/audio/script_status.json` with severity `error` or `warning`. Errors block `audio build --all`; warnings always print.

`audio build` is gated by validation status:

- `--all` hard-fails up front if any selected issue has unresolved errors, missing scripts, or stale validation. Pass `--allow-unvalidated` to override.
- `--issue N` / `--latest` warn but proceed.

**Fix scripts in `script.py`, not by hand.** `scripts build` would overwrite hand-edits — no recovery.

## Two-stage audio rendering

Each issue's audio is built in two stages so bumper/normalization changes don't trigger another paid round of TTS.

1. **Body** — TTS the script chunks and concat into `body.mp3`. Uploaded to `s3://files.thingelstad.com/weekly-thing/<N>/body-<N>.mp3`.
2. **Final** — concat `intro.mp3 + body.mp3 + outro.mp3`, run two-pass `loudnorm` (Apple Podcasts target: I=-16 LUFS, TP=-1.5 dBTP, LRA=11), 80 Hz high-pass for low-end cleanup, re-encode at 192k mono / 44.1 kHz. Uploaded to `s3://files.thingelstad.com/weekly-thing/<N>/weekly-thing-<N>.mp3`.

When the body script + voice haven't changed, `audio.py build` only re-runs stage 2 — fetching `body.mp3` from S3 if the local working tree no longer has it. That makes bumper edits and `LOUDNORM_VERSION` bumps **free**.

## Freshness decisions

`audio.py build` decides per issue:

- Body fresh **and** final fresh → skip.
- Body fresh, final stale (bumper or `LOUDNORM_VERSION` changed) → reassemble only. No TTS.
- Body slot empty in S3 but the legacy pre-bumper MP3 is still up there with a matching script hash → S3-copy it into the body slot, reassemble. No TTS. (`status` reports these as `promote`.)
- Body stale → render body, upload, reassemble. **TTS billed.**

## Bumpers

Intro and outro bumpers live in `data/audio/bumpers/intro.mp3` and `data/audio/bumpers/outro.mp3` (committed — they're tiny, and committing means CI doesn't re-render them per build). Text lives in `pipeline/audio/bumpers.py`. The manifest tracks each bumper's `hash` / `voice` / `generated_at` under the top-level `_bumpers` key, so changes to the text invalidate every issue's **final** MP3 (but not the body).

```bash
uv run --locked python pipeline/audio/audio.py bumpers build           # render any missing/changed bumper
uv run --locked python pipeline/audio/audio.py bumpers build --force   # re-render both
```

After updating bumper text, run `audio.py build --all` to reassemble. Issues whose bodies are already in S3 reassemble with no TTS spend.

## Manifest invalidation knobs

Bump these deliberately — each has a different cost shape.

| Knob | What invalidates | Cost |
|---|---|---|
| `synthesize.py:LOUDNORM_VERSION` (`"v1"` → `"v2"`) | All final MP3s (reassemble) | Free (no TTS) |
| `bumpers.py:INTRO_TEXT` / `OUTRO_TEXT` | All final MP3s | Free after bumpers re-render |
| `synthesize.py:TTS_VOICE` | **All body audio** | Full TTS rebill |
| `script_validate.py:VALIDATOR_VERSION` | Refreshes validation records on next `scripts validate` | Free |
| `script.py` | Changed scripts on next `scripts build`; bodies re-render on next `audio build` | TTS for affected issues |

## Backfill workflow

Backfilling 300+ archived issues uses the three-stage flow to keep TTS spend deliberate:

```bash
# 1. Generate every script. Cheap, fast, deterministic.
uv run --locked python pipeline/audio/audio.py scripts build --all

# 2. Validate. Free.
uv run --locked python pipeline/audio/audio.py scripts validate --all
# ... finds N errors across M issues

# 3. Triage:
#    - Common pattern (e.g. emoji-suffixed MailChimp section labels)?
#      Patch script.py, repeat 1+2.
#    - One-off historical format? Patch script.py with a narrow
#      special-case — no hand-editing of generated scripts.

# 4. Once validate is clean, commit script.py + data/audio/scripts/*.txt + script_status.json.

# 5. TTS in batches:
uv run --locked python pipeline/audio/audio.py build --all --limit 50
```

## Artifacts

- `data/audio/manifest.json` — per-issue audio metadata + top-level `_bumpers` block. Read by `pipeline/content/content.py build` (audio fields go into archive front matter).
- `data/audio/scripts/<N>.txt` — exact text sent to TTS for the body (committed; source of truth for `audio build`).
- `data/audio/script_status.json` — validation results per issue, schema version, validator version.
- `data/audio/bumpers/<name>.mp3` — committed intro/outro audio.
- `tmp/audio/<N>/` — working directory (chunks, concat lists, `body.mp3`, `weekly-thing-<N>.mp3`).
- `tmp/audio/synthesize/<name>/` — per-render TTS workfiles for short clips (bumpers, ad-hoc).
- `tmp/audio-script-<N>.txt` — dry-run output.

S3 keys:
- `s3://files.thingelstad.com/weekly-thing/<N>/body-<N>.mp3` — bumper-less body (used to reassemble without TTS).
- `s3://files.thingelstad.com/weekly-thing/<N>/weekly-thing-<N>.mp3` — the published MP3. This is what the on-page Listen button and the podcast feed point at.

## CloudFront

After upload, the script auto-invalidates the affected paths on CloudFront `E3AEA6KRKI2B7E` (`files.thingelstad.com`). Best-effort: a failed invalidation logs and continues. (Memory: `reference_files_thingelstad_cdn.md`.)

## Requirements

- `OPENAI_API_KEY` for OpenAI `tts-1-hd`. Voice is `echo`, persisted in the manifest as `openai-tts-1-hd:echo`.
- AWS credentials with S3 access to `files.thingelstad.com` + CloudFront invalidation rights on `E3AEA6KRKI2B7E`.
- `ffmpeg` + `ffprobe` on PATH.

## Workshop_bot interaction

`workshop_bot`'s `render-audio` job wraps `pipeline.audio.audio.build_issue` and runs it as part of the `send-to-buttondown` ship sequence. It uses the per-block transcript path (`data/issues/{N}/transcript/NNN-*.txt`) for modern issues — the script transform produces per-block files so the TTS pipeline can render each as its own utterance with breath placement at editorial boundaries. Legacy issues (those with only `data/audio/scripts/<N>.txt`) go through the single-string path.

## Conventions

- **Don't hand-edit generated scripts.** Fix in `script.py` and re-run `scripts build`.
- **`scripts validate` errors block `audio build --all`.** Don't `--allow-unvalidated` your way past a class of issues; patch the validator or the transform.
- **Bumper edits are free.** Don't fear them. Tweak the intro/outro text and reassemble.
- **Voice changes are expensive.** Plan the TTS spend before changing `TTS_VOICE`.
