"""External-system tool servers.

Each subpackage (``buttondown``, ``pinboard``, ``stripe``,
``tinylytics``) implements a ``SystemServer`` exposing ``list_tools``
plus per-tool handler dispatch. The shape mirrors MCP so a server can
be lifted to a real MCP server later by adding a transport adapter,
but no MCP SDK is used today — these run in-process.

The shared protocol + ``ToolDef`` dataclass live in ``_base``.
"""
