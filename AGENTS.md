# AGENTS.md

Use this as the quick working playbook for agents in Studio. `CLAUDE.md`
has the architectural map; app-level `CLAUDE.md` files have deeper runtime
memory.

## First Checks

Before editing:

```sh
git status --short
```

There may be user work in progress. Do not revert unrelated changes.

## Python Environment

This repo uses `venv/`, not `.venv/`.

Use:

```sh
venv/bin/python
venv/bin/pytest
```

Do not assume `python`, `python3`, or `.venv/bin/activate` will work in this
checkout.

## Thingy / Librarian

Thingy's backend lives in `apps/librarian/`. For Lambda work, read:

```sh
sed -n '1,140p' apps/librarian/CLAUDE.md
```

Lambda tests are Node tests:

```sh
npm --prefix apps/librarian/lambda test
```

Deploy code-only Librarian changes with the corpus upload skipped:

```sh
make librarian-deploy ARGS="--skip-corpus-upload"
```

Direct equivalent:

```sh
venv/bin/python pipeline/deploy/aws.py --skip-corpus-upload
```

Only do a full corpus deploy when corpus artifacts, embedding schema, or source
content actually need re-uploading.
