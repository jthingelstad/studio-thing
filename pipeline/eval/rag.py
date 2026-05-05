"""Print retrieval diagnostics for a small librarian RAG question set."""

from __future__ import annotations

import argparse
import importlib
import os
import sys
from pathlib import Path


QUESTIONS = [
    "What has Jamie said about AI agents recently?",
    "How has Jamie's thinking about RSS changed over time?",
    "What does the archive say about privacy and security?",
    "What themes show up around travel and place?",
    "What has changed in productivity and personal systems over the years?",
]

MULTI_HOP_QUESTIONS = [
    "Give me a 30-minute reading path on AI agents with older context and recent examples.",
    "Did Jamie ever say that RSS was subversive, and what else around that idea should I read?",
    "How did links to github.com show up across the archive, and what patterns changed?",
    "Compare what the archive said about privacy in 2017 versus 2024.",
    "What did Jamie seem to change his mind about around productivity systems?",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--question-set", choices=["standard", "multi-hop", "all"], default="standard")
    parser.add_argument("--no-rerank", action="store_true")
    args = parser.parse_args()

    os.environ.setdefault("SESSION_SECRET", "eval-only")
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    app = importlib.import_module("services.librarian.api.app")
    if args.question_set == "multi-hop":
        questions = MULTI_HOP_QUESTIONS
    elif args.question_set == "all":
        questions = QUESTIONS + MULTI_HOP_QUESTIONS
    else:
        questions = QUESTIONS
    for question in questions:
        print(f"\n## {question}")
        for source in app.retrieve(question, limit=args.limit, rerank=not args.no_rerank):
            modes = ",".join(source.get("retrieval_modes", []))
            topics = ", ".join(source.get("topics", [])[:3])
            rerank = f" rerank={source.get('_rerank_score')}" if source.get("_rerank_score") is not None else ""
            print(
                f"- #{source.get('issue_number')} "
                f"{str(source.get('publish_date') or '')[:10]} "
                f"{source.get('source_kind', 'chunk')} "
                f"[{modes}] "
                f"{source.get('section')}: {source.get('subject')} "
                f"({source.get('age_label', '')}; {topics}{rerank})"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
