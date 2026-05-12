"""Jobs — the spine of workshop_bot's content-production loop.

Every workshop_bot user-facing action is a job: deterministic Python in
this package, fired by the ``/workshop …`` slash surface (commands grouped by content artifact) and (for
some) by cron. See ``_base.py`` for the runtime (job context, single-asset
locking, draft-block helpers) and ``docs/workshop-content-loop-design-brief.md``
for the full design.
"""
