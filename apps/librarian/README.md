# apps/librarian/ — Thingy

The AWS Lambda agent that answers reader questions against Jamie Thingelstad's published archive: The Weekly Thing, thingelstad.com, and Another Thing. "Librarian" is the system name in code; **Thingy** is the product name shown to users.

> Operational memory for editing this stack lives in [`CLAUDE.md`](CLAUDE.md). Full runtime guide — IAM cleanup plan, retrieval architecture, Tinylytics events, deployment checklist — is at [`../../reference/librarian.md`](../../reference/librarian.md).

## What it is

Three Lambdas behind one CloudFormation stack:

- **Auth Lambda** (REST via API Gateway) — handles Buttondown subscriber lookup, Fastmail/JMAP magic-link login, HMAC-signed session tokens, conversation list/get/create/rename/delete, Discord bridge token minting, Dispatch drafting routes, profile updates, and per-answer feedback reactions.
- **Stream Lambda** (Function URL, response streaming) — handles `/chat` (SSE-streamed agent loop with server-side conversation history), `/welcome`, `/curiosity-map`, `/feedback`, and `/retrieve` (semantic JSON retrieval used by `workshop_bot` for its `archive__retrieve` tool + several pre-injection helpers).
- **Eval Lambda** (DynamoDB Stream trigger) — reviews updated server-side conversations out of band, writes summary/quality metadata back to DynamoDB, and posts operator cards directly to Discord via incoming webhook when configured.

The Q&A intelligence lives entirely here. Retrieval is **Bedrock Cohere embed → vector search → Cohere rerank** against a pre-embedded corpus in S3, with BM25 lexical fallback. Generation is Claude Sonnet via Bedrock Converse (cross-region inference profile, tool use enabled).

## Layout

```
apps/librarian/
├── README.md         ← this file
├── CLAUDE.md         ← operational memory
├── lambda/           ← Node.js Lambda code (runtime: Node 20, arm64)
│   ├── chat/         ← Stream Lambda — /chat, /welcome, /curiosity-map, /retrieve
│   │   ├── handler.mjs    (thin re-export)
│   │   └── runtime.mjs    (~1100 lines; agent loop, retrieval, routes)
│   ├── auth/         ← Auth Lambda — /auth, /feedback, conversations, Dispatch routes
│   ├── eval/         ← Eval Lambda — conversation reviews + Discord webhook cards
│   ├── shared/       ← AWS clients, Bedrock streaming parser, FAQ search, session crypto, rate limiting
│   ├── prompts/      ← editable system prompts (packaged into both Lambdas)
│   └── tests/        ← Node tests
├── infra/
│   └── cloudformation.yaml   ← full stack: Lambdas, API Gateway, DynamoDB, IAM, CloudWatch
└── admin/            ← operator scripts for the live stack
```

## Deploy

Always via `make librarian-deploy` or `venv/bin/python pipeline/deploy/aws.py`.
The deploy script needs the repo virtualenv packages (`boto3`, `python-dotenv`,
etc.); plain system `python`/`python3` may fail.

```bash
# Code + infra only (skip the slow + paid corpus reupload) — the default for code changes
make librarian-deploy ARGS="--skip-corpus-upload"

# Full deploy (rebuilds + embeds + uploads Weekly Thing, blog, and podcast corpora)
make librarian-deploy

# Run Node tests
npm --prefix apps/librarian/lambda test
```

CI auto-detects code/infra changes in `apps/librarian/` and runs the deploy step from `.github/workflows/deploy.yml`. Manual deploys are for local validation before commit.

Corpus build/upload is source-specific but treated as one API concern:

- Weekly Thing corpus + graph: `pipeline/deploy/upload_corpus.py`
- thingelstad.com blog corpus: `pipeline/deploy/upload_blog_corpus.py`
- Another Thing podcast corpus: `pipeline/deploy/upload_podcast_corpus.py`

New external content enters Studio through the `Studio — Sync External Content`
workflow first. It ingests Micro.blog posts into `data/blog/`, imports podcast
episodes into `data/podcast/`, commits those changes, and the production workflow
then uploads the updated corpus artifacts.

## Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/health` | none | Health check (returns model versions) |
| POST | `/chat` | session token (bearer) | SSE-streamed agent answer with tool use and server-side history |
| POST | `/welcome` | session token (bearer) | Agentic contextual welcome for authenticated users |
| POST | `/curiosity-map` | session token (bearer) | Generate and optionally store a curiosity-map artifact |
| POST | `/retrieve` | bridge secret (body) | JSON semantic retrieval — top-K archive passages, used by `workshop_bot` |
| POST | `/feedback` | session token (bearer) | Per-answer reactions plus optional comments |
| POST | `/auth` | none / bridge secret / session token | Magic-link auth, Discord bridge mint, user conversation management, profile updates, and Dispatch drafting |
| POST | `/memory` | session token (bearer) | Thingy profile fetch, learned item deletion, profile refresh, and profile deletion (`get`, `delete`, `refresh_profile`, `delete_profile`) |

## Tech stack

- **Node 20** (arm64) — Lambda runtime
- **AWS SDK v3** — `@aws-sdk/client-bedrock-runtime`, `client-bedrock-agent-runtime`, `client-dynamodb`, `client-s3`
- **Bedrock** — Cohere `embed-english-v3` (us-east-1), Cohere `rerank-v3-5:0` (us-west-2), Claude Sonnet 4.6 (cross-region inference)
- **DynamoDB** — conversation log, rate limits, per-user memory
- **S3** — pre-embedded corpus, graph artifacts
- **API Gateway** + **Lambda Function URL** (response streaming) — two HTTP front doors; the Eval Lambda is event-driven by DynamoDB Streams

## Environment

Env vars are set in CloudFormation at deploy time from the repo-root `.env`. The full list (with deploy-side handling) is in [`CLAUDE.md`](CLAUDE.md). The headline secrets:

- `SESSION_SECRET` — HMAC signing key for session tokens
- `DISCORD_BRIDGE_SECRET` — shared secret for Discord token minting and `/retrieve`
- `DISCORD_CONVERSATION_WEBHOOK_URL` — optional incoming webhook used by eval and Dispatch Lambdas to post operator cards to Discord
- `BUTTONDOWN_API_KEY` — subscriber email verification
- `FASTMAIL_JMAP_TOKEN` — optional Fastmail JMAP token used to send Thingy magic-link login emails from `thingy@thingelstad.com`
- `THINGY_TINYLYTICS_EMAIL_SITE_UID` — optional Tinylytics site UID override for email tracking pixels; defaults to Thingy's public site UID

Public Thingy email sessions always require possession-based magic-link authentication before minting a token. There is no direct-session deploy flag. Session tokens last ten days and can be refreshed while still valid.

## Conversation modes

Mode availability is encoded in the signed session token as entitlements and enforced by both conversation creation and chat:

| Mode | Entitlement | Who gets it |
|---|---|---|
| `thingy` | `reader` | Any active subscriber |
| `research_guide` | `supporting_member` | Premium/supporting subscribers or `thingy-supporting-member` tag |
| `thought_partner` | `owner` | Jamie's owner email/hash or `thingy-owner` tag |
| `trusted_circle` | `trusted_circle` | `thingy-trusted-circle`, `thingy-family`, or `thingy-close-friends` tag |

The `admin/` directory has its own [`README.md`](admin/README.md) for operator reporting and live-stack tooling.

## Related reading

- [`CLAUDE.md`](CLAUDE.md) — operational memory (Bedrock model gotchas, retrieve internals, conventions)
- [`../../reference/librarian.md`](../../reference/librarian.md) — full runtime guide
- [`../workshop_bot/tools/thingy_retrieve.py`](../workshop_bot/tools/thingy_retrieve.py) — workshop_bot's client for the `/retrieve` endpoint
