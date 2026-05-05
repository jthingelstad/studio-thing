# pipeline/buttondown/

Sync scripts for Buttondown automations and newsletter-level config under `content/buttondown/`. Scaffolding only — none of these are implemented yet.

Planned scripts:

- `pull_newsletter.py` — fetch settings/theme/email CSS/transactional bodies from Buttondown into `content/buttondown/newsletter/`
- `push_newsletter.py` — push local edits back to Buttondown
- `pull_automations.py` / `push_automations.py` — same shape, for `content/buttondown/automations/`
- `diff_buttondown.py` — preview changes (analogous to `pipeline/content/content.py diff`)

Pull-then-push-with-diff flow mirrors the issue body sync already implemented in `pipeline/content/content.py`.
