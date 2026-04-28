#!/usr/bin/env python3
"""Refresh the home page marketing copy using an LLM 'creative team'.

Two-pass pipeline:
  1. Sonnet 4.6 reads a stratified sample of recent issues (~48 issues
     over the last 2 years) plus the creative brief. Returns structured
     findings: themes, voice markers, candidate pull-quotes, running
     observations.
  2. Opus 4.7 reads the analyst's findings + the brief + the current
     copy.json + archive stats. Returns new copy.json fields, polished
     voiceSamples, and a rewritten brief.

Writes three files (unless --dry-run):
  - site/_data/copy.json
  - site/_data/voiceSamples.json
  - docs/creative/brief.md

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
from typing import Optional

import anthropic
from dotenv import load_dotenv
from pydantic import BaseModel, Field

sys.stdout.reconfigure(line_buffering=True)
load_dotenv()

REPO = Path(__file__).resolve().parents[2]
ARCHIVE = REPO / "site" / "archive"
DATA = REPO / "site" / "_data"
BRIEF_PATH = REPO / "docs" / "creative" / "brief.md"
COPY_PATH = DATA / "copy.json"
VOICE_PATH = DATA / "voiceSamples.json"
EMAILS_PATH = DATA / "emails.json"
SURVEY_PATH = DATA / "survey.json"
QUOTES_PATH = DATA / "quotes.json"
TMP = REPO / "tmp"
TMP.mkdir(exist_ok=True)

SONNET = "claude-sonnet-4-6"
OPUS = "claude-opus-4-7"
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
    observations: str = Field(description="2–4 sentence running-notes paragraph for the brief's Open observations section.")
    recurringThemesNotes: str = Field(description="Markdown-bulleted list (3–6 bullets) for the brief's Recurring themes section. Each bullet ≤20 words.")


class HeroCopy(BaseModel):
    eyebrow: str = Field(description="≤50 chars. Byline framing.")
    tagline: str = Field(description="1–2 sentences describing what the newsletter is. Concrete, specific.")


class ValueProp(BaseModel):
    headline: str = Field(description="Main value-prop headline. A single '<br>' is allowed for a deliberate line break; no other HTML.")
    paragraphs: list[str] = Field(description="2–3 paragraphs. Each is plain prose. No HTML.")


class WhatYouGet(BaseModel):
    headline: str = Field(description="Section headline, ≤50 chars.")
    lede: str = Field(description="One-sentence intro above the theme cards.")
    themes: list[Theme] = Field(description="3–4 theme cards, each with a real exampleIssue from the sample.")


class CTA(BaseModel):
    headline: Optional[str] = None
    proof: Optional[str] = None
    body: Optional[str] = None


class Sections(BaseModel):
    readersSay: str
    voiceTitle: str
    membership: str


class CTAs(BaseModel):
    hero: CTA
    mid1: CTA
    mid2: CTA
    footer: CTA


class OpusOutput(BaseModel):
    hero: HeroCopy
    valueProp: ValueProp
    whatYouGet: WhatYouGet
    sections: Sections
    ctas: CTAs
    voiceSamples: list[VoiceSample] = Field(description="3–5 voice samples drawn from the analyst's candidateQuotes, ordered by strength.")
    updatedBrief: str = Field(description="Full rewritten docs/creative/brief.md. Preserve the Voice / What makes it unique / What to avoid sections verbatim; only update Recurring themes and Open observations.")


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


def load_archive_stats() -> dict:
    """Read the computed archive stats by shelling to node. Simpler and
    more accurate than re-implementing the .js logic here."""
    # Fallback: compute minimal stats from emails.json directly.
    emails = json.loads(EMAILS_PATH.read_text())
    numbers = []
    for e in emails:
        n = e.get("number")
        if n is None:
            continue
        try:
            numbers.append(int(n))
        except (ValueError, TypeError):
            continue
    by_year: dict[str, int] = {}
    for e in emails:
        if not e.get("publish_date"):
            continue
        y = str(parse_pub(e).year)
        by_year[y] = by_year.get(y, 0) + 1
    return {
        "total_issues": len(numbers),
        "earliest_issue": min(numbers) if numbers else None,
        "latest_issue": max(numbers) if numbers else None,
        "issues_by_year": dict(sorted(by_year.items())),
        "years_active": max(1, len(by_year)),
    }


# ───────────────────────── prompt building ─────────────────────────

SONNET_SYSTEM_TMPL = """You are the analyst for "The Weekly Thing," a newsletter Jamie Thingelstad has published weekly since May 2017.

Your role: read a sample of recent issues plus the existing creative brief, reader survey data, and reader testimonials, then extract the raw material the copywriter will use. You do NOT write marketing copy. You analyze.

## The current creative brief

{brief}

## Reader survey data (what real subscribers say)

Use this to ground your themes and voice markers in what readers actually value. If readers consistently report feeling a certain way, note whether the sampled issues justify that.

```json
{survey}
```

## Reader testimonial quotes (authentic reader voice)

These are real subscriber quotes from reader surveys. Treat them as evidence of how readers describe the newsletter — useful for identifying language the copywriter can lean on.

```json
{quotes}
```

## What to return

- themes: 3–6 recurring themes observable across the sample. Not topics — recurring angles or moves (e.g., "uses personal anecdote to frame a technology argument," not "AI"). Each theme needs a real exampleIssue from the sample.
- voiceMarkers: 3–6 short, evidence-based observations about how Jamie writes. Ground each in something you saw.
- candidateQuotes: 6–12 verbatim excerpts (1–3 sentences, ≤350 chars each) that are characteristic. Prefer passages where Jamie's voice is on display — curiosity, opinion, observation, not just description or link summary. The text must appear EXACTLY as written in the source. issueTitle format: "#N — Subject" using the real subject line.
- observations: 2–4 sentences for the brief's "Open observations" section. What's interesting? What's shifted lately? Write in a voice suitable for a long-lived working document, not a report.
- recurringThemesNotes: 3–6 markdown bullets for the brief's "Recurring themes" section. Each bullet ≤20 words.

## Rules

- Issue numbers must be real and present in the sample.
- Quote text must be verbatim from an issue body.
- No hype, no superlatives, no invention.
- If a theme isn't clearly recurring, don't force it — return fewer."""


OPUS_SYSTEM_TMPL = """You are the copywriter for the home page of "The Weekly Thing," a newsletter by Jamie Thingelstad. You rewrite the site copy based on (a) the creative brief (authoritative guardrails), (b) the analyst's findings from the recent archive, and (c) real reader survey data and testimonial quotes.

## Creative brief

{brief}

## Reader survey data (the only numbers about readers you may cite)

These are real survey results. You may reference the numeric stats verbatim (recommendation score, read-whole-issue rate, long-time reader rate) and you may use the feeling-word list to inform tone — but do not invent new statistics or attribute specific percentages to effects not measured here.

```json
{survey}
```

## Reader testimonial quotes

Real subscriber quotes. Use these to hear how readers describe the newsletter in their own words. You may borrow phrasings and framings from these, but do not put quotation marks around invented reader speech.

```json
{quotes}
```

## Hard guardrails — these override everything

- No superlatives: "best," "amazing," "unmatched," "premier," "leading," "essential."
- No empty marketing phrases: "cutting-edge," "curated with care," "hand-picked," "thought leader," "game-changing."
- No second-person ad-speak: "Level up!" "Unlock!" "Supercharge!"
- No invented statistics. Only use the numbers in the Archive stats block below.
- No claims about reader benefits that aren't demonstrable from the sampled issues.
- Match Jamie's voice as evidenced in the analyst's candidate quotes: observational, dry, curious, specific.
- Prefer concrete over general. "47 links about agentic engineering in the last year" beats "stay on top of AI."
- The value-prop headline may use one `<br>` tag for a deliberate line break; no other HTML anywhere.
- Do not use em-dashes in CTA headlines. Em-dashes are fine in prose.

## Current home page copy (what you are replacing)

```json
{current_copy}
```

## Archive stats (the only numbers you may cite)

```json
{stats}
```

## Output rules

- Every field is required.
- Vary phrasing across the four CTAs (`ctas.hero.proof`, `ctas.mid1.headline`, `ctas.mid2.headline`, `ctas.footer.headline`/`body`). They all appear on the same page; seeing the same sentence four times is embarrassing.
- `whatYouGet.themes`: 3–4 cards. Each theme label is 2–4 words. Each description is one concrete sentence. Each `exampleIssue` must come from the analyst's themes or sample.
- `voiceSamples`: 3–5 quotes from the analyst's `candidateQuotes`. Prefer range (observational + opinionated + personal + curious). Keep text verbatim.
- `updatedBrief`: return the complete rewritten content of `docs/creative/brief.md`. Copy the Voice, What makes it unique, and What to avoid sections VERBATIM from the creative brief above. Update only the Recurring themes and Open observations sections using the analyst's `recurringThemesNotes` and `observations`. Preserve all headings and markdown formatting.

Return one structured response and nothing else."""


# ───────────────────────── API calls ─────────────────────────

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
        max_tokens=6000,
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


def call_opus(
    client: anthropic.Anthropic,
    brief: str,
    current_copy: dict,
    findings: SonnetFindings,
    stats: dict,
    survey: dict,
    quotes: list,
) -> tuple[OpusOutput, dict]:
    system = OPUS_SYSTEM_TMPL.format(
        brief=brief,
        current_copy=json.dumps(current_copy, indent=2),
        stats=json.dumps(stats, indent=2),
        survey=json.dumps(survey, indent=2),
        quotes=json.dumps(quotes, indent=2),
    )
    user = (
        "The analyst has returned the following findings. Use them to "
        "write the final home page copy.\n\n"
        "```json\n"
        f"{findings.model_dump_json(indent=2)}\n"
        "```\n\n"
        "Return the complete structured output."
    )

    t0 = time.monotonic()
    resp = client.messages.parse(
        model=OPUS,
        max_tokens=8000,
        system=[{"type": "text", "text": system}],
        messages=[{"role": "user", "content": user}],
        output_format=OpusOutput,
    )
    dur = round(time.monotonic() - t0, 2)
    usage = {
        "input_tokens": resp.usage.input_tokens,
        "output_tokens": resp.usage.output_tokens,
        "duration_s": dur,
    }
    # Opus 4.7: ~$5/M in, $25/M out (same as 4.x — approximation)
    cost = (usage["input_tokens"] * 5.0 + usage["output_tokens"] * 25.0) / 1_000_000
    usage["est_cost_usd"] = round(cost, 4)
    return resp.parsed_output, usage


# ───────────────────────── verification ─────────────────────────

def _norm(s: str) -> str:
    return (
        s.replace("\u2018", "'").replace("\u2019", "'")
         .replace("\u201c", '"').replace("\u201d", '"')
         .replace("\u2013", "-").replace("\u2014", "-")
         .replace("\u00a0", " ")
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
    out: OpusOutput,
    verified_samples: list[VoiceSample],
    sampled_numbers: list[int],
) -> None:
    new_copy = {
        "hero": out.hero.model_dump(),
        "valueProp": out.valueProp.model_dump(),
        "whatYouGet": out.whatYouGet.model_dump(),
        "sections": out.sections.model_dump(),
        "ctas": {
            "hero": out.ctas.hero.model_dump(exclude_none=True),
            "mid1": out.ctas.mid1.model_dump(exclude_none=True),
            "mid2": out.ctas.mid2.model_dump(exclude_none=True),
            "footer": out.ctas.footer.model_dump(exclude_none=True),
        },
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "sampledIssues": sampled_numbers,
    }
    COPY_PATH.write_text(json.dumps(new_copy, indent=2, ensure_ascii=False) + "\n")
    print(f"[refresh] wrote {COPY_PATH.relative_to(REPO)}", flush=True)

    VOICE_PATH.write_text(
        json.dumps(
            [s.model_dump() for s in verified_samples], indent=2, ensure_ascii=False
        ) + "\n"
    )
    print(f"[refresh] wrote {VOICE_PATH.relative_to(REPO)}", flush=True)

    BRIEF_PATH.write_text(out.updatedBrief.rstrip() + "\n")
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

    if "ANTHROPIC_API_KEY" not in __import__("os").environ and not args.print_sample:
        print("ERROR: ANTHROPIC_API_KEY not set in environment (or .env).", file=sys.stderr)
        return 2

    print(f"[refresh] loading archive index from {EMAILS_PATH.relative_to(REPO)}", flush=True)
    emails = json.loads(EMAILS_PATH.read_text())
    numbers = stratified_sample(emails, args.sample_size, args.window_days, args.seed)
    print(f"[refresh] sampled {len(numbers)} issues over last {args.window_days} days (seed={args.seed})", flush=True)
    print(f"[refresh] issues: {numbers}", flush=True)

    if args.print_sample:
        return 0

    brief = BRIEF_PATH.read_text()
    current_copy = json.loads(COPY_PATH.read_text())
    stats = load_archive_stats()
    survey = json.loads(SURVEY_PATH.read_text())
    quotes = json.loads(QUOTES_PATH.read_text())

    corpus, bodies = format_corpus(numbers)
    corpus_tokens = len(corpus) // 4  # rough
    print(f"[refresh] corpus ~{corpus_tokens:,} tokens ({len(corpus):,} chars)", flush=True)

    client = anthropic.Anthropic()

    print(f"[refresh] calling Sonnet ({SONNET})...", flush=True)
    findings, sonnet_usage = call_sonnet(client, brief, corpus, survey, quotes)
    print(
        f"[refresh]  sonnet: {sonnet_usage['input_tokens']:,}+{sonnet_usage['output_tokens']:,} tok, "
        f"{sonnet_usage['duration_s']}s, ~${sonnet_usage['est_cost_usd']}",
        flush=True,
    )
    print(f"[refresh]  themes: {len(findings.themes)}, "
          f"quotes: {len(findings.candidateQuotes)}, "
          f"markers: {len(findings.voiceMarkers)}", flush=True)

    print(f"[refresh] calling Opus ({OPUS})...", flush=True)
    out, opus_usage = call_opus(client, brief, current_copy, findings, stats, survey, quotes)
    print(
        f"[refresh]  opus:   {opus_usage['input_tokens']:,}+{opus_usage['output_tokens']:,} tok, "
        f"{opus_usage['duration_s']}s, ~${opus_usage['est_cost_usd']}",
        flush=True,
    )

    # Verify voice samples are verbatim
    verified, rejected = verify_voice_samples(out.voiceSamples, bodies)
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
        "opus_usage": opus_usage,
        "total_cost_usd": round(sonnet_usage["est_cost_usd"] + opus_usage["est_cost_usd"], 4),
        "findings": findings.model_dump(),
        "output": out.model_dump(),
        "verified_samples": [s.model_dump() for s in verified],
        "rejected_samples": rejected,
    }, indent=2, ensure_ascii=False))
    print(f"[refresh] run log: {run_log_path.relative_to(REPO)}", flush=True)

    total_cost = round(sonnet_usage["est_cost_usd"] + opus_usage["est_cost_usd"], 4)
    print(f"[refresh] total estimated cost: ~${total_cost}", flush=True)

    if args.dry_run:
        print("\n[refresh] --dry-run: not writing output files.")
        print("\n--- proposed hero ---")
        print(json.dumps(out.hero.model_dump(), indent=2, ensure_ascii=False))
        print("\n--- proposed valueProp ---")
        print(json.dumps(out.valueProp.model_dump(), indent=2, ensure_ascii=False))
        print("\n--- proposed whatYouGet ---")
        print(json.dumps(out.whatYouGet.model_dump(), indent=2, ensure_ascii=False))
        print("\n--- proposed CTAs ---")
        print(json.dumps({k: getattr(out.ctas, k).model_dump(exclude_none=True) for k in ("hero", "mid1", "mid2", "footer")}, indent=2, ensure_ascii=False))
        print("\n--- voice samples (verified) ---")
        for s in verified:
            print(f"  #{s.issueNumber}: {s.text[:120]}...")
        return 0

    write_outputs(out, verified, numbers)
    print_git_diff_stat([COPY_PATH, VOICE_PATH, BRIEF_PATH])
    return 0


if __name__ == "__main__":
    sys.exit(main())
