"""Eval harness — run generated Eddy questions without Discord.

Asks Haiku to generate realistic questions Jamie would send to Eddy
(cached to tmp/workshop_eval_questions.json so we don't regenerate on
every iteration). Then dispatches each question to Eddy's ``core()`` and
writes a markdown report plus SUMMARY.md.

Run:

    python -m apps.workshop_bot.eval                          # Eddy run
    python -m apps.workshop_bot.eval --regen                  # regenerate question set
    python -m apps.workshop_bot.eval --persona eddy

Cost: ~20 Haiku calls + 1 question-gen call.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import anthropic
from dotenv import load_dotenv

from .personas.base import Deps
from .personas.eddy import EddyBot
from .systems.buttondown.server import ButtondownServer
from .tools import db
from .tools.content import corpus
from .tools.llm import agent_tools, anthropic_client

logger = logging.getLogger("workshop.eval")

REPO = Path(__file__).resolve().parents[2]
TMP = REPO / "tmp"
QUESTIONS_PATH = TMP / "workshop_eval_questions.json"
PROMPTS_DIR = REPO / "apps" / "workshop_bot" / "prompts"

PERSONAS: dict[str, type] = {
    "eddy": EddyBot,
}

QUESTIONS_PER_PERSONA = 20

QUESTION_GEN_TEMPLATE = """\
You generate realistic Discord messages Jamie Thingelstad would send to {name}, his AI assistant for *The Weekly Thing* newsletter. Jamie is the author. {name} runs as a Discord bot and Jamie @-mentions them with the message body.

Here is who {name} is, in their own words:

---
{system_prompt}
---

Generate exactly {n} distinct messages Jamie might send to {name}. Mix:

- Casual hellos / one-liners ("hey", "still there?", "thoughts?")
- Direct task requests ({name}-specific — e.g. drafts, subject lines, CTA snippets, link curation)
- Specific archive references ("recap #346", "compare #287 to #301", "what was the angle in the latest issue?")
- Open questions ("what themes have been building lately?")
- Edge cases / awkward inputs (vague, off-topic, requests {name} can't really fulfill)
- Multi-sentence messages with substantive content (paste-style)

The questions should be PLAUSIBLE — phrased the way Jamie actually talks, not a survey-bot. Don't include the @-mention; the runtime strips it. Don't include backticks or special quoting around questions.

Output JSON only — a JSON array of {n} strings. No prose, no markdown fences. Just the array.
"""


def load_persona_prompt(name: str) -> str:
    return (PROMPTS_DIR / name / "prompt.md").read_text(encoding="utf-8").strip()


def parse_json_array(text: str) -> list[str]:
    """Forgiving JSON-array extractor (Haiku may wrap in fences)."""
    text = text.strip()
    # Strip ```json ... ``` fences if present.
    if text.startswith("```"):
        text = text.strip("`")
        text = text.removeprefix("json").strip()
    # Find the first `[` to last `]`.
    start = text.find("[")
    end = text.rfind("]")
    if start < 0 or end < 0:
        raise ValueError(f"no JSON array in: {text[:200]}")
    return [str(item) for item in json.loads(text[start : end + 1])]


def generate_questions(client: anthropic.Anthropic, persona_name: str) -> list[str]:
    prompt = QUESTION_GEN_TEMPLATE.format(
        name=persona_name.capitalize(),
        n=QUESTIONS_PER_PERSONA,
        system_prompt=load_persona_prompt(persona_name),
    )
    logger.info("generating %d questions for %s...", QUESTIONS_PER_PERSONA, persona_name)
    response = client.messages.create(
        model=anthropic_client.MODELS["haiku"],
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(b.text for b in response.content if b.type == "text")
    questions = parse_json_array(text)
    if len(questions) < QUESTIONS_PER_PERSONA:
        raise RuntimeError(f"{persona_name}: got {len(questions)} questions, expected {QUESTIONS_PER_PERSONA}")
    return questions[:QUESTIONS_PER_PERSONA]


def load_or_generate_questions(regen: bool) -> dict[str, list[str]]:
    if QUESTIONS_PATH.exists() and not regen:
        data = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
        # ensure every persona is present
        if all(p in data and len(data[p]) == QUESTIONS_PER_PERSONA for p in PERSONAS):
            logger.info("using cached questions from %s", QUESTIONS_PATH)
            return data
        logger.info("cached questions incomplete; regenerating")
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_GENERAL_API_KEY"])
    out: dict[str, list[str]] = {}
    for name in PERSONAS:
        out[name] = generate_questions(client, name)
    TMP.mkdir(parents=True, exist_ok=True)
    QUESTIONS_PATH.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("wrote %s", QUESTIONS_PATH)
    return out


def questions_cache_ready() -> bool:
    if not QUESTIONS_PATH.exists():
        return False
    try:
        data = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return False
    return all(p in data and len(data[p]) == QUESTIONS_PER_PERSONA for p in PERSONAS)


async def run_persona(
    name: str,
    cls: type,
    deps: Deps,
    questions: list[str],
    model: str,
    out_dir: Path,
) -> dict[str, Any]:
    bot = cls(deps)
    rows: list[dict[str, Any]] = []
    for i, q in enumerate(questions, 1):
        t0 = time.monotonic()
        try:
            answer, meta = await bot.core(latest=q, history=[], model=model)
            error: str | None = None
        except Exception as exc:  # noqa: BLE001
            answer = ""
            meta = {}
            error = f"{type(exc).__name__}: {exc}"
            logger.exception("%s Q%d errored", name, i)
        dt = time.monotonic() - t0
        rows.append({"i": i, "q": q, "a": answer, "meta": meta, "error": error, "seconds": dt})
        usage = meta.get("usage") or {}
        logger.info(
            "%s %02d/%02d  %.1fs  in=%s out=%s%s",
            name, i, len(questions), dt,
            usage.get("input", "?"), usage.get("output", "?"),
            f"  ERROR={error}" if error else "",
        )

    # Write per-persona markdown.
    md_lines: list[str] = []
    md_lines.append(f"# {name.capitalize()} — eval results")
    md_lines.append("")
    md_lines.append(f"- model: `{model}`")
    md_lines.append(f"- questions: {len(rows)}")
    md_lines.append(f"- errors: {sum(1 for r in rows if r['error'])}")
    md_lines.append("")
    for row in rows:
        md_lines.append("---")
        md_lines.append("")
        md_lines.append(f"### Q{row['i']:02d}")
        md_lines.append(f"**Question:** {row['q']}")
        md_lines.append("")
        if row["error"]:
            md_lines.append(f"**ERROR:** `{row['error']}`")
        else:
            md_lines.append("**Response:**")
            md_lines.append("")
            md_lines.append(row["a"] or "(empty)")
        md_lines.append("")
        usage = (row["meta"] or {}).get("usage") or {}
        meta_bits = [f"{row['seconds']:.1f}s"]
        if usage:
            meta_bits.append(
                f"in={usage.get('input', 0)} out={usage.get('output', 0)} "
                f"cache_r={usage.get('cache_read', 0)}"
            )
        cited = (row["meta"] or {}).get("cited_issues") or []
        if cited:
            meta_bits.append(f"cited={cited[:6]}")
        expanded = (row["meta"] or {}).get("expanded_refs") or []
        if expanded:
            meta_bits.append(f"expanded={expanded}")
        md_lines.append(f"_{' · '.join(meta_bits)}_")
        md_lines.append("")

    (out_dir / f"{name}.md").write_text("\n".join(md_lines), encoding="utf-8")

    return {
        "name": name,
        "errors": sum(1 for r in rows if r["error"]),
        "total_seconds": sum(r["seconds"] for r in rows),
        "total_in_tokens": sum((r["meta"] or {}).get("usage", {}).get("input", 0) for r in rows),
        "total_out_tokens": sum((r["meta"] or {}).get("usage", {}).get("output", 0) for r in rows),
    }


def _build_registry() -> agent_tools.ToolRegistry:
    """Mirror ``bot.py``'s registry composition for offline eval/rehearsal."""
    registry = agent_tools.ToolRegistry()
    agent_tools.register_local_helpers(registry)
    registry.register_system(ButtondownServer())
    return registry


async def run(args: argparse.Namespace) -> int:
    selected = {args.persona: PERSONAS[args.persona]} if args.persona else PERSONAS
    required_purposes = set(selected)
    if args.regen or not questions_cache_ready():
        required_purposes.add("general")
    try:
        anthropic_client.validate_keys(required_purposes)
    except RuntimeError as exc:
        logger.error("%s", exc)
        return 2

    db.run_migrations()
    corpus_handle = corpus.load()
    deps = Deps(corpus=corpus_handle, registry=_build_registry())

    questions = load_or_generate_questions(regen=args.regen)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = TMP / f"workshop_eval_{ts}"
    out_dir.mkdir(parents=True, exist_ok=True)
    logger.info("writing reports to %s", out_dir)

    summary_rows: list[dict[str, Any]] = []
    for name, cls in selected.items():
        summary_rows.append(
            await run_persona(name, cls, deps, questions[name], args.model, out_dir)
        )

    # SUMMARY.md
    summary: list[str] = []
    summary.append(f"# Workshop bot eval — {ts}")
    summary.append("")
    summary.append(f"- model: `{args.model}`")
    summary.append(f"- questions per persona: {QUESTIONS_PER_PERSONA}")
    summary.append("")
    summary.append("| persona | errors | total time | tokens (in) | tokens (out) |")
    summary.append("|---|---|---|---|---|")
    for row in summary_rows:
        summary.append(
            f"| {row['name']} | {row['errors']}/{QUESTIONS_PER_PERSONA} "
            f"| {row['total_seconds']:.1f}s "
            f"| {row['total_in_tokens']:,} | {row['total_out_tokens']:,} |"
        )
    summary.append("")
    summary.append("Per-persona reports:")
    for row in summary_rows:
        summary.append(f"- [{row['name']}](./{row['name']}.md)")
    (out_dir / "SUMMARY.md").write_text("\n".join(summary), encoding="utf-8")

    print(f"\nSummary written to {out_dir / 'SUMMARY.md'}")
    report_paths = ", ".join(str(out_dir / f"{r['name']}.md") for r in summary_rows)
    print(f"Reports: {report_paths}")
    return 0


def main() -> int:
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--regen", action="store_true", help="regenerate the cached question set")
    parser.add_argument("--persona", choices=list(PERSONAS), help="run only one persona")
    parser.add_argument("--model", default="haiku", choices=list(anthropic_client.MODELS))
    args = parser.parse_args()
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
