"""OpenAI TTS synthesis and MP3 assembly."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from dotenv import load_dotenv

REPO = Path(__file__).resolve().parents[2]
TMP_DIR = REPO / "tmp" / "audio"

TTS_MODEL = "tts-1-hd"
TTS_VOICE = "echo"
AUDIO_VOICE = f"openai-{TTS_MODEL}:{TTS_VOICE}"
MAX_CHARS = 3800

# Bump to invalidate every published MP3 and force reassembly without re-running TTS.
# v2: added ID3v2.3 tags + embedded cover art.
# v3: cover art center-cropped to square (was 1200×675 landscape).
LOUDNORM_VERSION = "v3"
LOUDNORM_TARGET_I = -16.0
LOUDNORM_TARGET_TP = -1.5
LOUDNORM_TARGET_LRA = 11.0
HIGHPASS_HZ = 80
FINAL_BITRATE = "192k"
FINAL_SAMPLE_RATE = 44100
FINAL_CHANNELS = 1

ID3_ARTIST = "Jamie Thingelstad"
ID3_ALBUM = "The Weekly Thing"
ID3_ALBUM_ARTIST = "Jamie Thingelstad"
ID3_GENRE = "Technology"
ID3_COMMENT = "AI-generated audio version of The Weekly Thing newsletter. weekly.thingelstad.com"

load_dotenv(REPO / ".env")


def ensure_audio_tools() -> None:
    missing = [name for name in ("ffmpeg", "ffprobe") if not shutil.which(name)]
    if missing:
        names = ", ".join(missing)
        raise RuntimeError(f"Missing required audio tool(s): {names}. Install ffmpeg before building audio.")


def chunk_text(text: str, max_chars: int = MAX_CHARS) -> list[str]:
    paragraphs = [paragraph.strip() for paragraph in re.split(r"\n{2,}", text) if paragraph.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            chunks.append(current)
            current = ""
        if len(paragraph) <= max_chars:
            current = paragraph
            continue
        sentences = split_sentences(paragraph)
        for sentence in sentences:
            candidate = f"{current} {sentence}".strip() if current else sentence
            if len(candidate) <= max_chars:
                current = candidate
                continue
            if current:
                chunks.append(current)
                current = ""
            if len(sentence) > max_chars:
                raise RuntimeError(
                    "Audio script contains a sentence longer than the TTS request limit; "
                    "adjust the script transform before synthesizing."
                )
            current = sentence
    if current:
        chunks.append(current)
    return chunks


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [part.strip() for part in parts if part.strip()]


def chunk_plan(text: str) -> list[dict[str, int]]:
    return [
        {"index": index + 1, "characters": len(chunk)}
        for index, chunk in enumerate(chunk_text(text))
    ]


def _openai_client():
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("The openai package is required for audio synthesis.") from exc
    return OpenAI(timeout=60.0, max_retries=1)


def synthesize_text_to_mp3(text: str, output_path: Path, label: str = "audio") -> Path:
    """TTS the given text, concat into a single MP3 at output_path. No normalization.

    Intermediate chunk MP3s and the concat list live in tmp/ keyed by the output
    file stem, so we never pollute committed-data directories with workfiles."""
    ensure_audio_tools()
    chunks = chunk_text(text)
    workdir = TMP_DIR / "synthesize" / output_path.stem
    workdir.mkdir(parents=True, exist_ok=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    client = _openai_client()
    chunk_paths: list[Path] = []
    for index, chunk in enumerate(chunks):
        print(f"{label}: synthesizing chunk {index + 1}/{len(chunks)} ({len(chunk)} chars)")
        chunk_path = workdir / f"chunk-{index:03d}.mp3"
        response = client.audio.speech.create(
            model=TTS_MODEL,
            voice=TTS_VOICE,
            input=chunk,
            response_format="mp3",
        )
        chunk_path.write_bytes(response.content)
        chunk_paths.append(chunk_path)

    list_path = workdir / "concat.txt"
    list_path.write_text(
        "".join(f"file '{path.resolve()}'\n" for path in chunk_paths),
        encoding="utf-8",
    )
    _run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_path), "-c", "copy", str(output_path)],
        cwd=REPO,
    )
    return output_path


def render_body(issue: str, text: str) -> tuple[Path, int]:
    """Render an issue body to a single MP3 (no bumpers, no normalization)."""
    workdir = TMP_DIR / str(issue)
    body_path = workdir / "body.mp3"
    synthesize_text_to_mp3(text, body_path, label=f"Issue #{issue}")
    return body_path, probe_duration_seconds(body_path)


def assemble_final(
    issue: str,
    intro_path: Path,
    body_path: Path,
    outro_path: Path,
    metadata: dict[str, str],
    cover_path: Path,
    output_path: Path | None = None,
) -> tuple[Path, int]:
    """Concat intro+body+outro, apply loudnorm, and embed ID3 tags + cover art."""
    ensure_audio_tools()
    workdir = TMP_DIR / str(issue)
    workdir.mkdir(parents=True, exist_ok=True)
    if output_path is None:
        output_path = workdir / f"weekly-thing-{issue}.mp3"

    concat_path = workdir / "final-concat.txt"
    raw_combined = workdir / "raw-combined.mp3"
    concat_path.write_text(
        "".join(f"file '{path.resolve()}'\n" for path in (intro_path, body_path, outro_path)),
        encoding="utf-8",
    )
    _run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_path), "-c", "copy", str(raw_combined)],
        cwd=REPO,
    )

    measured = _loudnorm_measure(raw_combined)
    filter_chain = (
        f"highpass=f={HIGHPASS_HZ},"
        f"loudnorm=I={LOUDNORM_TARGET_I}:TP={LOUDNORM_TARGET_TP}:LRA={LOUDNORM_TARGET_LRA}"
        f":measured_I={measured['input_i']}"
        f":measured_TP={measured['input_tp']}"
        f":measured_LRA={measured['input_lra']}"
        f":measured_thresh={measured['input_thresh']}"
        f":offset={measured['target_offset']}"
        f":linear=true:print_format=summary"
    )

    cmd: list[str] = [
        "ffmpeg",
        "-y",
        "-i", str(raw_combined),
        "-i", str(cover_path),
        "-map", "0:a",
        "-map", "1:v",
        "-c:v", "copy",
        "-disposition:v", "attached_pic",
        "-af", filter_chain,
        "-ar", str(FINAL_SAMPLE_RATE),
        "-ac", str(FINAL_CHANNELS),
        "-c:a", "libmp3lame",
        "-b:a", FINAL_BITRATE,
        "-write_xing", "1",
        "-id3v2_version", "3",
    ]
    for key, value in metadata.items():
        cmd.extend(["-metadata", f"{key}={value}"])
    cmd.extend([
        "-metadata:s:v", "title=Album cover",
        "-metadata:s:v", "comment=Cover (front)",
        str(output_path),
    ])
    _run(cmd, cwd=REPO)
    return output_path, probe_duration_seconds(output_path)


def build_id3_metadata(number: str, frontmatter: dict) -> dict[str, str]:
    """Build the per-issue ID3 tag dict from archive frontmatter."""
    subject = (frontmatter.get("subject") or "").strip()
    if " / " in subject:
        topical = subject.rsplit(" / ", 1)[1].strip()
        title = f"{number}: {topical}"
    else:
        title = subject or f"Weekly Thing {number}"

    publish_date = str(frontmatter.get("publish_date") or "")
    date = publish_date[:10] if len(publish_date) >= 10 else publish_date

    return {
        "title": title,
        "artist": ID3_ARTIST,
        "album": ID3_ALBUM,
        "album_artist": ID3_ALBUM_ARTIST,
        "date": date,
        "genre": ID3_GENRE,
        "track": str(number),
        "comment": ID3_COMMENT,
    }


def _ffmpeg_concat_copy(input_paths: list[Path], output_path: Path) -> None:
    list_path = output_path.with_suffix(output_path.suffix + ".concat.txt")
    list_path.write_text(
        "".join(f"file '{path.resolve()}'\n" for path in input_paths),
        encoding="utf-8",
    )
    _run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_path), "-c", "copy", str(output_path)],
        cwd=REPO,
    )


def _loudnorm_measure(input_path: Path) -> dict[str, str]:
    """Run pass-1 loudnorm in measurement mode and return parsed values."""
    result = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-i",
            str(input_path),
            "-af",
            (
                f"highpass=f={HIGHPASS_HZ},"
                f"loudnorm=I={LOUDNORM_TARGET_I}:TP={LOUDNORM_TARGET_TP}:LRA={LOUDNORM_TARGET_LRA}"
                ":print_format=json"
            ),
            "-f",
            "null",
            "-",
        ],
        cwd=REPO,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    # ffmpeg prints the JSON block on stderr.
    stderr = result.stderr
    start = stderr.rfind("{")
    end = stderr.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise RuntimeError("Could not parse loudnorm measurement output from ffmpeg")
    payload = json.loads(stderr[start : end + 1])
    required = ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")
    missing = [key for key in required if key not in payload]
    if missing:
        raise RuntimeError(f"loudnorm output missing fields: {', '.join(missing)}")
    return {key: str(payload[key]) for key in required}


def _run(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=cwd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def probe_duration_seconds(path: Path) -> int:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ],
        cwd=REPO,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    duration = float(json.loads(result.stdout)["format"]["duration"])
    return round(duration)
