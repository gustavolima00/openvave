"""The ``openvave`` MCP server: tools and resources over a :class:`PedalHolder`
(spec 006, contracts/tools.md).

Every tool calls an existing library operation and returns the CLI's ``--json`` document for it
plus a ``summary``; library errors become tool errors (:mod:`openvave.mcp_server.errors`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from openvave import __version__
from openvave.cli import render
from openvave.mcp_server.errors import tool_errors
from openvave.mcp_server.holder import PedalHolder
from openvave.mcp_server.results import with_summary

INSTRUCTIONS = (
    "Reads and controls an M-VAVE Tank-G guitar pedal over Bluetooth (unofficial openvave). "
    "The server holds one connection: the pedal accepts only one, so while it is held the "
    "M-VAVE phone app cannot connect; call pedal_disconnect to hand it over (it is also "
    "released after a few idle minutes, and the next pedal tool reconnects). Write tools take "
    "the command line's opt-ins as arguments: dry_run (plan only, nothing sent), experimental "
    "(messages not yet confirmed on hardware, untested firmware), discard_edits (lose unsaved "
    "edits), and unsafe (preset_save / preset_restore: overwrite stored presets, after an "
    "automatic backup). Ask the owner before passing unsafe or discard_edits. Edits to the "
    "current sound are never saved unless preset_save is called."
)


@dataclass(frozen=True)
class ToolSpec:
    """One row of the contract's tool table."""

    writes: bool
    read_only: bool
    destructive: bool
    idempotent: bool

    def annotations(self) -> ToolAnnotations:
        return ToolAnnotations(
            read_only_hint=self.read_only,
            destructive_hint=self.destructive,
            idempotent_hint=self.idempotent,
            open_world_hint=False,
        )


TOOLS: dict[str, ToolSpec] = {
    "pedal_status": ToolSpec(writes=False, read_only=True, destructive=False, idempotent=True),
    "pedal_disconnect": ToolSpec(writes=False, read_only=False, destructive=False, idempotent=True),
    "pedal_info": ToolSpec(writes=False, read_only=True, destructive=False, idempotent=True),
}
"""Every tool, its annotations and whether ``--read-only`` hides it (contracts/tools.md)."""


def build_server(holder: PedalHolder) -> MCPServer:
    """The MCP server for ``holder`` (tools of every milestone so far)."""
    server: MCPServer = MCPServer(
        "openvave",
        title="openvave (M-VAVE Tank-G)",
        instructions=INSTRUCTIONS,
        version=__version__,
    )

    def record(error: str) -> None:
        holder.last_error = error

    @server.tool(annotations=TOOLS["pedal_status"].annotations())
    async def pedal_status() -> dict[str, Any]:
        """Whether the server holds the pedal connection, which pedal, its firmware, the last
        error and the server options. Sends nothing to the pedal and never connects."""
        status = holder.status()
        if status["connected"]:
            pedal = status["pedal"] or {}
            name = pedal.get("nickname") or pedal.get("identifier") or "pedal"
            summary = f"connected to {name} (firmware {status['firmware']})"
        else:
            summary = "not connected; the next pedal tool connects"
        return {"summary": summary, **status}

    @server.tool(annotations=TOOLS["pedal_disconnect"].annotations())
    async def pedal_disconnect() -> dict[str, Any]:
        """Close the pedal connection so the M-VAVE phone app (or the openvave command line)
        can use the pedal. Harmless when not connected; the next pedal tool reconnects."""
        with tool_errors(record):
            was = await holder.disconnect()
        summary = (
            "disconnected; the pedal is free for the phone app"
            if was
            else "was not connected; the pedal is free"
        )
        return {"summary": summary, "was_connected": was}

    @server.tool(annotations=TOOLS["pedal_info"].annotations())
    async def pedal_info() -> dict[str, Any]:
        """Identify the pedal (name, firmware), its state (normal / edit / bypass / tuner,
        loaded preset) and its decoded device info, global settings and status regions.
        Read-only. Connects on first use."""
        with tool_errors(record):
            async with holder.use() as pedal:
                snapshot = await pedal.snapshot()
        return with_summary(render.info_json(snapshot), _info_summary(snapshot))

    return server


def _info_summary(snapshot: Any) -> str:
    identity = snapshot.identity
    state = render.state_text(snapshot.pedal_state) if snapshot.pedal_state else "state unknown"
    untested = " (untested firmware)" if identity.firmware_untested else ""
    return f"{identity.name}, firmware {identity.firmware}{untested}, {state}"


__all__ = ["INSTRUCTIONS", "TOOLS", "ToolSpec", "build_server"]
