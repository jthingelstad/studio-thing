# apps/librarian/

Thingy — the AWS Lambda agent that answers questions against the Weekly Thing archive. "Librarian" is the system name in code; "Thingy" is the product name shown to users.

## Layout

- `lambda/` — Node.js Lambda code
  - `chat/` — Lambda Function URL handler with response streaming
  - `auth/` — API Gateway Lambda for Buttondown auth + health checks
  - `shared/` — AWS clients, Bedrock streaming parser, FAQ search, session crypto, rate limiting
  - `prompts/` — editable system prompts (`agent-system.md`, etc.) packaged into both Lambdas
  - `tests/` — Node tests (`npm test`)
- `infra/cloudformation.yaml` — full stack: Lambdas, API Gateway, DynamoDB, IAM, CloudWatch

## Deploy

```bash
npm run librarian:deploy                      # full deploy
npm run librarian:deploy -- --skip-corpus-upload   # code-only, skips slow embed + S3 upload
npm run librarian:test                        # node tests
```

Deploy script: `pipeline/deploy/aws.py`. Corpus + graph build/upload: `pipeline/deploy/upload_corpus.py`.

For env vars, IAM, retrieval architecture, and the full deploy checklist, see [`docs/librarian.md`](../../docs/librarian.md).
