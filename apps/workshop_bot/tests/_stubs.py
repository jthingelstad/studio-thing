"""Shared discord/anthropic stubs for offline unit tests.

Multiple test files in this directory need to import workshop_bot
modules without the real ``discord`` and ``anthropic`` packages
installed (or, more commonly, without binding to those packages so
tests can run on bare CI). Rather than each file maintaining its own
inline stub — which collided under ``unittest discover`` because the
first stub installed wins and later test modules reference whichever
class binding was active at their own module-load time — this helper
installs one canonical stub.

The stub is **idempotent**: callers can safely call ``install()``
multiple times. The second call is a no-op.
"""

from __future__ import annotations

import sys
import types


_INSTALLED = False


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    _install_discord()
    _install_anthropic()


def _install_discord() -> None:
    discord = types.ModuleType("discord")

    class _Client:
        def __init__(self, *a, **k):
            self.user = None

    class _Intents:
        message_content = False
        guilds = False

        @staticmethod
        def default():
            return _Intents()

    class _Permissions:
        def __init__(self, **flags):
            self.flags = flags

    class _Object:
        def __init__(self, id):
            self.id = id

    class _DiscordException(Exception):
        pass

    class _HTTPException(_DiscordException):
        pass

    class _MessageReference:
        """Minimal stand-in for ``discord.MessageReference``. The real
        class takes ``message_id`` / ``channel_id`` / ``fail_if_not_
        exists`` kwargs; the stub stores them so tests can assert on
        the shape passed to ``channel.send(..., reference=ref)``."""

        def __init__(self, *, message_id, channel_id, fail_if_not_exists=True):
            self.message_id = message_id
            self.channel_id = channel_id
            self.fail_if_not_exists = fail_if_not_exists

    discord.Client = _Client  # type: ignore[attr-defined]
    discord.Intents = _Intents  # type: ignore[attr-defined]
    discord.Permissions = _Permissions  # type: ignore[attr-defined]
    discord.Object = _Object  # type: ignore[attr-defined]
    discord.Message = object  # type: ignore[attr-defined]
    discord.Interaction = object  # type: ignore[attr-defined]
    discord.RawReactionActionEvent = object  # type: ignore[attr-defined]
    discord.MessageReference = _MessageReference  # type: ignore[attr-defined]
    discord.DiscordException = _DiscordException  # type: ignore[attr-defined]
    discord.HTTPException = _HTTPException  # type: ignore[attr-defined]
    discord.NotFound = _HTTPException  # type: ignore[attr-defined]

    abc_mod = types.ModuleType("discord.abc")
    abc_mod.Messageable = object  # type: ignore[attr-defined]

    # discord.ui — Modal + TextInput surface used by the /eddy edit
    # asset-editor flow. Minimal: Modal stores its items and exposes
    # an awaitable on_submit hook; TextInput stores its value.
    ui_mod = types.ModuleType("discord.ui")

    class _Modal:
        def __init__(self, *, title=None, custom_id=None, timeout=None):
            self.title = title
            self.custom_id = custom_id
            self.timeout = timeout
            self.items: list = []

        def add_item(self, item):
            self.items.append(item)
            return self

        async def on_submit(self, interaction):  # pragma: no cover - subclass overrides
            pass

    class _TextInput:
        def __init__(
            self, *, label=None, style=None, default=None,
            max_length=None, required=True, custom_id=None, placeholder=None,
        ):
            self.label = label
            self.style = style
            self.default = default
            self.max_length = max_length
            self.required = required
            self.custom_id = custom_id
            self.placeholder = placeholder
            self.value = default or ""

    ui_mod.Modal = _Modal  # type: ignore[attr-defined]
    ui_mod.TextInput = _TextInput  # type: ignore[attr-defined]
    discord.ui = ui_mod  # type: ignore[attr-defined]

    class _TextStyle:
        short = "short"
        paragraph = "paragraph"

    discord.TextStyle = _TextStyle  # type: ignore[attr-defined]

    # discord.Embed — used by the ship-console card. Stores title /
    # description / color and an ordered field list so tests can assert
    # on the rendered rows.
    class _Embed:
        def __init__(self, *, title=None, description=None, color=None, colour=None, url=None):
            self.title = title
            self.description = description
            self.color = color if color is not None else colour
            self.url = url
            self.fields: list = []
            self.footer = None

        def add_field(self, *, name, value, inline=False):
            self.fields.append({"name": name, "value": value, "inline": inline})
            return self

        def set_footer(self, *, text=None, icon_url=None):
            self.footer = {"text": text, "icon_url": icon_url}
            return self

    discord.Embed = _Embed  # type: ignore[attr-defined]

    class _Color:
        def __init__(self, value=0):
            self.value = value

        @classmethod
        def from_rgb(cls, r, g, b):
            return cls((int(r) << 16) + (int(g) << 8) + int(b))

        # The handful of named colours the console uses.
        @classmethod
        def blurple(cls):
            return cls(0x5865F2)

        @classmethod
        def green(cls):
            return cls(0x2ECC71)

        @classmethod
        def gold(cls):
            return cls(0xF1C40F)

        @classmethod
        def greyple(cls):
            return cls(0x99AAB5)

    discord.Color = _Color  # type: ignore[attr-defined]
    discord.Colour = _Color  # type: ignore[attr-defined]

    class _ButtonStyle:
        primary = 1
        secondary = 2
        success = 3
        danger = 4
        link = 5
        blurple = 1
        grey = 2
        gray = 2
        green = 3
        red = 4

    discord.ButtonStyle = _ButtonStyle  # type: ignore[attr-defined]

    # ui.View / ui.Button / @ui.button — the persistent-view surface for
    # the ship console. The real metaclass collects @ui.button-decorated
    # methods into the view's children in declaration order; the stub
    # approximates by scanning for the marker the decorator leaves.
    class _Button:
        def __init__(
            self, *, label=None, style=None, custom_id=None, disabled=False,
            emoji=None, row=None, url=None,
        ):
            self.label = label
            self.style = style
            self.custom_id = custom_id
            self.disabled = disabled
            self.emoji = emoji
            self.row = row
            self.url = url
            self.callback = None

    class _View:
        def __init__(self, *, timeout=180):
            self.timeout = timeout
            self.children: list = []
            seen: set = set()
            for klass in type(self).__mro__:
                for name, attr in vars(klass).items():
                    spec = getattr(attr, "__discord_button__", None)
                    if spec is None or name in seen:
                        continue
                    seen.add(name)
                    btn = _Button(**spec)
                    btn.callback = getattr(self, name)
                    self.children.append(btn)

        def add_item(self, item):
            self.children.append(item)
            return self

        def stop(self):  # real discord.ui.View.stop() halts the timeout
            self._stopped = True

    def _button(*, label=None, style=None, custom_id=None, disabled=False, emoji=None, row=None):
        def deco(fn):
            fn.__discord_button__ = {
                "label": label, "style": style, "custom_id": custom_id,
                "disabled": disabled, "emoji": emoji, "row": row,
            }
            return fn
        return deco

    ui_mod.View = _View  # type: ignore[attr-defined]
    ui_mod.Button = _Button  # type: ignore[attr-defined]
    ui_mod.button = _button  # type: ignore[attr-defined]

    # discord.app_commands surface — minimal shape that workshop_bot's
    # commands module actually touches (Group, CommandTree.add_command,
    # @group.command, @app_commands.describe, @app_commands.choices,
    # Choice). Class-getitem on Choice supports ``Choice[str]`` generics.
    app_commands = types.ModuleType("discord.app_commands")

    class _Choice:
        def __init__(self, *, name=None, value=None):
            self.name = name
            self.value = value

        def __class_getitem__(cls, item):
            return cls

    class _Group:
        def __init__(
            self, *, name=None, description=None, default_permissions=None, parent=None
        ):
            self.name = name
            self.description = description
            self.default_permissions = default_permissions
            self.parent = parent
            # ``commands`` holds both leaf commands (functions) and
            # nested subgroups (other ``_Group`` instances), mirroring
            # discord.py's ``Group.commands``.
            self.commands: list = []
            self._cmd_name = name  # so a subgroup looks like a "command" to a parent
            if parent is not None:
                parent.commands.append(self)

        def command(self, *, name=None, description=None):
            def deco(fn):
                fn._cmd_name = name
                fn._cmd_description = description
                self.commands.append(fn)
                return fn
            return deco

    class _CommandTree:
        def __init__(self, client):
            self.client = client
            self.groups: list = []

        def add_command(self, cmd):
            self.groups.append(cmd)

    def _describe(**kwargs):
        def deco(fn):
            fn._describe = kwargs
            return fn
        return deco

    def _choices(**kwargs):
        def deco(fn):
            fn._choices = kwargs
            return fn
        return deco

    def _autocomplete(**kwargs):
        """Stub for ``@app_commands.autocomplete`` — records the
        per-parameter autocomplete callables on the decorated function so
        tests can introspect them; runtime dispatch isn't exercised in
        the test harness."""
        def deco(fn):
            existing = getattr(fn, "_autocomplete", {})
            existing.update(kwargs)
            fn._autocomplete = existing
            return fn
        return deco

    app_commands.Choice = _Choice  # type: ignore[attr-defined]
    app_commands.Group = _Group  # type: ignore[attr-defined]
    app_commands.CommandTree = _CommandTree  # type: ignore[attr-defined]
    app_commands.describe = _describe  # type: ignore[attr-defined]
    app_commands.choices = _choices  # type: ignore[attr-defined]
    app_commands.autocomplete = _autocomplete  # type: ignore[attr-defined]
    discord.app_commands = app_commands  # type: ignore[attr-defined]

    sys.modules["discord"] = discord
    sys.modules["discord.abc"] = abc_mod
    sys.modules["discord.app_commands"] = app_commands
    sys.modules["discord.ui"] = ui_mod


def _install_anthropic() -> None:
    anthropic = types.ModuleType("anthropic")

    class _A:
        def __init__(self, *a, **k):
            pass

    anthropic.Anthropic = _A  # type: ignore[attr-defined]
    sys.modules["anthropic"] = anthropic
