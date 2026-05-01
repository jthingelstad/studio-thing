"""Intro/outro bumpers for the podcast version of The Weekly Thing audio."""

from __future__ import annotations

from pathlib import Path

from manifest import (
    BUMPERS_DIR,
    BUMPER_NAMES,
    bumper_path,
    bumpers_state,
    hash_text,
    set_bumper_state,
)
from synthesize import AUDIO_VOICE, synthesize_text_to_mp3

INTRO_TEXT = (
    "You're listening to an AI-generated audio version of the Weekly Thing. "
    "For the complete experience with all the links, images, and more, "
    "visit weekly.thingelstad.com and sign up to receive the emails. "
    "Now, here's this week's thing."
)

OUTRO_TEXT = (
    "Thanks for listening to the Weekly Thing. "
    "Remember, this is generated audio. "
    "Head to weekly.thingelstad.com for the complete newsletter "
    "with all the links and resources."
)

BUMPER_TEXTS: dict[str, str] = {
    "intro": INTRO_TEXT,
    "outro": OUTRO_TEXT,
}


def bumper_text_hash(name: str) -> str:
    return hash_text(BUMPER_TEXTS[name])


def bumper_state_for(name: str) -> dict[str, str]:
    return {"hash": bumper_text_hash(name), "voice": AUDIO_VOICE}


def bumper_needs_render(name: str, manifest: dict, force: bool = False) -> bool:
    if force:
        return True
    path = bumper_path(name)
    if not path.exists():
        return True
    state = bumpers_state(manifest).get(name) or {}
    return state.get("hash") != bumper_text_hash(name) or state.get("voice") != AUDIO_VOICE


def render_bumper(name: str, manifest: dict) -> Path:
    if name not in BUMPER_TEXTS:
        raise ValueError(f"Unknown bumper: {name}")
    BUMPERS_DIR.mkdir(parents=True, exist_ok=True)
    path = bumper_path(name)
    print(f"Bumper {name}: synthesizing")
    synthesize_text_to_mp3(BUMPER_TEXTS[name], path, label=f"Bumper {name}")
    set_bumper_state(manifest, name, bumper_text_hash(name), AUDIO_VOICE)
    return path


def ensure_bumpers(manifest: dict, force: bool = False) -> bool:
    """Render any bumper whose text/voice changed or whose file is missing.

    Returns True if any bumper was (re)rendered."""
    changed = False
    for name in BUMPER_NAMES:
        if bumper_needs_render(name, manifest, force=force):
            render_bumper(name, manifest)
            changed = True
        else:
            print(f"Bumper {name}: up to date")
    return changed


def bumper_hashes() -> dict[str, str]:
    return {name: bumper_text_hash(name) for name in BUMPER_NAMES}
