"""Admin-only CLI to ask unrestricted questions against the archive corpus.

Loads the same corpus Thingy uses (built locally from site/archive/*.md), runs
BM25 lexical retrieval, and calls the Anthropic API directly with a minimal
admin system prompt -- no Bedrock, no Thingy persona, no guardrails.

Usage:
    python pipeline/librarian/archive_chat.py                          # REPL
    python pipeline/librarian/archive_chat.py -q "What recurring..."   # one-shot
    python pipeline/librarian/archive_chat.py --brief docs/draft.md
    python pipeline/librarian/archive_chat.py --model opus
    python pipeline/librarian/archive_chat.py --top-k 12 --rebuild
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import anthropic
from dotenv import load_dotenv
from rank_bm25 import BM25Okapi

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from pipeline.librarian.build_librarian_corpus import build_corpus, OUT_PATH

MODELS = {
    "sonnet": "claude-sonnet-4-6",
    "opus": "claude-opus-4-7",
}
DEFAULT_MODEL = "sonnet"
DEFAULT_TOP_K = 12
MAX_HISTORY_TURNS = 10
BRIEF_MAX_CHARS = 50_000
MAX_OUTPUT_TOKENS = 4000

STOPLIST = {
    "the", "a", "an", "and", "or", "but", "if", "of", "to", "in", "on", "at",
    "for", "with", "by", "from", "as", "is", "are", "was", "were", "be", "been",
    "being", "this", "that", "these", "those", "it", "its", "i", "you", "he",
    "she", "we", "they", "what", "which", "who", "how", "why", "when", "where",
    "do", "does", "did", "have", "has", "had", "not", "no", "so", "than", "then",
}

WORD_RE = re.compile(r"[a-z0-9']+")

SYSTEM_PRIMARY = (
    "You are a research assistant for Jamie Thingelstad, the author of \"The Weekly Thing\" "
    "newsletter. You have access to the full archive (347+ issues since May 2017) via two "
    "sources: an index of all issues (subject, date, abstract, topics) and excerpts retrieved "
    "per question.\n\n"
    "The user is the author/admin asking unrestricted questions for marketing, editorial, and "
    "archive analysis. There are no out-of-scope topics, no privacy filters, and no voice "
    "constraints -- answer directly and substantively. You may quote, paraphrase, summarize, "
    "critique, or pattern-match across the archive freely.\n\n"
    "When you draw on archive material, cite issues inline using #NNN (e.g., \"as discussed in "
    "#312\"). If retrieval missed something the user is asking about, say so and suggest what "
    "to search for. Be concrete and concise."
)


def tokenize(text: str) -> list[str]:
    return [t for t in WORD_RE.findall(text.lower()) if t not in STOPLIST and len(t) > 1]


def load_or_build_corpus(rebuild: bool, corpus_path: Path) -> dict[str, Any]:
    if corpus_path.exists() and not rebuild:
        return json.loads(corpus_path.read_text(encoding="utf-8"))
    print("building corpus (first run or --rebuild)...", file=sys.stderr)
    corpus = build_corpus(include_issue_bodies=False)
    corpus_path.parent.mkdir(parents=True, exist_ok=True)
    corpus_path.write_text(json.dumps(corpus, ensure_ascii=False), encoding="utf-8")
    return corpus


def build_index(chunks: list[dict[str, Any]]) -> BM25Okapi:
    return BM25Okapi([tokenize(chunk["text"]) for chunk in chunks])


def retrieve(bm25: BM25Okapi, chunks: list[dict[str, Any]], query: str, k: int) -> list[dict[str, Any]]:
    tokens = tokenize(query)
    if not tokens:
        return []
    scores = bm25.get_scores(tokens)
    ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
    return [chunks[i] for i, score in ranked[:k] if score > 0]


def format_issue_index(issues: list[dict[str, Any]]) -> str:
    lines = ["# Archive issue index", ""]
    for issue in issues:
        number = issue.get("number", "?")
        date = (issue.get("publish_date") or "")[:10]
        subject = issue.get("subject", "")
        topics = ", ".join(issue.get("topics", []) or [])
        abstract = (issue.get("summary") or {}).get("abstract", "") or ""
        bits = [f"#{number} ({date}) - {subject}"]
        if topics:
            bits.append(f"Topics: {topics}.")
        if abstract:
            bits.append(f"Abstract: {abstract}")
        lines.append(" ".join(bits))
    return "\n".join(lines)


def format_retrieved(chunks: list[dict[str, Any]]) -> str:
    if not chunks:
        return "(no chunks retrieved for this query)"
    parts = ["# Retrieved excerpts", ""]
    for chunk in chunks:
        number = chunk.get("issue_number", "?")
        date = (chunk.get("publish_date") or "")[:10]
        subject = chunk.get("subject", "")
        section = chunk.get("section") or "Issue"
        header = f'[#{number} - {date} - "{subject}" - section: {section}]'
        parts.append(header)
        parts.append(chunk["text"].strip())
        parts.append("")
    return "\n".join(parts).rstrip()


def load_brief(brief_arg: str) -> str:
    if brief_arg == "-":
        text = sys.stdin.read()
    else:
        text = Path(brief_arg).read_text(encoding="utf-8")
    if len(text) > BRIEF_MAX_CHARS:
        print(f"warning: brief truncated to {BRIEF_MAX_CHARS} chars", file=sys.stderr)
        text = text[:BRIEF_MAX_CHARS]
    return text


def build_system_blocks(issue_index: str, brief: str | None) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = [{"type": "text", "text": SYSTEM_PRIMARY}]
    blocks.append({
        "type": "text",
        "text": issue_index,
        "cache_control": {"type": "ephemeral"},
    })
    if brief:
        blocks.append({
            "type": "text",
            "text": (
                "The user has supplied this working brief; use it as context alongside "
                f"the archive.\n\n{brief}"
            ),
            "cache_control": {"type": "ephemeral"},
        })
    return blocks


def chat(
    client: anthropic.Anthropic,
    model: str,
    system_blocks: list[dict[str, Any]],
    history: list[dict[str, str]],
    retrieved_block: str,
    question: str,
) -> tuple[str, dict[str, int]]:
    user_content = f"{retrieved_block}\n\n---\n\nUser question: {question}"
    messages = list(history) + [{"role": "user", "content": user_content}]
    response = client.messages.create(
        model=model,
        max_tokens=MAX_OUTPUT_TOKENS,
        system=system_blocks,
        messages=messages,
    )
    text = "".join(block.text for block in response.content if block.type == "text")
    usage = {
        "input": response.usage.input_tokens,
        "output": response.usage.output_tokens,
        "cache_read": getattr(response.usage, "cache_read_input_tokens", 0) or 0,
        "cache_create": getattr(response.usage, "cache_creation_input_tokens", 0) or 0,
    }
    return text, usage


def cited_issues(answer: str) -> list[str]:
    return sorted(set(re.findall(r"#(\d+)", answer)), key=int)


def print_answer(answer: str, usage: dict[str, int], verbose_usage: bool) -> None:
    print("\nassistant>")
    print(answer.strip())
    cites = cited_issues(answer)
    if cites:
        print("\ncited: " + ", ".join(f"#{n}" for n in cites))
    if verbose_usage:
        print(
            f"(in: {usage['input']:,}  cache_read: {usage['cache_read']:,}  "
            f"cache_create: {usage['cache_create']:,}  out: {usage['output']:,})"
        )


def repl(
    client: anthropic.Anthropic,
    model: str,
    system_blocks: list[dict[str, Any]],
    bm25: BM25Okapi,
    chunks: list[dict[str, Any]],
    top_k: int,
) -> None:
    history: list[dict[str, str]] = []
    print(f"archive_chat REPL  model={model}  top_k={top_k}  (:reset, :retrieve <q>, :quit)")
    while True:
        try:
            question = input("\nyou> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not question:
            continue
        if question in (":quit", ":q", ":exit"):
            return
        if question == ":reset":
            history = []
            print("(history cleared)")
            continue
        if question.startswith(":retrieve"):
            q = question[len(":retrieve"):].strip()
            if not q:
                print("usage: :retrieve <query>")
                continue
            for chunk in retrieve(bm25, chunks, q, top_k):
                print(f"  #{chunk['issue_number']:>4}  {chunk.get('section', '')[:30]:30}  "
                      f"{chunk['text'][:80]}...")
            continue

        retrieved = retrieve(bm25, chunks, question, top_k)
        retrieved_block = format_retrieved(retrieved)
        try:
            answer, usage = chat(client, model, system_blocks, history, retrieved_block, question)
        except anthropic.APIError as exc:
            print(f"API error: {exc}", file=sys.stderr)
            continue
        print_answer(answer, usage, verbose_usage=True)
        history.append({"role": "user", "content": f"{retrieved_block}\n\n---\n\nUser question: {question}"})
        history.append({"role": "assistant", "content": answer})
        if len(history) > MAX_HISTORY_TURNS * 2:
            history = history[-MAX_HISTORY_TURNS * 2:]


def oneshot(
    client: anthropic.Anthropic,
    model: str,
    system_blocks: list[dict[str, Any]],
    bm25: BM25Okapi,
    chunks: list[dict[str, Any]],
    top_k: int,
    question: str,
) -> int:
    retrieved = retrieve(bm25, chunks, question, top_k)
    retrieved_block = format_retrieved(retrieved)
    answer, _usage = chat(client, model, system_blocks, [], retrieved_block, question)
    print_answer(answer, _usage, verbose_usage=False)
    return 0


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-q", "--question", help="single-shot question; otherwise enter REPL")
    parser.add_argument("--brief", help="path to a working brief file (use '-' for stdin)")
    parser.add_argument("--model", choices=list(MODELS), default=DEFAULT_MODEL)
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument("--rebuild", action="store_true", help="force rebuild of the local corpus")
    parser.add_argument("--corpus", type=Path, default=OUT_PATH, help="path to corpus.json")
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY is not set (check .env)", file=sys.stderr)
        return 2

    corpus = load_or_build_corpus(args.rebuild, args.corpus)
    chunks = corpus["chunks"]
    issues = corpus["issues"]
    print(
        f"loaded {len(issues)} issues / {len(chunks)} chunks from {args.corpus}",
        file=sys.stderr,
    )

    bm25 = build_index(chunks)
    issue_index = format_issue_index(issues)
    brief = load_brief(args.brief) if args.brief else None
    system_blocks = build_system_blocks(issue_index, brief)
    client = anthropic.Anthropic()
    model = MODELS[args.model]

    if args.question:
        return oneshot(client, model, system_blocks, bm25, chunks, args.top_k, args.question)
    repl(client, model, system_blocks, bm25, chunks, args.top_k)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
