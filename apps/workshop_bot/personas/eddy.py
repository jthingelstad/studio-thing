"""Eddy — editor.

Eddy hosts the ``/eddy`` slash tree (issue assembly, status,
follow-ups, ad-hoc editorial commands). Each persona owns its own
slash tree; ``PersonaBot.on_ready`` syncs ``self.command_tree`` if
present.
"""

from __future__ import annotations

from .base import Deps, PersonaBot
from .commands import register_eddy_commands


class EddyBot(PersonaBot):
    persona = "eddy"
    name = "Eddy"
    home_channel_env = "DISCORD_CHANNEL_EDITORIAL"
    empty_greeting = "Hey — what are we looking at?"
    # Sonnet is the default for all of Eddy's general work — mentions,
    # reorder, composition (subject/haiku/description/closer/thesis),
    # follow-ups. Two editorial-review surfaces override up to Opus:
    # ``update-draft:html-review`` (the canonical draft.html drawer
    # pass) and ``review-text`` (``/eddy review <text>``). See each
    # job's ``bot.core(..., model="opus")`` callsite.
    preferred_model = "sonnet"
    slash_commands_summary = (
        "/eddy commands: issue {start,update,status,final,haiku,subject,publish} · "
        "status · review · archive · followup"
    )

    def __init__(self, deps: Deps) -> None:
        super().__init__(deps)
        self.command_tree = register_eddy_commands(self)

    def persistent_views(self) -> list:
        # The Build + Publish phase cards live in #editorial and must keep
        # routing clicks across restarts — register the canonical (all-enabled)
        # views so custom_id dispatch survives a reboot.
        from .views.build_card_view import BuildCardView
        from .views.publish_card_view import PublishCardView

        return [BuildCardView(), PublishCardView()]
