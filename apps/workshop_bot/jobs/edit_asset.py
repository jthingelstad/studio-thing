"""``/eddy edit <asset>`` — pop a Discord modal pre-filled with the
asset's current content, write the edited result back to S3.

Edit doubles as create: when the asset doesn't exist on S3 yet, the
modal opens blank with an asset-specific placeholder hint and the
first submit writes the file fresh. No separate ``/eddy add`` /
``/eddy create`` verb — ``/eddy edit intro`` is the way to write the
intro for the very first time.

Editing the small per-issue atom files (``intro.md`` / ``outro.md`` /
``haiku.md`` / ``cover.json`` / ``cta-N.md`` / ``thanks-N.md``) used to
mean opening the AWS console or running a local script — friction
enough that WT348 had several "edit intro and reflect in the preview"
moments where the edit didn't happen.

Currently is no longer in this picker — the conversational + per-type
flow at ``/eddy currently …`` (and Eddy's #editorial dialogue) replaced
the static JSON edit.

Discord modals have a 4000-char per-input limit, which comfortably
fits every atom file (intro is ~1200 chars max; haiku ~80; the
cta/thanks bodies ~700; metadata.json is structured and not in this
flow). Bodies that exceed the cap are refused with a "use the S3
console" hint — better that than silent truncation.

This module deliberately does NOT touch the assembled documents
(``draft.md`` / ``archive.md`` / ``buttondown.md``). Those are renders,
not authored text — they regenerate from the atoms.

After a successful write, the job optionally re-fires
``update-draft`` so the preview refreshes for atoms that flow into
``draft.md`` (intro / outro / haiku / currently / cover). Edits to
``cta-N.md`` / ``thanks-N.md`` don't auto-fire anything — they only
affect ``buttondown.md``, and that's a deliberate step (the next
``update-draft`` tick re-renders, or ``/scout issue publish``).
"""

from __future__ import annotations

import logging
from typing import Optional

import discord
from discord import ui

from ..tools import content_store, db
from . import _base

logger = logging.getLogger("workshop.jobs.edit_asset")

NAME = "edit-asset"

# 4000 is Discord's hard cap on a paragraph TextInput. We leave a
# small margin so future schema changes don't push us over silently.
_MODAL_MAX = 4000

# Asset → (filename, friendly_label, placeholder). Adding a new asset:
# append a row here and the slash-command choice list at /eddy edit. The
# DB is the draft — a save IS the update, nothing to refire; the web
# preview renders live. The placeholder is shown when the modal opens
# with an empty value (asset doesn't exist yet).
_ASSETS: dict[str, tuple[str, str, str]] = {
    "intro":    ("intro.md",    "intro",
                 "Opening prose for the issue. 1–4 short paragraphs in Jamie's voice."),
    "outro":    ("outro.md",    "outro",
                 "Closing prose — sign-off paragraph(s) after the Briefly section."),
    "haiku":    ("haiku.md",    "haiku",
                 "Three lines, 5-7-5 syllables. Bold + hard breaks added at render time."),
    "cover":    ("cover.json",  "cover caption",
                 '{"caption": "...", "location": "Minneapolis, MN", "timestamp": "May 23, 2026"}'),
    "thesis":   ("thesis.md",   "thesis",
                 "1–3 sentences naming what the issue is about — Eddy's editorial anchor."),
    "echoes":   ("echoes.md",   "echoes",
                 "Thingy's 2–4 sentence archive note that closes the issue — markdown prose."),
    "cta-1":    ("cta-1.md",    "CTA slot 1",
                 "---\nkind: supporter\n---\n\nCall-to-action copy (Thingy's voice)."),
    "cta-2":    ("cta-2.md",    "CTA slot 2",
                 "---\nkind: supporter\n---\n\nSecond CTA slot copy."),
    "thanks-1": ("thanks-1.md", "thanks slot 1",
                 "---\nkind: thanks\n---\n\nThank-you copy shown only to premium members."),
}

ASSET_CHOICES = tuple(_ASSETS.keys())


def _read_current(issue_number: int, filename: str) -> str:
    """Read the asset's current contents from S3. Returns ``""`` when
    the file isn't there (treat as a blank-slate edit — ``/eddy edit``
    on a missing asset opens an empty modal so Jamie can author it on
    the spot, no separate `create` command needed). Best-effort: an S3
    transport error logs and falls through to ``""`` — better to let
    Jamie type into an empty modal than to refuse the edit outright."""
    try:
        body = content_store.read_issue(issue_number, filename)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "edit-asset: content read failed for WT%d/%s — opening empty modal: %s",
            issue_number, filename, exc,
        )
        return ""
    return body if body else ""


class _AssetEditModal(ui.Modal):
    """The modal Discord shows after ``/eddy edit``. Pre-filled with the
    asset's current DB contents; the submit handler writes the new value
    back. The DB is the draft — the save IS the update.
    """

    def __init__(
        self,
        *,
        ctx: "_base.JobContext",
        issue_number: int,
        asset_key: str,
        filename: str,
        label: str,
        current_text: str,
        placeholder: str = "",
    ) -> None:
        title = f"Edit {label} · WT{issue_number}"
        super().__init__(title=title[:45], timeout=30 * 60.0)
        self.ctx = ctx
        self.issue_number = int(issue_number)
        self.asset_key = asset_key
        self.filename = filename
        # Discord placeholders cap at 100 chars. An over-long hint
        # silently drops the field, so trim before passing.
        ph = (placeholder or "").strip()
        if len(ph) > 100:
            ph = ph[:97] + "…"
        # Discord rejects modals where a TextInput has `default=""`
        # alongside `required=False` — the modal opens blank in the
        # client but the interaction comes back as "this interaction
        # failed", which is what /eddy edit on a missing file used to
        # hit. Pass `default=None` when the file is empty so Discord
        # treats it as "no default" instead of "default = empty string".
        default = current_text if current_text else None
        self.input = ui.TextInput(
            label=f"{filename}  (max {_MODAL_MAX} chars)",
            style=discord.TextStyle.paragraph,
            default=default,
            placeholder=ph or None,
            max_length=_MODAL_MAX,
            required=False,
        )
        self.add_item(self.input)

    async def on_submit(self, interaction) -> None:  # type: ignore[override]
        new_text = self.input.value or ""
        try:
            content_store.write_issue(self.issue_number, self.filename, new_text)
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
            f"({len(new_text)} chars). Done.",
            ephemeral=True,
        )


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
    filename, label, placeholder = _ASSETS[asset_key]
    window = db.get_active_issue_window()
    if window is None:
        return None, "❌ no active issue window — run `/scout issue start` first."
    n = int(window["issue_number"])
    current = _read_current(n, filename)
    if len(current) > _MODAL_MAX:
        return None, (
            f"❌ `{filename}` for WT{n} is {len(current):,} chars; modals are capped at "
            f"{_MODAL_MAX:,}. Edit via the S3 console for this one."
        )
    modal = _AssetEditModal(
        ctx=ctx, issue_number=n, asset_key=asset_key,
        filename=filename, label=label,
        current_text=current, placeholder=placeholder,
    )
    return modal, None
