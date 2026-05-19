# apps/librarian/ — Thingy

The AWS Lambda agent that answers reader questions against the Weekly Thing archive. "Librarian" is the system name in code; **Thingy** is the product name shown to users.

> Operational memory for editing this stack lives in [`CLAUDE.md`](CLAUDE.md). Full runtime guide — IAM cleanup plan, retrieval architecture, Tinylytics events, deployment checklist — is at [`../../docs/librarian.md`](../../docs/librarian.md).

## What it is

Two Lambdas behind one CloudFormation stack:

- **Auth Lambda** (REST via API Gateway) — handles subscriber email confirmation through Buttondown, mints HMAC-signed session tokens for the chat UI, the operator-only conversation-mirror feed for `thingy_bridge`, and per-answer feedback reactions.
- **Stream Lambda** (Function URL, response streaming) — handles `/chat` (SSE-streamed agent loop with tool use against the archive) and `/retrieve` (semantic JSON retrieval used by `workshop_bot` for its `archive__retrieve` tool + several pre-injection helpers).

The Q&A intelligence lives entirely here. Retrieval is **Bedrock Cohere embed → vector search → Cohere rerank** against a pre-embedded corpus in S3, with BM25 lexical fallback. Generation is Claude Sonnet via Bedrock Converse (cross-region inference profile, tool use enabled).

## Layout

```
apps/librarian/
├── README.md         ← this file
├── CLAUDE.md         ← operational memory
├── lambda/           ← Node.js Lambda code (runtime: Node 20, arm64)
│   ├── chat/         ← Stream Lambda — /chat + /retrieve
│   │   ├── handler.mjs    (thin re-export)
│   │   └── runtime.mjs    (~1100 lines; agent loop, retrieval, routes)
│   ├── auth/         ← Auth Lambda — /auth, /feedback, /list_conversations
│   ├── shared/       ← AWS clients, Bedrock streaming parser, FAQ search, session crypto, rate limiting
│   ├── prompts/      ← editable system prompts (packaged into both Lambdas)
│   └── tests/        ← Node tests
├── infra/
│   └── cloudformation.yaml   ← full stack: Lambdas, API Gateway, DynamoDB, IAM, CloudWatch
└── admin/            ← operator scripts for the live stack (scaffolding)
```

## Deploy

Always via `pipeline/deploy/aws.py`. Two flavors:

```bash
# Code + infra only (skip the slow + paid corpus reupload) — the default for code changes
npm run librarian:deploy -- --skip-corpus-upload

# Full deploy (rebuilds + embeds + uploads corpus)
npm run librarian:deploy

# Run Node tests
npm run librarian:test
```

CI auto-detects code/infra changes in `apps/librarian/` and runs the deploy step from `.github/workflows/deploy.yml`. Manual deploys are for local validation before commit.

Corpus + graph build/upload: `pipeline/deploy/upload_corpus.py`.

## Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/health` | none | Health check (returns model versions) |
| POST | `/chat` | session token (bearer) | SSE-streamed agent answer with tool use against the archive |
| POST | `/retrieve` | bridge secret (body) | JSON semantic retrieval — top-K archive passages, used by `workshop_bot` |
| POST | `/feedback` | session token (bearer) | Per-answer reactions (`👍` / `👎`) |
| POST | `/auth` | none / bridge secret | Email confirmation flow + Discord bridge mint + `list_conversations` |

## Tech stack

- **Node 20** (arm64) — Lambda runtime
- **AWS SDK v3** — `@aws-sdk/client-bedrock-runtime`, `client-bedrock-agent-runtime`, `client-dynamodb`, `client-s3`
- **Bedrock** — Cohere `embed-english-v3` (us-east-1), Cohere `rerank-v3-5:0` (us-west-2), Claude Sonnet 4.6 (cross-region inference)
- **DynamoDB** — conversation log, rate limits, per-user memory
- **S3** — pre-embedded corpus, graph artifacts
- **API Gateway** + **Lambda Function URL** (response streaming) — two distinct front doors for the two Lambdas

## Environment

Env vars are set in CloudFormation at deploy time from the repo-root `.env`. The full list (with deploy-side handling) is in [`CLAUDE.md`](CLAUDE.md). The headline secrets:

- `SESSION_SECRET` — HMAC signing key for session tokens
- `DISCORD_BRIDGE_SECRET` — operator-only secret for `/list_conversations` and `/retrieve`
- `BUTTONDOWN_API_KEY` — subscriber email verification

The `admin/` directory has its own [`README.md`](admin/README.md) for the (currently empty) operator-tooling scaffolding.

## Related reading

- [`CLAUDE.md`](CLAUDE.md) — operational memory (Bedrock model gotchas, retrieve internals, conventions)
- [`../../docs/librarian.md`](../../docs/librarian.md) — full runtime guide
- [`../thingy_bridge/`](../thingy_bridge/) — the Discord bridge to this Lambda (reader-facing surface)
- [`../workshop_bot/tools/thingy_retrieve.py`](../workshop_bot/tools/thingy_retrieve.py) — workshop_bot's client for the `/retrieve` endpoint
