"""MCP server for openvave (spec 006): ``openvave mcp``.

Imported only by ``openvave mcp``; needs the optional ``mcp`` extra
(``pip install 'openvave[mcp]'``). The library and the rest of the command line never import
it. The server is a thin front end over the public library, like the command line: see
``specs/006-mcp-server/contracts/tools.md``.
"""

from __future__ import annotations

import asyncio
from typing import Any

from mcp.server.mcpserver import MCPServer

from openvave.mcp_server.holder import PedalHolder, ServerOptions, Sleep, TransportFactory
from openvave.mcp_server.server import TOOLS, build_server


def create(
    options: ServerOptions,
    factory: TransportFactory,
    *,
    sleep: Sleep = asyncio.sleep,
    poll_sleep: Sleep = asyncio.sleep,
    scanner_factory: Any = None,
) -> tuple[MCPServer, PedalHolder]:
    """A server and its holder (in-process use and tests). ``scanner_factory`` replaces
    ``BleakScanner`` for the scan and select tools; the sleeps are injectable for tests."""
    holder = PedalHolder(
        options, factory, sleep=sleep, poll_sleep=poll_sleep, scanner_factory=scanner_factory
    )
    return build_server(holder), holder


async def serve(
    options: ServerOptions, factory: TransportFactory, scanner_factory: Any = None
) -> int:
    """Run over stdio until the client closes stdin; the pedal is released on exit."""
    server, holder = create(options, factory, scanner_factory=scanner_factory)
    try:
        await server.run_stdio_async()
    finally:
        await holder.shutdown()
    return 0


__all__ = ["TOOLS", "PedalHolder", "ServerOptions", "create", "serve"]
