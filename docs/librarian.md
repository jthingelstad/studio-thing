# Archive Librarian

Thingy is a subscriber-gated chat interface for the Weekly Thing archive.

## Local Artifacts

- `npm run librarian:corpus` builds `data/librarian/corpus.json` from the cleaned generated archive.
- The tracked corpus is text-only and citation-ready. It includes issue summaries, topic metadata, and chunk-level retrieval metadata.
- Embedded corpus files should not be committed. Use the upload command to generate embeddings and push the deployable corpus to S3.
- `scripts/eval_librarian_rag.py` prints retrieval diagnostics for a fixed question set.
- `scripts/eval_librarian_answers.py` runs local retrieval plus OpenAI answer generation, then asks OpenAI to judge answer quality. Results are written to `tmp/librarian-answer-eval.json`.
- `scripts/review_librarian_conversations.py` reads beta conversation logs from DynamoDB for review.

## AWS Runtime

The backend is defined in `aws/cloudformation.yaml`. Auth, health checks, and the buffered JSON chat fallback run behind API Gateway/Lambda. Streaming chat runs through a Lambda Function URL with response streaming enabled. It uses:

- Buttondown API for subscriber lookup.
- OpenAI embeddings for query-to-archive retrieval.
- OpenAI Responses API for Thingy's final answer.
- DynamoDB for session and rate-limit state.
- S3 for the embedded archive corpus.
- Tinylytics API for server-side activity events.
- CloudWatch Logs for structured JSON request, retrieval, upstream, and error logs.

The browser fetches generated suggested questions from `site.librarianApiUrl + /prompts` after subscriber validation. It prefers `site.librarianStreamUrl` for chat and falls back to `site.librarianApiUrl + /chat` if no stream URL is configured.

## Commands

```sh
npm run librarian:corpus
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

After deployment, set `site.librarianApiUrl` in `src/_data/site.js` to the `LibrarianApiUrl` output by CloudFormation and `site.librarianStreamUrl` to `LibrarianStreamUrl`. The current production values are already stored in `src/_data/site.js`.

## Required Secrets

CloudFormation parameters:

- `ButtondownApiKey`
- `OpenAIApiKey`
- `TinylyticsApiKey`
- `TinylyticsSiteId`
- `SessionSecret`
- `CorpusBucket`

Local `.env` values used by upload/build scripts:

- `BUTTONDOWN_API_KEY`
- `OPENAI_API_KEY`
- `TINYLYTICS_API_KEY`
- `TINYLYTICS_SITE_ID` (numeric API site ID, currently `3063`)
- `TINYLYTICS_SITE_UID` (optional public embed UID for the static site, currently `a2YQr3ZMqkySNYSwz4uF`)
- `AWS_S3_BUCKET`
- `AWS_DEFAULT_REGION`
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

Premium subscribers get a small LLM-generated Supporting Member thank-you before entering chat, with a fixed fallback if OpenAI is unavailable. Unknown email addresses can opt in from the librarian page; those signups are created in Buttondown with the `sub_tag_3ts444xst99y08j8bqfnwt1g4h` source tag and must confirm their email before using Thingy. Unconfirmed subscribers can request Buttondown's confirmation reminder email from the same page. The logout control is local-only: it clears the browser's stored session token and returns to the email gate.

## Logging And Review

Lambda writes structured JSON logs to CloudWatch. Logs include request ID, route, status code, duration, subscriber email hash, retrieval mode, citation count, upstream status/duration, and error type. Raw email addresses, API keys, and session tokens are not logged.

Server-side Tinylytics events use the subscriber email hash as `visitor_id`, pass the visitor IP address as `ip_address` so Tinylytics can resolve geography, and, when useful, include the same hash in the event `value` as `member=...`. They do not include raw email addresses, user agents, questions, answers, tokens, or request IDs. Tinylytics API failures are logged as warnings and do not fail the user request.

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

`GET /health` is available as a cheap smoke-test endpoint. It verifies API Gateway and Lambda routing without calling Buttondown, OpenAI, DynamoDB, or S3.

`POST /prompts` requires a valid session token. It returns three generated suggested questions and falls back to a static set if OpenAI is unavailable.

Thingy uses hybrid retrieval. It merges semantic embedding matches, lexical matches, and issue-summary/topic graph matches, then applies context-aware recency and issue diversity before sending sources to OpenAI. Current/recommendation questions prefer newer material when relevance is close. History/evolution questions intentionally preserve sources across eras.

Thingy answers cite issue numbers inline, and the browser turns matching `#123` references into archive links with native tooltips containing the source details. The API still returns citation metadata for rendering and analytics, but the page does not show a separate Sources block.

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

The Librarian API also emits server-side events:

- `librarian.auth_success` with the hashed member ID and subscriber status.
- `librarian.prompts_generated` with `generated` or `fallback`.
- `librarian.chat_success` with hashed member ID, citation count, history count, and question length.
- `librarian.chat_no_sources` with hashed member ID, history count, and question length.
- `librarian.api_error` with hashed member ID when available, route, and error type.

Tinylytics events do not include raw email addresses, questions, answers, tokens, or request IDs.

## Deployment Checklist

For a normal code-only Thingy deployment:

```sh
npm run librarian:deploy -- --skip-corpus-upload
```

For a full corpus refresh and deploy:

```sh
npm run librarian:deploy
```

`npm run librarian:deploy` packages both Lambdas, uploads their zip files, builds/uploads the embedded corpus, and updates the CloudFormation stack. Use `npm run librarian:corpus:upload` by itself only when the deployed code is unchanged and only the corpus needs to be refreshed.

The deploy script packages both Lambda runtimes:

- `librarian_api/`: Python API Gateway Lambda for auth, prompts, health checks, and buffered JSON chat fallback.
- `librarian_stream/`: Node.js Lambda Function URL for streaming chat.

After deploy:

```sh
curl -sS -i https://k0yklt9vg3.execute-api.us-east-1.amazonaws.com/health
curl -sS -i -X OPTIONS https://jcvud66qqpq53frvno5stoqntm0zqntw.lambda-url.us-east-1.on.aws/
```

The static site still needs its normal deploy after frontend or content changes.
