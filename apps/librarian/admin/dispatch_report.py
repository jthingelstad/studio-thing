#!/usr/bin/env python3
"""Generate a local Thingy Dispatch operator report from DynamoDB rows."""

from __future__ import annotations

import argparse
import html
import json
import os
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import boto3
from boto3.dynamodb.types import TypeDeserializer
from dotenv import load_dotenv


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_STACK = "weekly-thing-librarian"
DEFAULT_OUTPUT = Path.home() / "Desktop" / "Thingy Dispatch Report.html"

deserializer = TypeDeserializer()


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_days_ago(days: int) -> str:
    return (utc_now() - timedelta(days=max(1, int(days)))).isoformat().replace("+00:00", "Z")


def h(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def compact(value: Any, limit: int = 260) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def local_time(value: Any) -> str:
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return str(value or "")
    if not dt.tzinfo:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone().strftime("%b %-d, %-I:%M %p %Z")


def dynamo_item(item: dict[str, Any]) -> dict[str, Any]:
    return {key: deserializer.deserialize(value) for key, value in (item or {}).items()}


def stack_resource(logical_id: str, *, stack_name: str) -> str:
    cfn = boto3.client("cloudformation")
    response = cfn.describe_stack_resources(StackName=stack_name, LogicalResourceId=logical_id)
    resources = response.get("StackResources") or []
    if not resources:
        raise RuntimeError(f"CloudFormation resource not found: {logical_id}")
    return str(resources[0]["PhysicalResourceId"])


def subscriber_hash(pk: str) -> str:
    text = str(pk or "")
    return text.removeprefix("user#") if text.startswith("user#") else text


def load_dispatches(table_name: str, *, days: int, limit: int) -> list[dict[str, Any]]:
    dynamodb = boto3.client("dynamodb")
    since = iso_days_ago(days)
    rows: list[dict[str, Any]] = []
    exclusive_start_key = None
    while True:
        kwargs: dict[str, Any] = {
            "TableName": table_name,
            "FilterExpression": "#item_type = :dispatch AND #created_at >= :since",
            "ExpressionAttributeNames": {
                "#item_type": "item_type",
                "#created_at": "created_at",
            },
            "ExpressionAttributeValues": {
                ":dispatch": {"S": "dispatch"},
                ":since": {"S": since},
            },
        }
        if exclusive_start_key:
            kwargs["ExclusiveStartKey"] = exclusive_start_key
        response = dynamodb.scan(**kwargs)
        for item in response.get("Items") or []:
            row = dynamo_item(item)
            row["subscriber_hash"] = subscriber_hash(row.get("pk", ""))
            rows.append(row)
        exclusive_start_key = response.get("LastEvaluatedKey")
        if not exclusive_start_key or len(rows) >= limit * 3:
            break
    rows.sort(key=lambda row: str(row.get("created_at") or ""), reverse=True)
    return rows[:limit]


def render_sources(sources: list[dict[str, Any]]) -> str:
    if not sources:
        return "<p class='muted'>No sources recorded.</p>"
    items = []
    for source in sources:
        title = h(source.get("title"))
        url = str(source.get("url") or "")
        label = h(source.get("label") or source.get("id") or "Source")
        link = f"<a href='{h(url)}'>{title}</a>" if url else title
        items.append(f"<li><strong>{label}</strong> · {link}</li>")
    return "<ol>" + "\n".join(items) + "</ol>"


def load_dispatch_content(row: dict[str, Any]) -> tuple[str, bool]:
    if row.get("content_html"):
        return str(row.get("content_html") or ""), True
    if row.get("content_text"):
        return str(row.get("content_text") or ""), False
    bucket = str(row.get("content_artifact_bucket") or "")
    key = str(row.get("content_artifact_key") or "")
    if not bucket or not key:
        return "", False
    try:
        body = boto3.client("s3").get_object(Bucket=bucket, Key=key)["Body"].read()
        payload = json.loads(body.decode("utf-8"))
        html_content = str(payload.get("html") or "")
        text_content = str(payload.get("text") or "")
        return (html_content, True) if html_content else (text_content, False)
    except Exception as exc:  # noqa: BLE001 - report generation should keep going.
        return f"Could not load Dispatch artifact s3://{bucket}/{key}: {exc}", False


def render_report(rows: list[dict[str, Any]], *, days: int) -> str:
    counts = Counter(str(row.get("status") or "unknown") for row in rows)
    status_pills = " ".join(f"<span class='pill'>{h(k)} {v}</span>" for k, v in counts.most_common())
    cards = []
    for row in rows:
        content, content_is_html = load_dispatch_content(row)
        test_badge = " · <span class='pill'>template test</span>" if row.get("template_test") else ""
        cards.append(f"""
        <article class="card status-{h(row.get('status'))}">
          <header>
            <span class="status">{h(row.get('status'))}</span>
            <h2>{h(row.get('title') or row.get('topic') or 'Untitled Dispatch')}</h2>
            <p class="meta">reader·{h(str(row.get('subscriber_hash') or '')[:8])} · {h(local_time(row.get('created_at')))} · {h(row.get('source_count') or 0)} sources{test_badge}</p>
          </header>
          <dl>
            <dt>Prompt</dt><dd>{h(compact(row.get('prompt'), 800))}</dd>
            <dt>Direction</dt><dd>{h(compact(row.get('direction'), 800))}</dd>
            <dt>Subject</dt><dd>{h(row.get('subject'))}</dd>
            <dt>Runtime</dt><dd>{h(row.get('model'))} · in {h(row.get('input_tokens') or 0)} / out {h(row.get('output_tokens') or 0)} tokens</dd>
            {f"<dt>Error</dt><dd class='error'>{h(row.get('error'))}</dd>" if row.get('error') else ""}
          </dl>
          <details>
            <summary>Sources</summary>
            {render_sources(row.get('sources') or [])}
          </details>
          <details>
            <summary>Stored content</summary>
            <div class="content">{content if content_is_html else '<pre>' + h(content) + '</pre>'}</div>
          </details>
        </article>
        """)
    generated = local_time(utc_now().isoformat())
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Thingy Dispatch Report</title>
  <style>
    body {{ margin: 0; background: #f6f8f5; color: #17211f; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    main {{ width: min(100% - 32px, 1180px); margin: 0 auto; padding: 32px 0 56px; }}
    h1 {{ font-size: 38px; margin: 0 0 8px; }}
    .muted, .meta {{ color: #66766f; }}
    .summary {{ display:flex; flex-wrap:wrap; gap:8px; margin:20px 0; }}
    .pill, .status {{ border-radius: 999px; padding: 3px 9px; background: #dff2ed; color: #194f49; font-size: 12px; font-weight: 800; }}
    .card {{ background:#fff; border:1px solid #dfe7e3; border-radius:8px; padding:20px; margin:16px 0; }}
    .status-failed {{ border-color:#e6b8a8; }}
    h2 {{ margin: 8px 0; }}
    dl {{ display:grid; grid-template-columns:120px minmax(0, 1fr); gap:8px 12px; }}
    dt {{ font-weight:800; color:#3f4f4a; }}
    dd {{ margin:0; }}
    .error {{ color:#9a341f; }}
    details {{ margin-top:14px; border-top:1px solid #edf2ef; padding-top:12px; }}
    summary {{ cursor:pointer; font-weight:800; }}
    .content {{ margin-top:12px; border:1px solid #edf2ef; padding:12px; overflow:auto; max-height:720px; background:#fffdf8; }}
    pre {{ white-space:pre-wrap; }}
    a {{ color:#14776f; }}
  </style>
</head>
<body>
  <main>
    <h1>Thingy Dispatch Report</h1>
    <p class="muted">Generated {h(generated)} · last {days} days · {len(rows)} Dispatches</p>
    <div class="summary">{status_pills}</div>
    {''.join(cards) if cards else '<p>No Dispatches found.</p>'}
  </main>
</body>
</html>"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate local Thingy Dispatch report.")
    parser.add_argument("--stack", default=os.environ.get("LIBRARIAN_STACK_NAME", DEFAULT_STACK))
    parser.add_argument("--table", default=os.environ.get("TABLE_NAME", ""))
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    load_dotenv(REPO_ROOT / ".env")
    table_name = args.table or os.environ.get("TABLE_NAME") or stack_resource("LibrarianTable", stack_name=args.stack)
    rows = load_dispatches(table_name, days=args.days, limit=args.limit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_report(rows, days=args.days), encoding="utf-8")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
