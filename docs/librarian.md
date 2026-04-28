# Archive Librarian

Thingy is a subscriber-gated chat interface for the Weekly Thing archive.

## Local Artifacts

- `npm run librarian:corpus` builds `data/librarian/corpus.json` from the cleaned generated archive.
- The tracked corpus is text-only and citation-ready. It includes issue summaries, topic metadata, and chunk-level retrieval metadata.
- Embedded corpus files should not be committed. Use the upload command to generate Bedrock Cohere embeddings and push the deployable corpus to S3.
- `npm run librarian:graph` builds `data/librarian/graph.json`, the offline entity/trope/similarity artifact used by the archive tools.
- `pipeline/librarian/eval_librarian_rag.py` prints retrieval and reranker diagnostics for standard or multi-hop question sets.
- `pipeline/librarian/eval_librarian_answers.py` runs baseline or agentic answer generation, then asks Bedrock to judge answer quality. Results are written to `tmp/librarian-answer-eval.json`.
- The `weekly-agent` eval suite covers 20 recall, synthesis, recommendation, pattern, voice, tricky retrieval, and edge-case prompts: `python pipeline/librarian/eval_librarian_answers.py --mode agent --question-set weekly-agent --sample-limit 20`.
- `pipeline/librarian/review_librarian_conversations.py` reads beta conversation logs from DynamoDB for review.

## AWS Runtime

The backend is defined in `infra/librarian/cloudformation.yaml`. Auth and auth health checks run behind API Gateway/Lambda. Streaming chat, generated prompts, and stream health checks run through a Lambda Function URL with response streaming enabled. It uses:

- Buttondown API for subscriber lookup.
- Amazon Bedrock Claude Sonnet 4.6 for prompts, premium messages, baseline synthesis, and the agent loop.
- Amazon Bedrock Cohere Embed v3 for query-to-archive retrieval.
- Amazon Bedrock Cohere Rerank 3.5 after archive searches.
- DynamoDB for session and rate-limit state.
- S3 for the embedded archive corpus and the offline graph artifact.
- CloudWatch Logs for structured JSON request, retrieval, upstream, and error logs.

The browser fetches generated suggested questions from `site.librarianStreamUrl + /prompts` after subscriber validation. Chat streams from `site.librarianStreamUrl + /chat`; there is no buffered API Gateway chat fallback.

## Commands

```sh
npm run librarian:corpus
npm run librarian:graph
npm run librarian:eval
npm run librarian:eval:answers
npm run librarian:conversations -- --limit 25
npm run librarian:corpus:upload
npm run librarian:deploy
```

For raw JSON conversation review:

```sh
npm run librarian:conversations -- --limit 25 --json
```

After deployment, set `site.librarianApiUrl` in `site/_data/site.js` to the `LibrarianApiUrl` output by CloudFormation and `site.librarianStreamUrl` to `LibrarianStreamUrl`. The current production values are already stored in `site/_data/site.js`.

## Required Secrets

CloudFormation parameters:

- `ButtondownApiKey`
- `SessionSecret`
- `CorpusBucket`

Local `.env` values used by upload/build scripts:

- `BUTTONDOWN_API_KEY`
- `TINYLYTICS_SITE_UID` or `TINYLYTICS_SITE_ID` for the static website embed, not the API.
- `AWS_S3_BUCKET`
- `AWS_DEFAULT_REGION`
- `BEDROCK_AGENT_MODEL` (optional; defaults to `us.anthropic.claude-sonnet-4-6`, the US Bedrock inference profile for Claude Sonnet 4.6)
- `BEDROCK_EMBEDDING_MODEL` (optional; defaults to `cohere.embed-english-v3`)
- `BEDROCK_RERANK_MODEL` (optional; defaults to `cohere.rerank-v3-5:0`)
- `BEDROCK_RERANK_REGION` (optional; defaults to `us-west-2`, where the Bedrock Rerank API exposes Cohere Rerank 3.5)
- `LIBRARIAN_AGENT_ENABLED` (runtime flag; deployed as `1`; set to `0` for rollback to the single-shot Bedrock path)
- `LIBRARIAN_LOG_LEVEL` (optional; defaults to `INFO`)
- `LIBRARIAN_AUTH_RATE_LIMIT_MAX` (optional; defaults to 30 auth attempts per client identity per hour)
- `LIBRARIAN_CONVERSATION_LOGGING` (optional; defaults to enabled. Set to `0` to disable beta transcript logging.)
- `LIBRARIAN_CONVERSATION_LOG_TTL_DAYS` (optional; defaults to 60 days.)

By default, deploy scripts ignore `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` from `.env` and use the configured AWS CLI credentials instead. Set `LIBRARIAN_USE_ENV_AWS_CREDENTIALS=1` only if those `.env` credentials should deploy infrastructure.

## Permanent IAM Setup

The first deploy can use local AWS CLI credentials to bootstrap the stack. Routine deploys currently use the `wt-archive` IAM user with an attached `WeeklyThingLibrarianDeploy` managed policy. That policy grants enough access to upload `s3://files.thingelstad.com/librarian/*` artifacts and update the `weekly-thing-librarian` CloudFormation stack.

The long-term cleanup is still a dedicated CloudFormation service role.

The stack already creates a Lambda execution role for Thingy. The remaining production cleanup is a dedicated deployment path:

- Create a `weekly-thing-librarian-cloudformation` service role trusted by CloudFormation.
- Give that service role permissions only for the Librarian stack resources: Lambda, API Gateway HTTP API, DynamoDB table, the Lambda execution role, CloudWatch log group, and `s3://$AWS_S3_BUCKET/librarian/*`.
- Create a narrow deploy identity, preferably a GitHub Actions OIDC role if deployments move into Actions, that can upload `librarian/*` S3 artifacts and update only the `weekly-thing-librarian` CloudFormation stack.
- Set `LIBRARIAN_CLOUDFORMATION_ROLE_ARN` to the service role ARN before running `npm run librarian:deploy`.

The deploy script passes `LIBRARIAN_CLOUDFORMATION_ROLE_ARN` to CloudFormation when present, so the caller only needs permission to upload artifacts, update the stack, and pass that one service role.

## Access Model

Thingy uses a soft subscriber gate. A visitor enters an email address, Lambda validates that email against Buttondown, and then returns a short-lived signed session token for active `regular` and `premium` subscribers. This does not prove inbox ownership; it is a pragmatic gate for a low-risk, rate-limited archive feature.

Premium subscribers get a small Bedrock-generated Supporting Member thank-you before entering chat, with a fixed fallback if Bedrock is unavailable. Unknown email addresses can opt in from the librarian page; those signups are created in Buttondown with the `sub_tag_3ts444xst99y08j8bqfnwt1g4h` source tag and must confirm their email before using Thingy. Unconfirmed subscribers can request Buttondown's confirmation reminder email from the same page. The logout control is local-only: it clears the browser's stored session token and returns to the email gate.

## Logging And Review

Lambda writes structured JSON logs to CloudWatch. Logs include request ID, route, status code, duration, subscriber email hash, retrieval mode, citation count, upstream status/duration, and error type. Raw email addresses, API keys, and session tokens are not logged. The backend does not call Tinylytics; server-side activity should come from CloudWatch logs, metrics, and DynamoDB conversation review.

Every API response includes an `x-request-id` header. Browser-visible errors include that reference so the matching CloudWatch request can be found quickly.

Successful beta conversations are stored in the existing DynamoDB table when `LIBRARIAN_CONVERSATION_LOGGING` is enabled. These records are intended for answer-quality review and include:

- timestamp and request ID
- subscriber hash, not raw email address
- route (`chat` or `stream`)
- question and answer text
- history count
- citation count
- source issue numbers
- citation metadata
- TTL, defaulting to 60 days

Review recent conversations with:

```sh
npm run librarian:conversations -- --limit 25
```

The script resolves the DynamoDB table name from the `weekly-thing-librarian` CloudFormation stack unless `LIBRARIAN_TABLE_NAME` is set.

The beta popup on `/librarian/` tells authenticated users that beta conversations may be logged and reviewed to improve Thingy.

`GET /health` is available as a cheap smoke-test endpoint. It verifies API Gateway and Lambda routing without calling Buttondown, Bedrock, DynamoDB, or S3.

`POST /prompts` is served by the streaming Lambda Function URL and requires a valid session token. It returns three generated suggested questions and falls back to a static set if Bedrock is unavailable.

Thingy uses hybrid retrieval. It merges semantic embedding matches, lexical matches, and issue-summary/topic graph matches, reranks the top candidates with Cohere Rerank 3.5 through the Bedrock Agent Runtime rerank API, then applies context-aware recency and issue diversity. Current/recommendation questions prefer newer material when relevance is close. History/evolution questions intentionally preserve sources across eras.

When `LIBRARIAN_AGENT_ENABLED=1`, chat requests run through a tool-using Claude Sonnet 4.6 loop capped by `MAX_TOOL_TURNS` (default 8). The agent can call:

- `search_archive(query, year_range?, section?, limit?)`
- `get_issue(number)`
- `get_section(number, section)`
- `find_links(domain?, topic?, year_range?)`
- `domain_history(domain)`
- `quote_search(phrase)`
- `list_issues(year?, topic?, entity?)`
- `compare_eras(topic, year_a, year_b)`

The agent uses the same subscriber gate, rate limits, browser-supplied history, and DynamoDB logging as the baseline path. Tool status is emitted over the existing streaming Function URL as `status` events.

The graph artifact is built offline from the corpus and archive front matter. It stores per-issue entities, recurring tropes/stances, and top-K similar issues from issue-level embedding averages. `pipeline/librarian/build_librarian_graph.py --use-bedrock-extraction` can use Sonnet for entity/trope extraction; the default heuristic mode is available for cheap local refreshes.

Typical cost is controlled by prompt caching on the stable system prompt and tool definitions, reranking only the top search candidates, limiting tool turns, and clipping tool result text. The target remains under $0.20 for typical questions and under $0.50 for worst-case multi-hop questions.

Thingy answers cite issue numbers inline, and the browser turns matching `#123` references into archive links with native tooltips containing the source details. The API still returns citation metadata for rendering, but the page does not show a separate Sources block.

The browser sends a compact recent conversation history with each chat request so follow-up questions can refer to earlier turns. The history is kept in browser memory only, clipped before sending, and is not written as a separate session transcript. Successful individual turns are written to DynamoDB for beta review as described above.

## Tinylytics Events

The site loads Tinylytics with `events` and `beacon` enabled. Thingy emits these events:

- `librarian.auth_submit`
- `librarian.auth_success`
- `librarian.auth_error` with value `client` or `server`
- `librarian.auth_not_found`
- `librarian.auth_unconfirmed`
- `librarian.auth_subscribe_success`
- `librarian.auth_reminder_success`
- `librarian.auth_inactive`
- `librarian.logout`
- `librarian.session_resume`
- `librarian.prompts_loaded` with value `generated` or `fallback`
- `librarian.prompts_error` with value `client` or `server`
- `librarian.prompt_select` with the prompt position
- `librarian.question_submit`
- `librarian.answer_success` with value `{question-size}.{citation-count}`
- `librarian.answer_error` with value `client` or `server`
- `librarian.source_click` with the cited issue number
- `librarian.beta_notice_shown`
- `librarian.beta_notice_dismissed`

Tinylytics is only used by the website/browser. The Librarian API does not emit server-side Tinylytics events.

## Deployment Checklist

For a normal code-only Thingy deployment:

```sh
npm run librarian:deploy -- --skip-corpus-upload
```

For a full corpus refresh and deploy:

```sh
npm run librarian:deploy
```

`npm run librarian:deploy` packages both Lambdas, uploads their zip files, builds/uploads the embedded corpus, builds/uploads the graph artifact, and updates the CloudFormation stack. Use `npm run librarian:corpus:upload` by itself only when the deployed code is unchanged and only data artifacts need to be refreshed; it uploads both corpus and graph unless `--skip-graph` is passed.

The deploy script packages both Lambda entrypoints from one Node source tree:

- `services/librarian/auth/`: API Gateway Lambda for Buttondown auth and auth health checks.
- `services/librarian/chat/`: Lambda Function URL for streaming chat, generated prompts, and stream health checks.
- `services/librarian/shared/` and `services/librarian/prompts/`: shared code and editable prompt files included in both packages.

After deploy:

```sh
curl -sS -i https://k0yklt9vg3.execute-api.us-east-1.amazonaws.com/health
curl -sS -i -X OPTIONS https://jcvud66qqpq53frvno5stoqntm0zqntw.lambda-url.us-east-1.on.aws/
```

The static site still needs its normal deploy after frontend or content changes.
