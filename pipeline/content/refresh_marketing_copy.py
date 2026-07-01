#!/usr/bin/env python3
"""Refresh the home page voice samples and creative brief.

Single-pass pipeline:
  Sonnet 4.6 reads a stratified sample of recent issues (~32 issues over
  the last 2 years) plus the existing creative brief, reader survey data,
  and reader testimonials. It returns: themes, voice markers, candidate
  pull-quotes (verbatim), the 3–5 selected voice samples for the home
  page, running observations, and a fully rewritten brief.

Writes two files (unless --dry-run):
  - apps/site/_data/voiceSamples.json
  - pipeline/content/marketing-brief.md  (this script's persistent context)

Also writes a run log to tmp/copy-refresh-<ts>.json for auditability.

Usage:
  python pipeline/content/refresh_marketing_copy.py --dry-run
  python pipeline/content/refresh_marketing_copy.py
  python pipeline/content/refresh_marketing_copy.py --sample-size 24 --seed 42
"""
from __future__ import annotations

import argparse
import json
import random
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from pydantic import BaseModel, Field

sys.stdout.reconfigure(line_buffering=True)
load_dotenv()

REPO = Path(__file__).resolve().parents[2]
ARCHIVE = REPO / "apps" / "site" / "archive"
DATA = REPO / "apps" / "site" / "_data"
BRIEF_PATH = REPO / "pipeline" / "content" / "marketing-brief.md"
VOICE_PATH = DATA / "voiceSamples.json"
EMAILS_PATH = DATA / "emails.json"
SURVEY_PATH = DATA / "survey.json"
QUOTES_PATH = DATA / "quotes.json"
TMP = REPO / "tmp"
TMP.mkdir(exist_ok=True)

SONNET = "claude-sonnet-5"
DEFAULT_SAMPLE = 32
DEFAULT_WINDOW_DAYS = 730
RECENT_ANCHOR = 6
BUCKETS = 6
# Cap each issue body so the corpus doesn't balloon past ~150K tokens on
# a default run. Full issues commonly run 6–10K tokens; the first ~4K
# tokens reliably contain the voice, subject framing, and the top-of-
# issue commentary. Tail material is usually link descriptions that add
# breadth but not voice signal.
MAX_BODY_CHARS = 16000

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.S)
RAW_WRAP_RE = re.compile(r"\{%\s*(?:end)?raw\s*%\}")


# ───────────────────────── structured output models ─────────────────────────

class Theme(BaseModel):
    label: str = Field(description="2–4 word theme label")
    description: str = Field(description="One concrete sentence. No hype. No superlatives.")
    exampleIssue: int = Field(description="An issue number from the sample that best exemplifies the theme.")


class VoiceSample(BaseModel):
    text: str = Field(description="Verbatim excerpt from the issue body. 1–3 sentences, ≤350 chars. No ellipses or editorial brackets unless present in source.")
    issueNumber: int
    issueTitle: str = Field(description="Formatted as '#N — Subject' using the real subject line.")


class SonnetFindings(BaseModel):
    themes: list[Theme] = Field(description="3–6 recurring themes visible across the sample (not just topics — recurring moves/angles).")
    voiceMarkers: list[str] = Field(description="3–6 short evidence-based observations about how Jamie writes.")
    candidateQuotes: list[VoiceSample] = Field(description="6–12 candidate pull-quotes, verbatim. Favor passages where Jamie's voice is on display.")
    selectedQuotes: list[VoiceSample] = Field(description="3–5 quotes from candidateQuotes, ordered by strength. These become the voice samples on the home page.")
    observations: str = Field(description="2–4 sentence running-notes paragraph for the brief's Open observations section.")
    recurringThemesNotes: str = Field(description="Markdown-bulleted list (3–6 bullets) for the brief's Recurring themes section. Each bullet ≤20 words.")
    updatedBrief: str = Field(description="Full rewritten content of pipeline/content/marketing-brief.md. Preserve the Voice / What makes it unique / What to avoid sections verbatim from the existing brief; only update Recurring themes and Open observations sections using your recurringThemesNotes and observations. Preserve all headings and markdown formatting.")


# ───────────────────────── loading / sampling ─────────────────────────

def load_issue(num: int) -> tuple[str, str]:
    path = ARCHIVE / f"{num}.md"
    raw = path.read_text(encoding="utf-8")
    m = FRONTMATTER_RE.match(raw)
    if not m:
        return "", raw
    fm, body = m.group(1), m.group(2)
    sm = re.search(r"^subject:\s*(.+)$", fm, re.M)
    subject = sm.group(1).strip().strip("'").strip('"') if sm else ""
    body = RAW_WRAP_RE.sub("", body).strip()
    return subject, body


def parse_pub(e: dict) -> datetime:
    return datetime.fromisoformat(e["publish_date"].replace("Z", "+00:00"))


def stratified_sample(emails: list[dict], n: int, window_days: int, seed: int) -> list[int]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    in_window = [
        e for e in emails
        if e.get("publish_date") and e.get("number")
        and parse_pub(e) >= cutoff
    ]
    in_window.sort(key=parse_pub, reverse=True)

    recent = in_window[:RECENT_ANCHOR]
    rest = in_window[RECENT_ANCHOR:]

    rng = random.Random(seed)
    need = max(0, n - len(recent))
    per_bucket = max(1, need // max(1, BUCKETS))
    picks: list[dict] = []
    if rest:
        bucket_size = max(1, len(rest) // BUCKETS)
        for b in range(BUCKETS):
            lo = b * bucket_size
            hi = (b + 1) * bucket_size if b < BUCKETS - 1 else len(rest)
            bucket = rest[lo:hi]
            if not bucket:
                continue
            k = min(per_bucket, len(bucket))
            picks.extend(rng.sample(bucket, k))

    combined = recent + picks
    seen: set[int] = set()
    ordered: list[int] = []
    for e in combined:
        num = int(e["number"])
        if num not in seen:
            seen.add(num)
            ordered.append(num)
    return sorted(ordered[:n])


# ───────────────────────── prompt building ─────────────────────────

SONNET_SYSTEM_TMPL = """You are the analyst and editor for "The Weekly Thing," a newsletter Jamie Thingelstad has published weekly since May 2017.

Your role: read a sample of recent issues plus the existing creative brief, reader survey data, and reader testimonials. Produce (a) raw analytical material about themes and voice, (b) the 3–5 selected verbatim pull-quotes that should appear on the home page's "How it sounds" section, and (c) a refreshed creative brief.

You do NOT write marketing copy. Your job is editorial: surface what's actually in the archive and let it speak for itself.

## The current creative brief

{brief}

## Reader survey data

These are real survey results. The numbers reflect how readers describe the newsletter. They may inform your understanding of voice but do not appear in your output.

```json
{survey}
```

## Reader testimonial quotes

Real subscriber quotes. They may inform your understanding of voice but do not appear in your output.

```json
{quotes}
```

## Output rules

- `themes`: 3–6 recurring themes (not topics — recurring moves/angles like "engineering with care" or "small craft notices"). Each `exampleIssue` must be a number from the sample.
- `voiceMarkers`: 3–6 short observations about how Jamie writes. Be specific and evidence-based.
- `candidateQuotes`: 6–12 verbatim pull-quotes. Favor passages where Jamie's voice is on display: observational, dry, curious, specific, occasionally opinionated. No editorial brackets or ellipses unless present in source.
- `selectedQuotes`: 3–5 of the candidateQuotes ordered by strength. These will appear on the home page. Prefer range (observational + opinionated + personal + curious). Keep text VERBATIM — they will be machine-verified against the issue body.
- `observations`: 2–4 sentence running-notes paragraph for the brief's "Open observations" section.
- `recurringThemesNotes`: Markdown-bulleted list (3–6 bullets) for the brief's "Recurring themes" section. Each bullet ≤20 words.
- `updatedBrief`: Return the complete rewritten content of `pipeline/content/marketing-brief.md`. Copy the Voice, What makes it unique, and What to avoid sections VERBATIM from the creative brief above. Update only the Recurring themes and Open observations sections using your `recurringThemesNotes` and `observations`. Preserve all headings and markdown formatting.

## Hard rules

- Issue numbers must be real and present in the sample.
- Quote text must be verbatim from an issue body — including punctuation and capitalization.
- No hype, no superlatives, no invention.
- If a theme isn't clearly recurring, don't force it — return fewer."""


# ───────────────────────── API call ─────────────────────────

def call_sonnet(
    client: anthropic.Anthropic,
    brief: str,
    corpus: str,
    survey: dict,
    quotes: list,
) -> tuple[SonnetFindings, dict]:
    system = SONNET_SYSTEM_TMPL.format(
        brief=brief,
        survey=json.dumps(survey, indent=2),
        quotes=json.dumps(quotes, indent=2),
    )
    user = f"Here is the sample.\n\n{corpus}\n\nReturn your structured findings."

    t0 = time.monotonic()
    resp = client.messages.parse(
        model=SONNET,
        max_tokens=8000,
        system=[{"type": "text", "text": system}],
        messages=[{"role": "user", "content": user}],
        output_format=SonnetFindings,
    )
    dur = round(time.monotonic() - t0, 2)
    usage = {
        "input_tokens": resp.usage.input_tokens,
        "output_tokens": resp.usage.output_tokens,
        "duration_s": dur,
    }
    # Sonnet 4.6: ~$3/M in, $15/M out
    cost = (usage["input_tokens"] * 3.0 + usage["output_tokens"] * 15.0) / 1_000_000
    usage["est_cost_usd"] = round(cost, 4)
    return resp.parsed_output, usage


# ───────────────────────── verification ─────────────────────────

def _norm(s: str) -> str:
    return (
        s.replace("‘", "'").replace("’", "'")
         .replace("“", '"').replace("”", '"')
         .replace("–", "-").replace("—", "-")
         .replace(" ", " ")
         .strip()
    )


def verify_voice_samples(
    samples: list[VoiceSample], bodies: dict[int, str]
) -> tuple[list[VoiceSample], list[dict]]:
    ok: list[VoiceSample] = []
    rejected: list[dict] = []
    for s in samples:
        body = bodies.get(s.issueNumber, "")
        if s.text in body or _norm(s.text) in _norm(body):
            ok.append(s)
        else:
            rejected.append({"issue": s.issueNumber, "text": s.text[:120]})
    return ok, rejected


def select_voice_samples(
    findings: SonnetFindings, bodies: dict[int, str]
) -> tuple[list[VoiceSample], list[dict]]:
    """Verify selectedQuotes; if too few pass, fall back to candidateQuotes."""
    verified, rejected = verify_voice_samples(findings.selectedQuotes, bodies)
    if len(verified) >= 3:
        return verified, rejected
    # Fall back: try candidateQuotes that aren't already in verified set.
    seen = {(s.issueNumber, s.text) for s in verified}
    extras = [c for c in findings.candidateQuotes if (c.issueNumber, c.text) not in seen]
    extra_verified, extra_rejected = verify_voice_samples(extras, bodies)
    return verified + extra_verified[: max(0, 5 - len(verified))], rejected + extra_rejected


# ───────────────────────── main ─────────────────────────

def format_corpus(numbers: list[int]) -> tuple[str, dict[int, str]]:
    parts: list[str] = []
    bodies: dict[int, str] = {}
    for n in numbers:
        subject, body = load_issue(n)
        # Keep the full body for verbatim-quote verification; truncate
        # only the copy sent to the analyst.
        bodies[n] = body
        truncated = body
        if len(body) > MAX_BODY_CHARS:
            truncated = body[:MAX_BODY_CHARS] + "\n\n…(issue continues — body truncated for analysis)…"
        parts.append(f"===== Issue #{n} — {subject} =====\n\n{truncated}\n")
    return "\n\n".join(parts), bodies


def write_outputs(
    findings: SonnetFindings,
    verified_samples: list[VoiceSample],
) -> None:
    VOICE_PATH.write_text(
        json.dumps(
            [s.model_dump() for s in verified_samples], indent=2, ensure_ascii=False
        ) + "\n"
    )
    print(f"[refresh] wrote {VOICE_PATH.relative_to(REPO)}", flush=True)

    BRIEF_PATH.write_text(findings.updatedBrief.rstrip() + "\n")
    print(f"[refresh] wrote {BRIEF_PATH.relative_to(REPO)}", flush=True)


def print_git_diff_stat(paths: list[Path]) -> None:
    try:
        rel = [str(p.relative_to(REPO)) for p in paths]
        r = subprocess.run(
            ["git", "-C", str(REPO), "diff", "--stat", "--", *rel],
            capture_output=True, text=True, check=False,
        )
        if r.stdout.strip():
            print("\n--- git diff --stat ---")
            print(r.stdout)
    except Exception as e:
        print(f"[refresh] could not run git diff: {e}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="Run the full pipeline but don't write output files.")
    ap.add_argument("--sample-size", type=int, default=DEFAULT_SAMPLE)
    ap.add_argument("--window-days", type=int, default=DEFAULT_WINDOW_DAYS)
    ap.add_argument("--seed", type=int, default=int(time.time()) // 86400, help="Random seed for sampling. Defaults to today's day-of-epoch so two runs on the same day are deterministic.")
    ap.add_argument("--print-sample", action="store_true", help="Print the sampled issue numbers and exit.")
    args = ap.parse_args()

    if "ANTHROPIC_GENERAL_API_KEY" not in __import__("os").environ and not args.print_sample:
        print("ERROR: ANTHROPIC_GENERAL_API_KEY not set in environment (or .env).", file=sys.stderr)
        return 2

    print(f"[refresh] loading archive index from {EMAILS_PATH.relative_to(REPO)}", flush=True)
    emails = json.loads(EMAILS_PATH.read_text())
    numbers = stratified_sample(emails, args.sample_size, args.window_days, args.seed)
    print(f"[refresh] sampled {len(numbers)} issues over last {args.window_days} days (seed={args.seed})", flush=True)
    print(f"[refresh] issues: {numbers}", flush=True)

    if args.print_sample:
        return 0

    brief = BRIEF_PATH.read_text()
    survey = json.loads(SURVEY_PATH.read_text())
    quotes = json.loads(QUOTES_PATH.read_text())

    corpus, bodies = format_corpus(numbers)
    corpus_tokens = len(corpus) // 4  # rough
    print(f"[refresh] corpus ~{corpus_tokens:,} tokens ({len(corpus):,} chars)", flush=True)

    client = anthropic.Anthropic(api_key=__import__("os").environ["ANTHROPIC_GENERAL_API_KEY"])

    print(f"[refresh] calling Sonnet ({SONNET})...", flush=True)
    findings, sonnet_usage = call_sonnet(client, brief, corpus, survey, quotes)
    print(
        f"[refresh]  sonnet: {sonnet_usage['input_tokens']:,}+{sonnet_usage['output_tokens']:,} tok, "
        f"{sonnet_usage['duration_s']}s, ~${sonnet_usage['est_cost_usd']}",
        flush=True,
    )
    print(f"[refresh]  themes: {len(findings.themes)}, "
          f"candidates: {len(findings.candidateQuotes)}, "
          f"selected: {len(findings.selectedQuotes)}, "
          f"markers: {len(findings.voiceMarkers)}", flush=True)

    verified, rejected = select_voice_samples(findings, bodies)
    if rejected:
        print(f"[refresh] WARNING: dropped {len(rejected)} voice sample(s) not found verbatim:", flush=True)
        for r in rejected:
            print(f"  - #{r['issue']}: {r['text']}...", flush=True)
    if len(verified) < 3:
        print(f"[refresh] WARNING: only {len(verified)} verbatim voice samples — consider re-running.", flush=True)

    # Run log
    run_log_path = TMP / f"copy-refresh-{int(time.time())}.json"
    run_log_path.write_text(json.dumps({
        "sample": numbers,
        "seed": args.seed,
        "sonnet_usage": sonnet_usage,
        "total_cost_usd": sonnet_usage["est_cost_usd"],
        "findings": findings.model_dump(),
        "verified_samples": [s.model_dump() for s in verified],
        "rejected_samples": rejected,
    }, indent=2, ensure_ascii=False))
    print(f"[refresh] run log: {run_log_path.relative_to(REPO)}", flush=True)
    print(f"[refresh] total estimated cost: ~${sonnet_usage['est_cost_usd']}", flush=True)

    if args.dry_run:
        print("\n[refresh] --dry-run: not writing output files.")
        print("\n--- voice samples (verified) ---")
        for s in verified:
            print(f"  #{s.issueNumber}: {s.text[:120]}...")
        print("\n--- updated brief (first 600 chars) ---")
        print(findings.updatedBrief[:600])
        return 0

    write_outputs(findings, verified)
    print_git_diff_stat([VOICE_PATH, BRIEF_PATH])
    return 0


if __name__ == "__main__":
    sys.exit(main())
