"""CLI entrypoint: build the offline archive graph.

Thin wrapper around :mod:`librarian_core.graph`. Build logic lives in the
package; this file just exposes the argparse interface used by CI, npm
scripts, and Makefile targets.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import boto3
from dotenv import load_dotenv

from librarian_core.graph import DEFAULT_MODEL, build_graph, load_corpus
from librarian_core.paths import CORPUS_PATH, GRAPH_PATH


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Build the offline archive graph used by the librarian tools.")
    parser.add_argument("--corpus", default=str(CORPUS_PATH))
    parser.add_argument("--output", default=str(GRAPH_PATH))
    parser.add_argument("--use-bedrock-extraction", action="store_true")
    parser.add_argument("--model", default=os.environ.get("THINGY_DEFAULT_MODEL", DEFAULT_MODEL))
    parser.add_argument("--upload-bucket", default=os.environ.get("AWS_S3_BUCKET"))
    parser.add_argument("--upload-key", default=os.environ.get("LIBRARIAN_GRAPH_KEY", "librarian/graph.json"))
    parser.add_argument("--upload", action="store_true")
    args = parser.parse_args()

    corpus = load_corpus(Path(args.corpus))
    graph = build_graph(corpus, use_bedrock=args.use_bedrock_extraction, model=args.model)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote graph for {graph['issue_count']} issues to {output}")

    if args.upload:
        if not args.upload_bucket:
            raise RuntimeError("Provide --upload-bucket or AWS_S3_BUCKET")
        boto3.client("s3").upload_file(str(output), args.upload_bucket, args.upload_key, ExtraArgs={"ContentType": "application/json"})
        print(f"Uploaded librarian graph to s3://{args.upload_bucket}/{args.upload_key}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
