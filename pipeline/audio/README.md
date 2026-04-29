# Weekly Thing Audio Pipeline

This stage runs after `pipeline/content/content.py build` and consumes the
canonical archive markdown in `site/archive/`. It does not read raw Buttondown
bodies and does not depend on the Librarian service.

## Commands

```bash
python pipeline/audio/audio.py build --latest
python pipeline/audio/audio.py build --issue 345
python pipeline/audio/audio.py build --all
python pipeline/audio/audio.py build --issue 345 --dry-run
python pipeline/audio/audio.py status
```

`make audio` renders the latest issue. `make audio-issue ISSUE=345` renders a
specific issue.

## Artifacts

- `data/audio/manifest.json` stores per-issue audio metadata.
- `data/audio/scripts/<issue>.txt` stores the exact final text sent to TTS.
- `tmp/audio-script-<issue>.txt` is written by dry runs only.
- MP3s are uploaded to
  `s3://files.thingelstad.com/weekly-thing/<issue>/weekly-thing-<issue>.mp3`.

## Requirements

- `OPENAI_API_KEY` for OpenAI `tts-1-hd`.
- AWS credentials with S3 access to `files.thingelstad.com`.
- `ffmpeg` and `ffprobe` available on `PATH`.

The voice is configured in `synthesize.py` as `echo` and persisted in the
manifest as `openai-tts-1-hd:echo`.
