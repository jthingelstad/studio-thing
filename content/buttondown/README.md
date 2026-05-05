# content/buttondown/

Author-managed Buttondown configuration kept under version control. Buttondown is the runtime; this directory is the source.

## Scope

- `automations/` — automation flow bodies and configs (e.g., `welcome-sequence/`)
- `newsletter/` — newsletter-level configuration: `settings.json`, `email.css`, `theme.json`, `transactional/{subscription_confirmation,churn,confirmation_reminder}.md`

## Not here

Issue bodies and per-email metadata are pulled from Buttondown by `pipeline/content/content.py` and live in `data/buttondown/{bodies,emails}/`. They're tracked, editable, and pushed back via `pipeline/content/content.py push` — but they originate from the API, so they live with generated artifacts under `data/`.

## Sync

Sync scripts (`pull_newsletter.py`, `push_newsletter.py`, `pull_automations.py`, `push_automations.py`, `diff_buttondown.py`) are not implemented yet. They'll live alongside `pipeline/content/content.py` when added.
