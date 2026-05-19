# pipeline/deploy/ — project memory

AWS deploy tooling for the Thingy Lambda stack. No README — this directory is operator-only.

## The three scripts

| Script | What it does |
|---|---|
| `aws.py` | Packages the two Lambda bundles, uploads them to S3, runs CloudFormation update-stack with the new code keys + secrets from `.env`. **The canonical deploy entrypoint.** |
| `upload_corpus.py` | Builds the corpus + graph from `apps/site/archive/`, embeds via Bedrock Cohere, uploads to S3. Called by `aws.py` unless `--skip-corpus-upload`. |
| `bedrock_logging.py` | Configures Bedrock model invocation logging (CloudWatch destination + S3 archive). One-time setup. |

## Invocation

Always via `npm run librarian:deploy` (which calls `aws.py`). Two flavors:

```bash
# Default for code changes — skip the slow + paid corpus reupload
npm run librarian:deploy -- --skip-corpus-upload

# Full deploy (re-embeds + uploads the corpus)
npm run librarian:deploy
```

The `--skip-corpus-upload` flag is the default for any **code-only** change (Lambda code, CloudFormation tweaks, env-var changes). Full corpus reupload is **slow** (~3 minutes for embedding + S3 upload) and **paid** (Bedrock embed cost ~$1 per full run). Only do a full deploy when:

- The corpus itself is stale (new issues to embed)
- The embed model has changed (Cohere v3 → v4, hypothetically)
- The corpus schema has changed (e.g., new chunk metadata field)

CI in `.github/workflows/deploy.yml` does the full corpus upload on every issue ship — `upload_corpus.py` is wired in directly there, not via `aws.py`. Manual deploys are for local validation before commit.

## `aws.py` flow

1. **Smoke-test the Bedrock agent model** (`smoke_test_agent_model`) via a minimal `InvokeModel` against `BEDROCK_AGENT_MODEL` (default `us.anthropic.claude-sonnet-4-6`). Refuses to deploy if the model isn't accessible from this account. Pass `--skip-smoke-test` to override.
2. **Ensure the private S3 bucket exists** (`ensure_private_bucket(bucket)`). Default bucket: `LIBRARIAN_BUCKET` env var or `weekly-thing-librarian`.
3. **Package both Lambda bundles** (`auth/` + `chat/`) — separate npm install + zip per bundle. Bundles ship independently because the auth Lambda is REST and the chat Lambda is response-streamed Function URL.
4. **Upload zips** to `s3://{bucket}/code/{auth,chat}-lambda/<unix-ts>.zip`. Timestamp keys so CloudFormation always sees a new version.
5. **Optional**: `upload_corpus.py` runs — rebuilds corpus + graph, embeds, uploads.
6. **CloudFormation update-stack** with the new code keys + secrets from `.env`: `SESSION_SECRET`, `DISCORD_BRIDGE_SECRET`, `BUTTONDOWN_API_KEY`.
7. **30-day log retention** on the auto-created log groups (`configure_log_retention`).
8. **Update `.env`** with the latest stack outputs: `LIBRARIAN_API_URL`, `LIBRARIAN_STREAM_URL`.

## `upload_corpus.py` flow

1. Build the corpus from `apps/site/archive/*.md` via `librarian_core.corpus.build_corpus(include_issue_bodies=True)`.
2. Build the graph (link references, topic co-occurrence) via `librarian_core.graph`.
3. Embed each chunk via Bedrock Cohere `embed-english-v3`. Dimension: 1024. Concurrency: 10. Retry-on-429 (Bedrock throttle).
4. Upload `corpus.json` + `graph.json` to `s3://{bucket}/{CORPUS_KEY, GRAPH_KEY}`.
5. The Lambda's `loadCorpus()` picks up the new file on the next cold start (or after `aws.py` triggers a new deployment).

## Secrets

Pulled from the repo-root `.env`. Required:

| Var | Source | What for |
|---|---|---|
| `BUTTONDOWN_API_KEY` | account secrets | Auth Lambda's subscriber verification |
| `LIBRARIAN_SESSION_SECRET` | (auto-generated if missing) | HMAC signing for session JWTs |
| `LIBRARIAN_BRIDGE_SECRET` | shared secret | `/list_conversations` + `/retrieve` auth |
| `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY` | the `wt-archive` IAM user | Deploys + corpus upload |

The CloudFormation stack uses an IAM service role for execution; the local AWS credentials are just for `cloudformation:UpdateStack` + `s3:PutObject`.

## Bedrock regions

- **Embed model** (`cohere.embed-english-v3`): **us-east-1**.
- **Rerank model** (`cohere.rerank-v3-5:0`): **us-west-2** — only region with the rerank model. The Lambda's `BedrockAgentRuntimeClient` is constructed with explicit `region: 'us-west-2'` override.
- **Agent model** (`us.anthropic.claude-sonnet-4-6`): cross-region inference profile.

Don't move the rerank region. Don't change the agent model without smoke-testing it against the deploy's account.

## CloudFormation template

Lives at `apps/librarian/infra/cloudformation.yaml`. Two Lambdas (auth + stream), API Gateway (REST), Lambda Function URL (Stream, RESPONSE_STREAM mode), DynamoDB (conversations + rate limits + user memory), IAM role + policies, CloudWatch log groups, Bedrock IAM policies for embed/rerank/invoke. See [`../../apps/librarian/CLAUDE.md`](../../apps/librarian/CLAUDE.md) for the runtime side of what's deployed.

## Conventions

- **`--skip-corpus-upload` is the default for code changes.** (Memory: `reference_librarian_deploy_flags.md`.)
- **Don't disable the smoke test casually.** The Bedrock model access check at deploy time prevents the most common "deployed but immediately broken" failure mode.
- **Stack name is `weekly-thing-librarian`** (`STACK_NAME` in `aws.py`). Don't rename without coordinating with `.env`-referenced outputs.
- **Log retention is 30 days.** Bedrock invocation logs go to a separate longer-retention destination via `bedrock_logging.py`.
