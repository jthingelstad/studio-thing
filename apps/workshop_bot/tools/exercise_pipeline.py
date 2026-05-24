"""WT348 publishing-flow exercise harness — drives the assembly jobs
against the real S3 workspace + workshop.db, without Discord.

Invoke from the repo root:

    venv/bin/python -m apps.workshop_bot.tools.exercise_pipeline \
        --issue 348 --mode full --pick first --auto-fire keep

Modes:
    full          reset gates + downstream; update→final→haiku→subject→cta→publish
    from-final    keep upstream; reset final + downstream; final→…→publish
    downstream    keep final.md + thesis.md; reset haiku/meta/cta/publish; haiku→…→publish
    publish-only  delete buttondown.md/.html only; run build-publish

Picker strategy (--pick):
    first         always select option 1 in every refresh-loop pick
    last          always select the last option
    seeded:N      use random.Random(N) to pick

Outputs land in tmp/wt348-pipeline-runs/<UTC-ISO>/:
    baseline/         pre-run snapshot of all non-protected S3 assets
    after/            post-run snapshot of all non-protected S3 assets
    report.json       per-step result + agent_runs delta + S3 diff

Hard guardrail: the audio MP3s, cover.jpg/cover-large.jpg, and journal/**
are NEVER deleted or overwritten by this harness. All deletes funnel
through ``_safe_delete`` which filters against PRESERVE_PATTERNS.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import hashlib
import json
import logging
import os
import random
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Optional
from unittest.mock import patch

# Repo root onto sys.path before workshop_bot imports.
_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

# Load .env so AWS + ANTHROPIC creds are visible to subprocess + boto3.
_DOTENV = _REPO / ".env"
if _DOTENV.exists():
    for line in _DOTENV.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())

from apps.workshop_bot.jobs import (
    _base,
    build_publish,
    compose_cta,
    compose_haiku,
    compose_meta,
    create_final,
    reset_issue,
    update_draft,
)
from apps.workshop_bot.tools import db, s3
from apps.workshop_bot.tools.discord import interaction
from apps.workshop_bot.tools.llm import agent_loop, anthropic_client

logger = logging.getLogger("exercise_pipeline")

BUCKET = "files.thingelstad.com"

# Keys we will never delete or overwrite under weekly-thing/{N}/.
PRESERVE_SUFFIXES = (".mp3",)
PRESERVE_FILENAMES = ("cover.jpg", "cover-large.jpg")
PRESERVE_PREFIXES = ("journal/",)


# ---------- preserve-asset guardrail ----------

def is_preserved(filename: str) -> bool:
    """True if ``filename`` (the path *inside* weekly-thing/{N}/) must
    not be deleted or overwritten by the harness."""
    if any(filename.endswith(s) for s in PRESERVE_SUFFIXES):
        return True
    if filename in PRESERVE_FILENAMES:
        return True
    if any(filename.startswith(p) for p in PRESERVE_PREFIXES):
        return True
    return False


def _safe_delete(issue_number: int, filename: str, *, dry_run: bool = False) -> bool:
    """Delete a file under weekly-thing/{N}/ — refusing protected keys.
    Returns True if the delete was attempted (file may or may not have
    existed; we don't check ahead of time)."""
    if is_preserved(filename):
        logger.warning("PRESERVED — refusing to delete %s/%s", issue_number, filename)
        return False
    if dry_run:
        logger.info("dry-run delete: %s/%s", issue_number, filename)
        return True
    try:
        s3.delete_issue_file(int(issue_number), filename)
        logger.info("deleted: %s/%s", issue_number, filename)
        return True
    except Exception:  # noqa: BLE001
        logger.exception("delete failed: %s/%s", issue_number, filename)
        return False


# ---------- S3 snapshot + inventory ----------

def snapshot_to(dir_path: Path, issue_number: int) -> None:
    """aws s3 sync the issue's text/JSON/HTML assets into ``dir_path``.
    Excludes audio + cover binaries + journal images."""
    dir_path.mkdir(parents=True, exist_ok=True)
    cmd = [
        "aws", "s3", "sync",
        f"s3://{BUCKET}/weekly-thing/{issue_number}/",
        str(dir_path),
        "--exclude", "*.mp3",
        "--exclude", "cover.jpg",
        "--exclude", "cover-large.jpg",
        "--exclude", "journal/*",
        "--no-progress",
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def inventory_of(dir_path: Path) -> dict[str, dict[str, Any]]:
    """{filename: {size, sha256}} for every file under ``dir_path``.
    Filenames are relative to ``dir_path``."""
    out: dict[str, dict[str, Any]] = {}
    if not dir_path.exists():
        return out
    for p in sorted(dir_path.rglob("*")):
        if not p.is_file():
            continue
        rel = str(p.relative_to(dir_path))
        data = p.read_bytes()
        out[rel] = {
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest()[:16],
        }
    return out


def diff_inventory(
    before: dict[str, dict[str, Any]],
    after: dict[str, dict[str, Any]],
) -> dict[str, list[str]]:
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    changed: list[str] = []
    for k in sorted(set(before) & set(after)):
        if before[k]["sha256"] != after[k]["sha256"]:
            changed.append(k)
    return {"added": added, "removed": removed, "changed": changed}


# ---------- workshop.db helpers ----------

def latest_agent_run_id() -> int:
    with db.connect() as con:
        rows = list(con.execute("SELECT COALESCE(MAX(id), 0) FROM agent_runs"))
    return int(rows[0][0]) if rows else 0


def agent_runs_since(since_id: int) -> list[dict[str, Any]]:
    with db.connect() as con:
        cur = con.execute(
            "SELECT * FROM agent_runs WHERE id > ? ORDER BY id ASC",
            (since_id,),
        )
        cols = [c[0] for c in cur.description]
        rows = [dict(zip(cols, row)) for row in cur]
    # Compute cost on read — agent_runs doesn't store cost_usd. Co-located
    # rates live in anthropic_client.RATES_USD_PER_MTOK.
    for r in rows:
        r["cost_usd"] = anthropic_client.cost_usd(
            r.get("model"),
            input_tokens=r.get("input_tokens") or 0,
            output_tokens=r.get("output_tokens") or 0,
            cache_read_tokens=r.get("cache_read_tokens") or 0,
            cache_create_tokens=r.get("cache_create_tokens") or 0,
        )
    return rows


# ---------- chooser / interaction patches ----------

class Chooser:
    def __init__(self, kind: str):
        self.kind = kind
        self._rng: Optional[random.Random] = None
        if kind.startswith("seeded:"):
            try:
                self._rng = random.Random(int(kind.split(":", 1)[1]))
            except ValueError as exc:
                raise ValueError(f"--pick seeded:N — N must be int (got {kind})") from exc

    def pick_index(self, options: list[Any]) -> int:
        if not options:
            return 0
        if self.kind == "first":
            return 0
        if self.kind == "last":
            return len(options) - 1
        if self._rng is not None:
            return self._rng.randrange(len(options))
        raise ValueError(f"unknown --pick {self.kind!r}")


def patch_interactions(chooser: Chooser):
    """Replace await_choice (returns int|"refresh"|None) and await_approval
    (returns True|False|"refresh"|None) so jobs never block on Discord.

    Also patches the picker's _post helper so message-id chains used by
    interaction.await_choice's reaction wait don't try to add reactions
    on a real Discord message — the patches don't go through those code
    paths, but a defensive replacement keeps stack traces clean if any
    code path slips past."""
    async def fake_choice(bot, channel, options, *, prompt, timeout=0, allow_refresh=True):
        idx = chooser.pick_index(options)
        logger.info("await_choice -> %d (of %d)", idx, len(options))
        return idx

    async def fake_approval(bot, channel, *, prompt, timeout=0, allow_refresh=True):
        # Always approve — exercising the ✅ path. The user can flip this
        # later if they want to test ❌ explicitly.
        logger.info("await_approval -> True")
        return True

    return [
        patch.object(interaction, "await_choice", fake_choice),
        patch.object(interaction, "await_approval", fake_approval),
    ]


def patch_autofire(mode: str):
    """If --auto-fire suppress, replace create_final._schedule_compose_cta
    with a no-op so the harness can run compose-cta explicitly."""
    if mode == "keep":
        return contextlib.nullcontext()

    def _noop(ctx, *, issue_number, slots_declared):
        logger.info("autofire suppressed (slots=%d)", slots_declared)

    return patch.object(create_final, "_schedule_compose_cta", _noop)


# ---------- fake bot / channel / deps ----------

class CapturingChannel:
    """Stand-in for a Discord channel. Logs sends; never raises."""

    def __init__(self, label: str):
        self.label = label
        self.sent: list[str] = []

    async def send(self, content: str, suppress_embeds: bool = True, **kwargs):
        self.sent.append(content)
        logger.debug("[%s] send: %s", self.label, content[:120].replace("\n", " ⏎ "))
        # Return a fake Message that supports add_reaction (so interaction.
        # _post → add_reaction never blows up if a non-patched path is hit).
        msg = SimpleNamespace(id=f"{self.label}-{len(self.sent)}", add_reaction=_noop_async)
        return msg


async def _noop_async(*args, **kwargs):
    return None


# Mirrors PersonaBot subclasses' `preferred_model` attribute so the
# harness's --model preferred mode matches what production uses.
PERSONA_PREFERRED_MODEL = {
    "eddy": "sonnet",
    "linky": "sonnet",
    "marky": "sonnet",
    "patty": "sonnet",
}


class FakeBot:
    """Minimal stand-in: ``user`` truthy, ``get_channel`` returns a
    capturing channel, ``core(latest, history, model)`` calls the real
    Anthropic agent loop with no tools (so the LLM responds with the
    JSON the prompts ask for, without any tool surface).

    ``default_model`` resolves the persona's model when ``core`` is
    called with ``model=None`` — matches ``PersonaBot._resolve_model``'s
    ``override or self.preferred_model or anthropic_client.default_model()``
    fallback chain so the harness can faithfully reproduce a prod-fidelity
    run when invoked with ``--model preferred``."""

    def __init__(self, persona: str, channel: CapturingChannel, *, default_model: Optional[str] = None):
        self.persona = persona
        self.user = SimpleNamespace(id="harness", name=persona)
        self._channel = channel
        self.preferred_model = default_model  # None → agent_loop's fallback

    def get_channel(self, cid: int):
        return self._channel

    async def core(self, *, latest: str, history=None, model=None):
        chosen = model or self.preferred_model
        return await asyncio.to_thread(
            agent_loop.run,
            persona=self.persona,
            user_message=latest,
            history=history or [],
            tools=[],
            deps=SimpleNamespace(registry=None),
            model=chosen,
        )

    async def wait_for(self, *args, **kwargs):
        raise RuntimeError("FakeBot.wait_for should never be called — interaction.* is patched")


class FakeTeam:
    def __init__(self, bots: dict[str, FakeBot]):
        self.bots = bots


class FakeDeps:
    def __init__(self, bots: dict[str, FakeBot]):
        self.team = FakeTeam(bots)
        self.registry = None
        self.corpus = None


def make_ctx(channels_by_env: dict[str, CapturingChannel], *, model_mode: str) -> _base.JobContext:
    """Build a JobContext whose ``channel()`` returns our capturing
    channels keyed by the channel env var the job asks for.

    ``model_mode`` is one of ``"preferred"`` (each bot uses its
    production preferred_model — see ``PERSONA_PREFERRED_MODEL``) or
    any model alias from ``anthropic_client.MODELS`` (``"haiku"``,
    ``"sonnet"``, ``"opus"``) which forces every bot onto that model."""
    eddy_channel = channels_by_env.get("DISCORD_CHANNEL_EDITORIAL")
    patty_channel = channels_by_env.get("DISCORD_CHANNEL_SUPPORTERS")

    def model_for(persona: str) -> Optional[str]:
        if model_mode == "preferred":
            return PERSONA_PREFERRED_MODEL.get(persona)
        return model_mode  # already an alias like "haiku"|"sonnet"|"opus"

    bots = {
        "eddy": FakeBot("eddy", eddy_channel, default_model=model_for("eddy")),
        "patty": FakeBot("patty", patty_channel, default_model=model_for("patty")),
    }
    deps = FakeDeps(bots)
    ctx = _base.JobContext(deps=deps, trigger="exercise")

    # Override ctx.channel so resolve_bot_and_channel finds our fakes
    # by env var (no real Discord lookup).
    original_channel = ctx.channel

    def fake_channel(env_var: str, *, persona=None):
        ch = channels_by_env.get(env_var)
        if ch is None:
            logger.warning("ctx.channel(%s) — no fake channel mapped", env_var)
        return ch

    ctx.channel = fake_channel  # type: ignore[assignment]
    return ctx


# ---------- reset logic per mode ----------

# Files that downstream jobs produce. Used to reset the workspace to the
# point each mode wants to start from.
DOWNSTREAM_FILES = (
    "haiku.md",
    "metadata.json",
    "cta-1.md", "cta-2.md",
    "thanks-1.md", "thanks-2.md",
    "buttondown.md",
    # picker option-card pages — re-generated each pick round
    "haiku-options.html",
    "subject-options.html",
    "cta-1-options.html", "cta-2-options.html",
    "thanks-1-options.html", "thanks-2-options.html",
)

FINAL_FILES = ("final.md", "thesis.md", "final-proposal.html")
DRAFT_FILES = ("draft.md", "draft.html")


def do_reset(mode: str, issue_number: int) -> dict[str, list[str]]:
    """Per-mode reset. Returns the set of files we asked to delete."""
    deleted: list[str] = []

    targets: list[str] = []
    if mode == "full":
        targets = list(DOWNSTREAM_FILES) + list(FINAL_FILES) + list(DRAFT_FILES)
    elif mode == "from-final":
        targets = list(DOWNSTREAM_FILES) + list(FINAL_FILES)
    elif mode == "downstream":
        targets = list(DOWNSTREAM_FILES)
    elif mode == "publish-only":
        targets = ["buttondown.md"]
    else:
        raise ValueError(f"unknown mode: {mode}")

    for fn in targets:
        if _safe_delete(issue_number, fn):
            deleted.append(fn)

    # Clear is_promoted flags when we're re-running create-final.
    promotions_cleared = 0
    if mode in ("full", "from-final"):
        from apps.workshop_bot.tools import issue_items
        promos = issue_items.promoted_items(issue_number)
        promotions_cleared = len(promos)
        if promos:
            issue_items.clear_promotions(issue_number)

    return {"files": deleted, "promotions_cleared": promotions_cleared}


# ---------- pipeline definitions ----------

def pipeline_for(mode: str) -> list[tuple[str, Callable]]:
    """Return ``[(job_name, run_callable), …]`` in execution order."""
    full = [
        ("update-draft", update_draft.run),
        ("reorder", create_final.run),
        ("compose-haiku", compose_haiku.run),
        ("compose-meta", compose_meta.run),
        ("compose-cta", compose_cta.run),
        ("build-publish", build_publish.run),
    ]
    if mode == "full":
        return full
    if mode == "from-final":
        return full[1:]
    if mode == "downstream":
        return full[2:]
    if mode == "publish-only":
        return full[-1:]
    raise ValueError(f"unknown mode: {mode}")


# ---------- run ----------

async def run_pipeline(args: argparse.Namespace) -> dict[str, Any]:
    issue = int(args.issue)
    chooser = Chooser(args.pick)

    # ``db.connect()`` now auto-runs migrations on schema-content drift, so
    # the harness doesn't need an explicit ``run_migrations()`` call.

    run_dir = Path("tmp") / "wt348-pipeline-runs" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    baseline_dir = run_dir / "baseline"
    after_dir = run_dir / "after"
    baseline_dir.mkdir(parents=True, exist_ok=True)

    print(
        f"\n=== exercise_pipeline: issue={issue} mode={args.mode} "
        f"pick={args.pick} auto-fire={args.auto_fire} model={args.model} ==="
    )
    print(f"run dir: {run_dir}")
    print()

    # 1. Snapshot baseline (text/JSON only — preserved assets stay in S3).
    print("snapshot baseline …", flush=True)
    snapshot_to(baseline_dir, issue)
    baseline_inv = inventory_of(baseline_dir)
    print(f"  {len(baseline_inv)} files captured.\n")

    # 2. Reset to mode's starting point.
    print(f"reset for mode={args.mode!r} …", flush=True)
    reset_summary = do_reset(args.mode, issue)
    print(f"  files deleted: {reset_summary['files']}")
    print(f"  promotions cleared: {reset_summary['promotions_cleared']}\n")

    # 3. Build fake bot + channel + ctx; patch interactions.
    editorial = CapturingChannel("editorial")
    supporters = CapturingChannel("supporters")
    chatter = CapturingChannel("chatter")
    channels_by_env = {
        "DISCORD_CHANNEL_EDITORIAL": editorial,
        "DISCORD_CHANNEL_SUPPORTERS": supporters,
        "DISCORD_CHANNEL_CHATTER": chatter,
    }
    ctx = make_ctx(channels_by_env, model_mode=args.model)

    steps: list[dict[str, Any]] = []

    # 4. Run each step, capturing agent_runs deltas + S3 inventory snapshots.
    with contextlib.ExitStack() as stack:
        for patcher in patch_interactions(chooser):
            stack.enter_context(patcher)
        stack.enter_context(patch_autofire(args.auto_fire))

        pipeline = pipeline_for(args.mode)
        for job_name, job_run in pipeline:
            print(f"--- {job_name} ---", flush=True)
            t0 = time.monotonic()
            agent_runs_high_water = latest_agent_run_id()
            try:
                result = await job_run(ctx)
                ok = bool(getattr(result, "ok", False))
                msg = getattr(result, "message", "")
                data = getattr(result, "data", {}) or {}
                err: Optional[str] = None
            except Exception as exc:  # noqa: BLE001
                ok = False
                msg = ""
                data = {}
                err = f"{type(exc).__name__}: {exc}"
                logger.exception("%s raised", job_name)
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            new_runs = agent_runs_since(agent_runs_high_water)

            step_record = {
                "job": job_name,
                "ok": ok,
                "message": msg,
                "data": data,
                "error": err,
                "elapsed_ms": elapsed_ms,
                "agent_runs": new_runs,
                "channel_posts": {
                    "editorial": len(editorial.sent),
                    "supporters": len(supporters.sent),
                },
            }
            steps.append(step_record)
            print(f"  ok={ok} elapsed={elapsed_ms}ms agent_runs+={len(new_runs)}")
            if msg:
                print(f"  message: {msg[:200]}")
            if err:
                print(f"  ERROR: {err}")
            print()

            # Tiny pause so concurrent S3 reads aren't racing the previous write.
            await asyncio.sleep(0.1)

    # 5. Snapshot after-state and compute diff.
    print("snapshot after …", flush=True)
    snapshot_to(after_dir, issue)
    after_inv = inventory_of(after_dir)
    diff = diff_inventory(baseline_inv, after_inv)
    print(f"  {len(after_inv)} files captured. "
          f"diff: +{len(diff['added'])} ~{len(diff['changed'])} -{len(diff['removed'])}\n")

    # 6. Write report.
    report = {
        "issue": issue,
        "mode": args.mode,
        "pick": args.pick,
        "auto_fire": args.auto_fire,
        "model": args.model,
        "run_dir": str(run_dir),
        "reset": reset_summary,
        "steps": steps,
        "diff": diff,
        "baseline_inventory": baseline_inv,
        "after_inventory": after_inv,
        "channels": {
            "editorial_posts": editorial.sent,
            "supporters_posts": supporters.sent,
        },
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    report_path = run_dir / "report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"report → {report_path}\n")

    # 7. Concise summary.
    total_ms = sum(s["elapsed_ms"] for s in steps)
    total_cost = sum((r.get("cost_usd") or 0.0) for s in steps for r in s["agent_runs"])
    ok_steps = sum(1 for s in steps if s["ok"])
    print(
        f"=== summary: {ok_steps}/{len(steps)} steps ok · "
        f"{total_ms/1000:.1f}s total · "
        f"~${total_cost:.4f} LLM cost ==="
    )

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--issue", type=int, required=True)
    parser.add_argument("--mode", choices=("full", "from-final", "downstream", "publish-only"),
                        default="full")
    parser.add_argument("--pick", default="first", help="first | last | seeded:N")
    parser.add_argument("--auto-fire", choices=("keep", "suppress"), default="keep",
                        dest="auto_fire")
    parser.add_argument(
        "--model",
        default="haiku",
        choices=("haiku", "sonnet", "opus", "preferred"),
        help=("model alias for every bot.core call. 'preferred' mirrors "
              "PersonaBot.preferred_model — see PERSONA_PREFERRED_MODEL. "
              "Closest match to a real prod run; default haiku is the "
              "cheap-fast option for plumbing-only tests."),
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    # Quiet some loud upstreams.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("anthropic").setLevel(logging.WARNING)
    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    return 0 if asyncio.run(run_pipeline(args)) else 1


if __name__ == "__main__":
    sys.exit(main())
