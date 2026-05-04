"""Build the offline archive graph used by the librarian tools."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
import os
import re
from pathlib import Path
from typing import Any

import boto3
from dotenv import load_dotenv

from librarian_core.corpus import build_corpus
from librarian_core.paths import CORPUS_PATH, GRAPH_PATH


DEFAULT_CORPUS_PATH = CORPUS_PATH
DEFAULT_OUTPUT_PATH = GRAPH_PATH
DEFAULT_MODEL = "us.anthropic.claude-sonnet-4-6"
ENTITY_RE = re.compile(r"\b(?:[A-Z][A-Za-z0-9&'.-]+(?:\s+[A-Z][A-Za-z0-9&'.-]+){0,4})\b")
STOP_ENTITIES = {
    "Weekly Thing",
    "Jamie",
    "The Weekly Thing",
    "Thingy",
    "Featured",
    "Notable",
    "Briefly",
    "Journal",
    "Currently",
}
TROPE_KEYWORDS = {
    "open web and ownership": {"rss", "blog", "blogs", "website", "web", "open web", "feed", "feeds", "domain"},
    "agency over convenience": {"privacy", "control", "convenience", "surveillance", "lock-in", "algorithm"},
    "tools for thought": {"obsidian", "notes", "knowledge", "workflow", "productivity", "omnifocus"},
    "local community": {"minneapolis", "minnesota", "community", "event", "meetup"},
    "ai as collaborator": {"ai", "agent", "agents", "llm", "claude", "openai", "model"},
    "durable archives": {"archive", "links", "pinboard", "database", "memory"},
}


def load_corpus(path: Path) -> dict[str, Any]:
    if path.exists():
        corpus = json.loads(path.read_text(encoding="utf-8"))
        if any(issue.get("body") for issue in corpus.get("issues", [])):
            return corpus
        fresh = build_corpus(include_issue_bodies=True)
        if any(chunk.get("embedding") for chunk in corpus.get("chunks", [])):
            fresh["chunks"] = corpus.get("chunks", [])
            fresh["embedding_model"] = corpus.get("embedding_model")
            fresh["embedding_dimensions"] = corpus.get("embedding_dimensions")
        return fresh
    return build_corpus(include_issue_bodies=True)

def clean_entity(value: str) -> str:
    value = " ".join(value.strip(" .,:;!?()[]{}").split())
    return value


def heuristic_entities(issue: dict[str, Any], limit: int = 40) -> list[str]:
    text = " ".join(
        [
            str(issue.get("subject") or ""),
            " ".join(str(link.get("text") or "") for link in issue.get("links", [])[:24]),
            str(issue.get("body") or "")[:14000],
        ]
    )
    counts: dict[str, int] = {}
    for match in ENTITY_RE.finditer(text):
        entity = clean_entity(match.group(0))
        if len(entity) < 3 or entity in STOP_ENTITIES or entity.lower().startswith("weekly thing"):
            continue
        if entity.isupper() and len(entity) <= 2:
            continue
        counts[entity] = counts.get(entity, 0) + 1
    for link in issue.get("links", []) or []:
        domain = str(link.get("domain") or "").removeprefix("www.")
        if domain:
            counts[domain] = counts.get(domain, 0) + 2
    return [entity for entity, _ in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]]


def heuristic_tropes(issue: dict[str, Any]) -> list[str]:
    text = f"{issue.get('subject', '')} {issue.get('body', '')[:20000]}".lower()
    result = []
    for trope, keywords in TROPE_KEYWORDS.items():
        score = sum(1 for keyword in keywords if keyword in text)
        if score >= 2:
            result.append(trope)
    return result


def issue_vectors(corpus: dict[str, Any]) -> dict[str, list[float]]:
    sums: dict[str, list[float]] = {}
    counts: dict[str, int] = {}
    for chunk in corpus.get("chunks", []):
        embedding = chunk.get("embedding")
        if not embedding:
            continue
        issue = str(chunk.get("issue_number"))
        if issue not in sums:
            sums[issue] = [0.0] * len(embedding)
        for index, value in enumerate(embedding):
            sums[issue][index] += float(value)
        counts[issue] = counts.get(issue, 0) + 1
    return {
        issue: [value / max(counts.get(issue, 1), 1) for value in vector]
        for issue, vector in sums.items()
    }


def cosine(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    return dot / (left_norm * right_norm) if left_norm and right_norm else 0.0


def similarity_edges(corpus: dict[str, Any], top_k: int = 6) -> dict[str, list[dict[str, Any]]]:
    vectors = issue_vectors(corpus)
    edges: dict[str, list[dict[str, Any]]] = {}
    for issue, vector in vectors.items():
        scored = [
            {"number": other, "score": round(cosine(vector, other_vector), 4)}
            for other, other_vector in vectors.items()
            if other != issue
        ]
        scored.sort(key=lambda item: item["score"], reverse=True)
        edges[issue] = scored[:top_k]
    return edges


def extract_with_bedrock(issue: dict[str, Any], model: str) -> dict[str, list[str]]:
    body = str(issue.get("body") or "")[:18000]
    prompt = (
        "Extract archive metadata from this Weekly Thing issue. Return only JSON with keys "
        "entities and tropes. entities should include people, companies, products, places, and projects. "
        "tropes should be recurring stances or themes expressed in plain noun phrases.\n\n"
        f"Issue #{issue.get('number')}: {issue.get('subject')}\nDate: {issue.get('publish_date')}\n\n{body}"
    )
    response = boto3.client("bedrock-runtime").converse(
        modelId=model,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": 900, "temperature": 0.1},
    )
    text = "\n".join(
        block.get("text", "")
        for block in response.get("output", {}).get("message", {}).get("content", [])
        if "text" in block
    )
    match = re.search(r"\{.*\}", text, re.S)
    data = json.loads(match.group(0) if match else text)
    return {
        "entities": [clean_entity(str(item)) for item in data.get("entities", []) if str(item).strip()][:50],
        "tropes": [clean_entity(str(item)).lower() for item in data.get("tropes", []) if str(item).strip()][:20],
    }


def build_graph(corpus: dict[str, Any], *, use_bedrock: bool = False, model: str = DEFAULT_MODEL) -> dict[str, Any]:
    similarities = similarity_edges(corpus)
    issues: dict[str, dict[str, Any]] = {}
    entity_index: dict[str, list[str]] = {}
    trope_index: dict[str, list[str]] = {}
    for issue in corpus.get("issues", []):
        number = str(issue.get("number"))
        if use_bedrock:
            try:
                extracted = extract_with_bedrock(issue, model)
            except Exception as exc:
                print(f"Bedrock extraction failed for #{number}: {type(exc).__name__}; using heuristics")
                extracted = {"entities": heuristic_entities(issue), "tropes": heuristic_tropes(issue)}
        else:
            extracted = {"entities": heuristic_entities(issue), "tropes": heuristic_tropes(issue)}
        issues[number] = {
            "entities": extracted["entities"],
            "tropes": extracted["tropes"],
            "similar_issues": similarities.get(number, []),
        }
        for entity in extracted["entities"]:
            entity_index.setdefault(entity.lower(), []).append(number)
        for trope in extracted["tropes"]:
            trope_index.setdefault(trope.lower(), []).append(number)
    return {
        "version": 1,
        "source": "data/librarian/corpus.json",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "extraction_model": model if use_bedrock else "heuristic",
        "issue_count": len(issues),
        "issues": issues,
        "entity_index": entity_index,
        "trope_index": trope_index,
    }


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", default=str(DEFAULT_CORPUS_PATH))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH))
    parser.add_argument("--use-bedrock-extraction", action="store_true")
    parser.add_argument("--model", default=os.environ.get("BEDROCK_AGENT_MODEL", DEFAULT_MODEL))
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
