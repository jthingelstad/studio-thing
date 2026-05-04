"""BM25 lexical retrieval over librarian corpus chunks."""

from __future__ import annotations

import re
from typing import Any

from rank_bm25 import BM25Okapi


STOPLIST = {
    "the", "a", "an", "and", "or", "but", "if", "of", "to", "in", "on", "at",
    "for", "with", "by", "from", "as", "is", "are", "was", "were", "be", "been",
    "being", "this", "that", "these", "those", "it", "its", "i", "you", "he",
    "she", "we", "they", "what", "which", "who", "how", "why", "when", "where",
    "do", "does", "did", "have", "has", "had", "not", "no", "so", "than", "then",
}

WORD_RE = re.compile(r"[a-z0-9']+")


def tokenize(text: str) -> list[str]:
    return [t for t in WORD_RE.findall(text.lower()) if t not in STOPLIST and len(t) > 1]


def build_index(chunks: list[dict[str, Any]]) -> BM25Okapi:
    return BM25Okapi([tokenize(chunk["text"]) for chunk in chunks])


def retrieve(bm25: BM25Okapi, chunks: list[dict[str, Any]], query: str, k: int) -> list[dict[str, Any]]:
    tokens = tokenize(query)
    if not tokens:
        return []
    scores = bm25.get_scores(tokens)
    ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
    return [chunks[i] for i, score in ranked[:k] if score > 0]
