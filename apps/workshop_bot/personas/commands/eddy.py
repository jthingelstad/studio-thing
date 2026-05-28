"""``/eddy`` slash tree.

Eddy is the editor + lead persona. He hosts the issue-assembly artifact
verbs (``/eddy issue start | update | status | final | haiku | subject |
publish``), the cross-cutting bot-health snapshot (``/eddy status``), and
his own follow-ups (``/eddy followup …``). The CTA composer that used
to live at ``/workshop issue cta`` moved to ``/patty cta`` (commit 3).

Ad-hoc editorial commands (``/eddy review``, ``/eddy archive``) land
in commit 5.

The dispatch shapes (fast-job vs interactive-job) mirror the legacy
``/workshop`` tree exactly — only the prefix changes. See
:mod:`._shared` for the dispatch helpers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands

from ...jobs import _base as jobs_base
from ...jobs import follow_up as followup_job
from ...jobs import status as status_job
from ...jobs import (
    archive_lookup,
    build_card,
    compose_echoes,
    compose_haiku,
    compose_meta,
    currently as currently_job,
    edit_asset,
    issue_status,
    publish as publish_job,
    put_to_bed as put_to_bed_job,
    reorder,
    reset_issue,
    review_text,
    start_issue,
    update_draft,
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
        name="start",
        description="Begin assembling a new issue (number, Saturday pub date, day count).",
    )
    @app_commands.describe(
        number="Issue number being assembled (e.g. 458)",
        pub_date="Publishing Saturday (YYYY-MM-DD)",
        day_count="Days to include before the cutoff — usually 7, sometimes 14",
    )
    async def issue_start_cmd(  # type: ignore[misc]
        interaction: discord.Interaction,
        number: int,
        pub_date: str,
        day_count: int = 7,
    ) -> None:
        await _run_and_ack(
            interaction,
            lambda: start_issue.run(
                _ctx(bot),
                number=number,
                pub_date=pub_date,
                day_count=int(day_count),
                set_by=str(interaction.user),
            ),
            "issue start",
        )

    @issue.command(
        name="update",
        description="Re-project upstream content (Pinboard + micro.blog + assets) into draft.md.",
    )
    async def issue_update_cmd(interaction: discord.Interaction) -> None:  # type: ignore[misc]
        await _run_and_ack(interaction, lambda: update_draft.run(_ctx(bot)), "issue update")

    @issue.command(
        name="status",
        description="Read-only state report on the in-flight issue (sections + assets).",
    )
    async def issue_status_cmd(interaction: discord.Interaction) -> None:  # type: ignore[misc]
        await _run_and_ack(interaction, lambda: issue_status.run(_ctx(bot)), "issue status")

    @issue.command(
        name="build",
        description="Post (or re-pin) the Build card — the content phase surface.",
    )
    async def issue_build_cmd(interaction: discord.Interaction) -> None:  # type: ignore[misc]
        await _run_and_ack(interaction, lambda: build_card.run(_ctx(bot)), "issue build")

    @issue.command(
        name="echoes",
        description="Write the Echoes note (Thingy's archive callback) for the in-flight issue.",
    )
    async def issue_echoes_cmd(interaction: discord.Interaction) -> None:  # type: ignore[misc]
        await _run_and_ack(interaction, lambda: compose_echoes.run(_ctx(bot)), "issue echoes")

    @issue.command(
        name="built",
        description="Mark the issue built → moves it from Build to Publish (opens the send controls).",
    )
    async def issue_built_cmd(interaction: discord.Interaction) -> None:  # type: ignore[misc]
        await _run_and_ack(interaction, lambda: build_card.mark_built(_ctx(bot)), "issue built")

    @issue.command(
        name="reopen",
        description="Reopen a published-phase issue for content edits → back to Build.",
    )
    async def issue_reopen_cmd(interaction: discord.Interaction) -> None:  # type: ignore[misc]
        await _run_and_ack(interaction, lambda: build_card.reopen(_ctx(bot)), "issue reopen")

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

    # /eddy issue publish — destination-aware ship. `destination` chooses
    # one of (audio, buttondown, website) or "all" (audio → buttondown
    # → website, the standard ship order). Each leg is independently
    # idempotent. Discord limits group nesting to one level, so this is
    # a single command with a choice arg rather than a publish subgroup.
    @issue.command(
        name="publish",
        description="Ship the issue. Destination = all | audio | buttondown | website.",
    )
    @app_commands.describe(
        destination="Which destination to ship to. 'all' runs audio → buttondown → website.",
    )
    @app_commands.choices(destination=[
        app_commands.Choice(name="all", value="all"),
        app_commands.Choice(name="audio", value="audio"),
        app_commands.Choice(name="buttondown", value="buttondown"),
        app_commands.Choice(name="website", value="website"),
    ])
    async def issue_publish_cmd(  # type: ignore[misc]
        interaction: discord.Interaction, destination: str = "all",
    ) -> None:
        dest = (destination or "all").strip().lower()
        handler = {
            "all": publish_job.publish_all,
            "audio": publish_job.publish_audio,
            "buttondown": publish_job.publish_buttondown,
            "website": publish_job.publish_website,
        }.get(dest, publish_job.publish_all)
        await _run_and_ack(
            interaction, lambda: handler(_ctx(bot)),
            f"issue publish {dest}",
        )

    # /eddy issue put-to-bed — newsroom closing bookend to /eddy issue start.
    # Takes no arguments; operates on the active issue window. Files the
    # shipped issue into the `issues` + `issue_links` data layer and flips
    # is_active=0 so workshop is between issues until the next start.
    @issue.command(
        name="put-to-bed",
        description="File the just-shipped active issue into the data layer and close the window.",
    )
    async def issue_put_to_bed_cmd(interaction: discord.Interaction) -> None:  # type: ignore[misc]
        await _run_and_ack(
            interaction, lambda: put_to_bed_job.run(_ctx(bot)), "issue put-to-bed",
        )

    @issue.command(
        name="reset",
        description="Drop the previous-step artifacts so the in-flight issue can be re-published.",
    )
    @app_commands.describe(
        step="Which artifacts to clear: 'reorder' (clear promotions, drop thesis) or 'publish' (drop buttondown.md/.html).",
    )
    @app_commands.choices(step=[
        app_commands.Choice(name="reorder", value="final"),
        app_commands.Choice(name="publish", value="publish"),
    ])
    async def issue_reset_cmd(  # type: ignore[misc]
        interaction: discord.Interaction, step: str,
    ) -> None:
        await _run_and_ack(
            interaction,
            lambda: reset_issue.run(_ctx(bot), step=str(step)),
            f"issue reset {step}",
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
