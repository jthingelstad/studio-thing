"""Build the archive corpus + BM25 index once at bot startup.

Reuses librarian_core. The corpus is a dict with `chunks`, `issues`, `topics`,
`links`, etc. The BM25 index is built from `chunks`.
"""

from __future__ import annotations

import logging
from typing import Any

from librarian_core.corpus import build_corpus
from librarian_core.retrieval import build_index, retrieve

from . import archive

logger = logging.getLogger("workshop.corpus")


class CorpusHandle:
    def __init__(self, corpus: dict[str, Any], bm25: Any) -> None:
        self.corpus = corpus
        self.bm25 = bm25
        self.chunks: list[dict[str, Any]] = corpus["chunks"]
        self.latest_issue_number = archive.latest_issue_number(corpus["issues"])

    def search(self, query: str, k: int = 12) -> list[dict[str, Any]]:
        return retrieve(self.bm25, self.chunks, query, k)


def load() -> CorpusHandle:
    logger.info("Building archive corpus...")
    corpus = build_corpus(include_issue_bodies=False)
    logger.info("Corpus ready: %d issues, %d chunks", corpus["issue_count"], corpus["chunk_count"])
    bm25 = build_index(corpus["chunks"])
    return CorpusHandle(corpus, bm25)
