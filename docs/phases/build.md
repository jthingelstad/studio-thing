# Build

Build is the working phase for the current newsletter issue.

**Owner:** Jamie, with Eddy as the only assistant.
**Surface:** Studio web app. Discord is secondary.

The issue is the first-class object. Content lives in the workshop DB:
Notable/Briefly from Pinboard, Journal from micro.blog, and authored atoms
such as Intro, Currently, Haiku, cover metadata, subject, and description.
Ship-shaped files are rendered from the DB when a publish action needs them.

## What Happens

- Start or resume the current issue in Studio.
- Run `sync-issue-daily` or a manual sync to mirror Pinboard and micro.blog
  into `issue_items`.
- Jamie writes and edits issue atoms in the web editor.
- Eddy can review the rendered issue on demand and store anchored editorial
  comments.
- The preview renders live from DB state; it is not a separate source of truth.

## Exit Gate

Build exits when the issue is actually ready to package. Studio's Mark built
action moves the active issue window to `phase = publish` and auto-runs Eddy's
publish-prep jobs that are still in scope: envelope and Echoes.

Build should not expand into blog posts, podcasts, campaigns, projects, seeds,
or idea gardening. Those can come back only after newsletter issue production is
clearly working.
