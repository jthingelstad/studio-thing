"""CLI entrypoint: build the citation-ready Another Thing podcast corpus."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from librarian_core.corpus import (
    DEFAULT_EMBEDDING_DIMENSIONS,
    DEFAULT_EMBEDDING_MODEL,
    add_bedrock_embeddings,
    build_podcast_corpus,
)
from librarian_core.paths import PODCAST_CORPUS_PATH, PODCAST_DIR

OUT_PATH = PODCAST_CORPUS_PATH

__all__ = [
    "DEFAULT_EMBEDDING_DIMENSIONS",
    "DEFAULT_EMBEDDING_MODEL",
    "OUT_PATH",
    "PODCAST_DIR",
    "add_bedrock_embeddings",
    "build_podcast_corpus",
    "main",
]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a citation-ready corpus for Another Thing transcripts."
    )
    parser.add_argument(
        "--input-dir", type=Path, default=PODCAST_DIR, help="Normalized episode JSON directory"
    )
    parser.add_argument("--output", default=str(PODCAST_CORPUS_PATH), help="Output JSON path")
    parser.add_argument(
        "--embed", action="store_true", help="Add Bedrock Cohere embeddings to each chunk"
    )
    parser.add_argument("--embedding-model", default=DEFAULT_EMBEDDING_MODEL)
    parser.add_argument("--embedding-dimensions", type=int, default=DEFAULT_EMBEDDING_DIMENSIONS)
    args = parser.parse_args()

    corpus = build_podcast_corpus(args.input_dir)
    if args.embed:
        add_bedrock_embeddings(corpus, args.embedding_model, args.embedding_dimensions)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(corpus, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"Wrote {corpus['chunk_count']} chunks from {corpus['episode_count']} episodes to {output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
