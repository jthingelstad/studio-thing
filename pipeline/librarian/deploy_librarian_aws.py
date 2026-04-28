"""Package and deploy Thingy to AWS with CloudFormation."""

from __future__ import annotations

import argparse
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

import boto3
from dotenv import load_dotenv


REPO = Path(__file__).resolve().parents[2]
STACK_NAME = "weekly-thing-librarian"
TEMPLATE = REPO / "infra" / "librarian" / "cloudformation.yaml"
LAMBDA_DIR = REPO / "services" / "librarian"
BUILD_DIR = REPO / "tmp" / "librarian_lambda"
STREAM_BUILD_DIR = REPO / "tmp" / "librarian_chat_lambda"
ZIP_PATH = REPO / "tmp" / "librarian_lambda.zip"
STREAM_ZIP_PATH = REPO / "tmp" / "librarian_chat_lambda.zip"
CODE_PREFIX = "librarian/lambda"
STREAM_CODE_PREFIX = "librarian/stream-lambda"
CORPUS_KEY = "librarian/corpus.json"
GRAPH_KEY = "librarian/graph.json"
DEFAULT_ALLOWED_ORIGINS = "https://weekly.thingelstad.com,http://localhost:8080,http://127.0.0.1:8080"


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def run(args: list[str], cwd: Path = REPO) -> None:
    subprocess.run(args, cwd=cwd, check=True)


def copy_lambda_source(build_dir: Path) -> None:
    if build_dir.exists():
        shutil.rmtree(build_dir)
    build_dir.mkdir(parents=True)

    for name in ("package.json", "package-lock.json"):
        shutil.copy2(LAMBDA_DIR / name, build_dir / name)
    run(["npm", "ci", "--omit=dev", "--no-audit", "--no-fund"], cwd=build_dir)

    for name in ("auth", "chat", "shared", "prompts"):
        shutil.copytree(LAMBDA_DIR / name, build_dir / name, dirs_exist_ok=True)


def zip_build_dir(build_dir: Path, zip_path: Path) -> None:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in build_dir.rglob("*"):
            if path.is_file():
                archive.write(path, path.relative_to(build_dir))


def package_lambda() -> None:
    copy_lambda_source(BUILD_DIR)
    zip_build_dir(BUILD_DIR, ZIP_PATH)


def package_stream_lambda() -> None:
    copy_lambda_source(STREAM_BUILD_DIR)
    zip_build_dir(STREAM_BUILD_DIR, STREAM_ZIP_PATH)


def upload_file(bucket: str, key: str, path: Path, content_type: str) -> None:
    boto3.client("s3").upload_file(str(path), bucket, key, ExtraArgs={"ContentType": content_type})


def deploy_stack(
    *,
    stack_name: str,
    bucket: str,
    code_key: str,
    stream_code_key: str,
    corpus_key: str,
    graph_key: str,
    allowed_origin: str,
    buttondown_api_key: str,
    session_secret: str | None,
    log_level: str,
    auth_rate_limit_max: str,
    cloudformation_role_arn: str | None,
) -> tuple[dict[str, str], bool]:
    cloudformation = boto3.client("cloudformation")
    body = TEMPLATE.read_text(encoding="utf-8")

    exists = True
    try:
        cloudformation.describe_stacks(StackName=stack_name)
    except cloudformation.exceptions.ClientError:
        exists = False

    generated_session_secret = False
    session_parameter: dict[str, str | bool]
    if session_secret:
        session_parameter = {"ParameterKey": "SessionSecret", "ParameterValue": session_secret}
    elif exists:
        session_parameter = {"ParameterKey": "SessionSecret", "UsePreviousValue": True}
    else:
        session_parameter = {"ParameterKey": "SessionSecret", "ParameterValue": secrets.token_urlsafe(48)}
        generated_session_secret = True

    parameters = [
        {"ParameterKey": "AllowedOrigin", "ParameterValue": allowed_origin},
        {"ParameterKey": "CodeBucket", "ParameterValue": bucket},
        {"ParameterKey": "CodeKey", "ParameterValue": code_key},
        {"ParameterKey": "StreamCodeKey", "ParameterValue": stream_code_key},
        {"ParameterKey": "CorpusBucket", "ParameterValue": bucket},
        {"ParameterKey": "CorpusKey", "ParameterValue": corpus_key},
        {"ParameterKey": "GraphKey", "ParameterValue": graph_key},
        {"ParameterKey": "ButtondownApiKey", "ParameterValue": buttondown_api_key},
        session_parameter,
        {"ParameterKey": "LogLevel", "ParameterValue": log_level},
        {"ParameterKey": "AuthRateLimitMax", "ParameterValue": auth_rate_limit_max},
    ]
    stack_options = {
        "TemplateBody": body,
        "Parameters": parameters,
        "Capabilities": ["CAPABILITY_IAM"],
    }
    if cloudformation_role_arn:
        stack_options["RoleARN"] = cloudformation_role_arn

    if exists:
        try:
            cloudformation.update_stack(
                StackName=stack_name,
                **stack_options,
            )
            waiter_name = "stack_update_complete"
        except cloudformation.exceptions.ClientError as exc:
            if "No updates are to be performed" in str(exc):
                return stack_outputs(cloudformation, stack_name), generated_session_secret
            raise
    else:
        cloudformation.create_stack(
            StackName=stack_name,
            **stack_options,
        )
        waiter_name = "stack_create_complete"

    cloudformation.get_waiter(waiter_name).wait(StackName=stack_name)
    return stack_outputs(cloudformation, stack_name), generated_session_secret


def stack_output(cloudformation, stack_name: str, key: str) -> str:
    return stack_outputs(cloudformation, stack_name).get(key, "")


def stack_outputs(cloudformation, stack_name: str) -> dict[str, str]:
    stack = cloudformation.describe_stacks(StackName=stack_name)["Stacks"][0]
    result = {}
    for output in stack.get("Outputs", []):
        if output.get("OutputKey"):
            result[str(output["OutputKey"])] = str(output.get("OutputValue", ""))
    return result


def update_env_file(values: dict[str, str]) -> None:
    env_path = REPO / ".env"
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    remaining = {key: value for key, value in values.items() if value}
    updated: list[str] = []
    for line in lines:
        key = line.split("=", 1)[0] if "=" in line else ""
        if key in remaining:
            updated.append(f"{key}={remaining.pop(key)}")
        else:
            updated.append(line)
    for key, value in remaining.items():
        updated.append(f"{key}={value}")
    env_path.write_text("\n".join(updated).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stack-name", default=STACK_NAME)
    parser.add_argument("--bucket", default=os.environ.get("AWS_S3_BUCKET"))
    parser.add_argument("--allowed-origin", default=os.environ.get("LIBRARIAN_ALLOWED_ORIGIN", DEFAULT_ALLOWED_ORIGINS))
    parser.add_argument("--corpus-key", default=os.environ.get("LIBRARIAN_CORPUS_KEY", CORPUS_KEY))
    parser.add_argument("--graph-key", default=os.environ.get("LIBRARIAN_GRAPH_KEY", GRAPH_KEY))
    parser.add_argument("--cloudformation-role-arn", default=os.environ.get("LIBRARIAN_CLOUDFORMATION_ROLE_ARN"))
    parser.add_argument("--log-level", default=os.environ.get("LIBRARIAN_LOG_LEVEL", "INFO"))
    parser.add_argument("--auth-rate-limit-max", default=os.environ.get("LIBRARIAN_AUTH_RATE_LIMIT_MAX", "30"))
    parser.add_argument("--skip-corpus-upload", action="store_true")
    args = parser.parse_args()

    bucket = args.bucket
    if not bucket:
        raise RuntimeError("Provide --bucket or AWS_S3_BUCKET")

    package_lambda()
    package_stream_lambda()
    code_key = f"{CODE_PREFIX}/{int(time.time())}.zip"
    stream_code_key = f"{STREAM_CODE_PREFIX}/{int(time.time())}.zip"
    upload_file(bucket, code_key, ZIP_PATH, "application/zip")
    print(f"Uploaded Lambda package to s3://{bucket}/{code_key}")
    upload_file(bucket, stream_code_key, STREAM_ZIP_PATH, "application/zip")
    print(f"Uploaded streaming Lambda package to s3://{bucket}/{stream_code_key}")

    if not args.skip_corpus_upload:
        embedded_corpus = REPO / "tmp" / "librarian_embedded_corpus.json"
        run([sys.executable, "pipeline/librarian/upload_librarian_corpus.py", "--bucket", bucket, "--key", args.corpus_key, "--graph-key", args.graph_key, "--keep-output", str(embedded_corpus)])

    session_secret = os.environ.get("LIBRARIAN_SESSION_SECRET")
    outputs, generated_session_secret = deploy_stack(
        stack_name=args.stack_name,
        bucket=bucket,
        code_key=code_key,
        stream_code_key=stream_code_key,
        corpus_key=args.corpus_key,
        graph_key=args.graph_key,
        allowed_origin=args.allowed_origin,
        buttondown_api_key=require_env("BUTTONDOWN_API_KEY"),
        session_secret=session_secret,
        log_level=args.log_level.upper(),
        auth_rate_limit_max=str(args.auth_rate_limit_max),
        cloudformation_role_arn=args.cloudformation_role_arn,
    )
    for key, value in sorted(outputs.items()):
        print(f"{key}={value}")
    update_env_file(
        {
            "LIBRARIAN_API_URL": outputs.get("LibrarianApiUrl", ""),
            "LIBRARIAN_STREAM_URL": outputs.get("LibrarianStreamUrl", ""),
        }
    )
    if generated_session_secret:
        print("Generated an initial session secret for this stack. Future updates will reuse it unless LIBRARIAN_SESSION_SECRET is set.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
