# librarian — project memory

Operational notes for the Thingy Lambda stack. Human-facing overview lives in [`README.md`](README.md). The full runtime guide (env vars, IAM cleanup plan, retrieval architecture in depth, Tinylytics events, deployment checklist) is at [`../../reference/librarian.md`](../../reference/librarian.md). This file is the "what to keep in mind when editing here" memory.

## Architecture: three Lambdas, one CloudFormation stack

The Lambda code is **Node.js** (Node 20 runtime, arm64). Everything else in this monorepo is Python — that's intentional: the Lambda needs the AWS SDK v3 + response-streaming primitives, both of which are smoother in Node.

Three Lambdas in `infra/cloudformation.yaml`:

- **`LibrarianFunction`** (`lambda/auth/handler.mjs`) — REST API behind API Gateway. Handles Buttondown subscriber lookup, Fastmail/JMAP magic-link login, HMAC session mint/redeem, user conversation list/get/create/rename/delete, Discord bridge mint, and operator-only canonical conversation reads. Memory 1024 MB, timeout 35s.
- **`LibrarianStreamFunction`** (`lambda/chat/handler.mjs` → `runtime.mjs`) — Function URL with `RESPONSE_STREAM`. Handles `/chat` (SSE-streamed agent loop with server-side history), `/welcome`, `/curiosity-map`, `/feedback`, and `/retrieve` (semantic JSON-only retrieval for workshop_bot). Memory 1536 MB, timeout 90s, ReservedConcurrentExecutions = 5.
- **`LibrarianEvalFunction`** (`lambda/eval/handler.mjs`) — DynamoDB Stream consumer. Reviews server-side conversations out of band, writes summary/quality/flags back to canonical conversation rows, and posts operator cards directly to Discord through `DISCORD_CONVERSATION_WEBHOOK_URL`. Memory 1024 MB, timeout 180s, ReservedConcurrentExecutions = 1.

All Lambdas share the same IAM role (`LibrarianFunctionRole`) and `shared/` helpers. The auth + stream bundles also include the `prompts/` directory.

### The `/chat` agent loop

`lambda/chat/runtime.mjs` is the meat of it (~1100 lines). On each turn:

1. Verify bearer token (HMAC-signed session JWT — `verifyToken`, `SESSION_SECRET`).
2. Rate-limit per subscriber hash (DynamoDB, hourly).
3. Resolve requested conversation mode from token entitlements and existing conversation metadata.
4. Load the relevant server-side conversation turns and user memory.
5. Load scoped corpus artifacts from S3 (cached on warm starts).
6. Run prompt preflight for privacy/scope handling.
7. Run the Bedrock Converse agent loop with tool use. Tools include `search_faq`, `search_archive`, `get_source`, `find_links`, `corpus_stats`, `latest_content`, `list_content`, `archive_lens`, `entity_lens`, `source_neighborhood`, `archive_gems`, `claim_check`, and `remember_user`.
8. Stream answer deltas, archive-work status, final citations, and experience artifacts via SSE; record the turn to DynamoDB; update per-user memory.

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

1. Smoke-test the three Thingy model buckets — refuses to deploy if any configured default/fast/advanced model isn't invokable from this account.
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
| `FASTMAIL_JMAP_TOKEN` | auth | Fastmail JMAP bearer token for sending magic links; aliases `THINGY_FASTMAIL_JMAP_TOKEN` / `THINGY_JMAP_TOKEN` also work locally |
| `THINGY_MAGIC_LINK_FROM_EMAIL` | auth | Magic-link From address, default `thingy@thingelstad.com` |
| `THINGY_MAGIC_LINK_BASE_URL` | auth | Public URL used when building `?login_token=` links, default `https://thingy.thingelstad.com/` |
| `LOG_LEVEL` | both | `INFO` default |
| `AUTH_RATE_LIMIT_MAX` | auth | Hourly cap per IP |
| `THINGY_DEFAULT_MODEL` | all | `us.anthropic.claude-sonnet-4-6`; main chat/default persona work |
| `THINGY_FAST_MODEL` | all | `us.anthropic.claude-haiku-4-5-20251001-v1:0`; small structured/background work |
| `THINGY_ADVANCED_MODEL` | all | `us.anthropic.claude-opus-4-6-v1`; high-synthesis work like Dispatch generation |
| `BEDROCK_EMBEDDING_MODEL` | stream | `cohere.embed-english-v3` |
| `BEDROCK_RERANK_MODEL` | stream | `cohere.rerank-v3-5:0` |
| `BEDROCK_RERANK_REGION` | stream | `us-west-2` (only region with the rerank model) |

## Bedrock model gotchas

- **Rerank lives in us-west-2 only.** The rest of the stack is us-east-1. `BedrockAgentRuntimeClient` is constructed with explicit `region: 'us-west-2'` override. Don't move it.
- **Embedding model is Cohere v3** at 1024 dimensions. Bumping to v4 would invalidate the entire embedded corpus — re-embed cost is $1-2 + ~3 minutes. Plan for it; don't drift accidentally.
- **Thingy models** use cross-region inference profiles. Default is Sonnet 4.6 for main chat/persona work, fast is Haiku 4.5 for structured/background work, and advanced is Opus 4.6 for Dispatch generation. The deploy smoke test checks all three before CloudFormation runs.

## Conventions

- **Prompts live in `prompts/`** as `.md` files. `loadToolSpecs()` reads them. Edits need a redeploy.
- **All structured logging via `logEvent(level, message, fields)`** — JSON output, CloudWatch-Insights-readable.
- **Magic-link auth is mandatory.** Public `/auth` always sends a Fastmail/JMAP magic link before minting an email session; there is no direct session fallback after subscriber validation.
- **Session tokens are HMAC-signed** (not encrypted). The `sub` claim is the SHA256 hash of the subscriber email (`emailHash()`). Discord bridge subs are prefixed `discord:` so they're trivially distinguishable. Reader sessions last ten days, and a still-valid session can be refreshed by `/auth` `action=refresh_session`.
- **Privacy guarding** lives in `runtime.mjs#privacyGuardAnswer`. Don't bypass; readers ask questions that leak their own PII and we don't echo it.
- **Conversation modes are entitlement-gated.** `thingy` is for all readers, `research_guide` requires `supporting_member`, `thought_partner` requires `owner`, and `trusted_circle` requires `trusted_circle`.
- **Citations use `#NNN` for Weekly Thing sources.** Blog and podcast sources should be cited by title/permalink because they do not have issue numbers.
- **Bridge-secret check is `crypto.timingSafeEqual`** — duplicated in two files (`runtime.mjs` + `auth/handler.mjs`) because the two bundles ship separately. Don't refactor to a shared helper without re-checking the bundle topology.

## Known follow-ups

- **No end-to-end handler tests.** Mocking Bedrock + DynamoDB + S3 in Node test is non-trivial; the agent-loop path is exercised in production via real reader Q&A.
- **No automated live QA harness.** Mode/auth/conversation/eval checks are still run manually against the live API when needed.
- **Operator report is local/static.** A public or remote operator dashboard needs stronger owner/admin auth first.
