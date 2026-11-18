"""Human and JSON renderers for CLI output (contracts/cli.md, contracts/*.schema.json)."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from openvave._jsonform import field_json, hex_bytes, identity_json
from openvave.models import (
    Backup,
    ByteChange,
    DecodedField,
    DecodedRegion,
    DeviceIdentity,
    DeviceInfo,
    DeviceSnapshot,
    Encoding,
    PedalState,
    Region,
    RegionRead,
    WatchChange,
    WatchStart,
    WritePlan,
    WriteResult,
)
from openvave.protocol.bytemap import TYPED_FIELDS, type_parts
from openvave.protocol.decode import decode_field, decode_region
from openvave.protocol.state import classify
from openvave.protocol.storage import EXPECTED_HEADER, position
from openvave.protocol.writes import WRITABLE_FIELDS

SCHEMA_VERSION = 2
"""JSON contract version; 2 since 0.2.0 (field renames, CHANGELOG)."""
LABEL_WIDTH = 11
REGION_LABEL_WIDTH = 14
REGION_SPEC_WIDTH = 32
BYTES_PER_LINE = 16
FIELD_INDENT = "      "
FIELD_OFFSET_WIDTH = 5
FIELD_LABEL_WIDTH = 25
FIELD_DISPLAY_WIDTH = 6
FIELD_RANGE_WIDTH = 11

REGION_TITLES = {
    Region.DEVICE_INFO: "Device info",
    Region.GLOBAL: "Global",
    Region.CURRENT_PRESET: "Current preset",
    Region.STATUS: "Status",
}
INFO_HUMAN_REGIONS = (Region.DEVICE_INFO, Region.GLOBAL, Region.STATUS)
"""Regions ``info`` prints for humans; the current preset is shown only by ``preset dump``."""


def _device_line(device: DeviceInfo) -> str:
    extra = device.name
    if device.rssi is not None:
        extra += f", {device.rssi} dBm"
    return f"{'Address':<{LABEL_WIDTH}}{device.identifier}  ({extra})"


def human_identity(identity: DeviceIdentity, device: DeviceInfo | None) -> str:
    """``Device     TANK-Gv2  (firmware 96)`` plus an address line when a device is known."""
    lines = [f"{'Device':<{LABEL_WIDTH}}{identity.name}  (firmware {identity.firmware})"]
    if device is not None:
        lines.append(_device_line(device))
    return "\n".join(lines)


def hex_dump(data: bytes, indent: str = "  ") -> list[str]:
    """16 bytes per line, each prefixed with its hex offset (``00:``, ``10:``, …)."""
    return [
        f"{indent}{i:02x}: {hex_bytes(data[i : i + BYTES_PER_LINE])}"
        for i in range(0, len(data), BYTES_PER_LINE)
    ]


def region_spec(region: Region) -> str:
    """``type 4 @ 0x20000000, 4 bytes`` (address upper-case for humans)."""
    unit = "byte" if region.length == 1 else "bytes"
    return f"type {region.type} @ 0x{region.address:08X}, {region.length} {unit}"


def _offset_cell(field: DecodedField) -> str:
    entry = field.entry
    text = f"[{entry.offset}]" if entry.mask is None else f"[{entry.offset}.0x{entry.mask:02x}]"
    return f"{text:<{FIELD_OFFSET_WIDTH}}" if len(text) < FIELD_OFFSET_WIDTH else text + " "


def _range_cell(field: DecodedField) -> str:
    entry = field.entry
    if entry.encoding is Encoding.SELECTOR:
        return "selector"
    if entry.encoding is Encoding.SWITCH:
        return "on/off"
    if entry.encoding is Encoding.FLAG:
        return "flag"
    return f"{entry.min}–{entry.max}"


def type_reading(field: DecodedField) -> str | None:
    """Type and position of a typed knob, for human output only (JSON keeps the raw value).

    ``room 6``, ``spring 10``, or ``off`` between two types (manual: the module is off there).
    Only fields in ``TYPED_FIELDS`` have one (command-layer.md "Reverb decay sections");
    ``None`` for every other field and out of range.
    """
    name = field.entry.name
    if name is None or name not in TYPED_FIELDS or field.out_of_range:
        return None
    type_name, position = type_parts(name, field.value)
    return "off" if type_name is None else f"{type_name} {position}"


def field_line(field: DecodedField, indent: str = FIELD_INDENT) -> str:
    """``[15] reverb decay   5   0–127   observed`` (contracts/cli.md column layout)."""
    entry = field.entry
    line = (
        f"{indent}{_offset_cell(field)}{entry.label:<{FIELD_LABEL_WIDTH}} "
        f"{field.display:>{FIELD_DISPLAY_WIDTH}}    "
        f"{_range_cell(field):<{FIELD_RANGE_WIDTH}}{entry.confidence}"
    )
    if entry.confidence == "hypothesis":
        line += " ?"
    if field.out_of_range:
        line += "  OUT OF RANGE"
    reading = type_reading(field)
    if reading is not None:
        line += f"  type: {reading}"
    return line


def field_lines(decoded: DecodedRegion, indent: str = FIELD_INDENT) -> list[str]:
    """One line per named field, then ``unknown: …`` listing the unknown offsets."""
    lines = [field_line(f, indent) for f in decoded.fields]
    if decoded.unknown_offsets:
        lines.append(f"{indent}unknown: " + " ".join(str(o) for o in decoded.unknown_offsets))
    return lines


def _map_note(decoded: DecodedRegion) -> str:
    return (
        f"  (decoded with the fw {decoded.map_firmware} map)" if decoded.firmware_untested else ""
    )


def human_region(read: RegionRead, firmware: int) -> str:
    """Header, hex dump and decoded-field lines for one region (device info stays undecoded)."""
    region = read.region
    header = (
        f"{REGION_TITLES[region]:<{REGION_LABEL_WIDTH}}"
        f"{region_spec(region):<{REGION_SPEC_WIDTH}}[meaning: unknown]"
    )
    if region is Region.DEVICE_INFO:
        return "\n".join([header, *hex_dump(read.data)])
    decoded = decode_region(read, firmware)
    return "\n".join([header + _map_note(decoded), *hex_dump(read.data), *field_lines(decoded)])


BYPASS_STATE = "state: bypass (all blocks off; the pedal does not report the loaded slot)"


def state_text(state: PedalState) -> str:
    """``normal, preset 1B`` / ``bypass`` / ``loading`` / ``tuner`` / ``unrecognised``."""
    if state.kind in ("normal", "edit") and state.position is not None:
        return f"{state.label}, preset {state.position}"
    return state.label


def state_lines(state: PedalState | None) -> list[str]:
    """The ``state:`` line of ``info`` / ``preset dump`` (spec 004 R13), plus the bank in bypass."""
    if state is None:
        return []
    if state.kind == "bypass" and not state.transient:
        bank = "?" if state.bank is None else str(state.bank + 1)
        return [BYPASS_STATE, f"bank {bank}, slot not reported"]
    return [f"state: {state_text(state)}"]


def human_info(snapshot: DeviceSnapshot) -> str:
    """Identity block and state line, a blank line, then device info / global / status blocks."""
    firmware = snapshot.identity.firmware
    blocks = [human_region(snapshot.regions[r], firmware) for r in INFO_HUMAN_REGIONS]
    head = [human_identity(snapshot.identity, snapshot.device), *state_lines(snapshot.pedal_state)]
    return "\n".join(head) + "\n\n" + "\n".join(blocks)


def human_preset(
    read: RegionRead, identity: DeviceIdentity, state: PedalState | None = None
) -> str:
    """``Current preset  (TANK-Gv2, firmware 96)   type 4 @ …``, the state line, hex dump and
    known fields. In bypass the buffer is all zero and is not the preset: no field lines."""
    decoded = decode_region(read, identity.firmware)
    header = (
        f"{REGION_TITLES[read.region]}  ({identity.name}, firmware {identity.firmware})   "
        f"{region_spec(read.region)}{_map_note(decoded)}"
    )
    fields = [] if state is not None and state.kind == "bypass" else field_lines(decoded)
    return "\n".join([header, *state_lines(state), *hex_dump(read.data), *fields])


def device_json(device: DeviceInfo | None) -> dict[str, Any] | None:
    if device is None:
        return None
    return {"identifier": device.identifier, "name": device.name, "rssi": device.rssi}


def envelope(
    command: str, read_at: datetime, device: DeviceInfo | None, identity: DeviceIdentity
) -> dict[str, Any]:
    """Fields shared by every JSON document (``schema_version``, ``command``, …)."""
    return {
        "schema_version": SCHEMA_VERSION,
        "command": command,
        "read_at": read_at.isoformat(),
        "device": device_json(device),
        "identity": identity_json(identity),
    }


def region_json(read: RegionRead, firmware: int) -> dict[str, Any]:
    region = read.region
    decoded = decode_region(read, firmware)
    return {
        "type": region.type,
        "address": f"0x{region.address:08x}",
        "length": region.length,
        "data": hex_bytes(read.data),
        "fields": [field_json(f) for f in decoded.fields],
        "map_firmware": decoded.map_firmware,
        "unknown_offsets": list(decoded.unknown_offsets),
    }


def info_json(snapshot: DeviceSnapshot) -> dict[str, Any]:
    """The ``openvave info --json`` document (``contracts/info.schema.json``)."""
    document = envelope("info", snapshot.read_at, snapshot.device, snapshot.identity)
    if snapshot.pedal_state is not None:
        document["pedal_state"] = snapshot.pedal_state.label
    document["regions"] = {
        region.name.lower(): region_json(read, snapshot.identity.firmware)
        for region, read in snapshot.regions.items()
    }
    return document


def preset_json(
    read: RegionRead, read_at: datetime, device: DeviceInfo | None, identity: DeviceIdentity
) -> dict[str, Any]:
    """The ``openvave preset dump --json`` document (``contracts/preset-dump.schema.json``)."""
    document = envelope("preset dump", read_at, device, identity)
    document["preset"] = region_json(read, identity.firmware)
    return document


def human_backup(backup: Backup, saved_to: str) -> str:
    """Summary line, one ``  2C  <21 bytes>`` line per stored preset, cross-check, saved path."""
    identity = backup.identity
    header = (
        f"Backup of {identity.name} (firmware {identity.firmware})   "
        f"{len(backup.presets)} presets, header {hex_bytes(backup.header)}"
    )
    if "unexpected_header" in backup.warnings:
        header += f"  UNEXPECTED (expected {hex_bytes(EXPECTED_HEADER)})"
    lines = [header]
    lines += [f"  {p.position}  {hex_bytes(p.data)}" for p in backup.presets]
    lines.append("Cross-check with whole-image read: OK")
    lines.append(f"Saved {saved_to}")
    return "\n".join(lines)


def backup_json(
    backup: Backup, document: dict[str, Any], device: DeviceInfo | None, saved_to: str
) -> dict[str, Any]:
    """The ``openvave preset backup --json`` document: envelope + backup file + saved path."""
    result = envelope("preset backup", backup.created_at, device, backup.identity)
    result["backup"] = document
    result["saved_to"] = saved_to
    return result


def dumps(document: dict[str, Any]) -> str:
    return json.dumps(document, indent=2)


# -- watch (contracts/cli.md "openvave watch") ---------------------------------------------------

WATCH_REGION_KEYS = {
    Region.GLOBAL: "global",
    Region.CURRENT_PRESET: "preset",
    Region.STATUS: "status",
}
"""Short region names of watch output and session records."""
WATCH_TIME_WIDTH = 7
WATCH_LOCATION_WIDTH = 12
WATCH_NAME_WIDTH = 18
WATCH_VALUE_WIDTH = 4


def watch_header(
    start: WatchStart, interval: float, record: str | None, state: PedalState | None = None
) -> list[str]:
    """Start block: what is watched, where it is recorded, and each region's baseline bytes.

    Decoded fields are appended for global and status (``preset dump`` shows the preset's).
    The pedal state comes last (spec 004 R13).
    """
    identity = start.identity
    lines = [
        f"Watching {identity.name} (firmware {identity.firmware}), every {interval:g} s. "
        "Type a label and Enter before each step; q to quit."
    ]
    if record is not None:
        lines.append(f"Recording to {record}")
    for region, decoded in start.regions.items():
        line = f"  {WATCH_REGION_KEYS[region]:<6}  {hex_bytes(decoded.read.data)}"
        if region is not Region.CURRENT_PRESET and decoded.fields:
            line += "   " + ", ".join(f"{f.entry.label} = {f.display}" for f in decoded.fields)
        lines.append(line)
    if state is not None:
        lines.append(f"  state   {state_text(state)}")
    return lines


def watch_state_line(state: PedalState, t: float) -> str:
    """``+1.02s  state: loading`` when the pedal state changes during a watch (spec 004 R13)."""
    return f"{f'+{t:.2f}s':>{WATCH_TIME_WIDTH}}  state: {state_text(state)}"


def watch_label_line(text: str) -> str:
    return f"── label: {text} ──"


def _with_reading(field: DecodedField) -> str:
    """``5`` or, for a typed knob, ``5 (room 6)``."""
    reading = type_reading(field)
    return field.display if reading is None else f"{field.display} ({reading})"


def _change_cells(change: ByteChange) -> tuple[str, str, str]:
    """(label, old, new) in the field's display form, or raw hex for unknown/flag bytes."""
    if change.field is not None:
        return (
            change.field.label,
            _with_reading(decode_field(change.field, change.old)),
            _with_reading(decode_field(change.field, change.new)),
        )
    name = " / ".join(e.label for e in change.fields) if change.fields else "unknown"
    return name, f"0x{change.old:02x}", f"0x{change.new:02x}"


def watch_change_lines(event: WatchChange, t: float) -> list[str]:
    """``+9.51s  preset[15]  reverb decay   5 → 64``; time printed once, co-moving marked."""
    lines = []
    count = len(event.changes)
    cells = [_change_cells(change) for change in event.changes]
    # Labels longer than the column widen it for this event, so values stay aligned.
    width = max([WATCH_NAME_WIDTH, *(len(name) + 1 for name, _, _ in cells)])
    # Same for old values carrying a type reading (``5 (room 6)``): arrows stay in one column.
    value_width = max([WATCH_VALUE_WIDTH, *(len(old) for _, old, _ in cells)])
    for i, (change, (name, old, new)) in enumerate(zip(event.changes, cells, strict=True)):
        time_cell = f"+{t:.2f}s" if i == 0 else ""
        location = f"{WATCH_REGION_KEYS[change.region]}[{change.offset}]"
        line = (
            f"{time_cell:>{WATCH_TIME_WIDTH}}  {location:<{WATCH_LOCATION_WIDTH}}"
            f"{name:<{width}}{old:>{value_width}} → {new}"
        )
        if i == 0 and count > 1:
            line += f"     (co-moving: {count})"
        lines.append(line)
    return lines


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def watch_summary(t: float, changes: int, cycles: int, record: str | None) -> str:
    line = f"Stopped after {t:.1f} s: {_plural(changes, 'change')} in {_plural(cycles, 'cycle')}."
    if record is not None:
        line += f" Record: {record}"
    return line


def _watch_event(event: str, t: float, **fields: Any) -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "event": event, "t": round(t, 4), **fields}


def watch_start_json(
    start: WatchStart,
    t: float,
    interval: float,
    record: str | None,
    state: PedalState | None = None,
) -> dict[str, Any]:
    firmware = start.identity.firmware
    extra = {} if state is None else {"pedal_state": state.label}
    return _watch_event(
        "start",
        t,
        identity=identity_json(start.identity),
        interval=interval,
        record=record,
        regions={
            region.name.lower(): region_json(decoded.read, firmware)
            for region, decoded in start.regions.items()
        },
        **extra,
    )


def watch_label_json(text: str, t: float) -> dict[str, Any]:
    return _watch_event("label", t, text=text)


def watch_change_json(
    event: WatchChange, t: float, label: str | None, state: PedalState | None = None
) -> dict[str, Any]:
    extra = {} if state is None else {"pedal_state": state.label}
    return _watch_event(
        "change",
        t,
        cycle=event.cycle,
        label=label,
        changes=[
            {
                "region": c.region.name.lower(),
                "offset": c.offset,
                "old": c.old,
                "new": c.new,
                "field": c.field.name if c.field is not None else None,
            }
            for c in event.changes
        ],
        **extra,
    )


def watch_stop_json(
    t: float, reason: str, error: str | None, changes: int, cycles: int
) -> dict[str, Any]:
    return _watch_event("stop", t, reason=reason, error=error, changes=changes, cycles=cycles)


def json_line(document: dict[str, Any]) -> str:
    """One JSON Lines record (``watch --json``)."""
    return json.dumps(document, ensure_ascii=False)


# -- writes (contracts/cli.md "openvave set" / "openvave preset select") ------------------------

NOT_SAVED = "Not saved. Discard: openvave preset reload"
NOT_SAVED_EDIT = (
    "Not saved. Discard: openvave preset reload --discard-edits "
    "(or leave edit mode on the pedal without saving)"
)
MODE_NAMES = {0: "edit", 1: "normal", 2: "tuner"}
REFUSAL_TEXT = {
    "not_edit_mode": "the pedal is not in edit mode",
    "tuner_mode": "the pedal is in tuner mode",
    "bypassed": "the pedal is bypassed",
    "unrecognised_state": "the pedal reports a state openvave does not recognise",
    "type_required": "the knob sits between two types (module off); needs --type",
    "out_of_range": "value out of range",
    "untested_firmware": "firmware not covered by a confirmed write gate; needs --experimental",
    "experimental_required": "message not confirmed yet; needs --experimental",
    "edits_would_be_discarded": "unsaved edits would be discarded; needs --discard-edits",
}


def _loaded_position(glob: RegionRead, buffer: RegionRead | None = None) -> str:
    """``1B``; ``bypass (bank 1)`` when the edit buffer shows bypass (spec 004); else ``?``."""
    bank, slot = glob.data[1], glob.data[2]
    if buffer is not None:
        state = classify(glob.data, buffer.data)
        if state.kind == "bypass" and state.bank is not None:
            return f"bypass (bank {state.bank + 1})"
    if bank > 8 or slot > 3:
        return "?"
    return f"{bank + 1}{'ABCD'[slot]}"


def _field_value(plan: WritePlan, data: bytes) -> str:
    """Display form of a field value from the preset bytes ``data`` (21) or the write data."""
    spec = WRITABLE_FIELDS[plan.field or ""]
    if spec.kind == "led_colour":
        return "#" + data[spec.offset : spec.offset + 3].hex()
    assert spec.entry is not None
    return _with_reading(decode_field(spec.entry, data[spec.offset]))


def _requested(plan: WritePlan) -> bytes:
    """The edit buffer as it would be after the write (for the requested value display)."""
    buffer = bytearray(plan.before.data)
    target = plan.target
    start = target.address - 0x10000000
    buffer[start : start + len(plan.data)] = plan.data
    return bytes(buffer)


def _change_text(change: ByteChange) -> str:
    if change.region is Region.GLOBAL:
        where = f"global[{change.offset}]"
    else:
        where = f"[{change.offset}]"
    if change.field is not None:
        return (
            f"{where} {change.field.name} {_with_reading(decode_field(change.field, change.new))}"
        )
    return f"{where} {change.new}"


def _refusal_lines(plan: WritePlan) -> list[str]:
    if plan.refusal is None:
        return []
    detail = REFUSAL_TEXT.get(plan.refusal, plan.refusal)
    if plan.refusal == "experimental_required":
        detail = f"{plan.target.kind} is '{plan.confidence}'; needs --experimental"
    return [f"  refused: {plan.refusal} ({detail})"]


def human_set(plan: WritePlan, result: WriteResult | None, *, dry_run: bool) -> str:
    """``Set gain 60 → 90   (current preset 1B, edit mode)`` + write/reply/after lines."""
    field = plan.field or ""
    if plan.no_change and plan.refusal is None:
        return f"{field} is already {_field_value(plan, plan.before.data)}; nothing sent"
    mode = MODE_NAMES.get(plan.global_before.data[3], str(plan.global_before.data[3]))
    old = _field_value(plan, plan.before.data)
    new = "?" if not plan.data else _field_value(plan, _requested(plan))
    lines = [
        f"Set {field} {old} → {new}   "
        f"(current preset {_loaded_position(plan.global_before)}, {mode} mode)"
    ]
    if plan.frame:
        lines.append(f"  write  {hex_bytes(plan.frame)}")
    lines += _refusal_lines(plan)
    if dry_run or result is None:
        lines.append("  dry run: nothing sent")
        return "\n".join(lines)
    lines.append(f"  reply  {hex_bytes(result.reply)}   ACK")
    status = "applied" if result.applied else "not applied"
    texts = [_change_text(c) for c in result.changes] or ["no change"]
    lines.append(f"  after  {texts[0]}   {status}")
    lines += [f"         {text}" for text in texts[1:]]
    lines.append(NOT_SAVED_EDIT if plan.global_before.data[3] == 0 else NOT_SAVED)
    return "\n".join(lines)


def human_select(plan: WritePlan, result: WriteResult | None, *, dry_run: bool) -> str:
    """``Select 2C (index 6)   from 1B`` + write/reply/now lines."""
    index = plan.target.argument
    assert index is not None
    loaded = _loaded_position(plan.global_before, plan.before)
    header = f"Select {position(index)} (index {index})   from {loaded}"
    return _select_lines(header, plan, result, dry_run=dry_run)


def human_reload(plan: WritePlan, result: WriteResult | None, *, dry_run: bool) -> str:
    """``Reload 1B (index 1)   discards unsaved edits`` + write/reply/now lines (spec 004 R4)."""
    index = plan.target.argument
    assert index is not None
    if plan.no_change and plan.refusal is None:
        return f"Reload {position(index)}: nothing to discard; nothing sent"
    header = f"Reload {position(index)} (index {index})   discards unsaved edits"
    return _select_lines(header, plan, result, dry_run=dry_run)


def _select_lines(
    header: str, plan: WritePlan, result: WriteResult | None, *, dry_run: bool
) -> str:
    index = plan.target.argument
    assert index is not None
    target = position(index)
    lines = [header, f"  write  {hex_bytes(plan.frame)}"]
    lines += _refusal_lines(plan)
    if dry_run or result is None:
        lines.append("  dry run: nothing sent")
        return "\n".join(lines)
    lines.append(f"  reply  {hex_bytes(result.reply)}   ACK")
    glob = result.global_after.data
    bank = str(glob[1] + 1) if glob[1] <= 8 else "?"
    slot = "ABCD"[glob[2]] if glob[2] <= 3 else "?"
    now = f"  now    bank {bank}, slot {slot}   "
    if result.applied:
        lines.append(now + f"buffer = stored {target}   applied")
    else:
        lines.append(now + f"not applied (expected {target} with its stored bytes)")
    return "\n".join(lines)


def _changes_json(changes: tuple[ByteChange, ...]) -> list[dict[str, Any]]:
    return [
        {
            "region": "global" if c.region is Region.GLOBAL else "preset",
            "offset": c.offset,
            "before": c.old,
            "after": c.new,
            "name": c.field.name if c.field is not None else None,
        }
        for c in changes
    ]


def write_json(
    command: str,
    plan: WritePlan,
    result: WriteResult | None,
    *,
    dry_run: bool,
    read_at: datetime,
    device: DeviceInfo | None,
    identity: DeviceIdentity,
) -> dict[str, Any]:
    """``set`` / ``preset select`` / ``preset reload --json`` (``write-result.schema.json``)."""
    target = plan.target
    document = envelope(command, read_at, device, identity)
    document["plan"] = {
        "action": plan.action,
        "target": {
            "kind": target.kind,
            "type": target.type,
            "address": f"0x{target.address:08x}",
            "length": target.length,
            "argument": target.argument,
        },
        "data": hex_bytes(plan.data),
        "frame": hex_bytes(plan.frame),
        "reads": [hex_bytes(r) for r in plan.reads],
        "before": hex_bytes(plan.before.data),
        "global_before": hex_bytes(plan.global_before.data),
        "no_change": plan.no_change,
        "refusal": plan.refusal,
        "dry_run": dry_run,
        "confidence": plan.confidence,
    }
    if result is not None and not dry_run and not plan.no_change:
        document["result"] = {
            "reply": hex_bytes(result.reply),
            "ack": True,
            "after": hex_bytes(result.after.data),
            "global_after": hex_bytes(result.global_after.data),
            "changes": _changes_json(result.changes),
            "applied": result.applied,
        }
    return document
