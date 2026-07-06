"""``render-audio`` — TTS + bumpers + loudnorm for the in-flight issue.

Workshop_bot side of audio rendering. The ship sequence calls this between
compose-transcript and the Buttondown POST so the MP3 is live at its public
URL by the time Jamie sees the success card — no "wait for CI before
scheduling Buttondown" caveat.

Reads transcripts from ``data/issues/{N}/transcript/`` (compose-transcript
mirrors them there). Wraps ``pipeline/audio/audio.build_issue`` so the
underlying TTS / chunking / S3 upload / manifest update logic stays in one
place; the workshop side only orchestrates.

Idempotent: ``build_issue``'s ``body_is_up_to_date`` / ``final_is_up_to_date``
gates skip the render when the transcript hash matches the manifest and the
S3 MP3 is intact. Re-running a ship is silent on the audio side too.

Note on ``apps/site/archive/{N}.md``: ``build_issue`` reads it for the
ID3 metadata + cover image URL. For a freshly-shipped issue that file
doesn't exist yet, so this job runs ``pipeline/content/content.py build``
first to materialize it (without ``audio_url`` — that gets injected the
next time the build runs after this job updates the manifest).
"""

from __future__ import annotations

import asyncio
import logging
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Optional

from ..tools import db
from . import _base

logger = logging.getLogger("workshop.jobs.render_audio")

NAME = "render-audio"

REPO = Path(__file__).resolve().parents[3]
AUDIO_MANIFEST = REPO / "data" / "audio" / "manifest.json"
TRANSCRIPT_DIR_TPL = REPO / "data" / "issues"
ARCHIVE_DIR = REPO / "apps" / "site" / "archive"


def _import_audio_pipeline():
    """Lazy-load pipeline/audio/ — not a Python package, so we add it to
    sys.path on demand rather than restructuring the audio tree."""
    audio_dir = REPO / "pipeline" / "audio"
    if str(audio_dir) not in sys.path:
        sys.path.insert(0, str(audio_dir))
    import audio  # noqa: F401
    import bumpers  # noqa: F401
    import manifest  # noqa: F401

    return audio, bumpers, manifest


def _materialize_apps_site_archive(issue_number: int) -> None:
    """Run ``pipeline/content/content.py build`` so the canonical
    apps/site/archive/{N}.md exists for the audio pipeline's frontmatter
    read. Builds the full archive (fast — sub-second for 349 issues)."""
    subprocess.run(
        [sys.executable, str(REPO / "pipeline" / "content" / "content.py"), "build"],
        check=True,
        cwd=REPO,
        capture_output=True,
    )


def _run_audio_pipeline(
    *,
    bumpers_mod,
    audio_mod,
    manifest_mod,
    manifest_data: dict,
    issue_number: int,
    progress_cb: Optional[Callable[[str], None]] = None,
) -> dict[str, Any]:
    """Run the full synchronous audio pipeline — bumper renders + TTS
    body + reassembly + S3 upload + manifest write — in one call.

    Wrapped in ``asyncio.to_thread`` from ``run`` so the asyncio loop
    stays responsive during the 30–60s OpenAI TTS round-trips. Returns
    the manifest entry for the issue with an extra ``_changed`` key
    carrying ``audio_mod.build_issue``'s "did anything actually rebuild
    today?" result.

    ``progress_cb`` receives one progress line per pipeline event
    (synthesizing block N/M, body uploaded, etc.) — called from the
    worker thread, so it must be thread-safe. ``run`` passes a callback
    that marshals events back to the asyncio loop via
    ``loop.call_soon_threadsafe``.
    """
    syn_mod = _synthesize_mod(audio_mod)
    logger.info(
        "render-audio: patching print on audio_mod=%r synthesize_mod=%r",
        getattr(audio_mod, "__name__", "?"),
        getattr(syn_mod, "__name__", "?") if syn_mod is not None else None,
    )
    with _print_intercept(audio_mod, syn_mod, bumpers_mod, progress_cb=progress_cb):
        _ensure_bumpers(bumpers_mod, manifest_data)
        changed = audio_mod.build_issue(
            str(issue_number),
            manifest_data,
            dry_run=False,
            force=False,
            reassemble_only=False,
        )
    manifest_mod.write_manifest(manifest_data)
    entry = dict(manifest_data.get(str(issue_number), {}))
    entry["_changed"] = bool(changed)
    return entry


def _synthesize_mod(audio_mod):
    """Find the synthesize module — where ``synthesize_blocks_to_mp3`` (and the
    per-block ``print`` that drives the live progress card) lives. Returns
    ``None`` defensively if the lookup misses; the print-intercept then just
    patches audio_mod (still catches the body / upload / bumper lines).

    **Authoritative path first:** ``audio.py`` does ``from synthesize import
    synthesize_blocks_to_mp3``, so resolve the function's *defining* module via
    ``__module__`` — that's the exact module object whose ``print`` emits the
    per-block lines, regardless of what key it landed under in ``sys.modules``.
    This is the §6 fix: keying off the literal name ``"synthesize"`` missed the
    module when the pipeline was imported under a package-qualified name, so the
    per-block events never reached the relay and the card stuck on "starting…".
    """
    import sys
    for fn_name in ("synthesize_blocks_to_mp3", "synthesize_text_to_mp3"):
        fn = getattr(audio_mod, fn_name, None)
        modname = getattr(fn, "__module__", None)
        if modname and modname in sys.modules:
            return sys.modules[modname]
    mod = sys.modules.get("synthesize")
    if mod is None:
        # Last resort: walk audio_mod's attributes for the synthesize module.
        for attr in vars(audio_mod).values():
            if (
                getattr(attr, "__name__", None) == "synthesize"
                or hasattr(attr, "synthesize_blocks_to_mp3")
            ):
                mod = attr
                break
    return mod


# Lines emitted by the audio pipeline that should surface in Discord.
# Pattern → short label (kept tight; Discord edits are 1990 char capped).
_PROGRESS_PATTERNS: tuple[tuple[re.Pattern, Callable[[re.Match], str]], ...] = (
    (
        re.compile(r"Issue #\S+: synthesizing block (\d+)/(\d+) \((\d+) chars\)"),
        lambda m: f"🎙️ block {m.group(1)}/{m.group(2)} ({m.group(3)} chars)",
    ),
    (
        re.compile(r"Issue #\S+: synthesizing body \((\d+) (\S+) chunk"),
        lambda m: f"▶️ starting body — {m.group(1)} {m.group(2)} chunk(s)",
    ),
    (
        re.compile(r"Issue #\S+: uploaded body (\S+)"),
        lambda m: f"☁️ body uploaded — {m.group(1)}",
    ),
    (
        re.compile(r"Issue #\S+: audio is up to date"),
        lambda _m: "✅ already up to date",
    ),
    (
        re.compile(r"Issue #\S+: reusing existing body audio"),
        lambda _m: "♻️ reusing existing body audio",
    ),
    (
        re.compile(r"Bumper (\w+): synthesizing"),
        lambda m: f"🔔 rendering bumper — {m.group(1)}",
    ),
)


def _classify_print(line: str) -> Optional[str]:
    """If ``line`` is a recognised pipeline progress message, return a
    short Discord-bound label for it. Otherwise None."""
    stripped = line.strip()
    if not stripped:
        return None
    for pat, fmt in _PROGRESS_PATTERNS:
        m = pat.search(stripped)
        if m:
            return fmt(m)
    return None


class _print_intercept:
    """Replace ``print`` in the audio pipeline modules with a hook that
    forwards each call through to the real builtin print AND, when the
    line matches a known progress pattern, hands it off to a thread-safe
    callback. Context-manager so the modules' print attribute is restored
    on exit even if the pipeline raises.

    Pipeline modules call ``print`` resolved via the LEGB chain — module
    globals before builtins — so setting ``mod.print = …`` is enough to
    intercept their calls without monkey-patching the builtin itself.
    """

    def __init__(self, *mods, progress_cb: Optional[Callable[[str], None]] = None):
        import builtins
        self._mods = [m for m in mods if m is not None]
        self._cb = progress_cb
        self._saved: list[tuple[Any, bool, Any]] = []
        self._builtin_print = builtins.print

    def _hook(self, *args, **kwargs):
        # Always forward to the real builtin so launchd-captured stdout
        # still gets the line.
        self._builtin_print(*args, **kwargs)
        if self._cb is None or kwargs.get("file"):
            return
        try:
            text = " ".join(str(a) for a in args)
            label = _classify_print(text)
            if label is not None:
                logger.info("render-audio: progress event → %s", label)
                self._cb(label)
        except Exception:  # noqa: BLE001 — never let progress crash the pipeline
            logger.exception("render-audio: progress hook raised; swallowing")

    def __enter__(self):
        for mod in self._mods:
            had_attr = "print" in vars(mod)
            prior = vars(mod).get("print", self._builtin_print)
            self._saved.append((mod, had_attr, prior))
            setattr(mod, "print", self._hook)
        return self

    def __exit__(self, exc_type, exc, tb):
        for mod, had_attr, prior in self._saved:
            if had_attr:
                setattr(mod, "print", prior)
            else:
                try:
                    delattr(mod, "print")
                except AttributeError:
                    pass
        self._saved.clear()
        return False


def _ensure_bumpers(bumpers_mod, manifest: dict) -> bool:
    """build_issue refuses if intro/outro bumper MP3s are missing. Render
    them on demand — deterministic text-keyed renders, so this is a no-op
    if they already exist and the text + voice match the manifest's
    ``_bumpers`` block.

    ``manifest`` is the audio manifest (mutated in place when a bumper
    actually re-renders so ``set_bumper_state`` can stamp the new hash).
    Returns True if anything was rendered."""
    return bool(bumpers_mod.ensure_bumpers(manifest))


async def run(ctx: "_base.JobContext") -> "_base.JobResult":
    window = db.get_active_issue_window()
    if window is None:
        return _base.JobResult(
            False, "❌ no active issue window — start one in Studio first."
        )
    n = int(window["issue_number"])

    transcript_dir = TRANSCRIPT_DIR_TPL / str(n) / "transcript"
    if not transcript_dir.is_dir() or not any(transcript_dir.glob("*.txt")):
        msg = (
            f"⛔ `render-audio` for **WT{n}** can't run — no per-block transcripts "
            f"under `{transcript_dir.relative_to(REPO)}`. Run `compose-transcript` first."
        )
        await ctx.post("DISCORD_CHANNEL_EDITORIAL", msg, persona="eddy")
        return _base.JobResult(False, msg, data={"issue_number": n})

    # Post an initial progress card to #editorial that the worker
    # thread will edit in place as each block lands. Best-effort — a
    # Discord hiccup at this stage shouldn't block the render.
    head = f"🎙️ rendering audio for **WT{n}**"
    try:
        progress = await ctx.progress(
            "DISCORD_CHANNEL_EDITORIAL",
            f"{head} — starting…",
            persona="eddy",
        )
    except Exception:  # noqa: BLE001
        logger.exception("render-audio: couldn't post initial progress message")
        progress = None
    if progress is None:
        progress = _base.ProgressMessage(None)

    asset = "data/audio/manifest.json"
    try:
        with _base.job_lock([asset], NAME):
            audio_mod, bumpers_mod, manifest_mod = _import_audio_pipeline()

            # Make sure apps/site/archive/{N}.md exists for the ID3 + cover lookup.
            _materialize_apps_site_archive(n)

            # Read the manifest first — ensure_bumpers needs it (it stamps
            # the bumper hash + voice into manifest["_bumpers"]) and so
            # does build_issue. One read, one write at the end picks up
            # both mutations.
            manifest_data = manifest_mod.read_manifest()
            # The whole pipeline (OpenAI TTS round-trips per block,
            # ffmpeg passes for concat / loudnorm / re-encode, S3 upload,
            # CloudFront invalidation) is synchronous and takes 30–60s
            # for a full issue. Run it on a worker thread so the asyncio
            # loop stays responsive; otherwise discord.py's heartbeat
            # misses and Python's faulthandler dumps the blocked stack
            # repeatedly into the log.
            #
            # The worker enqueues per-block progress lines via the
            # thread-safe ``progress_cb``; the relay coroutine drains
            # them into the ProgressMessage so #editorial shows live
            # "block N/M" status instead of a 60-second silent gap.
            loop = asyncio.get_running_loop()
            event_queue: asyncio.Queue = asyncio.Queue()
            done_sentinel = object()

            def _thread_safe_enqueue(line: str) -> None:
                loop.call_soon_threadsafe(event_queue.put_nowait, line)

            history: list[str] = []

            async def _relay() -> None:
                while True:
                    item = await event_queue.get()
                    if item is done_sentinel:
                        return
                    history.append(str(item))
                    # Keep the last ~8 lines so the message doesn't grow
                    # without bound (and stays under Discord's 2000-char
                    # message cap).
                    tail = "\n".join(history[-8:])
                    logger.debug("render-audio: relay updating card with %d line(s)", len(history))
                    await progress.update(f"{head}\n{tail}")

            relay_task = asyncio.create_task(_relay())
            try:
                entry = await asyncio.to_thread(
                    _run_audio_pipeline,
                    bumpers_mod=bumpers_mod,
                    audio_mod=audio_mod,
                    manifest_mod=manifest_mod,
                    manifest_data=manifest_data,
                    issue_number=n,
                    progress_cb=_thread_safe_enqueue,
                )
            finally:
                event_queue.put_nowait(done_sentinel)
                await relay_task
            changed = entry.pop("_changed", False)

    except _base.JobLocked as exc:
        return _base.JobResult(
            False, f"⏳ `render-audio` is already running ({exc.holder_desc})."
        )
    except Exception as exc:  # noqa: BLE001 — surface the error rather than crash the ship
        logger.exception("render-audio failed for WT%d", n)
        msg = f"❌ `render-audio` for **WT{n}** failed: `{exc}`"
        try:
            await progress.update(msg)
        except Exception:  # noqa: BLE001
            pass
        await ctx.post("DISCORD_CHANNEL_EDITORIAL", msg, persona="eddy")
        return _base.JobResult(False, msg, data={"issue_number": n})

    audio_url = entry.get("audio_url", "")
    duration_s = entry.get("audio_duration_seconds")
    byte_size = entry.get("audio_byte_size")
    action = "rendered" if changed else "already up to date"

    # Final state on the progress card — collapses the per-block log
    # into a one-line outcome so the in-place message reflects success.
    summary_bits = [f"✅ audio {action} for **WT{n}**"]
    if duration_s and byte_size:
        summary_bits.append(f"{duration_s}s · {byte_size:,} bytes")
    if audio_url:
        summary_bits.append(f"[mp3]({audio_url})")
    try:
        await progress.update(" — ".join(summary_bits))
    except Exception:  # noqa: BLE001
        pass

    return _base.JobResult(
        True,
        f"audio {action} for #{n}"
        + (f" — {duration_s}s, {byte_size}B" if duration_s and byte_size else ""),
        data={
            "issue_number": n,
            "audio_url": audio_url,
            "duration_seconds": duration_s,
            "byte_size": byte_size,
            "changed": changed,
        },
    )
