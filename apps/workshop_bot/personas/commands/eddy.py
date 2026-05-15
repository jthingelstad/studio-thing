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
    build_publish,
    compose_haiku,
    compose_meta,
    create_final,
    issue_status,
    review_text,
    start_issue,
    update_draft,
)
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
        name="final",
        description="Eddy's reorder review → final.md (then run issue haiku/subject and issue publish).",
    )
    async def issue_final_cmd(interaction: discord.Interaction) -> None:  # type: ignore[misc]
        await _run_interactive(
            interaction, lambda: create_final.run(_ctx(bot)), "issue final",
            "Starting `issue final` — Eddy will post a reorder proposal in #editorial; react there.",
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

    @issue.command(
        name="publish",
        description="Assemble publish.md from final.md + assets (refuses if anything required is missing).",
    )
    async def issue_publish_cmd(interaction: discord.Interaction) -> None:  # type: ignore[misc]
        await _run_and_ack(interaction, lambda: build_publish.run(_ctx(bot)), "issue publish")

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

    tree.add_command(eddy)
    return tree
