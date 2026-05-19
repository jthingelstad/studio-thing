"""``reset-issue`` — force the in-flight issue back to an earlier step.

The publish flow has natural gates: ``update-draft`` refuses when
``final.md`` exists; ``create-final`` refuses when ``final.md``
exists. Those gates are correct (re-firing the upstream step would
silently lose Eddy's editorial work). But when Jamie *wants* to back
up — content has shifted enough that he needs to re-do the editorial
pass, or he edited intro.md after buttondown.md was assembled — he needs
a way to drop the gate file without reaching for the AWS console.

This job is that. ``/eddy issue reset {final|publish}`` deletes the
corresponding gate artifacts in S3 and (for ``final``) clears any
row-level editorial state (promotions) so a re-run starts from a
clean editorial slate.

What stays put:

- ``issue_items`` rows themselves are *not* deleted — content
  identity survives. Re-running ``create-final`` proposes a fresh
  ordering against the same rows. (To wipe rows too, use
  :func:`issue_items.clear_issue` directly — that's a heavier
  operation that should be a deliberate, separate step.)
- ``cta-N.md`` / ``thanks-N.md`` files survive a ``reset final``
  even though ``create-final`` will re-declare slots — they're
  authored copy, and Patty re-skips already-filled slots on the
  next ``compose-cta``.
- ``metadata.json``'s ``buttondown_id`` survives a ``reset publish``
  so the next ``send-to-buttondown`` PATCHes the same Buttondown
  draft rather than orphaning it with a fresh POST.

Each successful reset posts a one-line confirmation to ``#editorial``
so the change is visible to anyone watching the channel — there's no
silent state change.
"""

from __future__ import annotations

import logging
from typing import Any

from ..tools import db, issue_items, s3
from . import _base

logger = logging.getLogger("workshop.jobs.reset_issue")

NAME = "reset-issue"

# What each step's "gate" looks like in the workspace. Listed here so
# the job's behavior is data-driven and the help text reads accurately
# without keeping the docstring in sync separately.
_STEP_ARTIFACTS: dict[str, tuple[str, ...]] = {
    "final": ("final.md", "thesis.md", "final.html"),
    "publish": ("buttondown.md", "buttondown.html"),
}


def _delete_if_present(issue_number: int, filenames: tuple[str, ...]) -> list[str]:
    """Best-effort delete. Returns the list of filenames that were
    actually present (and therefore deleted). Missing files are not an
    error — reset is idempotent."""
    listing = s3.list_issue(int(issue_number))
    present = {o.get("filename") for o in listing.get("objects", []) if o.get("filename")}
    deleted: list[str] = []
    for fn in filenames:
        if fn not in present:
            continue
        try:
            s3.delete_issue_file(int(issue_number), fn)
            deleted.append(fn)
        except Exception:  # noqa: BLE001
            logger.exception("reset-issue: delete failed for %s/%s", issue_number, fn)
    return deleted


async def run(ctx: "_base.JobContext", *, step: str) -> "_base.JobResult":
    step = (step or "").strip().lower()
    if step not in _STEP_ARTIFACTS:
        return _base.JobResult(
            False,
            f"❌ unknown reset step `{step}` — must be one of: "
            f"{', '.join(sorted(_STEP_ARTIFACTS))}.",
        )

    window = db.get_active_issue_window()
    if window is None:
        return _base.JobResult(
            False, "❌ no active issue window — nothing to reset.",
        )
    n = int(window["issue_number"])

    artifacts = _STEP_ARTIFACTS[step]
    deleted = _delete_if_present(n, artifacts)
    promotions_cleared = 0

    if step == "final":
        # Clearing promotions belongs with reset-final, not reset-publish:
        # promotions are part of the editorial pass that final.md
        # represents. If Jamie re-runs create-final, the new pass should
        # propose promotions fresh against the current row state.
        promos_before = issue_items.promoted_items(n)
        promotions_cleared = len(promos_before)
        if promos_before:
            issue_items.clear_promotions(n)

    summary_parts: list[str] = []
    if deleted:
        summary_parts.append(", ".join(f"`{fn}`" for fn in deleted) + " deleted")
    if promotions_cleared:
        summary_parts.append(f"{promotions_cleared} promotion(s) cleared")
    if not summary_parts:
        msg = f"ℹ️ nothing to reset — `{step}` artifacts weren't present for WT{n}."
        await ctx.post("DISCORD_CHANNEL_EDITORIAL", msg, persona="eddy")
        return _base.JobResult(True, msg, data={"issue_number": n, "step": step, "deleted": []})

    summary = "; ".join(summary_parts)
    next_hint = {
        "final": "Re-run `/eddy issue final` to propose a fresh editorial pass.",
        "publish": "Re-run `/eddy issue publish` to rebuild from the current `final.md`.",
    }[step]
    msg = (
        f"🔁 **reset-{step}** for WT{n} — {summary}.\n"
        f"{next_hint}"
    )
    await ctx.post("DISCORD_CHANNEL_EDITORIAL", msg, persona="eddy")
    return _base.JobResult(
        True, msg,
        data={
            "issue_number": n, "step": step, "deleted": deleted,
            "promotions_cleared": promotions_cleared,
        },
    )
