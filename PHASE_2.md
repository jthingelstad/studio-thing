# Phase 2 — Cutover & weekly slim-down (runbook)

Turn Studio into the live producer and reduce weekly to a pure render surface. Phase 1 verified that
Studio reproduces weekly's outputs exactly, so this is a controlled handoff, not a leap.

**Governing principle:** *turn Studio ON before turning weekly OFF.* A brief overlap where both could
build is harmless (identical output, idempotent commits). A gap where neither produces is not. Never
create the gap.

**Timing:** do this the **day after a successful send**. There's no recovery flow — a week's buffer
means any surprise has time to be fixed before the next issue.

---

## Prerequisites (all green before you start)

- [x] Phase 1 dry-run clean (Studio reproduces weekly's archive exactly; only delta was the un-handed-off WT349).
- [ ] Studio Actions secrets added: `BUTTONDOWN_API_KEY`, `STRIPE_API_KEY`, `AWS_ACCESS_KEY_ID`,
      `AWS_SECRET_ACCESS_KEY`, `LIBRARIAN_BRIDGE_SECRET`, `LIBRARIAN_SESSION_SECRET`, `STUDIO_PAT_TOKEN`.
- [ ] `STUDIO_PAT_TOKEN` has **Contents: write on `jthingelstad/weekly.thingelstad.com`** (Studio → weekly handoff).
- [ ] The bot's `GITHUB_PAT_TOKEN` has **Contents: write on `jthingelstad/studio-thing`** (the new ship target).
- [ ] The live `workshop_bot` process runs from the `studio-thing` checkout with the Studio `.env` (not the old weekly copy).

---

## The cutover, in order

### Step 1 — Point the ship sequence at Studio
workshop_bot currently commits canonical `data/issues/{N}/*` to the weekly repo
(`github_repo.DEFAULT_REPO`). Repoint it at Studio so a ship triggers Studio's CI.

- Set `GITHUB_REPO_NWO=jthingelstad/studio-thing` in the bot's `.env`.
- Restart the bot (prompts/config cache at first read).
- Now: ship → commit `data/issues` to **studio-thing** → triggers `.github/workflows/deploy.yml` here.

### Step 2 — Enable the handoff push (Studio → weekly)
The handoff defaults to a dry-run. Flip it on.

- Run **Studio — Production & Handoff** with `push_to_weekly = true` (or change the workflow default).
- Studio now builds the site inputs and commits them to weekly via `push_site_inputs.py --push`.
- That commit is a push to weekly's `main` → triggers weekly's CI (next step makes that render-only).

### Step 3 — Slim weekly's `deploy.yml` to render-only
Cut every production step (they now run in Studio). Target shape:

```yaml
# weekly.thingelstad.com/.github/workflows/deploy.yml  (after slim-down)
on:
  push: { branches: [main] }
  workflow_dispatch:
jobs:
  build:
    steps:
      - uses: actions/checkout@v6
      - uses: actions/setup-node@v6
        with: { node-version: '22', cache: 'npm' }
      - run: npm ci
      - run: npm run build           # 11ty
      - run: npm run build:search    # Pagefind
      - uses: actions/upload-pages-artifact@v5
        with: { path: _site }
  deploy:
    needs: build
    # unchanged: deploy-pages
```

Remove from weekly: Python/Lambda tests, Refresh stats, Build archive, Build corpus, Upload corpus,
Detect/Deploy Lambda, Generate status, Ensure corpus+graph, **and the push-gated "Commit downstream
artifacts" step** (the one that caused the WT349 drift — weekly now receives committed inputs from
Studio, so it never builds-and-forgets again).

### Step 4 — VERIFY end-to-end (gate — do not proceed until green)
- Confirm Studio's run committed the generated inputs to weekly (including the missing **WT349.md** —
  this cutover is what finally lands it in the repo).
- Confirm weekly's slimmed CI fired and the live site rebuilt + deployed.
- Confirm the Thingy Lambda still deploys from Studio and Thingy answers work.
- Ideally, wait for one real ship to flow the whole chain: ship → Studio commit → Studio build+push →
  weekly render+deploy.

### Step 5 — Delete the duplicated brain from weekly (last; least reversible)
Only after Step 4 is green. Weekly's 11ty build is pure Node (no `librarian_core`/`pipeline` imports),
so removing the brain doesn't touch the render.

Delete from weekly: `apps/workshop_bot`, `apps/librarian`, `apps/thingy_bridge`, `content/buttondown`,
`data/issues`, `data/audio`, `data/blog`, `pipeline/`, `librarian-core/`, `docs/` (brain), `reference/`,
`notes/`, `tests/` (brain), `requirements.txt`, `demo_echoes.py`.

Keep in weekly: `apps/site` (11ty), `apps/files-cdn`, node/package files, and the generated `_data/` +
`data/librarian/graph.json` that Studio now pushes in.

### Step 6 — Move secrets off weekly
With Studio owning all production, weekly needs no custom secrets (Pages uses the default
`GITHUB_TOKEN`). Delete from weekly's Actions secrets: `BUTTONDOWN_API_KEY`, `STRIPE_API_KEY`,
`AWS_*`, `LIBRARIAN_BRIDGE_SECRET`, `LIBRARIAN_SESSION_SECRET`. **Weekly ends secret-free.**

---

## What this fixes

The WT349 drift we found — published + live but not committed to the weekly repo — disappears. In the
new flow Studio is the single producer: it builds the archive and *explicitly commits it* to weekly, so
weekly's committed state, its deployed state, and Studio's canonical `data/issues` all agree. The
class of "which copy is authoritative / did it actually persist?" bug is designed out.

## Rollback

Everything through Step 4 is config flips, fully reversible:
- Repoint the bot: `GITHUB_REPO_NWO=jthingelstad/weekly.thingelstad.com`, restart.
- Restore weekly's `deploy.yml` (`git revert`), re-add weekly's secrets.

Step 5 deletes code, but it still lives in `studio-thing` and in weekly's git history — recoverable, just
less convenient. That's why it's last, behind the Step 4 gate.

## Coordination with the Thingy standalone

The standalone added `thingy.thingelstad.com` to the Librarian CORS `AllowedOrigin`
(`apps/librarian/infra/cloudformation.yaml`). That redeploys when the Lambda deploys — which is
weekly's job *until* this cutover, and Studio's job *after*. Decide:
- If Thingy needs to go live **before** the cutover, deploy the CORS change through weekly's current
  pipeline now.
- If **after**, it rides along with Studio's first post-cutover Lambda deploy.

Either is fine; just don't leave the CORS change committed-but-undeployed and wonder why the new domain
gets blocked.
