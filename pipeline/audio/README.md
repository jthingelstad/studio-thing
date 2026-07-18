# Weekly Thing audio pipeline

Turns each archive issue into a podcast-quality MP3 with intro/outro bumpers, ready to drop into the website's audio player and the podcast RSS feed.

> Operational deep-dive (freshness gates, manifest invalidation knobs, backfill workflow) lives in [`CLAUDE.md`](CLAUDE.md). This README is the orientation.

## What it does

Three stages, each independently re-runnable:

1. **`scripts build`** — deterministic markdown → script transform. Reads `apps/site/archive/{N}.md`, writes `data/audio/scripts/<N>.txt`. Cheap, fast, no API calls. The committed `.txt` is the source of truth for the next stage.
2. **`scripts validate`** — static checks (markdown leakage, template tags, oversized chunks). Writes `data/audio/script_status.json`. Free.
3. **`audio build`** — TTS the script chunks via OpenAI `tts-1-hd`, concat into a body MP3, then concat with intro/outro bumpers + run loudnorm + re-encode. Uploads body + final MP3 to `s3://files.thingelstad.com/weekly-thing/<N>/`. **Only this stage costs money.**

The audio pipeline runs after `pipeline/content/content.py build` (which generates `apps/site/archive/`) and is independent of the Librarian Lambda. workshop_bot's `render-audio` job wraps it for the ship sequence.

## Quick start

```bash
# Render audio for the latest issue
make audio

# Render a specific issue
make audio-issue ISSUE=345

# Common CLI shapes
uv run --locked python pipeline/audio/audio.py build --latest
uv run --locked python pipeline/audio/audio.py build --issue 345
uv run --locked python pipeline/audio/audio.py build --all
uv run --locked python pipeline/audio/audio.py build --all --reassemble-only   # no TTS, only stage 2
uv run --locked python pipeline/audio/audio.py status                          # what's stale
uv run --locked python pipeline/audio/audio.py status --all
```

For backfilling many issues at once, see the workflow in [`CLAUDE.md`](CLAUDE.md).

## Requirements

- `OPENAI_API_KEY` for the TTS calls
- AWS credentials with S3 write to `files.thingelstad.com` + CloudFront invalidation rights on `E3AEA6KRKI2B7E`
- `ffmpeg` + `ffprobe` on PATH

## Output

- **Committed**: `data/audio/scripts/<N>.txt`, `data/audio/script_status.json`, `data/audio/manifest.json`, `data/audio/bumpers/{intro,outro}.mp3`
- **S3**: `s3://files.thingelstad.com/weekly-thing/<N>/body-<N>.mp3` (bumper-less, used to reassemble without TTS) and `s3://files.thingelstad.com/weekly-thing/<N>/weekly-thing-<N>.mp3` (the published MP3)

The on-page Listen button and the podcast feed both point at `weekly-thing-<N>.mp3`.

## Related reading

- [`CLAUDE.md`](CLAUDE.md) — operational memory
- [`../content/CLAUDE.md`](../content/CLAUDE.md) — the build that runs before this and feeds it
- [`../../apps/workshop_bot/`](../../apps/workshop_bot/) — wraps `audio.build_issue` for the ship sequence
