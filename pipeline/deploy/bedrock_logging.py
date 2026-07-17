"""Inspect or enable Bedrock model invocation logging for Thingy."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

REPO = Path(__file__).resolve().parents[2]
DEFAULT_BUCKET = "weekly-thing-librarian"
DEFAULT_PREFIX = "logs/invocations"


def bedrock_log_statement(bucket: str, prefix: str, account_id: str, region: str) -> dict[str, Any]:
    clean_prefix = prefix.strip("/")
    return {
        "Sid": "AmazonBedrockModelInvocationLogsWrite",
        "Effect": "Allow",
        "Principal": {"Service": "bedrock.amazonaws.com"},
        "Action": ["s3:PutObject"],
        "Resource": [
            f"arn:aws:s3:::{bucket}/{clean_prefix}/AWSLogs/{account_id}/BedrockModelInvocationLogs/*"
        ],
        "Condition": {
            "StringEquals": {"aws:SourceAccount": account_id},
            "ArnLike": {"aws:SourceArn": f"arn:aws:bedrock:{region}:{account_id}:*"},
        },
    }


def merged_bucket_policy(bucket: str, prefix: str, account_id: str, region: str) -> dict[str, Any]:
    s3 = boto3.client("s3")
    try:
        policy = json.loads(s3.get_bucket_policy(Bucket=bucket)["Policy"])
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") != "NoSuchBucketPolicy":
            raise
        policy = {"Version": "2012-10-17", "Statement": []}
    statement = bedrock_log_statement(bucket, prefix, account_id, region)
    statements = [
        item for item in policy.get("Statement", []) if item.get("Sid") != statement["Sid"]
    ]
    policy["Statement"] = [*statements, statement]
    return policy


def current_logging_config() -> dict[str, Any]:
    try:
        return (
            boto3.client("bedrock")
            .get_model_invocation_logging_configuration()
            .get("loggingConfig", {})
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in {
            "ResourceNotFoundException",
            "ValidationException",
        }:
            return {}
        if exc.response.get("Error", {}).get("Code") == "AccessDeniedException":
            return {"error": "Access denied for bedrock:GetModelInvocationLoggingConfiguration"}
        raise


def main() -> int:
    load_dotenv(REPO / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bucket", default=os.environ.get("LIBRARIAN_BUCKET") or DEFAULT_BUCKET)
    parser.add_argument(
        "--prefix", default=os.environ.get("BEDROCK_INVOCATION_LOG_PREFIX", DEFAULT_PREFIX)
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the S3 bucket policy and Bedrock logging configuration.",
    )
    args = parser.parse_args()

    session = boto3.session.Session()
    region = session.region_name or os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
    account_id = boto3.client("sts").get_caller_identity()["Account"]
    logging_config = {
        "s3Config": {
            "bucketName": args.bucket,
            "keyPrefix": args.prefix.strip("/"),
        },
        "textDataDeliveryEnabled": True,
        "embeddingDataDeliveryEnabled": True,
        "imageDataDeliveryEnabled": False,
        "videoDataDeliveryEnabled": False,
        "audioDataDeliveryEnabled": False,
    }

    print("Current Bedrock invocation logging:")
    print(json.dumps(current_logging_config(), indent=2, default=str))
    print("\nDesired Bedrock invocation logging:")
    print(json.dumps(logging_config, indent=2))

    if not args.apply:
        print(
            "\nDry run only. Re-run with --apply to update the bucket policy and Bedrock account-level logging config."
        )
        return 0

    policy = merged_bucket_policy(args.bucket, args.prefix, account_id, region)
    boto3.client("s3").put_bucket_policy(Bucket=args.bucket, Policy=json.dumps(policy))
    boto3.client("bedrock").put_model_invocation_logging_configuration(loggingConfig=logging_config)
    print(f"Enabled Bedrock invocation logging to s3://{args.bucket}/{args.prefix.strip('/')}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
