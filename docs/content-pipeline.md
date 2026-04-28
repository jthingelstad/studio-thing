# Content Pipeline

The archive is generated from a tracked Buttondown baseline. The source of truth for archive cleanup is `data/buttondown/`, not `site/archive/`.

## Directory Roles

- `data/buttondown/emails/*.json`: tracked metadata snapshots for each Buttondown issue. These include ID, issue number, subject, description, image, slug, publish date, status, source hash, and a `body_path`.
- `data/buttondown/bodies/*.md`: tracked raw Buttondown body content before archive transformation. This is the right place for broad body scans and cleanup edits.
- `data/buttondown/manifest.json`: generated manifest mapping issue numbers to snapshot, body, and archive paths.
- `site/archive/*.md`: generated Eleventy issue pages. These files include a generated notice and should not be edited by hand.
- `site/_data/emails.json`: generated archive index data used by Eleventy templates.
- `site/_data/stats.json`: generated subscriber/supporting-member stats.
- `data/librarian/corpus.json`: generated, tracked text-only corpus for Thingy. Embedded corpus files are generated for upload and should not be committed.

## Normal Workflows

Pull all public sent Buttondown issues and rebuild the archive:

```sh
npm run content:pull
```

Pull only the newest public sent issue:

```sh
npm run content:pull:latest
```

Pull the newest issue but no-op when the existing snapshot hash already matches Buttondown:

```sh
npm run content:pull:latest:skip-existing
```

Rebuild generated archive files from tracked snapshots:

```sh
npm run content:build
```

Build the static site:

```sh
npm run build
```

Build the archive and Thingy corpus together:

```sh
npm run data
```

## Archive Cleanup

Edit `data/buttondown/bodies/N.md` for body cleanup and `data/buttondown/emails/N.json` for metadata cleanup. Then run:

```sh
npm run content:build
npm run librarian:corpus
npm run build
```

Do not edit `site/archive/N.md` directly. Those files are regenerated from `data/buttondown/` and local edits will be overwritten.

## Buttondown Template Handling

Raw Buttondown bodies can contain Liquid/Django-style template tags. The archive renderer in `pipeline/content/content.py` tokenizes these tags before writing `site/archive/`.

Current archive behavior:

- `medium == 'web'` blocks are rendered.
- `medium == 'email'` blocks are omitted.
- `subscriber.*` conditional blocks are omitted publicly.
- Known Buttondown variables such as `email.subject`, `email_url`, and `subscribe_url` are rendered to archive-safe values.
- Subscription-management variables and unknown personalized variables render as empty strings.
- Unknown top-level tags are dropped while surrounding text is preserved.
- Unknown personalized conditional branches are not rendered publicly.

This keeps email-only, premium-only, and subscriber-specific content out of the public archive while preserving normal archive content. When adding support for more template syntax, update `pipeline/content/content.py` and add tests in `tests/test_content.py` or `tests/test_librarian_corpus.py` as appropriate.

## Syncing Changes Back To Buttondown

The pipeline can push local raw changes back to Buttondown with conflict checks.

Preview local changes against the committed snapshot baseline:

```sh
npm run content:diff
```

Preview one issue:

```sh
python pipeline/content/content.py diff --issue 345
```

Dry-run a Buttondown sync:

```sh
npm run content:push
```

Push safe local changes to Buttondown:

```sh
npm run content:push:live
```

Push one issue:

```sh
python pipeline/content/content.py push --issue 345 --yes
```

The sync uses a three-way comparison:

- committed snapshot baseline from `HEAD`
- local tracked snapshot/body files
- live Buttondown issue fetched by API

If Buttondown changed a field since the local baseline, that field is treated as a conflict and skipped unless `--force` is used. Empty bodies are never pushed.

After a successful push, the local snapshot is refreshed from Buttondown and the manifest is rewritten.

## GitHub Actions

The default deploy workflow does not always run the content pipeline. Content pulls are controlled by the `content_pipeline` workflow input:

- `none`: build/deploy existing repository content.
- `latest`: pull the latest Buttondown issue.
- `latest-skip-existing`: pull the latest issue only when Buttondown has changed it.
- `all`: refresh all sent public Buttondown issues.

For scheduled content pickup, the workflow runs only during the narrow publishing window configured in `.github/workflows/deploy.yml`. Manual dispatch is the fallback for issues published outside that window.

When content changes are detected during non-push runs, the workflow commits generated content files back to the repository before deploying.

## Buttondown Webhook Note

Buttondown cannot directly trigger GitHub Actions with this repository's normal `workflow_dispatch` authentication unless an intermediate service signs the request with a GitHub token or GitHub App credential. For now, the simpler model is:

- scheduled polling during the usual publish window
- manual GitHub Actions dispatch outside that window
- direct local `npm run content:pull:latest` when working from the checkout
