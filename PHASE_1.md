# Phase 1 — Stand up Studio (implementation)

**Status: built, not yet activated.** Nothing here touches the live publishing path until you add the
secrets and run it — and even then the handoff **defaults to a dry-run diff** that commits nothing. This
is the parallel-run step from `weekly.thingelstad.com/STUDIO_MIGRATION_PLAN.md`.

## What this adds

- **`.github/workflows/deploy.yml`** — Studio's production CI. Runs the production half of the old weekly
  pipeline (tests → stats → archive build → corpus → graph → corpus-to-S3 → Lambda deploy on change →
  status), then hands the generated 11ty inputs to the website repo. No 11ty/Pages here — that stays in
  weekly.
- **`pipeline/deploy/push_site_inputs.py`** — gathers the generated inputs
  (`apps/site/archive/*.md`, `apps/site/_data/{emails,stats,status}.json`, `data/librarian/graph.json`)
  and either **diffs** them against the website repo (default) or **commits** them via
  `github_repo.put_tree` (`--push`). Atomic and idempotent — a no-op when nothing changed.

## Secrets to add to `studio-thing`

GitHub → Settings → Secrets and variables → Actions. **Add these; leave them in weekly for now**
(add-then-remove, never the reverse):

| Secret | Used by |
|---|---|
| `BUTTONDOWN_API_KEY` | stats |
| `STRIPE_API_KEY` | stats |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | corpus→S3, Lambda deploy, status |
| `LIBRARIAN_BRIDGE_SECRET` / `LIBRARIAN_SESSION_SECRET` | Lambda deploy |
| `WEBSITE_REPO_PAT` | **NEW** — the cross-repo handoff |

`WEBSITE_REPO_PAT` is a fine-grained PAT with **Contents: write on `jthingelstad/weekly.thingelstad.com`**.
The default `GITHUB_TOKEN` only has rights on the current repo, so the handoff needs its own token.

## Verification gate (the most important step — do this before any cutover)

1. Add the secrets above.
2. Actions → **Studio — Production & Handoff** → **Run workflow**, leaving **`push_to_weekly` = false**.
3. Read the **"Hand off site inputs"** step output. It dry-run-diffs the files Studio generated against
   the website repo's current `main`:
   - **Expected: a clean diff** (0 added / 0 changed), or only the issues that are legitimately newer in
     Studio. Clean means Studio reproduces exactly what weekly serves today.
   - **Unexpected differences = investigate before cutover.** That's the signal something in the moved
     pipeline behaves differently — the whole point of running in parallel first.
4. Re-run after a real issue ships to confirm a new issue flows end to end.

## Cutover (Phase 2 — later, day after a send; not now)

1. Point workshop_bot's ship commit at the Studio repo: `GITHUB_REPO_NWO=jthingelstad/studio-thing`, so a
   ship triggers this workflow.
2. Run this workflow with **`push_to_weekly` = true** (or flip the default) so it commits to weekly.
3. Slim weekly per `STUDIO_MIGRATION_PLAN.md` — delete the duplicated brain, cut the production steps from
   weekly's `deploy.yml`, remove the secrets from weekly.

## Notes

- The handoff reuses `apps/workshop_bot/tools/github_repo.py` (the same atomic-commit tool the ship
  sequence uses) via a `sys.path` insert. Candidate to promote into `librarian_core` as a shared util,
  since two callers now depend on it.
- The build self-creates its output dirs (`apps/site/...`, `data/librarian/`), so Studio doesn't need a
  committed `apps/site/` — the generated files are transient CI artifacts that exist only to be handed
  off.
- `data/librarian/corpus.json` is gitignored and goes to **S3** (for the Lambda), not to weekly. Only
  `graph.json` goes to weekly (for the site's topic pages).
