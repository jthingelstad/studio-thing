# Project Documentation

This directory contains operational notes for the Weekly Thing archive site.

- [Archive Librarian](librarian.md): Thingy architecture, AWS runtime, deployment, observability, beta logging, and review commands.
- [External systems](systems/README.md): Auth quirks, endpoint catalogs, and gotchas for Buttondown / Pinboard / Stripe / Tinylytics.
- [Audits](audits/README.md): Archive audit outputs and one-off cleanup references.

The content pipeline architecture (workshop-as-source, the build path from `data/issues/`, the ship sequence) lives in the root [`CLAUDE.md`](../CLAUDE.md) and [`apps/workshop_bot/CLAUDE.md`](../apps/workshop_bot/CLAUDE.md). Historical design notes are in [`workshop-content-loop-design-brief.md`](workshop-content-loop-design-brief.md) and [`workshop-content-loop-progress.md`](workshop-content-loop-progress.md).

## Common Commands

```sh
make build              # regenerate apps/site/archive/ from data/issues/, then 11ty + Pagefind
make stats              # refresh subscriber count + Stripe balance in stats.json
npm run librarian:corpus
npm run librarian:deploy
```

The generated files in `apps/site/archive/` are not the editing surface. The canonical editorial source is `data/issues/{N}/archive.md` — written by workshop_bot's ship sequence, or hand-edited and committed. `pipeline/content/content.py build` (wrapped by `make build`) regenerates `apps/site/archive/{N}.md` from those bytes.
