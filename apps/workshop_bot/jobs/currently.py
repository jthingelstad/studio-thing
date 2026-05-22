"""``/eddy currently …`` — DB-backed Currently editing for the in-flight
issue, plus a per-type Discord modal for quick edits that include
markdown links.

Currently is the conversational replacement for the retired
``Drafts → Shortcut → currently.json`` flow. The canonical type pool
and per-issue values live in ``workshop.db`` (``currently_types`` /
``currently_entries``); ``jobs/_currently.render`` projects them into
``draft.md`` and ``buttondown.md``. Authoring happens three ways:

1. **Conversational with Eddy in #editorial** — the primary path.
   Eddy uses the ``currently__*`` agent tools (``set`` / ``clear`` /
   ``reorder`` / ``add_type`` / ``suggest_stale``) when Jamie mentions
   what he's currently doing.

2. **``/eddy currently edit <type>``** — pops a single-field modal
   pre-filled with the current DB value. Best when the value carries
   markdown links (no JSON escaping). UPSERTs ``currently_entries``.

3. **``/eddy currently set <type> <value>``** — non-modal quick path
   for plain-text values. Same UPSERT.

Mutations write to the DB and stop there — they don't refire
``update-draft``. The next scheduled (daily 17:00 CT) or manual
``/eddy issue update`` projects the new state into ``draft.md``.

Type ordering inside an issue is editorial — entries default to
insertion order; Eddy (or Jamie via ``/eddy currently reorder``) can
re-rank when sequencing matters.
"""

from __future__ import annotations

import logging
from typing import Optional

import discord
from discord import ui

from ..tools import db
from . import _base

logger = logging.getLogger("workshop.jobs.currently")

NAME = "currently"

# Discord caps a paragraph TextInput at 4000 chars. Every observed
# Currently value sits well under 600 — the cap is just a guardrail.
_MODAL_MAX = 4000


# ---------- internal helpers ----------

def _resolve_active_issue() -> tuple[Optional[int], Optional[str]]:
    window = db.get_active_issue_window()
    if window is None:
        return None, "❌ no active issue window — run `/eddy issue start` first."
    return int(window["issue_number"]), None


def _resolve_type(label: str) -> tuple[Optional[str], Optional[str]]:
    """Resolve a free-text label to its canonical type row. Returns
    ``(canonical_label, error)`` — error suggests using ``add-type``."""
    norm = (label or "").strip()
    if not norm:
        return None, "❌ give a Currently type (e.g. `Reading`, `Playing`)."
    row = db.currently_get_type(norm)
    if row is None:
        return None, (
            f"❌ `{norm}` isn't a known Currently type. "
            f"Add it with `/eddy currently add-type {norm}` first."
        )
    if not row.get("is_active"):
        return row["label"], (
            f"⚠️ `{row['label']}` is retired. Reactivate by re-adding it."
        )
    return row["label"], None


def _format_entries(entries: list[dict]) -> str:
    if not entries:
        return "_(no entries)_"
    return "\n".join(
        f"  {i}. **{r['type_label']}** · {(r['value'] or '').strip()}"
        for i, r in enumerate(entries, start=1)
    )


# ---------- list ----------

async def list_state(ctx: "_base.JobContext") -> "_base.JobResult":
    """Read-only summary: current issue's filled entries + a stale hint."""
    n, err = _resolve_active_issue()
    if n is None:
        return _base.JobResult(False, err or "")
    entries = db.currently_get_entries(n)
    filled = {r["type_label"] for r in entries}
    active_types = [t["label"] for t in db.currently_list_types() if t.get("is_active")]
    empty = [lbl for lbl in active_types if lbl not in filled]
    stale = db.currently_suggest_stale(n, k=3)
    stale_line = ", ".join(
        f"{s['label']} ({s['gap_issues']} ago)"
        if s.get("gap_issues") is not None
        else f"{s['label']} (never)"
        for s in stale
    ) or "_(no types yet)_"

    lines = [
        f"**Currently · WT{n}**",
        "",
        _format_entries(entries),
    ]
    if empty:
        lines.extend(["", f"_Unfilled active types ({len(empty)}):_ {', '.join(empty)}"])
    lines.extend(["", f"_Stale picks (least-recent):_ {stale_line}"])
    return _base.JobResult(True, "\n".join(lines))


# ---------- set / clear / reorder ----------

async def set_value(
    ctx: "_base.JobContext", *, type_label: str, value: str,
) -> "_base.JobResult":
    n, err = _resolve_active_issue()
    if n is None:
        return _base.JobResult(False, err or "")
    canonical, type_err = _resolve_type(type_label)
    if canonical is None:
        return _base.JobResult(False, type_err or "")
    val = (value or "").strip()
    if not val:
        return _base.JobResult(
            False,
            f"❌ value is empty. Use `/eddy currently clear {canonical}` to remove the entry.",
        )
    try:
        res = db.currently_set_entry(n, canonical, val)
    except db.CurrentlyError as exc:
        return _base.JobResult(False, f"❌ {exc}")
    return _base.JobResult(
        True,
        f"✅ **{canonical}** set for WT{n} (position {res['position']}, "
        f"{len(val)} chars).",
        data={"issue_number": n, "label": canonical, "position": res["position"]},
    )


async def clear_value(
    ctx: "_base.JobContext", *, type_label: str,
) -> "_base.JobResult":
    n, err = _resolve_active_issue()
    if n is None:
        return _base.JobResult(False, err or "")
    canonical, type_err = _resolve_type(type_label)
    if canonical is None:
        # Allow clear on a retired/unknown label too — if there's an entry, drop it.
        canonical = (type_label or "").strip()
        if not canonical:
            return _base.JobResult(False, type_err or "")
    deleted = db.currently_clear_entry(n, canonical)
    if not deleted:
        return _base.JobResult(
            True, f"_(nothing to clear — **{canonical}** isn't set for WT{n})_",
        )
    return _base.JobResult(
        True,
        f"🗑️ cleared **{canonical}** for WT{n}.",
        data={"issue_number": n, "label": canonical},
    )


async def reorder(
    ctx: "_base.JobContext", *, labels: str,
) -> "_base.JobResult":
    """``labels`` is a comma-separated permutation of the active issue's
    currently-filled type labels."""
    n, err = _resolve_active_issue()
    if n is None:
        return _base.JobResult(False, err or "")
    raw = [p.strip() for p in (labels or "").split(",") if p.strip()]
    if not raw:
        return _base.JobResult(
            False, "❌ give a comma-separated list of currently-filled type labels.",
        )
    try:
        applied = db.currently_reorder(n, raw)
    except db.CurrentlyError as exc:
        return _base.JobResult(False, f"❌ {exc}")
    return _base.JobResult(
        True,
        f"🔀 Currently reordered for WT{n}: **{', '.join(applied)}**.",
        data={"issue_number": n, "order": applied},
    )


# ---------- type-pool management ----------

async def add_type(ctx: "_base.JobContext", *, label: str) -> "_base.JobResult":
    norm = (label or "").strip()
    if not norm:
        return _base.JobResult(False, "❌ give a `label` (e.g. `Printing`).")
    try:
        row = db.currently_add_type(norm)
    except db.CurrentlyError as exc:
        return _base.JobResult(False, f"❌ {exc}")
    return _base.JobResult(
        True,
        f"➕ added Currently type **{row['label']}**. "
        f"Set a value with `/eddy currently set {row['label']} <value>` "
        f"or `/eddy currently edit {row['label']}`.",
        data={"label": row["label"]},
    )


async def retire_type(ctx: "_base.JobContext", *, label: str) -> "_base.JobResult":
    norm = (label or "").strip()
    if not norm:
        return _base.JobResult(False, "❌ give a `label`.")
    if db.currently_get_type(norm) is None:
        return _base.JobResult(False, f"❌ no Currently type `{norm}`.")
    ok = db.currently_retire_type(norm)
    return _base.JobResult(
        ok, f"🪦 retired Currently type **{norm}** (past entries still render).",
    )


# ---------- per-type Discord modal ----------

class _CurrentlyEditModal(ui.Modal):
    """Single-field modal pre-filled with the active issue's value for
    one type. Submit UPSERTs ``currently_entries``. The next scheduled
    ``update-draft`` (or a manual one) projects the new value into the
    rendered draft — this modal doesn't refire on its own."""

    def __init__(
        self,
        *,
        ctx: "_base.JobContext",
        issue_number: int,
        type_label: str,
        current_value: str,
    ) -> None:
        super().__init__(
            title=f"Edit Currently · {type_label} · WT{issue_number}"[:45],
            timeout=30 * 60.0,
        )
        self.ctx = ctx
        self.issue_number = int(issue_number)
        self.type_label = type_label
        self.input = ui.TextInput(
            label=f"{type_label} (markdown OK)",
            style=discord.TextStyle.paragraph,
            default=current_value,
            max_length=_MODAL_MAX,
            required=False,
            placeholder=f"What are you currently {type_label.lower()}?",
        )
        self.add_item(self.input)

    async def on_submit(self, interaction) -> None:  # type: ignore[override]
        new_value = (self.input.value or "").strip()
        try:
            if not new_value:
                # Empty submit = clear the entry.
                deleted = db.currently_clear_entry(self.issue_number, self.type_label)
                msg = (
                    f"🗑️ cleared **{self.type_label}** for WT{self.issue_number}."
                    if deleted
                    else f"_(no value entered — **{self.type_label}** wasn't set)_"
                )
            else:
                res = db.currently_set_entry(
                    self.issue_number, self.type_label, new_value,
                )
                msg = (
                    f"✅ updated **{self.type_label}** for WT{self.issue_number} "
                    f"({len(new_value)} chars, position {res['position']})."
                )
        except db.CurrentlyError as exc:
            await interaction.response.send_message(
                f"❌ couldn't update Currently: {exc}", ephemeral=True,
            )
            return
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "currently edit modal: write failed for WT%d / %s",
                self.issue_number, self.type_label,
            )
            await interaction.response.send_message(
                f"❌ couldn't update **{self.type_label}** for WT{self.issue_number}: "
                f"`{type(exc).__name__}: {exc}`",
                ephemeral=True,
            )
            return
        await interaction.response.send_message(msg, ephemeral=True)


def build_modal(
    ctx: "_base.JobContext", *, type_label: str,
) -> tuple[Optional[_CurrentlyEditModal], Optional[str]]:
    """Construct the per-type modal. Returns ``(modal, error_message)`` —
    one is ``None`` and the other carries the result."""
    n, err = _resolve_active_issue()
    if n is None:
        return None, err
    canonical, type_err = _resolve_type(type_label)
    if canonical is None:
        return None, type_err
    entries = db.currently_get_entries(n)
    current = ""
    for row in entries:
        if (row["type_label"] or "").lower() == canonical.lower():
            current = row.get("value") or ""
            break
    if len(current) > _MODAL_MAX:
        return None, (
            f"❌ existing value for **{canonical}** is {len(current):,} chars; "
            f"modals are capped at {_MODAL_MAX:,}. Use "
            f"`/eddy currently clear {canonical}` then re-set in pieces."
        )
    return _CurrentlyEditModal(
        ctx=ctx, issue_number=n, type_label=canonical, current_value=current,
    ), None
