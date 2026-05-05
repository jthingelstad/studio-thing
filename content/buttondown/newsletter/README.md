# content/buttondown/newsletter/

Newsletter-level Buttondown configuration: settings, theme, email CSS, transactional template bodies.

Suggested layout:

```
settings.json                # newsletter-level settings (name, description, etc.)
email.css                    # custom email CSS — paste contents into Buttondown's Custom CSS field
theme.json                   # color/typography tokens
transactional/
├── subscription_confirmation.md
├── churn.md
└── confirmation_reminder.md
```

Sync scripts (`pull_newsletter.py`, `push_newsletter.py`) are not implemented yet. The current production email CSS lives at `docs/email/buttondown-email.css`; it will move here when sync lands.
