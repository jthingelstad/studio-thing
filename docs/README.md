# Project Documentation

This directory contains operational notes for the Weekly Thing archive site.

- [Content pipeline](content-pipeline.md): Buttondown pulls, tracked raw snapshots, generated archive files, and syncing edits back to Buttondown.
- [Archive Librarian](librarian.md): Thingy architecture, AWS runtime, deployment, observability, beta logging, and review commands.
- [External systems](systems/README.md): Auth quirks, endpoint catalogs, and gotchas for Buttondown / Pinboard / Stripe / Tinylytics.
- [Audits](audits/README.md): Archive audit outputs and one-off cleanup references.

## Common Commands

```sh
npm run content:pull:latest
npm run content:build
npm run build
npm run librarian:corpus
npm run librarian:deploy
```

The generated files in `apps/site/archive/` are not the editing surface. Archive cleanup should happen in `data/buttondown/bodies/` and the metadata snapshots in `data/buttondown/emails/`, then be rebuilt with `npm run content:build`.
