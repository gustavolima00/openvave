"""The ``openvave`` MCP server: tools and resources over a :class:`PedalHolder`
(spec 006, contracts/tools.md).

Every tool calls an existing library operation and returns the CLI's ``--json`` document for it
plus a ``summary``; library errors become tool errors (:mod:`openvave.mcp_server.errors`).
"""

from __future__ import annotations

import contextlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from openvave import __version__
from openvave.cli import choice, files, pedals, render
from openvave.devices import KnownDevices, Target, check_nickname, is_identifier
from openvave.errors import ConfigError
from openvave.mcp_server import backups, resources
from openvave.mcp_server.errors import InvalidValue, tool_errors
from openvave.mcp_server.holder import PedalHolder
from openvave.mcp_server.results import add_knob_types, change_json, change_label, with_summary
from openvave.mcp_server.sequences import register_sequences
from openvave.mcp_server.writes import parse_preset_position, register_writes
from openvave.models import ByteChange, DeviceInfo, PedalState, Region, RegionRead
from openvave.protocol import classify, diff
from openvave.protocol.storage import position as position_of
from openvave.session import TankG

logger = logging.getLogger("openvave.mcp")

INSTRUCTIONS = (
    "Reads and controls an M-VAVE Tank-G guitar pedal over Bluetooth (unofficial openvave). "
    "The server holds one connection: the pedal accepts only one, so while it is held the "
    "M-VAVE phone app cannot connect; call pedal_disconnect to hand it over (it is also "
    "released after a few idle minutes, and the next pedal tool reconnects). Write tools take "
    "the command line's opt-ins as arguments: dry_run (plan only, nothing sent), experimental "
    "(messages not yet confirmed on hardware, untested firmware), discard_edits (lose unsaved "
    "edits), and unsafe (preset_save / restore / copy / swap / import: overwrite stored presets, "
    "after an "
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
    "pedal_scan": ToolSpec(writes=False, read_only=True, destructive=False, idempotent=True),
    "pedal_select": ToolSpec(writes=False, read_only=False, destructive=False, idempotent=True),
    "pedal_info": ToolSpec(writes=False, read_only=True, destructive=False, idempotent=True),
    "preset_read": ToolSpec(writes=False, read_only=True, destructive=False, idempotent=True),
    "pedal_changes": ToolSpec(writes=False, read_only=True, destructive=False, idempotent=False),
    "preset_backup": ToolSpec(writes=False, read_only=False, destructive=False, idempotent=False),
    "backups_list": ToolSpec(writes=False, read_only=True, destructive=False, idempotent=True),
    "pedal_set": ToolSpec(writes=True, read_only=False, destructive=False, idempotent=True),
    "preset_select": ToolSpec(writes=True, read_only=False, destructive=False, idempotent=True),
    "preset_reload": ToolSpec(writes=True, read_only=False, destructive=False, idempotent=True),
    "bypass_on": ToolSpec(writes=True, read_only=False, destructive=False, idempotent=True),
    "bypass_off": ToolSpec(writes=True, read_only=False, destructive=False, idempotent=True),
    "loopback": ToolSpec(writes=True, read_only=False, destructive=False, idempotent=True),
    "preset_save": ToolSpec(writes=True, read_only=False, destructive=True, idempotent=False),
    "preset_restore": ToolSpec(writes=True, read_only=False, destructive=True, idempotent=False),
    # spec 007 US5
    "preset_export": ToolSpec(writes=False, read_only=False, destructive=False, idempotent=False),
    "preset_copy": ToolSpec(writes=True, read_only=False, destructive=True, idempotent=False),
    "preset_swap": ToolSpec(writes=True, read_only=False, destructive=True, idempotent=False),
    "preset_import": ToolSpec(writes=True, read_only=False, destructive=True, idempotent=False),
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

    @server.tool(annotations=TOOLS["preset_read"].annotations())
    async def preset_read(region: str = "current") -> dict[str, Any]:
        """Read and decode one region. region="current" (default): the current sound, every
        field with name, display, raw value and confidence (typed knobs MOD FX / DLY MIX /
        RVB DECAY also carry knob_type and knob_position), plus the pedal state; in bypass or
        tuner mode the state says the fields do not apply. "global": loaded bank / slot and
        mode. "status": the loopback flag. Read-only."""
        with tool_errors(record):
            wanted = READ_REGIONS.get(region)
            if wanted is None:
                raise InvalidValue(f"unknown region {region!r}; regions: {', '.join(READ_REGIONS)}")
            async with holder.use() as pedal:
                state = await pedal.state()
                read = await pedal.read(wanted)
                identity, device = pedal.identity, pedal.device
        holder.baseline = {**(holder.baseline or {}), wanted: read}
        now = datetime.now(UTC)
        if wanted is Region.CURRENT_PRESET:
            document = render.preset_json(read, now, device, identity)
            document["pedal_state"] = state.label
            add_knob_types(document["preset"])
            summary = _preset_summary(state, len(document["preset"]["fields"]))
            return {"summary": summary, **document}
        document = render.envelope("preset read", now, device, identity)
        document["pedal_state"] = state.label
        document["region"] = render.region_json(read, identity.firmware)
        return {"summary": _region_summary(read, identity.firmware), **document}

    @server.tool(annotations=TOOLS["pedal_changes"].annotations())
    async def pedal_changes(wait_seconds: float = 0) -> dict[str, Any]:
        """What changed on the pedal since the last read (knobs turned, preset changed, bypass):
        each changed field with its name and value before / after, and the state before /
        after. The first call only takes the baseline. With wait_seconds (0-30) it polls every
        0.5 s until something changes or the wait ends; the pedal is busy meanwhile.
        Read-only."""
        with tool_errors(record):
            if not 0 <= wait_seconds <= MAX_WAIT:
                raise InvalidValue(
                    f"wait_seconds must be 0–{MAX_WAIT:g} seconds, got {wait_seconds:g}"
                )
            async with holder.use() as pedal:
                previous = holder.baseline
                reads = await _read_changes(pedal)
                base = reads if previous is None else {**reads, **previous}
                changes = _changes(base, reads)
                waited = 0.0
                while not changes and wait_seconds - waited > 1e-9:
                    step = min(POLL_STEP, wait_seconds - waited)
                    await holder.poll_sleep(step)
                    waited += step
                    reads = await _read_changes(pedal)
                    changes = _changes(base, reads)
            holder.baseline = reads
        before, after = _state_label(base), _state_label(reads)
        return {
            "summary": _changes_summary(previous is None, changes, before, after, waited),
            "baseline": previous is None,
            "changed": bool(changes),
            "waited": round(waited, 3),
            "state_before": before,
            "state_after": after,
            "changes": [change_json(c) for c in changes],
        }

    @server.tool(annotations=TOOLS["pedal_scan"].annotations())
    async def pedal_scan(include_all: bool = False) -> dict[str, Any]:
        """List the Tank-G pedals in range (identifier, name, signal strength, nickname, whether
        it is the default) without connecting to any. A pedal this server is connected to does
        not advertise; it is listed with connected: true. include_all also lists other
        Bluetooth devices."""
        from openvave.transport import ble

        with tool_errors(record):
            known = _known_or_none()
            async with holder.exclusive():
                scanned_at = datetime.now(UTC)
                entries = await ble.scan(
                    holder.options.scan_timeout,
                    include_all=include_all,
                    known=known,
                    scanner_factory=holder.scanner_factory,
                )
                held = holder.device if holder.connected else None
        document = render.scan_json(
            entries, known, scanned_at=scanned_at, scan_seconds=holder.options.scan_timeout
        )
        _mark_connected(document, held, known)
        return {"summary": _scan_summary(document), **document}

    @server.tool(annotations=TOOLS["pedal_select"].annotations())
    async def pedal_select(
        target: str, remember: bool = False, nickname: str | None = None
    ) -> dict[str, Any]:
        """Choose the pedal this server uses: target is a known nickname, a full identifier,
        or an identifier prefix of at least 4 hex digits matching one pedal in range (as
        openvave select). A held connection to another pedal is closed first. For this server
        session only, unless remember: true, which also saves it as the default pedal for the
        command line and later sessions (nickname: give it this nickname; needs remember)."""
        with tool_errors(record):
            if nickname is not None and not remember:
                raise InvalidValue("a nickname is saved only with remember: true")
            if nickname is not None:
                check_nickname(nickname)
            try:
                known: KnownDevices | None = KnownDevices.load()
            except ConfigError:
                if remember or not is_identifier(target):
                    raise
                known = None
            async with holder.exclusive():
                identifier, name, rssi = await pedals.resolve_selection(
                    target, known, holder.options.scan_timeout, holder.scanner_factory
                )
                document: dict[str, Any] | None = None
                if remember:
                    assert known is not None
                    previous = known.default
                    updated = known.select(identifier, nickname, name=name)
                    updated.save()
                    known = updated
                    document = render.device_document(
                        "select", updated, rssi=rssi, previous_default=previous
                    )
                chosen = nickname or choice.nickname_of(identifier, known)
                await holder.choose(Target(identifier, chosen, "device_option"))
        label = f"{chosen} ({identifier})" if chosen else identifier
        if document is not None:
            summary = f"{label} is now the default pedal and is used by this server"
            return {"summary": summary, **document, "remembered": True}
        return {
            "summary": f"{label} is used by this server for this session (default unchanged)",
            "session_choice": {
                "identifier": identifier,
                "nickname": chosen,
                "name": name,
                "rssi": rssi,
            },
            "remembered": False,
        }

    @server.tool(annotations=TOOLS["preset_backup"].annotations())
    async def preset_backup() -> dict[str, Any]:
        """Back up all 36 stored presets: read, verified against a whole-image read, and
        written to a new file in the backup folder (never overwriting). Sends only reads to
        the pedal. The file name can be given to preset_restore later (preset_export saves a
        single preset for preset_import)."""
        with tool_errors(record):
            folder = backups.ensure_dir(holder.options.backup_dir)
            async with holder.use() as pedal:
                backup = await pedal.backup()
                device = pedal.device
            if "unexpected_header" in backup.warnings:
                logger.warning(
                    "unexpected stored-image header %s (expected a5 5a); the backup is saved, "
                    "but the layout may differ",
                    backup.header.hex(" "),
                )
            document = backup.to_document()
            path = _write_new_backup(folder, document)
        result = render.backup_json(backup, document, device, str(path))
        result["path"] = str(path)
        first = render.human_backup(backup, str(path)).splitlines()[0]
        summary = " ".join(first.split()) + f"; saved {path.name}"
        return {"summary": summary, **result}

    @server.tool(annotations=TOOLS["preset_export"].annotations())
    async def preset_export(position: str | int) -> dict[str, Any]:
        """Save one stored preset (1A-9D or 0-35) to a new preset file in the backup folder
        (never overwriting). Sends only reads to the pedal. The file name can be given to
        preset_import later, to put this sound into any slot."""
        with tool_errors(record):
            index = parse_preset_position(position, "position")
            folder = backups.ensure_dir(holder.options.backup_dir)
            async with holder.use() as pedal:
                exported = await pedal.export_preset(index)
            document = exported.to_document()
            where = position_of(index)
            path = backups.preset_file_path(folder, where, datetime.now())
            files.write_json_atomic(path, document, force=False)
        return {
            "summary": f"exported {where}: {document['raw']}; saved {path.name}",
            "path": str(path),
            **document,
        }

    @server.tool(annotations=TOOLS["backups_list"].annotations())
    async def backups_list() -> dict[str, Any]:
        """The backup files in the backup folder, newest first: name, time, firmware, preset
        count, and whether it passes the restore checks (problems listed). No pedal needed."""
        with tool_errors(record):
            folder = holder.options.backup_dir
            rows = backups.list_backups(folder)
        restorable = sum(1 for row in rows if row["restorable"])
        count = f"{len(rows)} backup{'' if len(rows) == 1 else 's'}" if rows else "no backups"
        summary = f"{count} in {folder}" + (f" ({restorable} restorable)" if rows else "")
        return {"summary": summary, "folder": str(folder), "backups": rows}

    register_writes(server, holder, lambda name: TOOLS[name].annotations(), record)
    register_sequences(server, holder, lambda name: TOOLS[name].annotations(), record)
    if holder.options.read_only:
        # --read-only: the write tools are neither listed nor callable (FR-010)
        for name, spec in TOOLS.items():
            if spec.writes:
                with contextlib.suppress(ToolError):
                    server.remove_tool(name)
    _resources(server)
    return server


READ_REGIONS = {
    "current": Region.CURRENT_PRESET,
    "global": Region.GLOBAL,
    "status": Region.STATUS,
}
"""``preset_read`` regions (the device info region is in ``pedal_info``)."""

CHANGE_REGIONS = (Region.GLOBAL, Region.CURRENT_PRESET, Region.STATUS)
MAX_WAIT = 30.0
"""Longest ``pedal_changes`` wait (FR-024): a call cannot hold the pedal longer."""
POLL_STEP = 0.5


async def _read_changes(pedal: TankG) -> dict[Region, RegionRead]:
    return {region: await pedal.read(region) for region in CHANGE_REGIONS}


def _changes(base: dict[Region, RegionRead], reads: dict[Region, RegionRead]) -> list[ByteChange]:
    return [change for region in CHANGE_REGIONS for change in diff(base[region], reads[region])]


def _state(reads: dict[Region, RegionRead]) -> PedalState:
    return classify(reads[Region.GLOBAL].data, reads[Region.CURRENT_PRESET].data)


def _state_label(reads: dict[Region, RegionRead]) -> str:
    return _state(reads).label


def _changes_summary(
    first: bool, changes: list[ByteChange], before: str, after: str, waited: float
) -> str:
    if not changes:
        if first and waited == 0:
            return f"baseline taken (state: {after}); call again to see what changed"
        return "no change" + (f" within {waited:g} s" if waited else "") + f" (state: {after})"
    parts = [] if before == after else [f"state {before} → {after}"]
    for change in changes:
        item = change_json(change)
        parts.append(f"{change_label(change)} {item['display_before']} → {item['display_after']}")
    return "; ".join(parts)


def _preset_summary(state: PedalState, count: int) -> str:
    if state.kind == "bypass" and not state.transient:
        return render.BYPASS_STATE.removeprefix("state: ") + "; the preset fields do not apply"
    if state.kind == "tuner":
        return "tuner mode; the preset fields do not apply until the tuner is closed"
    return f"current preset: {render.state_text(state)}; {count} fields decoded"


def _region_summary(read: RegionRead, firmware: int) -> str:
    fields = render.region_json(read, firmware)["fields"]
    values = ", ".join(f"{f['name']} {f['display']}" for f in fields)
    return f"{render.REGION_TITLES[read.region]}: {values}"


def _known_or_none() -> KnownDevices | None:
    try:
        return KnownDevices.load()
    except ConfigError as err:
        logger.warning("%s (nicknames unavailable)", err)
        return None


def _mark_connected(
    document: dict[str, Any], held: DeviceInfo | None, known: KnownDevices | None
) -> None:
    """Every row gets ``connected``; a held pedal (it does not advertise) is added if missing."""
    match = held.identifier.casefold() if held is not None else None
    for row in document["devices"]:
        row["connected"] = match is not None and row["identifier"].casefold() == match
    if held is None or any(row["connected"] for row in document["devices"]):
        return
    entry = known.find(held.identifier) if known is not None else None
    if entry is not None and entry.identifier.casefold() != match:
        entry = None
    default = known.default_identifier if known is not None else None
    document["devices"].append(
        {
            "identifier": held.identifier,
            "name": held.name,
            "rssi": held.rssi,
            "tank_g": True,
            "nickname": held.nickname,
            "known": entry is not None,
            "selected": default is not None and default.casefold() == match,
            "connected": True,
        }
    )


def _scan_summary(document: dict[str, Any]) -> str:
    rows = [row for row in document["devices"] if row["tank_g"]]
    if not rows:
        return (
            "no Tank-G found: switch the pedal on and close the M-VAVE phone app (a pedal "
            "connected to the app or another program stops advertising)"
        )
    names = [row["nickname"] or row["identifier"] for row in rows]
    count = f"{len(rows)} {'pedal' if len(rows) == 1 else 'pedals'} found: {', '.join(names)}"
    default = next((row for row in rows if row["selected"]), None)
    if default is not None:
        count += f" (default: {default['nickname'] or default['identifier']})"
    return count


def _write_new_backup(folder: Path, document: dict[str, Any]) -> Path:
    """Write ``document`` to a new manual backup file in ``folder``; never overwrites."""
    while True:
        path = backups.manual_backup_path(folder, datetime.now())
        try:
            files.write_json_atomic(path, document, force=False)
        except files.TargetExistsError:
            continue  # taken between the check and the write: next name
        return path


def _resources(server: MCPServer) -> None:
    def dump(document: dict[str, Any]) -> str:
        return json.dumps(document, indent=2, ensure_ascii=False)

    @server.resource(
        "openvave://fields",
        name="fields",
        description="Every field pedal_set accepts: value syntax, range, typed-knob types and "
        "positions, and whether it needs experimental: true.",
        mime_type="application/json",
    )
    def fields() -> str:
        return dump(resources.fields_document())

    @server.resource(
        "openvave://effect-types",
        name="effect-types",
        description="Types of the MOD FX, DLY MIX and RVB DECAY knobs and the raw values of each.",
        mime_type="application/json",
    )
    def effect_types() -> str:
        return dump(resources.effect_types_document())

    @server.resource(
        "openvave://byte-map",
        name="byte-map",
        description="What every byte of the global, current preset and status regions means "
        "(offset, name, encoding, range, confidence).",
        mime_type="application/json",
    )
    def byte_map() -> str:
        return dump(resources.byte_map_document())

    @server.resource(
        "openvave://safety",
        name="safety",
        description="Volatile vs persistent writes, the opt-ins, what openvave never sends, "
        "and the one-connection rule.",
        mime_type="text/markdown",
    )
    def safety() -> str:
        return resources.SAFETY


def _info_summary(snapshot: Any) -> str:
    identity = snapshot.identity
    state = render.state_text(snapshot.pedal_state) if snapshot.pedal_state else "state unknown"
    untested = " (untested firmware)" if identity.firmware_untested else ""
    return f"{identity.name}, firmware {identity.firmware}{untested}, {state}"


__all__ = ["INSTRUCTIONS", "TOOLS", "ToolSpec", "build_server"]
