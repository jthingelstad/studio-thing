# Studio

Studio is the private publishing website for **The Weekly Thing** newsletter.
Its job is narrow: help Jamie assemble, review, package, publish, and file each
newsletter issue.

The current product is intentionally smaller than the earlier "publishing
brain" model:

- The newsletter issue is the unit of work.
- The Studio web app is the primary work surface.
- Eddy is the only assistant.
- Jamie writes every word.
- Blog posts, podcast episodes, projects, seeds, and idea gardening are out of
  scope.

Everything downstream remains a surface. Studio prepares and ships canonical
newsletter artifacts; `weekly.thingelstad.com` renders and publishes the public
site.

## Architecture

| Repo / host | Role |
|---|---|
| **Studio** (this repo) | Private newsletter publishing app, issue source of truth, publish pipeline, Librarian API/corpus build inputs |
| weekly.thingelstad.com | Public newsletter site and archive render surface |
| thingy.thingelstad.com | Query surface backed by the Librarian API |

## What's Here

| Path | What it is |
|---|---|
| `apps/workshop_bot/` | Studio web app, Eddy runtime, newsletter issue jobs, and the workshop DB |
| `apps/librarian/` | Librarian API Lambda + infra |
| `librarian-core/` | Shared corpus/graph/retrieval package |
| `pipeline/` | Build, audio, corpus, graph, deploy, and weekly handoff pipeline |
| `data/issues/` | Canonical shipped issue content |
| `data/audio/` | Audio production source and manifest |
| `content/buttondown/` | Buttondown newsletter config |
| `docs/`, `notes/`, `reference/` | Architecture and editorial reference |
| `tests/` | Python tests |

## Newsletter Flow

1. Define or open the current issue in Studio.
2. Sync sources into the issue DB from Pinboard and micro.blog.
3. Edit issue atoms and item ordering in the web UI.
4. Preview the issue live from the DB.
5. Run Eddy's on-demand editorial review when useful.
6. Save the email envelope and shipping fields.
7. Publish email, website, and audio from the Studio web UI.
8. Put the issue to bed so it is filed into the local issue data layer.

The DB is the draft. There is no S3 collaboration layer, no Shortcuts pipeline,
and no separate idea-garden workflow.

## Development

Use the repo-local virtualenv:

```sh
venv/bin/python
venv/bin/pytest
```

Run the workshop tests from the repo root:

```sh
venv/bin/python -m unittest discover -s apps/workshop_bot/tests -t .
```

Before editing, check for user work:

```sh
git status --short
```
