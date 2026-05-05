"""Prepare and optionally start an Amazon Bedrock model evaluation job for Thingy."""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import re
import time
import urllib.request
from pathlib import Path
from typing import Any

import boto3
from dotenv import load_dotenv


REPO = Path(__file__).resolve().parents[2]
DEFAULT_BUCKET = "weekly-thing-librarian"
DEFAULT_MODEL_IDENTIFIER = "thingy-live"
DEFAULT_EVALUATOR_MODEL = "amazon.nova-pro-v1:0"
BUILTIN_METRICS = [
    "Builtin.Helpfulness",
    "Builtin.Faithfulness",
    "Builtin.Relevance",
    "Builtin.FollowingInstructions",
]


def slug(value: str) -> str:
    text = re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-")
    return text[:48] or "thingy-eval"


def load_questions(path: Path) -> list[dict[str, str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [{"tag": str(item.get("tag", "uncategorized")), "question": str(item["question"])} for item in data]


def load_responses(path: Path | None) -> dict[str, str]:
    if not path:
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    responses: dict[str, str] = {}
    for item in data.get("results", []):
        question = str(item.get("question", ""))
        answer = str(item.get("answer", ""))
        if question and answer:
            responses[question] = answer
    return responses


def sign_eval_token(session_secret: str, identity: str) -> str:
    expires_at = int(time.time()) + 60 * 60
    subscriber_hash = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    payload = {"exp": expires_at, "sid": "thingy-eval", "sub": subscriber_hash}
    encoded = base64.urlsafe_b64encode(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).decode("ascii").rstrip("=")
    signature = base64.urlsafe_b64encode(
        hmac.new(session_secret.encode("utf-8"), encoded.encode("utf-8"), hashlib.sha256).digest()
    ).decode("ascii").rstrip("=")
    return f"{encoded}.{signature}"


def extract_sse_answer(text: str) -> str:
    answer: list[str] = []
    current_event = ""
    for line in text.splitlines():
        if line.startswith("event: "):
            current_event = line[7:].strip()
        elif line.startswith("data: "):
            try:
                payload = json.loads(line[6:])
            except json.JSONDecodeError:
                continue
            if current_event == "answer_delta":
                answer.append(str(payload.get("delta", "")))
            elif current_event == "error":
                raise RuntimeError(str(payload.get("error", "Live chat returned an error event")))
    return "".join(answer).strip()


def live_chat_answer(chat_url: str, token: str, question: str, timeout: int) -> str:
    url = chat_url.rstrip("/") + "/chat"
    request = urllib.request.Request(
        url,
        data=json.dumps({"message": question}).encode("utf-8"),
        headers={"content-type": "application/json", "authorization": f"Bearer {token}"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8")
    return extract_sse_answer(body)


def fetch_lambda_session_secret(function_name: str, region: str) -> str:
    config = boto3.client("lambda", region_name=region).get_function_configuration(FunctionName=function_name)
    return str(config.get("Environment", {}).get("Variables", {}).get("SESSION_SECRET", ""))


def generate_live_responses(
    *,
    questions: list[dict[str, str]],
    chat_url: str,
    session_secret: str,
    timeout: int,
    retries: int,
    output_path: Path,
) -> dict[str, str]:
    results = []
    completed: dict[str, str] = {}
    if output_path.exists():
        existing = json.loads(output_path.read_text(encoding="utf-8"))
        results = list(existing.get("results", []))
        completed = {str(item.get("question", "")): str(item.get("answer", "")) for item in results if item.get("question") and item.get("answer")}
        if completed:
            print(f"Resuming from {output_path} with {len(completed)} completed responses.", flush=True)
    for index, item in enumerate(questions, 1):
        question = item["question"]
        if question in completed:
            print(f"[{index}/{len(questions)}] {question}", flush=True)
            print("  already complete", flush=True)
            continue
        token = sign_eval_token(session_secret, f"thingy-eval-{index}@example.com")
        print(f"[{index}/{len(questions)}] {question}", flush=True)
        started = time.perf_counter()
        last_error: Exception | None = None
        for attempt in range(1, retries + 2):
            try:
                answer = live_chat_answer(chat_url, token, question, timeout)
                break
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if attempt > retries:
                    raise
                print(f"  attempt {attempt} failed: {exc}; retrying", flush=True)
                time.sleep(2 * attempt)
        else:
            raise RuntimeError("Live response generation failed") from last_error
        elapsed = round(time.perf_counter() - started, 2)
        print(f"  answer_chars={len(answer)} elapsed_seconds={elapsed}", flush=True)
        results.append({"tag": item["tag"], "question": question, "answer": answer, "elapsed_seconds": elapsed})
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps({"results": results}, indent=2), encoding="utf-8")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps({"results": results}, indent=2), encoding="utf-8")
    print(f"Wrote live Thingy responses to {output_path}", flush=True)
    return {item["question"]: item["answer"] for item in results}


def dataset_rows(questions: list[dict[str, str]], responses: dict[str, str], model_identifier: str) -> list[dict[str, Any]]:
    rows = []
    for item in questions:
        row: dict[str, Any] = {"prompt": item["question"], "category": item["tag"]}
        answer = responses.get(item["question"])
        if answer:
            row["modelResponses"] = [{"response": answer, "modelIdentifier": model_identifier}]
        rows.append(row)
    return rows


def write_jsonl(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


def upload_dataset(bucket: str, key: str, path: Path) -> str:
    boto3.client("s3").upload_file(str(path), bucket, key, ExtraArgs={"ContentType": "application/jsonl"})
    return f"s3://{bucket}/{key}"


def model_identifier(model: str, account_id: str, region: str) -> str:
    if model.startswith("arn:"):
        return model
    if model.startswith("us."):
        return f"arn:aws:bedrock:{region}:{account_id}:inference-profile/{model}"
    return f"arn:aws:bedrock:{region}::foundation-model/{model}"


def start_evaluation_job(
    *,
    job_name: str,
    role_arn: str,
    dataset_uri: str,
    output_uri: str,
    evaluator_model: str,
    model_response_identifier: str,
    rubric: str,
) -> str:
    session = boto3.session.Session()
    region = session.region_name or os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
    account_id = boto3.client("sts").get_caller_identity()["Account"]
    evaluator_arn = model_identifier(evaluator_model, account_id, region)
    metric_instructions = rubric.strip()
    if "{{prediction}}" not in metric_instructions:
        metric_instructions = (
            f"{metric_instructions}\n\n"
            "Here is the actual task:\n"
            "Prompt: {{prompt}}\n"
            "Response: {{prediction}}\n"
        )
    response = boto3.client("bedrock").create_evaluation_job(
        jobName=job_name,
        jobDescription="Thingy archive assistant evaluation using precomputed system responses.",
        roleArn=role_arn,
        applicationType="ModelEvaluation",
        evaluationConfig={
            "automated": {
                "datasetMetricConfigs": [{
                    "taskType": "General",
                    "dataset": {
                        "name": "ThingyArchiveQuestions",
                        "datasetLocation": {"s3Uri": dataset_uri},
                    },
                    "metricNames": [*BUILTIN_METRICS, "ThingyOverall"],
                }],
                "evaluatorModelConfig": {
                    "bedrockEvaluatorModels": [{"modelIdentifier": evaluator_arn}],
                },
                "customMetricConfig": {
                    "customMetrics": [{
                        "customMetricDefinition": {
                            "name": "ThingyOverall",
                            "instructions": metric_instructions,
                            "ratingScale": [
                                {"definition": "Poor: ungrounded, generic, or not useful.", "value": {"floatValue": 1.0}},
                                {"definition": "Weak: partially useful but missing evidence or Thingy voice.", "value": {"floatValue": 2.0}},
                                {"definition": "Adequate: mostly correct and useful, but thin.", "value": {"floatValue": 3.0}},
                                {"definition": "Strong: grounded, specific, useful, and natural.", "value": {"floatValue": 4.0}},
                                {"definition": "Excellent: grounded synthesis with clear orientation and strong Thingy voice.", "value": {"floatValue": 5.0}},
                            ],
                        }
                    }],
                    "evaluatorModelConfig": {
                        "bedrockEvaluatorModels": [{"modelIdentifier": evaluator_arn}],
                    },
                },
            }
        },
        inferenceConfig={
            "models": [{
                "precomputedInferenceSource": {
                    "inferenceSourceIdentifier": model_response_identifier,
                }
            }]
        },
        outputDataConfig={"s3Uri": output_uri},
    )
    return response["jobArn"]


def main() -> int:
    load_dotenv(REPO / ".env")
    timestamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", type=Path, default=REPO / "pipeline/eval/questions.json")
    parser.add_argument("--responses", type=Path, help="JSON output from pipeline/eval/answers.py or another Thingy response run.")
    parser.add_argument("--rubric", type=Path, default=REPO / "pipeline/eval/rubric.md")
    parser.add_argument("--bucket", default=os.environ.get("LIBRARIAN_BUCKET") or DEFAULT_BUCKET)
    parser.add_argument("--dataset-key", default=f"eval/datasets/thingy-{timestamp}.jsonl")
    parser.add_argument("--output-prefix", default=f"eval/runs/thingy-{timestamp}/")
    parser.add_argument("--model-identifier", default=DEFAULT_MODEL_IDENTIFIER)
    parser.add_argument("--evaluator-model", default=os.environ.get("BEDROCK_EVAL_MODEL", DEFAULT_EVALUATOR_MODEL))
    parser.add_argument("--role-arn", default=os.environ.get("BEDROCK_EVAL_ROLE_ARN"))
    parser.add_argument("--job-name", default=f"thingy-{timestamp}")
    parser.add_argument("--generate-responses-live", action="store_true", help="Call the deployed Thingy /chat endpoint to create precomputed model responses.")
    parser.add_argument("--chat-url", default=os.environ.get("LIBRARIAN_STREAM_URL"), help="Base URL for the deployed streaming chat endpoint.")
    parser.add_argument("--session-secret", default=os.environ.get("LIBRARIAN_SESSION_SECRET") or os.environ.get("SESSION_SECRET"))
    parser.add_argument("--session-secret-from-lambda", default=os.environ.get("LIBRARIAN_STREAM_FUNCTION_NAME"))
    parser.add_argument("--request-timeout", type=int, default=120)
    parser.add_argument("--response-retries", type=int, default=2)
    parser.add_argument("--start-job", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    questions = load_questions(args.questions)
    if args.generate_responses_live:
        session = boto3.session.Session()
        region = session.region_name or os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
        session_secret = args.session_secret
        if not session_secret and args.session_secret_from_lambda:
            session_secret = fetch_lambda_session_secret(args.session_secret_from_lambda, region)
        if not args.chat_url:
            raise RuntimeError("--chat-url or LIBRARIAN_STREAM_URL is required with --generate-responses-live")
        if not session_secret:
            raise RuntimeError("--session-secret, LIBRARIAN_SESSION_SECRET, SESSION_SECRET, or --session-secret-from-lambda is required with --generate-responses-live")
        response_path = args.responses or (REPO / "tmp" / f"thingy-live-responses-{timestamp}.json")
        responses = generate_live_responses(
            questions=questions,
            chat_url=args.chat_url,
            session_secret=session_secret,
            timeout=args.request_timeout,
            retries=args.response_retries,
            output_path=response_path,
        )
    else:
        responses = load_responses(args.responses)
    rows = dataset_rows(questions, responses, args.model_identifier)
    if args.start_job and len(responses) != len(questions):
        missing = len(questions) - len(responses)
        raise RuntimeError(f"--start-job requires precomputed responses for every prompt; {missing} missing")

    local_dataset = REPO / "tmp" / Path(args.dataset_key).name
    write_jsonl(rows, local_dataset)
    print(f"Wrote {len(rows)} eval rows to {local_dataset}")

    if args.dry_run:
        return 0

    dataset_uri = upload_dataset(args.bucket, args.dataset_key, local_dataset)
    output_uri = f"s3://{args.bucket}/{args.output_prefix.rstrip('/')}/"
    print(f"Uploaded eval dataset to {dataset_uri}")

    if args.start_job:
        if not args.role_arn:
            raise RuntimeError("BEDROCK_EVAL_ROLE_ARN or --role-arn is required with --start-job")
        job_arn = start_evaluation_job(
            job_name=slug(args.job_name),
            role_arn=args.role_arn,
            dataset_uri=dataset_uri,
            output_uri=output_uri,
            evaluator_model=args.evaluator_model,
            model_response_identifier=args.model_identifier,
            rubric=args.rubric.read_text(encoding="utf-8"),
        )
        print(f"Started Bedrock evaluation job: {job_arn}")
    else:
        print("Dataset uploaded. Re-run with --start-job and BEDROCK_EVAL_ROLE_ARN to start Bedrock evaluation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
