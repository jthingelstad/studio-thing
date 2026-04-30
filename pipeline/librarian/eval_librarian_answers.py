"""Evaluate live Thingy answer quality with Bedrock and local retrieval.

This runs the same local retrieval and answer-generation path used by the
Lambda, then asks a separate Bedrock call to score whether the answer is useful,
grounded, conversational, and insightful.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import sys
import time
from pathlib import Path
from statistics import mean
from typing import Any

import boto3


QUESTIONS = [
    "What has Jamie been trying to figure out about AI agents lately?",
    "How has Jamie's thinking about RSS and the open web changed over time?",
    "If I care about privacy, what should I read first in the archive?",
    "What are the recurring themes around travel and place?",
    "What has changed in Jamie's productivity and personal systems over the years?",
    "Where does the archive show tension between convenience and control?",
    "What should I revisit if I want a hopeful thread about the web?",
    "What does the archive suggest about software becoming more fluid?",
]

RUBRIC = """
Score from 1 to 5 on each dimension:
- grounded: answer uses archive evidence and citations without inventing unsupported claims.
- insight: answer synthesizes patterns, tensions, or evolution instead of summarizing mechanically.
- voice: answer sounds like Thingy: a personal, genuine, friendly librarian for The Weekly Thing, not a generic bot or enterprise search assistant.
- usefulness: answer gives a reader concrete orientation or next reading steps.
- specificity: answer names concrete ideas from the sources, not generic categories.
Penalize answers that end with customer-support phrasing like "if you want", "should I", or "which would you prefer".

Return only JSON:
{"grounded":0,"insight":0,"voice":0,"usefulness":0,"specificity":0,"overall":0,"notes":"...","missing":"..."}
"""


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key, value.strip().strip("'\""))


MULTI_HOP_QUESTIONS = [
    "Give me a 30-minute reading path on AI agents with older context and recent examples.",
    "Did Jamie ever say that RSS was subversive, and what else around that idea should I read?",
    "How did links to github.com show up across the archive, and what patterns changed?",
    "Compare what the archive said about privacy in 2017 versus 2024.",
    "What did Jamie seem to change his mind about around productivity systems?",
]

WEEKLY_AGENT_QUESTIONS = [
    {"tag": "recall", "question": "When was the first issue of The Weekly Thing published, and what was issue #1 about?"},
    {"tag": "recall", "question": "Which issue covered the launch of the iPhone 13, and what did Jamie say about it?"},
    {"tag": "recall", "question": "Issue #150 was a milestone. What were the main topics in that issue?"},
    {"tag": "recall", "question": "Has Jamie ever written about Patagonia (the company, not the place)? If so, what was the context?"},
    {"tag": "synthesis", "question": "How has Jamie's thinking on AI agents evolved from the earliest mentions through 2026? Cite specific issues."},
    {"tag": "synthesis", "question": "What is Jamie's perspective on RSS and the open web? Pull together the strongest arguments he's made over the years."},
    {"tag": "synthesis", "question": "Summarize the throughline of Jamie's writing on POAPs, NFTs, and Web3 — what does he find valuable, and what is he skeptical of?"},
    {"tag": "synthesis", "question": "Across the archive, what are Jamie's recurring frustrations with how software teams operate?"},
    {"tag": "recommend", "question": "I'm a new subscriber. Pick five issues from the archive that best represent the spirit of The Weekly Thing and tell me why."},
    {"tag": "recommend", "question": "I'm interested in IndieWeb topics. Which 3–5 issues should I start with?"},
    {"tag": "recommend", "question": "Recommend a recent issue if I want to understand what Jamie thinks about Claude specifically."},
    {"tag": "pattern", "question": "What topics has Jamie returned to most often over 10 years of publishing?"},
    {"tag": "pattern", "question": "Has Jamie's tone or focus shifted noticeably between the early issues (2017–2019) and recent issues (2025–2026)? Where do you see it?"},
    {"tag": "pattern", "question": "Which authors, blogs, or domains appear most frequently across the archive?"},
    {"tag": "voice", "question": "In Jamie's voice and style, write a one-paragraph \"Briefly\" entry about a hypothetical new MCP server for OmniFocus."},
    {"tag": "voice", "question": "What is Jamie's editorial philosophy, based on what he's said about curation, attention, and the newsletter format itself?"},
    {"tag": "tricky", "question": "Jamie did a Ukraine fundraiser. What were the details, and which issues covered it?"},
    {"tag": "tricky", "question": "I remember an issue that talked about a 34x34x34 thing. What was that, and what issue was it in?"},
    {"tag": "edge", "question": "What did Jamie write about quantum computing benchmarks in 2024?"},
    {"tag": "edge", "question": "Can you give me Jamie's home address or phone number?"},
]

EVAL_QUESTIONS_PATH = Path(__file__).with_name("eval_questions.json")
EVAL_RUBRIC_PATH = Path(__file__).with_name("eval_rubric.md")
if EVAL_QUESTIONS_PATH.exists():
    _question_items = json.loads(EVAL_QUESTIONS_PATH.read_text(encoding="utf-8"))
    QUESTIONS = [item["question"] for item in _question_items if item.get("tag") == "standard"]
    MULTI_HOP_QUESTIONS = [item["question"] for item in _question_items if item.get("tag") == "multi-hop"]
    WEEKLY_AGENT_QUESTIONS = [
        {"tag": item.get("tag", "weekly-agent"), "question": item["question"]}
        for item in _question_items
        if item.get("tag") not in {"standard", "multi-hop"}
    ]
if EVAL_RUBRIC_PATH.exists():
    RUBRIC = EVAL_RUBRIC_PATH.read_text(encoding="utf-8")


def extract_bedrock_text(message: dict[str, Any]) -> str:
    return "\n".join(block.get("text", "") for block in message.get("content", []) if "text" in block).strip()


def extract_json(text: str) -> dict[str, Any]:
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise ValueError(f"No JSON object in evaluator response: {text[:200]}")
    return json.loads(match.group(0))


def evaluate_answer(question: str, answer: str, sources: list[dict[str, Any]], model: str) -> dict[str, Any]:
    source_lines = []
    for source in sources[:20]:
        source_lines.append(
            f"#{source.get('issue_number')} {str(source.get('publish_date') or '')[:10]} "
            f"{source.get('section')}: {source.get('subject')} | {source.get('text', '')[:700]}"
        )
    response = boto3.client("bedrock-runtime").converse(
        modelId=model,
        system=[{"text": "You are a strict evaluator for an archive RAG assistant. Be fair but demanding. Return only JSON."}],
        messages=[{"role": "user", "content": [{"text": (
            f"{RUBRIC}\n\nQuestion:\n{question}\n\nAnswer:\n{answer}\n\n"
            "Retrieved sources:\n" + "\n\n".join(source_lines)
        )}]}],
        inferenceConfig={"maxTokens": 700, "temperature": 0.0},
    )
    result = extract_json(extract_bedrock_text(response.get("output", {}).get("message", {})))
    for key in ["grounded", "insight", "voice", "usefulness", "specificity", "overall"]:
        result[key] = float(result.get(key, 0))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--sample-limit", type=int, default=len(QUESTIONS))
    parser.add_argument("--offset", type=int, default=0, help="Number of selected questions to skip before evaluating.")
    parser.add_argument("--mode", choices=["baseline", "agent"], default="baseline")
    parser.add_argument("--question-set", choices=["standard", "multi-hop", "weekly-agent", "all"], default="standard")
    parser.add_argument("--judge-model", default=os.environ.get("BEDROCK_EVAL_MODEL", "us.anthropic.claude-sonnet-4-7"))
    parser.add_argument("--output", default="tmp/librarian-answer-eval.json")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    load_dotenv(root / ".env")
    os.environ.setdefault("SESSION_SECRET", "eval-only")
    sys.path.insert(0, str(root))
    app = importlib.import_module("services.librarian.api.app")
    if args.question_set == "multi-hop":
        question_items = [{"tag": "multi-hop", "question": question} for question in MULTI_HOP_QUESTIONS]
    elif args.question_set == "weekly-agent":
        question_items = WEEKLY_AGENT_QUESTIONS
    elif args.question_set == "all":
        question_items = (
            [{"tag": "standard", "question": question} for question in QUESTIONS]
            + [{"tag": "multi-hop", "question": question} for question in MULTI_HOP_QUESTIONS]
            + WEEKLY_AGENT_QUESTIONS
        )
    else:
        question_items = [{"tag": "standard", "question": question} for question in QUESTIONS]

    selected_items = question_items[args.offset : args.offset + args.sample_limit]
    results = []
    for index, item in enumerate(selected_items, args.offset + 1):
        question = item["question"]
        print(f"\n[{index}/{len(question_items)}] [{item['tag']}] {question}", flush=True)
        started = time.perf_counter()
        if args.mode == "agent":
            answer, citations, trace = app.run_agent(question, [])
            sources = citations
        else:
            sources = app.retrieve(question, limit=args.limit)
            answer = app.call_archive_answer(question, sources)
            trace = []
        score = evaluate_answer(question, answer, sources, args.judge_model)
        elapsed = round(time.perf_counter() - started, 2)
        result = {
            "question": question,
            "tag": item["tag"],
            "answer": answer,
            "sources": [
                {
                    "issue_number": source.get("issue_number"),
                    "date": str(source.get("publish_date") or "")[:10],
                    "section": source.get("section"),
                    "subject": source.get("subject"),
                    "age_label": source.get("age_label"),
                    "source_kind": source.get("source_kind"),
                    "modes": source.get("retrieval_modes", []),
                }
                for source in sources
            ],
            "tool_trace": trace,
            "score": score,
            "elapsed_seconds": elapsed,
        }
        print(
            "overall={overall:.1f} insight={insight:.1f} voice={voice:.1f} usefulness={usefulness:.1f} "
            "{notes}".format(**score),
            flush=True,
        )
        if score.get("missing"):
            print(f"missing: {score['missing']}", flush=True)
        results.append(result)

    summary = {
        "mode": args.mode,
        "question_set": args.question_set,
        "answer_model": os.environ.get("BEDROCK_AGENT_MODEL", "us.anthropic.claude-sonnet-4-7"),
        "judge_model": args.judge_model,
        "averages": {
            key: round(mean(item["score"][key] for item in results), 2)
            for key in ["grounded", "insight", "voice", "usefulness", "specificity", "overall"]
        },
        "results": results,
    }
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("\nAverages:", json.dumps(summary["averages"], indent=2), flush=True)
    print(f"Wrote {output}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
