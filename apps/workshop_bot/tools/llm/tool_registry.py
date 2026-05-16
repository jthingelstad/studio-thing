"""Tool registry and per-turn ContextVars for the workshop agent loop."""

from __future__ import annotations

import re
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Callable, Optional

from ...systems._base import SystemServer

# The agent loop sets this before each tool execution so per-persona
# tools (`memory__remember`, `memory__recall`) can attribute their work
# without leaning on a shared, mutable Deps object.
active_persona: ContextVar[str] = ContextVar("active_persona", default="unknown")

# Mention/peer/team handlers set this so ``react__add`` knows which
# Discord message to attach the emoji to.
active_react_target: ContextVar[Optional[tuple[int, int]]] = ContextVar(
    "active_react_target", default=None
)


@dataclass(frozen=True)
class Tool:
    name: str
    spec: dict[str, Any]
    func: Callable[..., Any]
    source: str = "local"  # "local" or "system:<name>"
    # Personas that can see this tool. ``None`` means unrestricted.
    restricted_to: Optional[frozenset[str]] = None


class ToolRegistry:
    """Composes external-system tools and local helpers into one namespace."""

    _NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(
        self,
        name: str,
        spec: dict[str, Any],
        func: Callable[..., Any],
        source: str = "local",
        restricted_to: Optional[frozenset[str]] = None,
    ) -> None:
        if not self._NAME_RE.match(name):
            raise ValueError(
                f"tool name {name!r} is not API-safe; expected "
                f"<system>__<action> using [a-zA-Z0-9_-]"
            )
        if name in self._tools:
            raise ValueError(f"duplicate tool registration: {name!r}")
        spec_with_name = dict(spec)
        spec_with_name["name"] = name
        self._tools[name] = Tool(
            name=name,
            spec=spec_with_name,
            func=func,
            source=source,
            restricted_to=restricted_to,
        )

    def register_system(self, server: SystemServer) -> None:
        restricted_raw = getattr(server, "restricted_to", None)
        restricted = (
            frozenset(restricted_raw) if restricted_raw is not None else None
        )
        for tdef in server.list_tools():
            full = f"{server.name}__{tdef.name}"
            spec = {
                "name": full,
                "description": tdef.description,
                "input_schema": tdef.input_schema,
            }
            self.register(
                full,
                spec,
                tdef.handler,
                source=f"system:{server.name}",
                restricted_to=restricted,
            )

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def all_specs(self) -> list[dict[str, Any]]:
        return [dict(t.spec) for t in self._tools.values()]

    def all_names(self) -> list[str]:
        return list(self._tools.keys())

    def names_for(self, persona: str) -> list[str]:
        return [
            n
            for n, t in self._tools.items()
            if t.restricted_to is None or persona in t.restricted_to
        ]

    def dispatch(
        self,
        name: str,
        deps: Any,
        args: dict[str, Any],
        persona: str,
    ) -> Any:
        tool = self._tools.get(name)
        if tool is None:
            raise KeyError(f"unknown tool {name!r}")
        if tool.restricted_to is not None and persona not in tool.restricted_to:
            raise PermissionError(
                f"tool {name!r} is not visible to persona {persona!r}"
            )
        token = active_persona.set(persona)
        try:
            return tool.func(deps, **(args or {}))
        finally:
            active_persona.reset(token)
