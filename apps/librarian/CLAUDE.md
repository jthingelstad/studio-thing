# librarian — project memory

Operational notes for the Thingy Lambda stack. Human-facing overview lives in [`README.md`](README.md). The full runtime guide (env vars, IAM cleanup plan, retrieval architecture in depth, Tinylytics events, deployment checklist) is at [`../../reference/librarian.md`](../../reference/librarian.md). This file is the "what to keep in mind when editing here" memory.

## Architecture: three Lambdas, one CloudFormation stack

The Lambda code is **Node.js** (Node 20 runtime, arm64). Everything else in this monorepo is Python — that's intentional: the Lambda needs the AWS SDK v3 + response-streaming primitives, both of which are smoother in Node.

Three Lambdas in `infra/cloudformation.yaml`:

- **`LibrarianFunction`** (`lambda/auth/handler.mjs`) — REST API behind API Gateway. Handles `/auth` (subscriber email confirmation via Buttondown + JWT-style session token + Discord bridge mint), `/feedback` (per-answer reactions + optional comments), and operator-only canonical conversation reads for `thingy_bridge`. Memory 1024 MB, timeout 35s.
- **`LibrarianStreamFunction`** (`lambda/chat/handler.mjs` → `runtime.mjs`) — Function URL with `RESPONSE_STREAM`. Handles `/chat` (SSE-streamed agent loop) and `/retrieve` (semantic JSON-only retrieval for workshop_bot). Memory 1536 MB, timeout 90s, ReservedConcurrentExecutions = 5.
- **`LibrarianEvalFunction`** (`lambda/eval/handler.mjs`) — DynamoDB Stream consumer. Reviews server-side conversations out of band, writes summary/quality/flags back to canonical conversation rows, and posts operator cards directly to Discord through `DISCORD_CONVERSATION_WEBHOOK_URL`. Memory 1024 MB, timeout 180s, ReservedConcurrentExecutions = 1.

All Lambdas share the same IAM role (`LibrarianFunctionRole`) and `shared/` helpers. The auth + stream bundles also include the `prompts/` directory.

### The `/chat` agent loop

`lambda/chat/runtime.mjs` is the meat of it (~1100 lines). On each turn:

1. Verify bearer token (HMAC-signed session JWT — `verifyToken`, `SESSION_SECRET`).
2. Rate-limit per subscriber hash (DynamoDB, hourly).
3. Load corpus from S3 (cached on warm starts — `loadCorpus`).
4. Privacy-guard the question (`privacyGuardAnswer` — short-circuits PII / "what's my email" probes).
5. Run the Bedrock Converse agent loop with tool use (`streamBedrockAgentAnswer`). Tools available: `search_archive`, `retrieve_archive`, `get_issue`, `get_section`, `quote_search`, `list_recent`, `search_faq`. Each tool call dispatches to the corresponding shared/ helper.
6. Stream answer deltas + final citations via SSE; record the conversation to DynamoDB; update per-user memory.

The retrieval pipeline (functions live in `runtime.mjs`):

- **`embedQuery`** — Bedrock Cohere `embed-english-v3` (us-east-1).
- **`retrieveSemantic`** — cosine similarity against pre-embedded corpus chunks.
- **`retrieveLexical`** — BM25 fallback if semantic returns nothing.
- **`rerankSources`** — Bedrock Cohere `rerank-v3-5:0` (us-west-2 — only region with rerank). Capped at top 40 candidates.
- **`retrieve`** — orchestrator that does semantic → rerank, falls back to lexical → rerank on error.

### The `/retrieve` endpoint

Added in May 2026. Same `retrieve()` function `/chat` uses, exposed as a JSON-only POST with bridge-secret auth (no per-user session token). Returns `{passages, embedding_model, rerank_model, request_id}`. Called by `workshop_bot` for its `archive__retrieve` agent tool + several pre-injection helpers (compose-closer, pinboard-scan resonance, draft-review echoes, promotion-prep thread context, compose-subject thread awareness).

The `bridgeSecretOk` helper in `runtime.mjs` mirrors the same check in `auth/handler.mjs` — both compare against `DISCORD_BRIDGE_SECRET` via `crypto.timingSafeEqual`. It's duplicated rather than shared because the two bundles ship separately and adding a shared `crypto` helper to `shared/` would add build complexity for 5 lines.

## Deploy

Always via `pipeline/deploy/aws.py`:

```bash
# Default: skip corpus reupload — code+infra only
python pipeline/deploy/aws.py --skip-corpus-upload

# Full deploy (rebuilds + embeds + uploads Weekly Thing, blog, and podcast corpora)
python pipeline/deploy/aws.py
```

The `--skip-corpus-upload` flag is the **default for any code-only change**. Full corpus reupload is slow and paid (Bedrock embed cost); only do it when one or more corpus artifacts are stale (new source content, schema change, embed model change).

Deploy steps:

1. Smoke-test the Bedrock agent model (`smoke_test_agent_model`) — refuses to deploy if the model isn't invokable from this account.
2. Package both Lambda bundles (`auth/` + `chat/` separately).
3. Upload zip to `s3://weekly-thing-librarian/code/{auth,chat}-lambda/<ts>.zip`.
4. If not `--skip-corpus-upload`: upload all three API corpora — Weekly Thing corpus + graph, blog corpus, and podcast corpus.
5. CloudFormation `update-stack` with the new code keys + secrets from `.env` (`SESSION_SECRET`, `DISCORD_BRIDGE_SECRET`, `DISCORD_CONVERSATION_WEBHOOK_URL`, `BUTTONDOWN_API_KEY`).
6. Configure 30-day log retention on the auto-created log groups.
7. Update `.env` with the latest stack outputs (`LIBRARIAN_API_URL`, `LIBRARIAN_STREAM_URL`).

CI auto-detects code/infra changes in `apps/librarian/` and runs the deploy step (`.github/workflows/deploy.yml`). New blog/podcast content enters through `.github/workflows/sync-external-content.yml`, which commits `data/blog/**` / `data/podcast/**` updates so the production workflow can rebuild and upload corpora. Manual deploys are for local validation before commit.

## Tests

`lambda/tests/*.test.mjs` — Node tests for shared modules (`session`, `conversations`, `attribution`, FAQ search, Bedrock stream parsing, etc.). No end-to-end handler invocation tests — handlers depend on Bedrock + S3 + DynamoDB mocks that don't exist yet.

```bash
npm run librarian:test
# or: cd apps/librarian/lambda && npm test
```

Python tests don't cover this directory — the Lambda is pure Node.

## Env vars set in CloudFormation

These are set at deploy time from `.env`, written into the Lambda environment by CloudFormation. Don't try to read them from `process.env` outside the Lambda.

| Var | Used by | Notes |
|---|---|---|
| `ALLOWED_ORIGIN` | both | Comma-separated CORS origins |
| `TABLE_NAME` | both | DynamoDB conversation table |
| `CORPUS_BUCKET`, `CORPUS_KEY`, `GRAPH_KEY` | stream | S3 corpus/graph location |
| `BLOG_CORPUS_KEY`, `PODCAST_CORPUS_KEY` | stream | Optional source-specific corpora loaded lazily |
| `BUTTONDOWN_API_KEY` | auth | Email subscriber verification |
| `SESSION_SECRET` | both | HMAC secret for session JWTs |
| `DISCORD_BRIDGE_SECRET` | auth + stream | Bridge-secret auth for operator conversation reads + `/retrieve` |
| `DISCORD_CONVERSATION_WEBHOOK_URL` | eval | Discord incoming webhook for posting reviewed conversation cards to `#chatter` |
| `LOG_LEVEL` | both | `INFO` default |
| `AUTH_RATE_LIMIT_MAX` | auth | Hourly cap per IP |
| `BEDROCK_AGENT_MODEL` | both | `us.anthropic.claude-sonnet-4-6` |
| `BEDROCK_EMBEDDING_MODEL` | stream | `cohere.embed-english-v3` |
| `BEDROCK_RERANK_MODEL` | stream | `cohere.rerank-v3-5:0` |
| `BEDROCK_RERANK_REGION` | stream | `us-west-2` (only region with the rerank model) |

## Bedrock model gotchas

- **Rerank lives in us-west-2 only.** The rest of the stack is us-east-1. `BedrockAgentRuntimeClient` is constructed with explicit `region: 'us-west-2'` override. Don't move it.
- **Embedding model is Cohere v3** at 1024 dimensions. Bumping to v4 would invalidate the entire embedded corpus — re-embed cost is $1-2 + ~3 minutes. Plan for it; don't drift accidentally.
- **Agent model** is currently `us.anthropic.claude-sonnet-4-6` (cross-region inference profile). The smoke test at deploy time catches "this account doesn't have access" before the deploy lands.

## Conventions

- **Prompts live in `prompts/`** as `.md` files. `loadToolSpecs()` reads them. Edits need a redeploy.
- **All structured logging via `logEvent(level, message, fields)`** — JSON output, CloudWatch-Insights-readable.
- **Session tokens are HMAC-signed** (not encrypted). The `sub` claim is the SHA256 hash of the subscriber email (`emailHash()`). Discord bridge subs are prefixed `discord:` so they're trivially distinguishable.
- **Privacy guarding** lives in `runtime.mjs#privacyGuardAnswer`. Don't bypass; readers ask questions that leak their own PII and we don't echo it.
- **Citations use `#NNN`** (Discord-bridge readers see them rewritten to clickable archive links in `thingy_bridge`).
- **Bridge-secret check is `crypto.timingSafeEqual`** — duplicated in two files (`runtime.mjs` + `auth/handler.mjs`) because the two bundles ship separately. Don't refactor to a shared helper without re-checking the bundle topology.

## Known follow-ups

- **No end-to-end handler tests.** Mocking Bedrock + DynamoDB + S3 in Node test is non-trivial; the agent-loop path is exercised in production via real reader Q&A.
- **`admin/` is scaffolding.** Conversation review, eval harness, log inspection — all planned, none built. See `admin/README.md`.
- **The pre-embedded corpus reupload** doesn't have a "what changed" pre-check — it always re-embeds the whole archive. A delta-aware uploader would cut deploy cost on issue ships.
