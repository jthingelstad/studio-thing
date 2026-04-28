"""Build the embedded librarian corpus and upload it to S3."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

import boto3
from dotenv import load_dotenv

import build_librarian_corpus
import build_librarian_graph


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bucket", default=os.environ.get("AWS_S3_BUCKET"))
    parser.add_argument("--key", default=os.environ.get("LIBRARIAN_CORPUS_KEY", "librarian/corpus.json"))
    parser.add_argument("--graph-key", default=os.environ.get("LIBRARIAN_GRAPH_KEY", "librarian/graph.json"))
    parser.add_argument("--embedding-model", default=build_librarian_corpus.DEFAULT_EMBEDDING_MODEL)
    parser.add_argument("--embedding-dimensions", type=int, default=build_librarian_corpus.DEFAULT_EMBEDDING_DIMENSIONS)
    parser.add_argument("--keep-output", help="Optional local path for the embedded corpus JSON")
    parser.add_argument("--skip-graph", action="store_true", help="Only upload the corpus, not the graph artifact")
    args = parser.parse_args()

    if not args.bucket:
        raise RuntimeError("Provide --bucket or AWS_S3_BUCKET")

    corpus = build_librarian_corpus.build_corpus(include_issue_bodies=True)
    build_librarian_corpus.add_bedrock_embeddings(corpus, args.embedding_model, args.embedding_dimensions)

    if args.keep_output:
        upload_path = Path(args.keep_output)
        upload_path.parent.mkdir(parents=True, exist_ok=True)
        upload_path.write_text(json.dumps(corpus, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    else:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as handle:
            handle.write(json.dumps(corpus, ensure_ascii=False) + "\n")
            upload_path = Path(handle.name)

    boto3.client("s3").upload_file(str(upload_path), args.bucket, args.key, ExtraArgs={"ContentType": "application/json"})
    print(f"Uploaded embedded librarian corpus to s3://{args.bucket}/{args.key}")
    if not args.skip_graph:
        graph = build_librarian_graph.build_graph(corpus)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as handle:
            handle.write(json.dumps(graph, ensure_ascii=False) + "\n")
            graph_path = Path(handle.name)
        boto3.client("s3").upload_file(str(graph_path), args.bucket, args.graph_key, ExtraArgs={"ContentType": "application/json"})
        print(f"Uploaded librarian graph to s3://{args.bucket}/{args.graph_key}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
