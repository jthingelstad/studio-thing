"""``/eddy`` slash tree.

Eddy is the editor. He hosts the **editorial** issue verbs
(``/eddy issue echoes | reorder | haiku | subject``), the cross-cutting
bot-health snapshot (``/eddy status``), the ``/eddy edit`` /
``/eddy currently`` content editors, ad-hoc ``/eddy review`` /
``/eddy archive``, and his own follow-ups (``/eddy followup …``).

The **production** verbs (start / update / status / build / built /
reopen / publish / put-to-bed / reset) and the Build/Publish phase cards
moved to Scout (``/scout issue …``, ``#production``) — Scout owns the
production slate; Eddy owns editorial shape. The CTA composer lives at
``/patty cta``.

The dispatch shapes (fast-job vs interactive-job) mirror the legacy
``/workshop`` tree exactly — only the prefix changes. See
:mod:`._shared` for the dispatch helpers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands

from ...jobs import follow_up as followup_job
from ...jobs import status as status_job
from ...jobs import (
    archive_lookup,
    compose_echoes,
    compose_haiku,
    compose_meta,
    currently as currently_job,
    edit_asset,
    reorder,
    review_text,
)
from ...tools import db as _db
from ._shared import _ctx, make_ack, make_run_and_ack, make_run_interactive

if TYPE_CHECKING:
    from ..base import PersonaBot  # noqa: F401


def register_eddy_commands(
    bot: "PersonaBot",
    *,
    tree: Optional[app_commands.CommandTree] = None,
) -> app_commands.CommandTree:
    """Attach the ``/eddy`` command tree to Eddy's bot.

    If ``tree`` is provided, the ``/eddy`` group is added to it; otherwise a
    new ``CommandTree`` is created. (Tree injection was used during the
    transient ``/workshop`` ↔ ``/eddy`` overlap; kept since it's harmless
    and the test harness exercises both paths.)
    """
    if tree is None:
        tree = app_commands.CommandTree(bot)

    _ack = make_ack("/eddy")
    _run_and_ack = make_run_and_ack(_ack, "/eddy")
    _run_interactive = make_run_interactive("/eddy")

    eddy = app_commands.Group(
        name="eddy",
        description="Eddy (editor) — issue assembly, status, follow-ups",
        default_permissions=discord.Permissions(manage_guild=True),
    )
    issue = app_commands.Group(
        name="issue", description="Assemble the in-flight issue", parent=eddy
    )
    followup = app_commands.Group(
        name="followup", description="Eddy's follow-up commitments", parent=eddy
    )
    currently = app_commands.Group(
        name="currently",
        description="The in-flight issue's ## Currently section (per-type)",
        parent=eddy,
    )

    # ── /eddy issue ───────────────────────────────────────────────────

    @issue.command(
        name="echoes",
        description="Write the Echoes note (Thingy's archive callback) for the in-flight issue.",
    )
    async def issue_echoes_cmd(interaction: discord.Interaction) -> None:  # type: ignore[misc]
        await _run_and_ack(interaction, lambda: compose_echoes.run(_ctx(bot)), "issue echoes")

    @issue.command(
        name="reorder",
        description="Eddy proposes a Notable/Brief reorder; on ✅ the DB row positions update.",
    )
    async def issue_reorder_cmd(interaction: discord.Interaction) -> None:  # type: ignore[misc]
        await _run_interactive(
            interaction, lambda: reorder.run(_ctx(bot)), "issue reorder",
            "Starting `issue reorder` — Eddy will post a reorder proposal in #editorial; react there.",
        )

    @issue.command(
        name="haiku",
        description="Generate haiku options for the in-flight issue → haiku.md.",
    )
    async def issue_haiku_cmd(interaction: discord.Interaction) -> None:  # type: ignore[misc]
        await _run_interactive(
            interaction, lambda: compose_haiku.run(_ctx(bot)), "issue haiku",
            "Starting `issue haiku` — options will post in #editorial; react there to pick.",
        )

    @issue.command(
        name="subject",
        description="Pick the email subject (5 options) then generate the description → metadata.json.",
    )
    async def issue_subject_cmd(interaction: discord.Interaction) -> None:  # type: ignore[misc]
        await _run_interactive(
            interaction, lambda: compose_meta.run(_ctx(bot)), "issue subject",
            "Starting `issue subject` — 5 subject options then a description will post in #editorial; react there to pick.",
        )

    # ── /eddy followup ────────────────────────────────────────────────

    @followup.command(
        name="list",
        description="Eddy's pending follow-up commitments — when he checks in, on what.",
    )
    async def followup_list_cmd(interaction: discord.Interaction) -> None:  # type: ignore[misc]
        await _run_and_ack(
            interaction,
            lambda: followup_job.list_open(_ctx(bot), persona="eddy"),
            "followup list",
        )

    @followup.command(
        name="add",
        description="Schedule an Eddy follow-up at a time, in N days, or when an issue is reached.",
    )
    @app_commands.describe(
        note="What the follow-up is about",
        when="ISO date YYYY-MM-DD (≈6pm that day) or datetime YYYY-MM-DDTHH:MM",
        in_days="…or a relative offset in days (1 = tomorrow evening)",
        at_issue="…or an issue number — fires once that issue is in flight",
    )
    async def followup_add_cmd(  # type: ignore[misc]
        interaction: discord.Interaction,
        note: str,
        when: str = "",
        in_days: int = -1,
        at_issue: int = -1,
    ) -> None:
        await _run_and_ack(
            interaction,
            lambda: followup_job.add(
                _ctx(bot), note=note, persona="eddy",
                when=(when or ""),
                in_days=(None if int(in_days) < 0 else int(in_days)),
                at_issue=(None if int(at_issue) < 0 else int(at_issue)),
                created_by=str(interaction.user),
            ),
            "followup add",
        )

    @followup.command(
        name="cancel",
        description="Cancel a pending Eddy follow-up by id (from `followup list`).",
    )
    @app_commands.describe(id="The follow-up id")
    async def followup_cancel_cmd(  # type: ignore[misc]
        interaction: discord.Interaction, id: int
    ) -> None:
        await _run_and_ack(
            interaction,
            lambda: followup_job.cancel(_ctx(bot), followup_id=int(id), persona="eddy"),
            "followup cancel",
        )

    # ── /eddy edit ────────────────────────────────────────────────────

    @eddy.command(
        name="edit",
        description="Edit a small per-issue asset (intro/outro/haiku/cover/currently/cta/thanks) in a modal.",
    )
    @app_commands.describe(
        asset="Which asset to edit (modal pops with the current contents)",
    )
    @app_commands.choices(asset=[
        app_commands.Choice(name=key, value=key) for key in edit_asset.ASSET_CHOICES
    ])
    async def edit_cmd(  # type: ignore[misc]
        interaction: discord.Interaction, asset: str,
    ) -> None:
        modal, err = edit_asset.build_modal(_ctx(bot), asset_key=str(asset))
        if modal is None:
            try:
                await interaction.response.send_message(err or "❌ couldn't build modal.", ephemeral=True)
            except Exception:  # noqa: BLE001
                pass
            return
        try:
            await interaction.response.send_modal(modal)
        except Exception as exc:  # noqa: BLE001
            try:
                await interaction.response.send_message(
                    f"❌ couldn't open the editor: `{type(exc).__name__}: {exc}`",
                    ephemeral=True,
                )
            except Exception:  # noqa: BLE001
                pass

    # ── /eddy status ──────────────────────────────────────────────────

    @eddy.command(
        name="status",
        description="Ops snapshot — issue window, goal/campaigns, held job locks, recent runs.",
    )
    async def status_cmd(interaction: discord.Interaction) -> None:  # type: ignore[misc]
        await _run_and_ack(interaction, lambda: status_job.run(_ctx(bot)), "status")

    # ── /eddy review ──────────────────────────────────────────────────

    @eddy.command(
        name="review",
        description="Ad-hoc editorial review of pasted text — Eddy posts a critique to #editorial.",
    )
    @app_commands.describe(
        text="The text Eddy should review (voice, structure, factual flags)",
    )
    async def review_cmd(  # type: ignore[misc]
        interaction: discord.Interaction, text: str
    ) -> None:
        await _run_and_ack(
            interaction,
            lambda: review_text.run(_ctx(bot), text=text, invoker=str(interaction.user)),
            "review",
        )

    # ── /eddy archive ─────────────────────────────────────────────────

    @eddy.command(
        name="archive",
        description="Show a past issue overview — subject, publish date, sections, teaser.",
    )
    @app_commands.describe(issue="Issue number (e.g. 287)")
    async def archive_cmd(  # type: ignore[misc]
        interaction: discord.Interaction, issue: int
    ) -> None:
        await _run_and_ack(
            interaction,
            lambda: archive_lookup.run(_ctx(bot), issue_number=int(issue)),
            "archive",
        )

    # ── /eddy currently ───────────────────────────────────────────────

    async def _type_autocomplete(  # type: ignore[misc]
        _interaction: discord.Interaction, current: str,
    ) -> list[app_commands.Choice[str]]:
        try:
            rows = _db.currently_list_types()
        except Exception:  # noqa: BLE001
            return []
        needle = (current or "").strip().lower()
        choices: list[app_commands.Choice[str]] = []
        for row in rows:
            label = row["label"]
            if needle and needle not in label.lower():
                continue
            choices.append(app_commands.Choice(name=label, value=label))
            if len(choices) >= 25:
                break
        return choices

    @currently.command(
        name="list",
        description="Show the in-flight issue's Currently entries + unfilled types.",
    )
    async def currently_list_cmd(interaction: discord.Interaction) -> None:  # type: ignore[misc]
        await _run_and_ack(
            interaction,
            lambda: currently_job.list_state(_ctx(bot)),
            "currently list",
        )

    @currently.command(
        name="edit",
        description="Edit one Currently entry in a modal (markdown links OK).",
    )
    @app_commands.describe(type="Which Currently type to edit (e.g. Listening, Reading).")
    @app_commands.autocomplete(type=_type_autocomplete)
    async def currently_edit_cmd(  # type: ignore[misc]
        interaction: discord.Interaction, type: str,
    ) -> None:
        modal, err = currently_job.build_modal(_ctx(bot), type_label=str(type))
        if modal is None:
            try:
                await interaction.response.send_message(
                    err or "❌ couldn't build modal.", ephemeral=True,
                )
            except Exception:  # noqa: BLE001
                pass
            return
        try:
            await interaction.response.send_modal(modal)
        except Exception as exc:  # noqa: BLE001
            try:
                await interaction.response.send_message(
                    f"❌ couldn't open the editor: `{type(exc).__name__}: {exc}`",
                    ephemeral=True,
                )
            except Exception:  # noqa: BLE001
                pass

    @currently.command(
        name="set",
        description="Quick-set one Currently entry (no modal — for plain-text values).",
    )
    @app_commands.describe(
        type="Currently type (autocompletes from canonical pool).",
        value="The entry text. Markdown OK; preserved verbatim.",
    )
    @app_commands.autocomplete(type=_type_autocomplete)
    async def currently_set_cmd(  # type: ignore[misc]
        interaction: discord.Interaction, type: str, value: str,
    ) -> None:
        await _run_and_ack(
            interaction,
            lambda: currently_job.set_value(_ctx(bot), type_label=str(type), value=str(value)),
            f"currently set {type}",
        )

    @currently.command(
        name="clear",
        description="Remove one Currently entry from the in-flight issue.",
    )
    @app_commands.describe(type="Currently type to clear.")
    @app_commands.autocomplete(type=_type_autocomplete)
    async def currently_clear_cmd(  # type: ignore[misc]
        interaction: discord.Interaction, type: str,
    ) -> None:
        await _run_and_ack(
            interaction,
            lambda: currently_job.clear_value(_ctx(bot), type_label=str(type)),
            f"currently clear {type}",
        )

    @currently.command(
        name="reorder",
        description="Reorder Currently entries — comma-separated permutation of filled labels.",
    )
    @app_commands.describe(
        labels="Comma-separated list of currently-filled labels in the desired order.",
    )
    async def currently_reorder_cmd(  # type: ignore[misc]
        interaction: discord.Interaction, labels: str,
    ) -> None:
        await _run_and_ack(
            interaction,
            lambda: currently_job.reorder(_ctx(bot), labels=str(labels)),
            "currently reorder",
        )

    @currently.command(
        name="add-type",
        description="Add a new canonical Currently type (e.g. Printing). No code change needed.",
    )
    @app_commands.describe(label="New type label, e.g. Printing.")
    async def currently_add_type_cmd(  # type: ignore[misc]
        interaction: discord.Interaction, label: str,
    ) -> None:
        await _run_and_ack(
            interaction,
            lambda: currently_job.add_type(_ctx(bot), label=str(label)),
            "currently add-type",
        )

    @currently.command(
        name="retire-type",
        description="Retire a canonical Currently type (past entries still render).",
    )
    @app_commands.describe(label="Type label to retire.")
    @app_commands.autocomplete(label=_type_autocomplete)
    async def currently_retire_type_cmd(  # type: ignore[misc]
        interaction: discord.Interaction, label: str,
    ) -> None:
        await _run_and_ack(
            interaction,
            lambda: currently_job.retire_type(_ctx(bot), label=str(label)),
            "currently retire-type",
        )

    tree.add_command(eddy)
    return tree
