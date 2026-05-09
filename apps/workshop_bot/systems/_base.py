"""SystemServer protocol + ToolDef dataclass.

A system module exposes a ``SystemServer`` whose ``list_tools()``
returns ``ToolDef`` records. The registry in ``tools/agent_tools.py``
prefixes each tool's action name with the server's namespace
(``buttondown__list_subscribers`` etc.) when registering.

The shape mirrors MCP's ``list_tools`` so a single server can be lifted
to a real MCP server later by adding a transport adapter.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol


@dataclass(frozen=True)
class ToolDef:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[..., Any]


class SystemServer(Protocol):
    name: str

    def list_tools(self) -> list[ToolDef]: ...
