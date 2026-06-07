# apps/librarian/admin/

Operator tooling for the deployed Thingy stack lives here.

This is the home for scripts that talk to the *live* librarian stack — DynamoDB conversations, CloudWatch logs, S3 corpus state, eval harnesses — as distinct from `pipeline/` (build-time data → site) and `lambda/` (runtime code).

## Tools

### `operator_report.py`

Generates a local, static HTML report from the canonical DynamoDB
conversation/eval rows. It has no public web route and does not expose any
browser-side secrets. By default it writes to Jamie's Desktop so iCloud can
sync it to other devices:

```bash
venv/bin/python apps/librarian/admin/operator_report.py
open ~/Desktop/Thingy\ Operator\ Report.html
```

Useful options:

```bash
# 30-day report
venv/bin/python apps/librarian/admin/operator_report.py --days 30

# Custom output
venv/bin/python apps/librarian/admin/operator_report.py --output tmp/thingy-report.html
```

The report includes quality counts, eval flags, explicit feedback, daily
volume, a watchlist, recent conversations, and expandable transcript detail
for prioritized conversations.

## Planned

- **Eval harness** — replacement for the removed `pipeline/eval/` pipeline. Approach TBD; the previous Bedrock Model Evaluation flow was over-engineered for the question volume.
- **Log inspection** — convenience wrappers over CloudWatch Insights queries for the streaming and auth Lambdas.

## Conventions

- Scripts read AWS credentials from `.env` via `python-dotenv` (same pattern as `pipeline/deploy/`).
- Resolve stack resources (DynamoDB table name, Lambda ARNs) from CloudFormation stack outputs rather than hard-coding.
- Output should default to human-readable; offer `--json` for piping into other tools.
