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


def synthesize_mp3(issue: str, text: str) -> tuple[Path, int]:
    ensure_audio_tools()
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("The openai package is required for audio synthesis.") from exc

    chunks = chunk_text(text)
    workdir = TMP_DIR / str(issue)
    workdir.mkdir(parents=True, exist_ok=True)
    chunk_paths: list[Path] = []
    client = OpenAI(timeout=60.0, max_retries=1)

    for index, chunk in enumerate(chunks):
        print(f"Issue #{issue}: synthesizing chunk {index + 1}/{len(chunks)} ({len(chunk)} chars)")
        path = workdir / f"chunk-{index:03d}.mp3"
        response = client.audio.speech.create(
            model=TTS_MODEL,
            voice=TTS_VOICE,
            input=chunk,
            response_format="mp3",
        )
        path.write_bytes(response.content)
        chunk_paths.append(path)

    list_path = workdir / "concat.txt"
    list_path.write_text(
        "".join(f"file '{path.resolve()}'\n" for path in chunk_paths),
        encoding="utf-8",
    )
    output = workdir / "audio.mp3"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_path), "-c", "copy", str(output)],
        cwd=REPO,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    duration = probe_duration_seconds(output)
    return output, duration


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
