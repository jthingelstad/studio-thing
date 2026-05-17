"""``/eddy edit <asset>`` — pop a Discord modal pre-filled with the
asset's current content, write the edited result back to S3.

Editing the small per-issue atom files (``intro.md`` / ``outro.md`` /
``haiku.md`` / ``currently.json`` / ``cover.json`` / ``cta-N.md`` /
``thanks-N.md``) used to mean opening the AWS console or running a
local script — friction enough that WT348 had several "edit intro
and reflect in the preview" moments where the edit didn't happen.

Discord modals have a 4000-char per-input limit, which comfortably
fits every atom file (intro is ~1200 chars max; haiku ~80; the
cta/thanks bodies ~700; metadata.json is structured and not in this
flow). Bodies that exceed the cap are refused with a "use the S3
console" hint — better that than silent truncation.

This module deliberately does NOT touch the assembled documents
(``draft.md`` / ``final.md`` / ``publish.md``). Those are renders,
not authored text — they regenerate from the atoms.

After a successful write, the job optionally re-fires
``update-draft`` so the preview refreshes for atoms that flow into
``draft.md`` (intro / outro / haiku / currently / cover). Edits to
``cta-N.md`` / ``thanks-N.md`` don't auto-fire anything — they only
affect ``publish.md``, and that's a deliberate step (``/eddy issue
publish`` or post-final rebuild).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

import discord
from discord import ui

from ..tools import db, s3
from . import _base

logger = logging.getLogger("workshop.jobs.edit_asset")

NAME = "edit-asset"

# 4000 is Discord's hard cap on a paragraph TextInput. We leave a
# small margin so future schema changes don't push us over silently.
_MODAL_MAX = 4000

# Asset → (filename, friendly_label, refire_update_draft).
# Adding a new asset: append a row here and the slash-command choice
# list at /eddy edit. Files that flow into draft.md should
# refire_update_draft=True so the preview refreshes after the write.
_ASSETS: dict[str, tuple[str, str, bool]] = {
    "intro":       ("intro.md",      "intro",            True),
    "outro":       ("outro.md",      "outro",            True),
    "haiku":       ("haiku.md",      "haiku",            True),
    "currently":   ("currently.json", "Currently",        True),
    "cover":       ("cover.json",    "cover caption",    True),
    "cta-1":       ("cta-1.md",      "CTA slot 1",       False),
    "cta-2":       ("cta-2.md",      "CTA slot 2",       False),
    "thanks-1":    ("thanks-1.md",   "thanks slot 1",    False),
}

ASSET_CHOICES = tuple(_ASSETS.keys())


def _read_current(issue_number: int, filename: str) -> str:
    """Read the asset's current contents from S3. Returns ``""`` when
    the file isn't there (treat as a blank-slate edit)."""
    res = s3.read_issue_file(issue_number, filename)
    if res.get("found") and isinstance(res.get("text"), str):
        return res["text"]
    return ""


class _AssetEditModal(ui.Modal):
    """The modal Discord shows after ``/eddy edit``. Pre-filled with
    the asset's current S3 contents; the submit handler writes the
    new value back and (when applicable) re-fires ``update-draft``.
    """

    def __init__(
        self,
        *,
        ctx: "_base.JobContext",
        issue_number: int,
        asset_key: str,
        filename: str,
        label: str,
        refire_update_draft: bool,
        current_text: str,
    ) -> None:
        title = f"Edit {label} · WT{issue_number}"
        super().__init__(title=title[:45], timeout=30 * 60.0)
        self.ctx = ctx
        self.issue_number = int(issue_number)
        self.asset_key = asset_key
        self.filename = filename
        self.refire_update_draft = refire_update_draft
        self.input = ui.TextInput(
            label=f"{filename}  (max {_MODAL_MAX} chars)",
            style=discord.TextStyle.paragraph,
            default=current_text,
            max_length=_MODAL_MAX,
            required=False,
        )
        self.add_item(self.input)

    async def on_submit(self, interaction) -> None:  # type: ignore[override]
        new_text = self.input.value or ""
        try:
            s3.write_issue_file(self.issue_number, self.filename, new_text)
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "edit-asset: write failed for WT%d/%s",
                self.issue_number, self.filename,
            )
            await interaction.response.send_message(
                f"❌ Couldn't write `{self.filename}` for WT{self.issue_number}: "
                f"`{type(exc).__name__}: {exc}`",
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            f"✅ Updated `{self.filename}` for WT{self.issue_number} "
            f"({len(new_text)} chars). "
            + ("Re-firing `update-draft`…" if self.refire_update_draft else "Done."),
            ephemeral=True,
        )
        if self.refire_update_draft:
            # Update-draft refuses when final.md exists. That's fine —
            # the error surfaces via the agent_runs log; we don't want
            # to block the modal acknowledgement on it.
            _schedule_update_draft(self.ctx, self.issue_number)


def _schedule_update_draft(ctx: "_base.JobContext", issue_number: int) -> None:
    """Fire ``update-draft`` as a background task. Same fire-and-forget
    pattern as ``create-final``'s compose-cta autofire — errors are
    logged, not surfaced; the modal ack has already shipped."""
    from . import update_draft as _update_draft  # local import — circular at module-load

    async def _run() -> None:
        try:
            result = await _update_draft.run(ctx)
            logger.info(
                "edit-asset → update-draft refire for WT%d: %s",
                issue_number, getattr(result, "message", ""),
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "edit-asset → update-draft refire failed for WT%d",
                issue_number,
            )

    try:
        asyncio.create_task(_run())
    except RuntimeError:
        logger.debug("edit-asset: no event loop for update-draft refire")


def build_modal(
    ctx: "_base.JobContext", *, asset_key: str,
) -> tuple[Optional[_AssetEditModal], Optional[str]]:
    """Construct the modal for a given asset choice. Returns
    ``(modal, error_message)``: when the modal can be shown, ``modal``
    is set and ``error_message`` is ``None``; otherwise ``modal`` is
    ``None`` and the error string explains why (no active issue, asset
    body too long, etc).
    """
    if asset_key not in _ASSETS:
        return None, f"❌ unknown asset `{asset_key}` — must be one of: {', '.join(ASSET_CHOICES)}."
    filename, label, refire = _ASSETS[asset_key]
    window = db.get_active_issue_window()
    if window is None:
        return None, "❌ no active issue window — run `/eddy issue start` first."
    n = int(window["issue_number"])
    current = _read_current(n, filename)
    if len(current) > _MODAL_MAX:
        return None, (
            f"❌ `{filename}` for WT{n} is {len(current):,} chars; modals are capped at "
            f"{_MODAL_MAX:,}. Edit via the S3 console for this one."
        )
    modal = _AssetEditModal(
        ctx=ctx, issue_number=n, asset_key=asset_key,
        filename=filename, label=label, refire_update_draft=refire,
        current_text=current,
    )
    return modal, None
