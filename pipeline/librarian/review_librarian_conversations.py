"""Review logged Thingy beta conversations from DynamoDB."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from typing import Any

import boto3
from boto3.dynamodb.conditions import Attr
from dotenv import load_dotenv


STACK_NAME = "weekly-thing-librarian"
TABLE_LOGICAL_ID = "LibrarianTable"


def table_name_from_stack(stack_name: str) -> str:
    client = boto3.client("cloudformation")
    response = client.describe_stack_resource(StackName=stack_name, LogicalResourceId=TABLE_LOGICAL_ID)
    return str(response["StackResourceDetail"]["PhysicalResourceId"])


def load_conversations(table_name: str, limit: int) -> list[dict[str, Any]]:
    table = boto3.resource("dynamodb").Table(table_name)
    items: list[dict[str, Any]] = []
    kwargs: dict[str, Any] = {
        "FilterExpression": Attr("pk").begins_with("conversation#"),
    }
    while len(items) < limit:
        response = table.scan(**kwargs)
        items.extend(response.get("Items", []))
        if "LastEvaluatedKey" not in response:
            break
        kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
    return sorted(items, key=lambda item: str(item.get("created_at") or ""), reverse=True)[:limit]


def format_text(value: Any, width: int = 1000) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= width:
        return text
    return text[: width - 1].rsplit(" ", 1)[0] + "..."


def print_text(items: list[dict[str, Any]]) -> None:
    for item in items:
        issues = ", ".join(str(issue) for issue in item.get("source_issues", []))
        print("=" * 88)
        print(f"{item.get('created_at')}  request={item.get('request_id')}  route={item.get('route')}")
        print(f"subscriber={item.get('subscriber_hash')}  citations={item.get('citation_count')}  issues={issues}")
        print("\nQUESTION")
        print(format_text(item.get("question")))
        print("\nANSWER")
        print(format_text(item.get("answer"), width=1800))
        print()


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stack-name", default=os.environ.get("LIBRARIAN_STACK_NAME", STACK_NAME))
    parser.add_argument("--table-name", default=os.environ.get("LIBRARIAN_TABLE_NAME"))
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--json", action="store_true", help="Print raw conversation records as JSON.")
    args = parser.parse_args()

    table_name = args.table_name or table_name_from_stack(args.stack_name)
    items = load_conversations(table_name, args.limit)
    if args.json:
        print(json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(), "table": table_name, "items": items}, indent=2, default=str))
    else:
        print_text(items)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
