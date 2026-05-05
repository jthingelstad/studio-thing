# apps/librarian/admin/

**Status: empty scaffolding.** Operator tooling for the deployed Thingy stack lives here.

This is the home for scripts that talk to the *live* librarian stack — DynamoDB conversations, CloudWatch logs, S3 corpus state, eval harnesses — as distinct from `pipeline/` (build-time data → site) and `lambda/` (runtime code).

## Planned

- **Conversation review** — replaces the removed `pipeline/eval/review_conversations.py`. Reads the conversations DynamoDB table and surfaces recent Q&A with citations and feedback. Worth doing better than the original: filter by thumbs-down feedback, search by question text, group by subscriber hash, and flag low-citation or low-confidence answers.
- **Eval harness** — replacement for the removed `pipeline/eval/` pipeline. Approach TBD; the previous Bedrock Model Evaluation flow was over-engineered for the question volume.
- **Log inspection** — convenience wrappers over CloudWatch Insights queries for the streaming and auth Lambdas.

## Conventions

- Scripts read AWS credentials from `.env` via `python-dotenv` (same pattern as `pipeline/deploy/`).
- Resolve stack resources (DynamoDB table name, Lambda ARNs) from CloudFormation stack outputs rather than hard-coding.
- Output should default to human-readable; offer `--json` for piping into other tools.
