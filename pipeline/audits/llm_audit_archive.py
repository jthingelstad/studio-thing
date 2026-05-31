#!/usr/bin/env python3
"""
LLM-powered semantic audit of every archive issue.

Sends the raw markdown body of each issue to Claude (Opus 4.7) with
era context and the prior static-audit findings. Claude returns
structured findings (category + severity + verbatim snippet + why +
suggested fix). Snippets are verified against the source before being
accepted, which kills most hallucinations.

Output:
  tmp/llm-audit.json     machine-parseable findings per issue + usage
  tmp/llm-audit.md       human-readable report

Usage:
  python pipeline/audits/llm_audit_archive.py --sample 5
  python pipeline/audits/llm_audit_archive.py --issues 15,45,132,247,319
  python pipeline/audits/llm_audit_archive.py --full
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Literal

import anthropic
from pydantic import BaseModel, Field

sys.stdout.reconfigure(line_buffering=True)

REPO = Path(__file__).resolve().parents[2]
ARCHIVE = REPO / "apps" / "site" / "archive"
OUT = REPO / "tmp"
OUT.mkdir(exist_ok=True)

MODEL = "claude-opus-4-7"
CONCURRENCY = 4
MAX_TOKENS_OUT = 4000


# ---------- era detection ----------

def era_for(num: int) -> str:
    if num <= 41:
        return "Tinyletter"
    if num <= 130:
        return "MailChimp"
    return "Buttondown"


ERA_CONTEXT = {
    "Tinyletter": (
        "Issues #1–#41 (May 2017 – Feb 2018). Plain markdown, inline links, "
        "no H2 section structure expected. Bare H3 link lists are era-normal. "
        "Early issues may have a date stamp at the top."
    ),
    "MailChimp": (
        "Issues #42–~#130 (Mar 2018 – late 2019). Emoji-suffixed H2 section "
        "names are canonical: `## Featured Links 🏅`, `## Notable Links 📌`, "
        "`## Yet More Links 🍞`, `## Microposts 🎈`, `## Fortune 🥠`, "
        "`## Give Back 🎁`, `## My Weekly Photo 📷`. Link titles under sections "
        "are H3: `### [Title](url)`. Some early-era MailChimp issues are "
        "plain-text with bare URLs — this is era-normal, not a bug. Templated "
        "headers at the top may have been stripped already."
    ),
    "Buttondown": (
        "Issues #131+ (2020 – present). Canonical section names: `## Notable`, "
        "`## Featured`, `## Briefly`, `## Must Read`, `## Currently`, "
        "`## Fortune`, `## Journal`, `## Microposts`, `## Recommended Links`, "
        "`## Status Updates`, `## FYI`, `## Reply All`. Link titles are H3: "
        "`### [Title](url)`. `{% raw %}` wrappers and "
        "`<!-- buttondown-editor-mode: plaintext -->` preamble are era-normal "
        "(stripped at render) — do NOT flag these."
    ),
}


SYSTEM_PROMPT = """You are auditing one issue of "The Weekly Thing," a newsletter Jamie Thingelstad has published weekly since May 2017. The archive was migrated across three email platforms; each issue retains its era's style.

Your job: find problems that would affect a reader of the archive website. A static regex/DOM audit has already run — you will receive its findings for this issue. Validate those, and add anything the static audit missed.

Focus on:
- Narrative breaks: sentences that truncate mid-word/clause; missing paragraph breaks from migration; orphaned quote fragments
- Dangling references: "see image above/below" with no image nearby; "[read more]" without a link; cross-issue references like "#45" that dangle without context
- Malformed links: bracketed text that clearly lost its URL (e.g., `[LWN.net]` followed by plain text when it should be a link). NOTE: `[sic]`, `[...]`, `[Updated]`, `[video]`, `[Event Title]` are valid prose — do NOT flag these.
- Header-level mistakes that break the TOC: body H1 (never correct — page title is H1), inconsistent levels within a section, orphan headings
- Encoding / migration artifacts: literal template tags like `{{ email_url }}`, Mailchimp merge tags like `*|ARCHIVE|*`, mojibake (â€™, Ã©), double-encoded HTML entities, stray HTML fragments
- Image problems visible in source: obviously-broken URLs, images referenced in text but missing from the body, hotlinked images from dead hosts
- Typos — only very obvious, non-stylistic ones. Don't nitpick.

DO NOT flag:
- Era-normal style (emoji H2s in MailChimp era, bare H3 lists in Tinyletter era)
- `{% raw %}` / `{% endraw %}` wrappers — these are intentional Nunjucks escapes
- `<!-- buttondown-editor-mode: plaintext -->` HTML comment — stripped at render
- Editorial choices, stylistic preferences, content quality opinions
- Valid markdown that renders correctly
- Minor whitespace
- Typos you're less than 95% sure about

For each finding return:
- category: one of `narrative-break`, `dangling-reference`, `malformed-link`, `header-error`, `migration-artifact`, `image-problem`, `typo`, `other`
- severity: `high` (breaks reading / renders visibly wrong), `medium` (degraded but readable), `low` (nitpick / low-confidence)
- exact_snippet: verbatim text from the markdown that demonstrates the problem, ≤180 characters. Must appear EXACTLY in the body as shown — no paraphrasing, no truncation markers, no fixing quotes or punctuation.
- why: one sentence explaining the issue
- suggested_fix: one sentence saying what an editor should change

Also return:
- overall_assessment: one sentence on whether the issue is in good shape; note the main concern if any.

Return exactly one `report_findings` call. If the issue is clean, return an empty `findings` array and a positive overall_assessment. Do not flag era-normal patterns."""


# ---------- data model ----------

Category = Literal[
    "narrative-break",
    "dangling-reference",
    "malformed-link",
    "header-error",
    "migration-artifact",
    "image-problem",
    "typo",
    "other",
]
Severity = Literal["high", "medium", "low"]


class Finding(BaseModel):
    category: Category
    severity: Severity
    exact_snippet: str
    why: str
    suggested_fix: str


class Report(BaseModel):
    findings: list[Finding]
    overall_assessment: str


# ---------- loading ----------

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.S)
RAW_WRAP_RE = re.compile(r"\{%\s*(?:end)?raw\s*%\}")


def load_issue(num: int) -> tuple[str, str]:
    """Return (subject, stripped_body)."""
    path = ARCHIVE / f"{num}.md"
    raw = path.read_text(encoding="utf-8")
    m = FRONTMATTER_RE.match(raw)
    if not m:
        return "", raw
    fm, body = m.group(1), m.group(2)
    subject_m = re.search(r"^subject:\s*(.+)$", fm, re.M)
    subject = ""
    if subject_m:
        subject = subject_m.group(1).strip().strip("'").strip('"')
    body = RAW_WRAP_RE.sub("", body).strip()
    return subject, body


def prior_findings_for(num: int, index: dict[int, dict]) -> list[dict]:
    rep = index.get(num)
    if not rep:
        return []
    out = []
    for f in rep.get("findings", []):
        out.append({
            "category": f.get("category"),
            "detail": f.get("detail"),
            "snippet": (f.get("snippet") or "")[:140],
        })
    return out


# ---------- LLM call ----------

async def audit_one(
    client: anthropic.AsyncAnthropic,
    sem: asyncio.Semaphore,
    num: int,
    subject: str,
    body: str,
    prior: list[dict],
) -> dict:
    era = era_for(num)
    era_ctx = ERA_CONTEXT[era]

    user_msg = (
        f"# Issue #{num}\n"
        f"**Era:** {era}\n"
        f"**Era context:** {era_ctx}\n"
        f"**Subject line:** {subject}\n\n"
        f"## Prior static-audit findings ({len(prior)})\n"
        f"{json.dumps(prior, indent=2) if prior else '(none)'}\n\n"
        f"## Markdown body\n"
        f"```markdown\n{body}\n```"
    )

    async with sem:
        t0 = time.monotonic()
        try:
            resp = await client.messages.parse(
                model=MODEL,
                max_tokens=MAX_TOKENS_OUT,
                thinking={"type": "disabled"},
                system=[{
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }],
                messages=[{"role": "user", "content": user_msg}],
                output_format=Report,
            )
        except Exception as e:
            # Catch API errors, pydantic validation errors, anything.
            # We still want the rest of the 344 runs to complete.
            print(f"[#{num}] ERROR {type(e).__name__}: {str(e)[:200]}", flush=True)
            return {
                "number": num,
                "error": f"{type(e).__name__}: {str(e)[:400]}",
                "findings": [],
                "rejected_findings": [],
                "overall_assessment": "",
                "usage": {},
                "duration_s": round(time.monotonic() - t0, 2),
            }

        duration = round(time.monotonic() - t0, 2)

    report: Report = resp.parsed_output
    # Verify snippets appear in body. Normalize typographic characters
    # first — models often substitute ASCII quotes for smart quotes and
    # vice versa, which otherwise rejects valid findings.
    def _norm(s: str) -> str:
        return (
            s.replace("\u2018", "'").replace("\u2019", "'")
             .replace("\u201c", '"').replace("\u201d", '"')
             .replace("\u2013", "-").replace("\u2014", "-")
             .replace("\u00a0", " ")
        )

    norm_body = _norm(body)
    verified: list[dict] = []
    rejected: list[dict] = []
    for f in report.findings:
        snippet = f.exact_snippet.strip()
        if not snippet:
            rejected.append({**f.model_dump(), "rejection_reason": "empty snippet"})
            continue
        if snippet in body or _norm(snippet) in norm_body:
            verified.append(f.model_dump())
        else:
            rejected.append({**f.model_dump(), "rejection_reason": "snippet not found in body"})

    usage = {
        "input_tokens": resp.usage.input_tokens,
        "output_tokens": resp.usage.output_tokens,
        "cache_read_input_tokens": getattr(resp.usage, "cache_read_input_tokens", 0) or 0,
        "cache_creation_input_tokens": getattr(resp.usage, "cache_creation_input_tokens", 0) or 0,
    }

    print(
        f"[#{num}] {len(verified)} verified, {len(rejected)} rejected | "
        f"{usage['input_tokens']}+{usage['output_tokens']} tok | "
        f"cache r/w: {usage['cache_read_input_tokens']}/{usage['cache_creation_input_tokens']} | "
        f"{duration}s",
        flush=True,
    )

    return {
        "number": num,
        "subject": subject,
        "era": era,
        "findings": verified,
        "rejected_findings": rejected,
        "overall_assessment": report.overall_assessment,
        "usage": usage,
        "duration_s": duration,
    }


# ---------- orchestration ----------

async def run(numbers: list[int], index: dict[int, dict]) -> list[dict]:
    client = anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_GENERAL_API_KEY"])
    sem = asyncio.Semaphore(CONCURRENCY)

    async def task(num: int) -> dict:
        subject, body = load_issue(num)
        prior = prior_findings_for(num, index)
        return await audit_one(client, sem, num, subject, body, prior)

    results = await asyncio.gather(*(task(n) for n in numbers))
    return sorted(results, key=lambda r: r["number"])


# ---------- reports ----------

def write_reports(results: list[dict]) -> None:
    total_in = sum(r["usage"].get("input_tokens", 0) for r in results if r.get("usage"))
    total_out = sum(r["usage"].get("output_tokens", 0) for r in results if r.get("usage"))
    total_read = sum(r["usage"].get("cache_read_input_tokens", 0) for r in results if r.get("usage"))
    total_write = sum(r["usage"].get("cache_creation_input_tokens", 0) for r in results if r.get("usage"))
    total_findings = sum(len(r.get("findings", [])) for r in results)
    total_rejected = sum(len(r.get("rejected_findings", [])) for r in results)

    # approximate cost for Opus 4.7
    cost_input = (total_in + total_write * 1.25 + total_read * 0.1) * 5.0 / 1_000_000
    cost_output = total_out * 25.0 / 1_000_000
    est_cost = cost_input + cost_output

    json_path = OUT / "llm-audit.json"
    json_path.write_text(
        json.dumps(
            {
                "model": MODEL,
                "issues_scanned": len(results),
                "total_findings": total_findings,
                "total_rejected_snippets": total_rejected,
                "usage_totals": {
                    "input_tokens": total_in,
                    "output_tokens": total_out,
                    "cache_read_input_tokens": total_read,
                    "cache_creation_input_tokens": total_write,
                    "est_cost_usd": round(est_cost, 4),
                },
                "results": results,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"[llm-audit] wrote {json_path}", flush=True)

    # Markdown
    lines: list[str] = []
    lines.append("# LLM Archive Audit")
    lines.append("")
    lines.append(f"Model: `{MODEL}`")
    lines.append(f"Issues scanned: **{len(results)}**")
    lines.append(f"Verified findings: **{total_findings}**")
    lines.append(f"Rejected (snippet not found in source): {total_rejected}")
    lines.append(f"Tokens: {total_in:,} in + {total_out:,} out (cache r/w {total_read:,}/{total_write:,})")
    lines.append(f"Estimated cost: ~${est_cost:.2f}")
    lines.append("")

    # Severity tally across verified findings
    sev_counts = {"high": 0, "medium": 0, "low": 0}
    cat_counts: dict[str, int] = {}
    for r in results:
        for f in r.get("findings", []):
            sev_counts[f["severity"]] = sev_counts.get(f["severity"], 0) + 1
            cat_counts[f["category"]] = cat_counts.get(f["category"], 0) + 1

    lines.append("## Verified findings by severity")
    lines.append("")
    for sev in ("high", "medium", "low"):
        lines.append(f"- `{sev}`: {sev_counts.get(sev, 0)}")
    lines.append("")

    lines.append("## Verified findings by category")
    lines.append("")
    for cat in sorted(cat_counts, key=lambda k: -cat_counts[k]):
        lines.append(f"- `{cat}`: {cat_counts[cat]}")
    lines.append("")

    # Per-issue detail — include only issues with findings or error
    interesting = [r for r in results if r.get("findings") or r.get("error")]
    if interesting:
        lines.append("## Per-issue findings")
        lines.append("")
        for r in interesting:
            n = r["number"]
            lines.append(f"### #{n} — {r.get('subject', '')}")
            lines.append("")
            lines.append(f"- Era: {r.get('era')}")
            lines.append(f"- Overall: {r.get('overall_assessment', '').strip()}")
            if r.get("error"):
                lines.append(f"- **Error:** {r['error']}")
            for f in r.get("findings", []):
                sev = f["severity"].upper()
                snip = f["exact_snippet"].replace("`", "´")
                lines.append(f"  - **[{sev}] {f['category']}** — {f['why']}")
                lines.append(f"    - `{snip}`")
                lines.append(f"    - Fix: {f['suggested_fix']}")
            lines.append("")

    # Also list clean issues briefly
    clean = [r for r in results if not r.get("findings") and not r.get("error")]
    if clean:
        lines.append(f"## Clean issues ({len(clean)})")
        lines.append("")
        lines.append(", ".join(f"#{r['number']}" for r in clean))
        lines.append("")

    md_path = OUT / "llm-audit.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[llm-audit] wrote {md_path}", flush=True)


# ---------- CLI ----------

def resolve_numbers(args) -> list[int]:
    all_nums = sorted(
        int(p.stem) for p in ARCHIVE.glob("*.md") if p.stem.isdigit()
    )
    if args.issues:
        wanted = [int(x.strip()) for x in args.issues.split(",") if x.strip()]
        return [n for n in wanted if n in all_nums]
    if args.sample:
        # Distributed sample across eras
        picks: list[int] = []
        if any(n <= 41 for n in all_nums):
            tinyletters = [n for n in all_nums if n <= 41]
            picks.append(tinyletters[len(tinyletters) // 2])
        if any(42 <= n <= 130 for n in all_nums):
            mc = [n for n in all_nums if 42 <= n <= 130]
            picks.append(mc[len(mc) // 2])
        buttondown = [n for n in all_nums if n >= 131]
        # include some from Buttondown era, including known-noisy ones
        for cand in [247, 319, 232, 310]:
            if cand in buttondown and cand not in picks:
                picks.append(cand)
            if len(picks) >= args.sample:
                break
        # pad with evenly-distributed buttondowns if needed
        i = 0
        while len(picks) < args.sample and buttondown:
            cand = buttondown[(i * 37) % len(buttondown)]
            if cand not in picks:
                picks.append(cand)
            i += 1
            if i > 1000:
                break
        return sorted(picks[: args.sample])
    if args.full:
        return all_nums
    raise SystemExit("Must pass --sample N, --issues ..., or --full")


def main() -> None:
    global CONCURRENCY
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--sample", type=int, help="Run on N distributed sample issues")
    g.add_argument("--issues", type=str, help="Comma-separated issue numbers")
    g.add_argument("--full", action="store_true", help="Run on every issue")
    ap.add_argument("--concurrency", type=int, default=CONCURRENCY)
    args = ap.parse_args()
    CONCURRENCY = args.concurrency

    # Load prior static-audit findings
    prior_path = OUT / "archive-audit.json"
    index: dict[int, dict] = {}
    if prior_path.exists():
        data = json.loads(prior_path.read_text())
        for rep in data.get("reports", []):
            index[rep["number"]] = rep
        print(f"[llm-audit] loaded {len(index)} prior reports", flush=True)
    else:
        print("[llm-audit] no prior static audit found — proceeding without", flush=True)

    numbers = resolve_numbers(args)
    print(f"[llm-audit] auditing {len(numbers)} issue(s): {numbers[:20]}"
          f"{'...' if len(numbers) > 20 else ''}", flush=True)
    results = asyncio.run(run(numbers, index))
    write_reports(results)


if __name__ == "__main__":
    main()
