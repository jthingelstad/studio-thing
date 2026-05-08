"""External-system tool servers.

Each subpackage (e.g. ``buttondown``, ``pinboard``, ``tinylytics``,
``stripe``) implements a ``SystemServer`` exposing ``list_tools`` plus
per-tool handler dispatch. The shape mirrors MCP so a server can be
lifted to a real MCP server later by adding a transport adapter, but
no MCP SDK is used today — these run in-process.

Phase 0 ships only the protocol/dataclass contract in ``_base``; the
concrete system modules land in phases 1–3 of the workshop-bot
redesign.
"""
