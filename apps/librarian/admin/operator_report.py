#!/usr/bin/env python3
"""Generate a local Thingy operator report from canonical DynamoDB rows.

This is intentionally local-only: it reads AWS credentials from the repo-root
``.env`` and writes a static HTML file under ``tmp/`` by default. No public
operator web surface, no browser-side secrets, no extra database.
"""

from __future__ import annotations

import argparse
import html
import json
import os
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import boto3
from boto3.dynamodb.types import TypeDeserializer
from dotenv import load_dotenv


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_STACK = "weekly-thing-librarian"
DEFAULT_OUTPUT = Path.home() / "Desktop" / "Thingy Operator Report.html"

deserializer = TypeDeserializer()


def utc_now() -> datetime:
    return datetime.now(UTC)


def parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def iso_days_ago(days: int) -> str:
    return (utc_now() - timedelta(days=max(1, int(days)))).isoformat().replace("+00:00", "Z")


def h(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def compact(value: Any, limit: int = 240) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def local_time(value: Any) -> str:
    dt = parse_iso(value)
    if not dt:
        return str(value or "")
    local = dt.astimezone()
    return local.strftime("%b %-d, %-I:%M %p %Z")


def dynamo_item(item: dict[str, Any]) -> dict[str, Any]:
    return {key: deserializer.deserialize(value) for key, value in (item or {}).items()}


def stack_resource(logical_id: str, *, stack_name: str) -> str:
    cfn = boto3.client("cloudformation")
    response = cfn.describe_stack_resources(StackName=stack_name, LogicalResourceId=logical_id)
    resources = response.get("StackResources") or []
    if not resources:
        raise RuntimeError(f"CloudFormation resource not found: {logical_id}")
    return str(resources[0]["PhysicalResourceId"])


def source_label(citation: dict[str, Any]) -> str:
    if citation.get("issue_number"):
        return f"WT{citation['issue_number']}"
    return str(citation.get("subject") or citation.get("url") or citation.get("source_kind") or "").strip()


@dataclass
class Turn:
    created_at: str = ""
    request_id: str = ""
    question: str = ""
    answer: str = ""
    feedback_reaction: str = ""
    feedback_comment: str = ""
    citations: list[dict[str, Any]] = field(default_factory=list)
    tool_names: list[str] = field(default_factory=list)
    preflight: dict[str, Any] | None = None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "Turn":
        return cls(
            created_at=str(row.get("created_at") or ""),
            request_id=str(row.get("request_id") or ""),
            question=str(row.get("question") or ""),
            answer=str(row.get("answer") or ""),
            feedback_reaction=str(row.get("feedback_reaction") or ""),
            feedback_comment=str(row.get("feedback_comment") or ""),
            citations=[c for c in row.get("citations") or [] if isinstance(c, dict)],
            tool_names=[str(t) for t in row.get("tool_names") or [] if t],
            preflight=row.get("preflight") if isinstance(row.get("preflight"), dict) else None,
        )

    @property
    def source_labels(self) -> list[str]:
        out: list[str] = []
        for citation in self.citations:
            label = source_label(citation)
            if label and label not in out:
                out.append(label)
        return out


@dataclass
class Conversation:
    subscriber_hash: str
    conversation_id: str
    title: str
    topic: str
    summary: str
    scope: str
    created_at: str
    updated_at: str
    turn_count: int
    eval_quality: str
    eval_flags: list[str]
    eval_improvements: list[str]
    eval_reader: str
    eval_thingy: str
    eval_takeaway: str
    eval_posted_to_chatter_at: str
    turns: list[Turn] = field(default_factory=list)

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "Conversation | None":
        pk = str(row.get("pk") or "")
        sk = str(row.get("sk") or "")
        if not pk.startswith("user#") or not sk.startswith("conversation#"):
            return None
        return cls(
            subscriber_hash=pk.removeprefix("user#"),
            conversation_id=str(row.get("conversation_id") or sk.removeprefix("conversation#")),
            title=str(row.get("title") or "Untitled chat"),
            topic=str(row.get("eval_topic") or row.get("topic") or ""),
            summary=str(row.get("summary") or ""),
            scope=str(row.get("scope") or "all"),
            created_at=str(row.get("created_at") or ""),
            updated_at=str(row.get("updated_at") or row.get("last_message_at") or row.get("created_at") or ""),
            turn_count=int(row.get("turn_count") or 0),
            eval_quality=str(row.get("eval_quality") or "unreviewed"),
            eval_flags=[str(flag) for flag in row.get("eval_flags") or [] if flag],
            eval_improvements=[str(item) for item in row.get("eval_improvements") or [] if item],
            eval_reader=str(row.get("eval_reader") or ""),
            eval_thingy=str(row.get("eval_thingy") or ""),
            eval_takeaway=str(row.get("eval_takeaway") or ""),
            eval_posted_to_chatter_at=str(row.get("eval_posted_to_chatter_at") or ""),
        )

    @property
    def has_feedback(self) -> bool:
        return any(t.feedback_reaction for t in self.turns)

    @property
    def has_downvote(self) -> bool:
        return any(t.feedback_reaction == "down" for t in self.turns)

    @property
    def source_labels(self) -> list[str]:
        out: list[str] = []
        for turn in self.turns:
            for label in turn.source_labels:
                if label not in out:
                    out.append(label)
        return out


def scan_conversations(table_name: str, *, since_iso: str, max_pages: int) -> list[Conversation]:
    client = boto3.client("dynamodb")
    conversations: list[Conversation] = []
    exclusive_start_key = None
    pages = 0
    while True:
        kwargs: dict[str, Any] = {
            "TableName": table_name,
            "FilterExpression": (
                "begins_with(#pk, :user_prefix) AND begins_with(#sk, :conversation_prefix) "
                "AND #updated_at >= :since"
            ),
            "ExpressionAttributeNames": {"#pk": "pk", "#sk": "sk", "#updated_at": "updated_at"},
            "ExpressionAttributeValues": {
                ":user_prefix": {"S": "user#"},
                ":conversation_prefix": {"S": "conversation#"},
                ":since": {"S": since_iso},
            },
        }
        if exclusive_start_key:
            kwargs["ExclusiveStartKey"] = exclusive_start_key
        response = client.scan(**kwargs)
        for raw in response.get("Items", []):
            conv = Conversation.from_row(dynamo_item(raw))
            if conv:
                conversations.append(conv)
        exclusive_start_key = response.get("LastEvaluatedKey")
        pages += 1
        if not exclusive_start_key or pages >= max_pages:
            break
    conversations.sort(key=lambda c: c.updated_at, reverse=True)
    return conversations


def load_turns(table_name: str, conversation: Conversation, *, limit: int = 80) -> list[Turn]:
    client = boto3.client("dynamodb")
    response = client.query(
        TableName=table_name,
        KeyConditionExpression="#pk = :pk AND begins_with(#sk, :prefix)",
        ExpressionAttributeNames={"#pk": "pk", "#sk": "sk"},
        ExpressionAttributeValues={
            ":pk": {"S": f"user#{conversation.subscriber_hash}"},
            ":prefix": {"S": f"turn#{conversation.conversation_id}#"},
        },
        ScanIndexForward=True,
        Limit=limit,
    )
    return [Turn.from_row(dynamo_item(item)) for item in response.get("Items", [])]


def select_detail_conversations(conversations: list[Conversation], limit: int) -> list[Conversation]:
    priority = {
        "problem": 0,
        "watch": 1,
        "unreviewed": 2,
        "clean": 3,
    }
    return sorted(
        conversations,
        key=lambda c: (
            priority.get(c.eval_quality, 2),
            0 if c.has_downvote else 1,
            0 if c.eval_flags else 1,
            c.updated_at,
        ),
    )[:limit]


def metric_cards(conversations: list[Conversation]) -> dict[str, Any]:
    quality = Counter(c.eval_quality or "unreviewed" for c in conversations)
    flags = Counter(flag for c in conversations for flag in c.eval_flags)
    feedback = Counter(t.feedback_reaction for c in conversations for t in c.turns if t.feedback_reaction)
    return {
        "total": len(conversations),
        "turns": sum(c.turn_count for c in conversations),
        "readers": len({c.subscriber_hash for c in conversations}),
        "quality": quality,
        "flags": flags,
        "feedback": feedback,
    }


def render_metric(label: str, value: Any, sub: str = "") -> str:
    return f'<div class="metric"><div class="metric-value">{h(value)}</div><div class="metric-label">{h(label)}</div><div class="metric-sub">{h(sub)}</div></div>'


def render_counter(counter: Counter, *, empty: str = "None", limit: int = 12) -> str:
    if not counter:
        return f'<p class="muted">{h(empty)}</p>'
    rows = []
    total = sum(counter.values()) or 1
    for key, value in counter.most_common(limit):
        pct = round(value * 100 / total)
        rows.append(
            "<tr>"
            f"<td>{h(key)}</td>"
            f"<td class=\"num\">{value}</td>"
            f"<td><div class=\"bar\"><span style=\"width:{pct}%\"></span></div></td>"
            "</tr>"
        )
    return '<table class="compact"><tbody>' + "".join(rows) + "</tbody></table>"


def render_conversation_row(c: Conversation) -> str:
    flags = " ".join(f'<span class="chip">{h(flag)}</span>' for flag in c.eval_flags[:4])
    return (
        "<tr>"
        f"<td><code>{h(c.conversation_id[:8])}</code></td>"
        f"<td><span class=\"quality q-{h(c.eval_quality)}\">{h(c.eval_quality)}</span></td>"
        f"<td>{h(local_time(c.updated_at))}</td>"
        f"<td>{h(c.topic or c.title)}</td>"
        f"<td>{h(c.turn_count)}</td>"
        f"<td>{flags}</td>"
        "</tr>"
    )


def render_turn(turn: Turn, index: int) -> str:
    feedback = ""
    if turn.feedback_reaction:
        feedback = f'<p class="feedback">Feedback: <strong>{h(turn.feedback_reaction)}</strong> {h(turn.feedback_comment)}</p>'
    sources = ", ".join(turn.source_labels[:10])
    tools = ", ".join(turn.tool_names[:10])
    metadata = []
    if sources:
        metadata.append(f"Sources: {h(sources)}")
    if tools:
        metadata.append(f"Tools: {h(tools)}")
    if turn.preflight and (turn.preflight.get("category") or turn.preflight.get("action")):
        metadata.append(f"Preflight: {h(turn.preflight.get('category'))}/{h(turn.preflight.get('action'))}")
    meta = f'<p class="meta">{" · ".join(metadata)}</p>' if metadata else ""
    return (
        '<div class="turn">'
        f'<h4>Turn {index} <span>{h(local_time(turn.created_at))}</span></h4>'
        f'<div class="bubble reader"><strong>Reader</strong><p>{h(turn.question)}</p></div>'
        f'<div class="bubble thingy"><strong>Thingy</strong><p>{h(turn.answer)}</p></div>'
        f"{feedback}{meta}"
        "</div>"
    )


def render_detail(c: Conversation) -> str:
    flags = " ".join(f'<span class="chip">{h(flag)}</span>' for flag in c.eval_flags)
    improvements = "".join(f"<li>{h(item)}</li>" for item in c.eval_improvements)
    sources = ", ".join(c.source_labels[:16])
    turns = "".join(render_turn(turn, i + 1) for i, turn in enumerate(c.turns))
    return (
        '<details class="conversation">'
        f'<summary><span class="quality q-{h(c.eval_quality)}">{h(c.eval_quality)}</span> '
        f'<strong>{h(c.topic or c.title)}</strong> <code>{h(c.conversation_id)}</code></summary>'
        '<div class="conversation-body">'
        f'<p class="meta">Updated {h(local_time(c.updated_at))} · {h(c.turn_count)} turns · reader·{h(c.subscriber_hash[:8])} · scope {h(c.scope)}</p>'
        f'<p>{h(c.summary)}</p>'
        f'<p><strong>Reader:</strong> {h(c.eval_reader)}</p>'
        f'<p><strong>Thingy:</strong> {h(c.eval_thingy)}</p>'
        f'<p><strong>Takeaway:</strong> {h(c.eval_takeaway)}</p>'
        f'<p>{flags}</p>'
        f'{"<h4>Improvements</h4><ul>" + improvements + "</ul>" if improvements else ""}'
        f'<p class="meta">Sources: {h(sources or "None")}</p>'
        f"{turns}"
        "</div></details>"
    )


def render_html(conversations: list[Conversation], *, since_iso: str, generated_at: str, stack_name: str, table_name: str) -> str:
    metrics = metric_cards(conversations)
    quality = metrics["quality"]
    flags = metrics["flags"]
    feedback = metrics["feedback"]
    by_day: dict[str, int] = defaultdict(int)
    for c in conversations:
        dt = parse_iso(c.updated_at)
        by_day[(dt or utc_now()).date().isoformat()] += 1
    recent_rows = "".join(render_conversation_row(c) for c in conversations[:80])
    watch_rows = "".join(
        render_conversation_row(c)
        for c in conversations
        if c.eval_quality in {"watch", "problem"} or c.has_downvote
    )
    details = "".join(render_detail(c) for c in select_detail_conversations(conversations, 30))
    timeline = Counter(dict(sorted(by_day.items())))
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Thingy Operator Report</title>
<style>
:root {{ color-scheme: light; --ink:#17211d; --muted:#66736d; --line:#dfe6e2; --soft:#f6f8f7; --accent:#176b5b; --warn:#9f5c00; --bad:#9d2c2c; }}
* {{ box-sizing: border-box; }}
body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; color:var(--ink); background:#fbfcfb; }}
main {{ max-width:1180px; margin:0 auto; padding:32px 20px 56px; }}
h1 {{ margin:0 0 4px; font-size:32px; letter-spacing:0; }}
h2 {{ margin:34px 0 12px; font-size:20px; }}
h3 {{ margin:0 0 12px; font-size:16px; }}
h4 {{ margin:18px 0 8px; font-size:14px; }}
h4 span, .muted, .meta, .metric-sub {{ color:var(--muted); font-weight:400; }}
.lede {{ color:var(--muted); margin:0 0 22px; }}
.grid {{ display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:12px; }}
.two {{ display:grid; grid-template-columns:repeat(2, minmax(0,1fr)); gap:16px; }}
.panel, .metric, details.conversation {{ background:white; border:1px solid var(--line); border-radius:8px; box-shadow:0 1px 2px rgba(0,0,0,.03); }}
.panel {{ padding:16px; }}
.metric {{ padding:18px; }}
.metric-value {{ font-size:30px; font-weight:700; }}
.metric-label {{ color:var(--muted); font-size:13px; }}
table {{ width:100%; border-collapse:collapse; font-size:14px; }}
th, td {{ text-align:left; padding:10px 8px; border-bottom:1px solid var(--line); vertical-align:top; }}
th {{ color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.04em; }}
.compact td {{ padding:7px 4px; }}
.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
.bar {{ height:7px; background:var(--soft); border-radius:99px; overflow:hidden; }}
.bar span {{ display:block; height:100%; background:var(--accent); }}
.quality, .chip {{ display:inline-block; border:1px solid var(--line); border-radius:999px; padding:2px 8px; font-size:12px; white-space:nowrap; }}
.q-clean {{ background:#eef7f1; color:#1f6c3b; border-color:#c8e4cf; }}
.q-watch {{ background:#fff7e8; color:var(--warn); border-color:#efd29a; }}
.q-problem {{ background:#fff0f0; color:var(--bad); border-color:#edb9b9; }}
.q-unreviewed {{ background:#f2f3f2; color:#5d6862; }}
.chip {{ margin:1px 2px 1px 0; color:#3f4d47; background:#f7f9f8; }}
details.conversation {{ margin:10px 0; }}
summary {{ cursor:pointer; padding:14px 16px; }}
.conversation-body {{ border-top:1px solid var(--line); padding:14px 16px 18px; }}
.turn {{ border-top:1px solid var(--line); margin-top:14px; padding-top:10px; }}
.bubble {{ border-radius:8px; padding:10px 12px; margin:8px 0; }}
.bubble p {{ white-space:pre-wrap; margin:5px 0 0; line-height:1.5; }}
.reader {{ background:#f2f4f3; }}
.thingy {{ background:#eef6f4; }}
.feedback {{ color:var(--bad); }}
code {{ font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; font-size:.92em; }}
@media (max-width: 820px) {{ .grid, .two {{ grid-template-columns:1fr; }} main {{ padding:22px 14px 42px; }} table {{ font-size:13px; }} }}
</style>
</head>
<body>
<main>
<h1>Thingy Operator Report</h1>
<p class="lede">Generated {h(local_time(generated_at))}. Covers conversations updated since {h(local_time(since_iso))}. Stack <code>{h(stack_name)}</code>, table <code>{h(table_name)}</code>.</p>

<section class="grid">
{render_metric("Conversations", metrics["total"])}
{render_metric("Turns", metrics["turns"])}
{render_metric("Readers", metrics["readers"])}
{render_metric("Downvotes", feedback.get("down", 0), "comments included in details")}
</section>

<section class="two">
<div class="panel"><h3>Quality</h3>{render_counter(quality)}</div>
<div class="panel"><h3>Eval Flags</h3>{render_counter(flags, empty="No flags in this window")}</div>
<div class="panel"><h3>Feedback</h3>{render_counter(feedback, empty="No explicit feedback in this window")}</div>
<div class="panel"><h3>Daily Volume</h3>{render_counter(timeline, empty="No conversations in this window", limit=30)}</div>
</section>

<h2>Watchlist</h2>
<div class="panel">
<table><thead><tr><th>ID</th><th>Quality</th><th>Updated</th><th>Topic</th><th>Turns</th><th>Flags</th></tr></thead><tbody>
{watch_rows or '<tr><td colspan="6" class="muted">No watch/problem/downvoted conversations in this window.</td></tr>'}
</tbody></table>
</div>

<h2>Recent Conversations</h2>
<div class="panel">
<table><thead><tr><th>ID</th><th>Quality</th><th>Updated</th><th>Topic</th><th>Turns</th><th>Flags</th></tr></thead><tbody>
{recent_rows or '<tr><td colspan="6" class="muted">No conversations in this window.</td></tr>'}
</tbody></table>
</div>

<h2>Conversation Detail</h2>
{details or '<p class="muted">No conversations selected for detail.</p>'}
</main>
</body>
</html>
"""


def build_report(args: argparse.Namespace) -> tuple[Path, int]:
    load_dotenv(REPO_ROOT / ".env")
    stack_name = args.stack_name
    table_name = args.table_name or stack_resource("LibrarianTable", stack_name=stack_name)
    since_iso = args.since or iso_days_ago(args.days)
    conversations = scan_conversations(table_name, since_iso=since_iso, max_pages=args.max_scan_pages)

    for conversation in conversations:
        conversation.turns = load_turns(table_name, conversation)

    output = Path(args.output)
    if not output.is_absolute():
        output = REPO_ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    html_text = render_html(
        conversations,
        since_iso=since_iso,
        generated_at=utc_now().isoformat().replace("+00:00", "Z"),
        stack_name=stack_name,
        table_name=table_name,
    )
    output.write_text(html_text, encoding="utf-8")
    return output, len(conversations)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a local Thingy operator HTML report.")
    parser.add_argument("--stack-name", default=os.environ.get("LIBRARIAN_STACK_NAME", DEFAULT_STACK))
    parser.add_argument("--table-name", default="")
    parser.add_argument("--days", type=int, default=7, help="Look back this many days when --since is omitted.")
    parser.add_argument("--since", default="", help="ISO timestamp lower bound for updated_at.")
    parser.add_argument("--max-scan-pages", type=int, default=30)
    parser.add_argument("--detail-limit", type=int, default=30, help="Number of prioritized conversations to expand.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    return parser.parse_args()


def main() -> int:
    output, count = build_report(parse_args())
    print(f"Wrote {output} ({count} conversations)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
