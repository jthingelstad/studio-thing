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


# Lines that open a new semantic block in the generated audio script (section
# intros, per-link/journal cues, quote blocks, the closing). Chunk boundaries
# are only allowed between blocks — or, for a block too big for one TTS request,
# between its paragraphs/sentences — so a "Link five." cue is never stranded at
# the end of one request with its commentary read "cold" at the start of the
# next, which is what produced the audible pacing/intonation jumps mid-card.
_BLOCK_START_RE = re.compile(
    r"""^(?:
        Now,\ the\ .+?\ section\.
      | Now,\ more\ links\.
      | Now,\ for\ your\ information\.
      | That's\ the\ end\ of\ .
      | That\ brings\ us\ to\ the\ end\ of\ the\ Weekly\ Thing
      | Link\ \S+\.
      | Journal\ entry\ \S+\.
      | Quote\.
    )""",
    re.VERBOSE,
)


def _paragraphs(text: str) -> list[str]:
    return [paragraph.strip() for paragraph in re.split(r"\n{2,}", text) if paragraph.strip()]


def split_into_blocks(text: str) -> list[str]:
    """Group the script's paragraphs into semantic blocks.

    A block runs from one block-start marker (inclusive) up to the next; any
    leading paragraphs before the first marker (the preamble) form the first
    block. Each block is the paragraphs rejoined with blank lines."""
    blocks: list[str] = []
    current: list[str] = []
    for paragraph in _paragraphs(text):
        first_line = paragraph.splitlines()[0].strip()
        if current and _BLOCK_START_RE.match(first_line):
            blocks.append("\n\n".join(current))
            current = []
        current.append(paragraph)
    if current:
        blocks.append("\n\n".join(current))
    return blocks


def chunk_text(text: str, max_chars: int = MAX_CHARS) -> list[str]:
    chunks: list[str] = []
    current = ""
    for block in split_into_blocks(text):
        candidate = f"{current}\n\n{block}".strip() if current else block
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            chunks.append(current)
            current = ""
        if len(block) <= max_chars:
            current = block
            continue
        # A single block too large for one request: fall back to packing its
        # paragraphs, then its sentences, into the size budget.
        current = _pack_paragraphs(block, max_chars, chunks)
    if current:
        chunks.append(current)
    return chunks


def _pack_paragraphs(text: str, max_chars: int, chunks: list[str]) -> str:
    current = ""
    for paragraph in _paragraphs(text):
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
        for sentence in split_sentences(paragraph):
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
    return current


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


def synthesize_blocks_to_mp3(
    blocks: list[str], output_path: Path, label: str = "audio"
) -> Path:
    """TTS each block as its own utterance, concat into a single MP3 at
    output_path. No normalization.

    Used by Workshop-shipped issues where each transcript file is a semantic
    block (preamble, intro, Currently, each Notable link, etc.). Letting the
    TTS engine treat each block as a separate utterance lands breath/pause
    placement at the editorial boundaries — what the per-block transcript
    model exists to deliver. Skips chunk_text packing entirely so a small
    issue isn't collapsed into one chunk and read flat."""
    ensure_audio_tools()
    if not blocks:
        raise RuntimeError(f"synthesize_blocks_to_mp3: no blocks for {label}")
    workdir = TMP_DIR / "synthesize" / output_path.stem
    workdir.mkdir(parents=True, exist_ok=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    client = _openai_client()
    chunk_paths: list[Path] = []
    for index, block in enumerate(blocks):
        if len(block) > MAX_CHARS:
            raise RuntimeError(
                f"synthesize_blocks_to_mp3: block {index + 1} is {len(block)} chars, "
                f"exceeds MAX_CHARS={MAX_CHARS}. Split the block at compose time."
            )
        print(f"{label}: synthesizing block {index + 1}/{len(blocks)} ({len(block)} chars)")
        chunk_path = workdir / f"chunk-{index:03d}.mp3"
        response = client.audio.speech.create(
            model=TTS_MODEL,
            voice=TTS_VOICE,
            input=block,
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


def render_body(issue: str, text: str, blocks: list[str] | None = None) -> tuple[Path, int]:
    """Render an issue body to a single MP3 (no bumpers, no normalization).

    If ``blocks`` is provided (Workshop per-block transcript path), TTSes each
    block as its own utterance for natural breath placement. Otherwise falls
    back to the legacy single-string path which chunks via chunk_text."""
    workdir = TMP_DIR / str(issue)
    body_path = workdir / "body.mp3"
    if blocks:
        synthesize_blocks_to_mp3(blocks, body_path, label=f"Issue #{issue}")
    else:
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
