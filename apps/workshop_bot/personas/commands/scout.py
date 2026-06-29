"""``/scout`` slash tree.

Scout is the producer — owner of the production slate. Two read-only
top-level verbs frame the slate: ``/scout status`` (a slate-framed ops
snapshot) and ``/scout slate`` (the production-slate view).

The ``/scout issue …`` subgroup is the **production** lifecycle — the
verbs that drive an issue from start through ship and put-to-bed:
``start | update | status | build | built | reopen | publish |
put-to-bed | reset``. These migrated over from ``/eddy issue …`` once
Scout took ownership of production; the Build/Publish phase cards they
drive live in ``#production`` under Scout's avatar. The editorial verbs
(echoes / reorder / haiku / subject) stay with Eddy at ``/eddy issue``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands

from ...jobs import (
    issue_status,
    production_ops,
    publish as publish_job,
    put_to_bed as put_to_bed_job,
    reset_issue,
    scout_slate,
    scout_status,
    start_issue,
    update_draft,
)
from ._shared import _ctx, make_ack, make_run_and_ack

if TYPE_CHECKING:
    from ..base import PersonaBot  # noqa: F401


def register_scout_commands(
    bot: "PersonaBot",
    *,
    tree: Optional[app_commands.CommandTree] = None,
) -> app_commands.CommandTree:
    """Attach the ``/scout`` command tree to Scout's bot."""
    if tree is None:
        tree = app_commands.CommandTree(bot)

    _ack = make_ack("/scout")
    _run_and_ack = make_run_and_ack(_ack, "/scout")

    scout = app_commands.Group(
        name="scout",
        description="Scout (producer) — production slate, lifecycle, status",
        default_permissions=discord.Permissions(manage_guild=True),
    )
    issue = app_commands.Group(
        name="issue", description="Drive the in-flight issue through production", parent=scout
    )

    # ── /scout status ────────────────────────────────────────────────
    @scout.command(
        name="status",
        description="Scout's read-only ops snapshot — slate, locks, recent runs.",
    )
    async def scout_status_cmd(interaction: discord.Interaction) -> None:  # type: ignore[misc]
        await _run_and_ack(
            interaction,
            lambda: scout_status.run(_ctx(bot)),
            "status",
        )

    # ── /scout slate ─────────────────────────────────────────────────
    @scout.command(
        name="slate",
        description="The production slate (newsletter today; blog/podcast/membership in Phase 2).",
    )
    @app_commands.describe(
        kind="Optional surface filter (newsletter / blog / podcast / membership)",
    )
    @app_commands.choices(kind=[
        app_commands.Choice(name="newsletter", value="newsletter"),
        app_commands.Choice(name="blog", value="blog"),
        app_commands.Choice(name="podcast", value="podcast"),
        app_commands.Choice(name="membership", value="membership"),
    ])
    async def scout_slate_cmd(  # type: ignore[misc]
        interaction: discord.Interaction, kind: str = ""
    ) -> None:
        normalized: Optional[str] = kind.strip().lower() or None
        await _run_and_ack(
            interaction,
            lambda: scout_slate.run(
                _ctx(bot),
                kind=normalized,  # type: ignore[arg-type]
            ),
            "slate",
        )

    # ── /scout issue ─────────────────────────────────────────────────
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
        name="built",
        description="Mark the issue built → moves it from Build to Publish (escape hatch; use the web page).",
    )
    async def issue_built_cmd(interaction: discord.Interaction) -> None:  # type: ignore[misc]
        await _run_and_ack(interaction, lambda: production_ops.mark_built(_ctx(bot)), "issue built")

    @issue.command(
        name="reopen",
        description="Reopen a published-phase issue for content edits → back to Build.",
    )
    async def issue_reopen_cmd(interaction: discord.Interaction) -> None:  # type: ignore[misc]
        await _run_and_ack(interaction, lambda: production_ops.reopen(_ctx(bot)), "issue reopen")

    # /scout issue publish — destination-aware ship. `destination` chooses
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

    # /scout issue put-to-bed — newsroom closing bookend to /scout issue start.
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
        step="Artifacts to clear: 'reorder' (promotions + thesis) or 'publish' (buttondown.md/.html).",
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

    tree.add_command(scout)
    return tree
