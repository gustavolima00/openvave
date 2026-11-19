"""``openvave mcp``: run the MCP server over stdio (spec 006, contracts/tools.md §Command).

This module needs no MCP package: it parses the options and imports
:mod:`openvave.mcp_server` (which needs the ``mcp`` extra) only when the server starts.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

INSTALL_HINT = "error: the MCP server needs the 'mcp' extra: pip install 'openvave[mcp]'"


def default_backup_dir() -> Path:
    """The per-user backup folder (spec 006 research R10), shared with the command line's
    automatic backups (:func:`openvave.cli.files.default_backup_dir`): ``$OPENVAVE_BACKUP_DIR``,
    else ``$XDG_DATA_HOME/openvave/backups``, else ``%LOCALAPPDATA%\\openvave\\backups`` on
    Windows, else ``~/.local/share/openvave/backups``."""
    from openvave.cli.files import default_backup_dir as shared

    return shared()


def _non_negative(text: str) -> float:
    try:
        value = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a number: {text!r}") from None
    if value < 0:
        raise argparse.ArgumentTypeError(f"must be 0 or more, got {text}")
    return value


def add_parser(sub: Any, common: argparse.ArgumentParser) -> None:
    parser = sub.add_parser(
        "mcp",
        parents=[common],
        help="run an MCP server on stdin/stdout for AI assistants (needs the 'mcp' extra)",
        description="Runs a Model Context Protocol server over stdio, for AI assistants such as "
        "Claude Desktop or Claude Code. It holds one pedal connection between tool calls and "
        "releases it after --idle-release seconds. Every capability of the command line is "
        "available; write tools take --dry-run / --experimental / --discard-edits / --unsafe "
        "as arguments. See docs/mcp.md.",
    )
    parser.add_argument(
        "--read-only",
        action="store_true",
        help="offer no tool that writes to the pedal",
    )
    parser.add_argument(
        "--backup-dir",
        metavar="DIR",
        type=Path,
        default=None,
        help="folder for backups and the files restore may read (default "
        "$XDG_DATA_HOME/openvave/backups or ~/.local/share/openvave/backups)",
    )
    parser.add_argument(
        "--idle-release",
        metavar="SECONDS",
        type=_non_negative,
        default=300.0,
        help="release the pedal after this many idle seconds (default 300; 0 never)",
    )


def run(args: argparse.Namespace, transport_factory: Any, scanner_factory: Any = None) -> int:
    """Start the server; exit 2 without the ``mcp`` extra. ``scanner_factory`` replaces
    ``BleakScanner`` (tests)."""
    try:
        import openvave.mcp_server as mcp_server
    except ImportError as err:
        if (err.name or "").split(".")[0] != "mcp":
            raise
        print(INSTALL_HINT, file=sys.stderr)
        return 2
    import asyncio

    options = mcp_server.ServerOptions(
        backup_dir=args.backup_dir or default_backup_dir(),
        device=args.device,
        read_only=args.read_only,
        idle_release=args.idle_release,
        scan_timeout=args.scan_timeout,
        timeout=args.timeout,
        trace=args.trace,
    )
    return asyncio.run(mcp_server.serve(options, transport_factory, scanner_factory))


__all__ = ["INSTALL_HINT", "add_parser", "default_backup_dir", "run"]
