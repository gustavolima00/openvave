"""Human and JSON renderers for CLI output (contracts/cli.md, contracts/*.schema.json)."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from openvave._jsonform import field_json, hex_bytes, identity_json
from openvave.models import (
    IMAGE_ACTIONS,
    Backup,
    ByteChange,
    DecodedField,
    DecodedRegion,
    DeviceIdentity,
    DeviceInfo,
    DeviceSnapshot,
    EditPlan,
    EditResult,
    EditWrite,
    Encoding,
    PedalState,
    Region,
    RegionRead,
    SequencePlan,
    SequenceResult,
    SequenceStep,
    WatchChange,
    WatchStart,
    WritePlan,
    WriteResult,
)
from openvave.protocol.bytemap import TYPED_FIELDS, type_parts
from openvave.protocol.decode import decode_field, decode_region
from openvave.protocol.names import NAMED_FIELDS, PositionName, position_name
from openvave.protocol.state import classify
from openvave.protocol.storage import EXPECTED_HEADER, position
from openvave.protocol.writes import WRITABLE_FIELDS, sendable_by_default

if TYPE_CHECKING:
    from openvave.devices import KnownDevice, KnownDevices
    from openvave.models import ScanEntry

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


def _position_name(field: DecodedField) -> PositionName | None:
    if field.out_of_range:
        return None
    return position_name(field.entry.name, field.value)


def name_reading(field: DecodedField) -> str | None:
    """The model an amp type or IR cab position is named after, with its source and confidence
    (spec 007 US4): ``Plexi 100, overdrive (manual-2024, hypothesis)``, or for a cab
    ``Mesa Boogie 4x12, factory IR (manual-2024, hypothesis)``. ``None`` without a name."""
    name = _position_name(field)
    if name is None:
        return None
    kind = "factory IR" if name.factory else name.detail
    return f"{name.text}, {kind} ({name.source}, {name.confidence})"


def _short_name(field: DecodedField) -> str | None:
    """``Plexi 100 ?`` (``?`` while the name is a hypothesis), or ``None``."""
    name = _position_name(field)
    if name is None:
        return None
    return name.text + (" ?" if name.confidence == "hypothesis" else "")


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
    named = name_reading(field)
    if named is not None:
        line += f"  name: {named}"
    return line


LED_PARTS = ("led_red", "led_green", "led_blue")


def led_colour_text(decoded: DecodedRegion) -> str | None:
    """``#rrggbb`` of the preset LED from bytes 18–20, or ``None`` when the region has none."""
    parts = {f.entry.name: f.value for f in decoded.fields if f.entry.name in LED_PARTS}
    if set(parts) != set(LED_PARTS):
        return None
    return "#" + "".join(f"{parts[name]:02x}" for name in LED_PARTS)


def field_lines(decoded: DecodedRegion, indent: str = FIELD_INDENT) -> list[str]:
    """One line per named field (the LED colour also as ``#rrggbb``), then ``unknown: …``
    listing the unknown offsets."""
    lines = []
    for f in decoded.fields:
        line = field_line(f, indent)
        if f.entry.name == LED_PARTS[-1]:
            colour = led_colour_text(decoded)
            if colour is not None:
                line += f"  LED colour {colour}"
        lines.append(line)
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
    return {
        "identifier": device.identifier,
        "name": device.name,
        "rssi": device.rssi,
        "nickname": device.nickname,
        "chosen_by": device.chosen_by,
    }


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


def with_reading(field: DecodedField) -> str:
    """``5``; for a typed knob ``5 (room 6)``; for a named position ``#4 (Plexi 100 ?)``."""
    reading = type_reading(field) or _short_name(field)
    return field.display if reading is None else f"{field.display} ({reading})"


def change_names(change: ByteChange) -> tuple[str | None, str | None] | None:
    """Names of the old and new position of an amp type or IR cab change, for JSON
    (``None`` for a position without one); ``None`` for any other byte."""
    entry = change.field
    if entry is None or entry.name not in NAMED_FIELDS:
        return None
    old, new = (_position_name(decode_field(entry, raw)) for raw in (change.old, change.new))
    return (None if old is None else old.text, None if new is None else new.text)


def _change_cells(change: ByteChange) -> tuple[str, str, str]:
    """(label, old, new) in the field's display form, or raw hex for unknown/flag bytes."""
    if change.field is not None:
        return (
            change.field.label,
            with_reading(decode_field(change.field, change.old)),
            with_reading(decode_field(change.field, change.new)),
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
                **_names_json(c, "old", "new"),
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

NOT_SAVED = "Not saved. Discard: openvave preset reload   Keep: openvave preset save --unsafe"
"""After a write in normal mode. ``stored_slot`` and ``commit`` are confirmed on fw 96 (spec 004
gate session B), so the hint needs only ``--unsafe``; on another firmware ``preset save`` itself
says it needs ``--experimental``."""
NOT_SAVED_EDIT = (
    "Not saved. Discard: openvave preset reload --discard-edits "
    "(or leave edit mode on the pedal without saving)"
)
MODE_NAMES = {0: "edit", 1: "normal", 2: "tuner"}
REFUSAL_TEXT = {
    "tuner_mode": "the pedal is in tuner mode",
    "bypassed": "the pedal is bypassed",
    "unrecognised_state": "the pedal reports a state openvave does not recognise",
    "type_required": "the knob sits between two types (module off); needs --type",
    "out_of_range": "value out of range",
    "untested_firmware": "firmware not covered by a confirmed write gate; needs --experimental",
    "experimental_required": "message not confirmed yet; needs --experimental",
    "edits_would_be_discarded": "unsaved edits would be discarded; needs --discard-edits",
    "edit_mode": "the pedal is in edit mode",
    "not_bypassed": "the pedal is not bypassed; use preset select",
    "unsafe_required": "overwrites stored presets; needs --unsafe",
    "firmware_mismatch": "the file comes from another firmware; needs --experimental",
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
    return _value_text(plan.field or "", data)


def _value_text(field: str, data: bytes) -> str:
    """Display form of ``field`` read from the preset bytes ``data`` (21)."""
    spec = WRITABLE_FIELDS[field]
    if spec.kind == "led_colour":
        return "#" + data[spec.offset : spec.offset + 3].hex()
    assert spec.entry is not None
    return with_reading(decode_field(spec.entry, data[spec.offset]))


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
        return f"{where} {change.field.name} {with_reading(decode_field(change.field, change.new))}"
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


def human_bypass_on(plan: WritePlan, result: WriteResult | None, *, dry_run: bool) -> str:
    """``Bypass on   (was 1B, normal mode)`` + write/reply/now and the line that leaves bypass."""
    if plan.no_change and plan.refusal is None:
        return "already bypassed; nothing sent"
    mode = MODE_NAMES.get(plan.global_before.data[3], str(plan.global_before.data[3]))
    lines = [f"Bypass on   (was {_loaded_position(plan.global_before, plan.before)}, {mode} mode)"]
    lines.append(f"  write  {hex_bytes(plan.frame)}")
    lines += _refusal_lines(plan)
    if dry_run or result is None:
        lines.append("  dry run: nothing sent")
        return "\n".join(lines)
    lines.append(f"  reply  {hex_bytes(result.reply)}   ACK")
    if result.applied:
        lines.append("  now    bypass (slot ff, buffer all 00)   applied")
        if result.return_index is not None:
            lines.append(f"Leave bypass: openvave bypass off {position(result.return_index)}")
    else:
        slot = result.global_after.data[2]
        zero = "all 00" if result.after.data == bytes(len(result.after.data)) else "not all 00"
        lines.append(
            f"  now    slot {slot:02x}, buffer {zero}   "
            "not applied (expected slot ff, buffer all 00)"
        )
    return "\n".join(lines)


def human_bypass_off(plan: WritePlan, result: WriteResult | None, *, dry_run: bool) -> str:
    """``Bypass off: select 1B (index 1)   from bypass (bank 1)`` + the select lines."""
    index = plan.target.argument
    assert index is not None
    loaded = _loaded_position(plan.global_before, plan.before)
    header = f"Bypass off: select {position(index)} (index {index})   from {loaded}"
    return _select_lines(header, plan, result, dry_run=dry_run)


def _loopback_name(data: bytes) -> str:
    return {b"\x00": "off", b"\x01": "on"}.get(data, data.hex(" ") or "?")


def human_loopback(plan: WritePlan, result: WriteResult | None, *, dry_run: bool) -> str:
    """``Loopback on → off   (status byte 0xD0000000, …)`` + write/reply/after lines."""
    new = _loopback_name(plan.data)
    if plan.no_change and plan.refusal is None:
        return f"loopback is already {new}; nothing sent"
    old = _loopback_name(plan.before.data)
    lines = [
        f"Loopback {old} → {new}   (status byte 0xD0000000: Bluetooth audio in the USB recording)",
        f"  write  {hex_bytes(plan.frame)}",
    ]
    lines += _refusal_lines(plan)
    if dry_run or result is None:
        lines.append("  dry run: nothing sent")
        return "\n".join(lines)
    lines.append(f"  reply  {hex_bytes(result.reply)}   ACK")
    status = "applied" if result.applied else "not applied"
    after = result.after.data
    reading = f"status {hex_bytes(after)} (loopback {_loopback_name(after)})"
    lines.append(f"  after  {reading}   {status}")
    return "\n".join(lines)


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


_REGION_NAMES = {Region.GLOBAL: "global", Region.STATUS: "status"}


def _changes_json(changes: tuple[ByteChange, ...]) -> list[dict[str, Any]]:
    return [
        {
            "region": _REGION_NAMES.get(c.region, "preset"),
            "offset": c.offset,
            "before": c.old,
            "after": c.new,
            "name": c.field.name if c.field is not None else None,
            **_names_json(c, "before", "after"),
        }
        for c in changes
    ]


def _names_json(change: ByteChange, old_key: str, new_key: str) -> dict[str, str | None]:
    """``position_name_<old>`` / ``position_name_<new>`` for an amp type or IR cab change
    (spec 007 US4, additive keys); empty for any other byte."""
    names = change_names(change)
    if names is None:
        return {}
    return {f"position_name_{old_key}": names[0], f"position_name_{new_key}": names[1]}


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
    """``set`` / ``preset select`` / ``preset reload`` / ``bypass`` / ``loopback --json``
    (``write-result.schema.json``)."""
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
        if result.return_index is not None:
            document["result"]["return_index"] = result.return_index
            document["result"]["return_position"] = position(result.return_index)
    return document


# -- batch edit (contracts/cli.md "openvave set FIELD=VALUE ...") -------------------------------

FIELD_STATUS_TEXT = {
    "applied": "applied",
    "unchanged": "unchanged",
    "not_applied": "not applied",
    "unknown": "unknown",
    "not_sent": "not sent",
}
EDIT_FAILURE_HINT = (
    "Nothing was retried. Applied fields are in the edit buffer, not saved. "
    "Discard: openvave preset reload"
)


def _edit_target(write: EditWrite) -> str:
    target = write.target
    name = target.kind if target.argument is None else f"{target.kind} {target.argument}"
    return f"{name}: {', '.join(write.fields)}"


def _edit_requested(plan: EditPlan) -> bytes:
    """The edit buffer as it would be after every write of the plan."""
    buffer = bytearray(plan.before.data)
    for f in plan.fields:
        if f.wanted:
            buffer[f.offset : f.offset + len(f.wanted)] = f.wanted
    return bytes(buffer)


def _edit_refusal_lines(plan: EditPlan) -> list[str]:
    reason = plan.refusal
    if reason is None:
        return []
    detail = REFUSAL_TEXT.get(reason, reason)
    edit = next((f for f in plan.fields if f.field == plan.refused_field), None)
    if edit is not None:
        if reason == "experimental_required":
            write = next(w for w in plan.writes if edit.field in w.fields)
            detail = f"{write.target.kind} is '{write.confidence}'; needs --experimental"
        detail = f"{edit.field}: {detail}"
    return [f"  refused: {reason} ({detail})"]


def human_edit(plan: EditPlan, result: EditResult | None) -> str:
    """``Set 5 fields   (current preset 1B, normal mode)``, one line per field, then every
    write (and its reply when sent), the changes and the not-saved hint."""
    if plan.no_change and plan.refusal is None:
        return f"{', '.join(f.field for f in plan.fields)} already set; nothing sent"
    mode = MODE_NAMES.get(plan.global_before.data[3], str(plan.global_before.data[3]))
    count = len(plan.fields)
    lines = [
        f"Set {count} field{'' if count == 1 else 's'}   "
        f"(current preset {_loaded_position(plan.global_before)}, {mode} mode)"
    ]
    width = max(len(f.field) for f in plan.fields)
    requested = _edit_requested(plan)
    for f in plan.fields:
        old = _value_text(f.field, plan.before.data)
        if f.no_change:
            text = f"{old} (unchanged)"
        else:
            text = f"{old} → {_value_text(f.field, requested) if f.wanted else '?'}"
        lines.append(f"  {f.field:<{width}}  {text}")
    outcomes = result.writes if result is not None else ()
    for i, write in enumerate(plan.writes):
        lines.append(f"  write  {hex_bytes(write.frame)}   {_edit_target(write)}")
        if i < len(outcomes) and outcomes[i].status == "acked":
            done = "applied" if outcomes[i].applied else "not applied"
            lines.append(f"  reply  {hex_bytes(outcomes[i].reply)}   ACK   {done}")
    lines += _edit_refusal_lines(plan)
    if result is None:
        lines.append("  dry run: nothing sent")
        return "\n".join(lines)
    texts = [_change_text(c) for c in result.changes] or ["no change"]
    lines.append(f"  after  {texts[0]}")
    lines += [f"         {text}" for text in texts[1:]]
    lines.append(NOT_SAVED_EDIT if plan.global_before.data[3] == 0 else NOT_SAVED)
    return "\n".join(lines)


def edit_failure_lines(message: str, result: EditResult) -> list[str]:
    """stderr report of a batch edit that stopped: the error, each field's status, the hint."""
    outcome_of = {name: o for o in result.writes for name in o.write.fields}
    width = max(len(name) for name, _ in result.field_status)
    lines = [f"error: {message}"]
    for name, status in result.field_status:
        text = FIELD_STATUS_TEXT[status]
        outcome = outcome_of.get(name)
        if status == "unknown" and outcome is not None:
            text += f" ({outcome.status.replace('_', ' ')})"
        lines.append(f"  {name:<{width}}  {text}")
    lines.append(EDIT_FAILURE_HINT)
    return lines


def edit_json(
    plan: EditPlan,
    result: EditResult | None,
    *,
    dry_run: bool,
    read_at: datetime,
    device: DeviceInfo | None,
    identity: DeviceIdentity,
) -> dict[str, Any]:
    """``set FIELD=VALUE ... --json`` (``set-fields-result.schema.json``)."""
    document = envelope("set", read_at, device, identity)
    document["plan"] = {
        "action": "set",
        "fields": [
            {
                "field": f.field,
                "kind": f.target.kind,
                "offset": f.offset,
                "before": hex_bytes(f.current),
                "requested": hex_bytes(f.wanted),
                "no_change": f.no_change,
                "refusal": f.refusal,
            }
            for f in plan.fields
        ],
        "writes": [
            {
                "target": {
                    "kind": w.target.kind,
                    "type": w.target.type,
                    "address": f"0x{w.target.address:08x}",
                    "length": w.target.length,
                    "argument": w.target.argument,
                },
                "data": hex_bytes(w.data),
                "frame": hex_bytes(w.frame),
                "fields": list(w.fields),
                "confidence": w.confidence,
            }
            for w in plan.writes
        ],
        "reads": [hex_bytes(r) for r in plan.reads],
        "before": hex_bytes(plan.before.data),
        "global_before": hex_bytes(plan.global_before.data),
        "no_change": plan.no_change,
        "refusal": plan.refusal,
        "refused_field": plan.refused_field,
        "dry_run": dry_run,
    }
    if result is not None and not dry_run:
        document["result"] = {
            "writes": [
                {"status": o.status, "reply": hex_bytes(o.reply), "applied": o.applied}
                for o in result.writes
            ],
            "fields": dict(result.field_status),
            "after": None if result.after is None else hex_bytes(result.after.data),
            "global_after": (
                None if result.global_after is None else hex_bytes(result.global_after.data)
            ),
            "changes": _changes_json(result.changes),
            "applied": result.applied,
        }
    return document


# -- save and restore (contracts/cli.md "preset save" / "preset restore") -----------------------

POWER_WARNING = "A power loss during the next second has an unknown outcome."
IMAGE_HEAD = 16
"""Bytes of the image write shown before the ellipsis in a real run (a dry run shows all)."""
STEP_LABEL_WIDTH = 16


def _pending_messages(plan: SequencePlan, identity: DeviceIdentity) -> list[str]:
    """Write kinds of the plan that are not sendable without ``--experimental``."""
    kinds = []
    for step in plan.steps:
        target = step.target
        if target is not None and not sendable_by_default(
            target.kind, target.argument, identity.firmware
        ):
            kinds.append(target.kind)
    return sorted(set(kinds))


def _sequence_refusal_line(
    plan: SequencePlan, identity: DeviceIdentity, experimental: bool
) -> list[str]:
    reason = plan.refusal
    if reason is None:
        return []
    detail = REFUSAL_TEXT.get(reason, reason)
    pending = [] if experimental else _pending_messages(plan, identity)
    if reason == "unsafe_required" and pending:
        detail += f" and --experimental ({', '.join(pending)} not confirmed yet)"
    elif reason == "experimental_required":
        detail = f"{', '.join(pending)} not confirmed yet; needs --experimental"
    return [f"  refused: {reason} ({detail})"]


def _diff_line(change: ByteChange) -> str:
    entry = change.field
    if entry is None:
        return f"  [{change.offset}] {change.old} → {change.new}"
    old = with_reading(decode_field(entry, change.old))
    new = with_reading(decode_field(entry, change.new))
    return f"  [{change.offset}] {entry.name} {old} → {new}"


def human_sequence_header(plan: SequencePlan, source: str | None) -> str:
    """``Save current sound to 1C (index 2)   UNSAFE: …`` and what changes (FR-030)."""
    if plan.action in IMAGE_ACTIONS:
        differ = " ".join(position(i) for i in plan.changed_slots) or "header only"
        count = len(plan.changed_slots)
        head = f"Swap {source}" if plan.action == "swap" else f"Restore all presets from {source}"
        return "\n".join(
            [
                f"{head}   UNSAFE: overwrites stored presets",
                f"  differ: {differ} ({count} of {len(plan.after) // 21})",
            ]
        )
    index = plan.target_index
    assert index is not None
    if plan.action == "save":
        head = f"Save current sound to {position(index)} (index {index})"
    elif plan.action == "copy":
        head = f"Copy {source} to {position(index)} (index {index})"
    elif plan.action == "import":
        head = f"Import {source} into {position(index)} (index {index})"
    else:
        head = f"Restore {position(index)} from {source}"
    lines = [f"{head}   UNSAFE: overwrites a stored preset"]
    lines += [_diff_line(c) for c in plan.diff]
    return "\n".join(lines)


def human_sequence_no_change(plan: SequencePlan, source: str | None) -> str:
    """The ``nothing sent`` line of a save / restore with nothing to change."""
    if plan.action == "save":
        assert plan.target_index is not None
        return f"{position(plan.target_index)} already holds this sound; nothing sent"
    if plan.action in ("copy", "import"):
        assert plan.target_index is not None
        return f"{position(plan.target_index)} already holds {source}; nothing sent"
    if plan.action == "swap":
        return f"{source} hold the same sound; nothing sent"
    return f"pedal already matches {source}; nothing sent"


def _step_note(step: SequenceStep) -> str:
    target = step.target
    assert target is not None
    if target.kind == "commit":
        return "   (commit)"
    if target.kind == "preset_select":
        assert target.argument is not None
        return f"   (select {position(target.argument)})"
    return ""


def _write_cell(step: SequenceStep, *, full: bool) -> str:
    target = step.target
    if target is not None and target.kind == "stored_image" and not full:
        frame = step.frame
        return f"{hex_bytes(frame[:IMAGE_HEAD])} …({len(step.data)} bytes)… {frame[-1]:02x}"
    return hex_bytes(step.frame)


def human_sequence_plan(
    plan: SequencePlan, source: str | None, identity: DeviceIdentity, *, experimental: bool
) -> str:
    """Dry run: header, every step with its exact frame (the image in full), refusal."""
    if plan.no_change and plan.refusal is None:
        return human_sequence_no_change(plan, source)
    lines = [human_sequence_header(plan, source)]
    for step in plan.steps:
        if step.kind == "wait":
            lines.append(f"  wait   {round((step.seconds or 0) * 1000)} ms")
        else:
            lines.append(f"  write  {_write_cell(step, full=True)}{_step_note(step)}")
    lines += _sequence_refusal_line(plan, identity, experimental)
    lines.append("  dry run: nothing sent, no backup taken")
    return "\n".join(lines)


def _verify_line(plan: SequencePlan, source: str | None, verified: bool) -> str:
    if plan.action == "swap":
        count = len(plan.after) // 21
        status = "swapped" if verified else "NOT swapped"
        return f"  verify {count} of {count} presets and header as planned   {status}"
    if plan.action == "restore_all":
        count = len(plan.after) // 21
        status = "restored" if verified else "NOT restored"
        return f"  verify {count} of {count} presets and header equal {source}   {status}"
    index = plan.target_index
    assert index is not None
    where = position(index)
    if plan.action == "save":
        return f"  verify stored {where} = written bytes, pedal on {where}, buffer = stored   " + (
            "saved" if verified else "NOT saved"
        )
    if plan.action in ("copy", "import"):
        done = "copied" if plan.action == "copy" else "imported"
        return f"  verify stored {where} = {source}, pedal on {where}, buffer = stored   " + (
            done if verified else f"NOT {done}"
        )
    return f"  verify stored {where} = {source} {where}, pedal on {where}, buffer = stored   " + (
        "restored" if verified else "NOT restored"
    )


def human_sequence_steps(result: SequenceResult, source: str | None) -> str:
    """After the backup: one line per step with its reply, then the verification."""
    plan = result.plan
    lines = []
    for outcome in result.steps:
        step = outcome.step
        if step.kind == "wait":
            lines.append(f"  wait   {round((step.seconds or 0) * 1000)} ms")
            continue
        status = {"acked": "ACK", "nak": "NAK"}.get(outcome.status, outcome.status)
        cell = _write_cell(step, full=False)
        note = _step_note(step)
        if step.target is not None and step.target.kind == "stored_image":
            note = f"   ({len(step.frame)} bytes)"
        lines.append(f"  write  {cell}   {status}{note}")
    lines.append(_verify_line(plan, source, result.verified))
    return "\n".join(lines)


def _step_label(step: SequenceStep) -> str:
    target = step.target
    assert target is not None
    if target.kind == "stored_slot":
        assert target.argument is not None
        return f"slot write {position(target.argument)}"
    if target.kind == "stored_image":
        return "image write"
    if target.kind == "preset_select":
        assert target.argument is not None
        return f"select {position(target.argument)}"
    return target.kind


STEP_STATUS = {"acked": "ACK", "nak": "NAK", "no_reply": "no reply", "not_sent": "not sent"}


def sequence_failure_lines(
    message: str, result: SequenceResult, backup_path: str | None, identity: DeviceIdentity
) -> list[str]:
    """The stderr report of a save / restore that stopped (contracts/cli.md, FR-031)."""
    lines = [f"error: {message}"]
    for outcome in result.steps:
        if outcome.step.kind == "write":
            label = _step_label(outcome.step)
            lines.append(f"  {label:<{STEP_LABEL_WIDTH}}{STEP_STATUS[outcome.status]}")
    plan = result.plan
    acked = all(o.status in ("acked", "waited") for o in result.steps)
    if acked or (result.read_back is not None and plan.action not in IMAGE_ACTIONS):
        if plan.action in IMAGE_ACTIONS:
            if result.mismatched_slots:
                lines.append("  differ:  " + " ".join(position(i) for i in result.mismatched_slots))
        elif result.read_back is not None and result.read_back != plan.after:
            lines.append(f"  expected {hex_bytes(plan.after)}")
            lines.append(f"  read     {hex_bytes(result.read_back)}")
    if result.stored_may_have_changed:
        lines.append("Stored presets may have changed. Nothing was retried.")
    else:
        lines.append("Stored presets did not change. Nothing was retried.")
    lines.append("Check:   openvave preset backup")
    if backup_path is not None:
        flags = "--all --unsafe"
        if not all(
            sendable_by_default(kind, None, identity.firmware)
            for kind in ("stored_image", "commit", "preset_select")
        ):
            flags += " --experimental"
        lines.append(f"Undo:    openvave preset restore {backup_path} {flags}")
    return lines


def _sequence_step_json(step: SequenceStep) -> dict[str, Any]:
    if step.kind == "wait":
        return {"kind": "wait", "seconds": step.seconds}
    assert step.target is not None
    return {"kind": "write", "target": step.target.kind, "frame": hex_bytes(step.frame)}


def sequence_json(
    command: str,
    plan: SequencePlan,
    result: SequenceResult | None,
    *,
    dry_run: bool,
    read_at: datetime,
    device: DeviceInfo | None,
    identity: DeviceIdentity,
    source: str | None,
    backup_saved_to: str | None,
) -> dict[str, Any]:
    """``preset save`` / ``preset restore --json`` (``sequence-result.schema.json``)."""
    document = envelope(command, read_at, device, identity)
    document["backup_saved_to"] = backup_saved_to
    document["plan"] = {
        "action": plan.action,
        "pedal_state": plan.state.kind,
        "target_index": plan.target_index,
        "return_index": plan.return_index,
        "source": source,
        "changed_slots": [position(i) for i in plan.changed_slots],
        "diff": [
            {
                "offset": c.offset,
                "before": c.old,
                "after": c.new,
                "name": c.field.name if c.field is not None else None,
            }
            for c in plan.diff
        ],
        "steps": [_sequence_step_json(s) for s in plan.steps],
        "reads": [hex_bytes(r) for r in plan.reads],
        "no_change": plan.no_change,
        "refusal": plan.refusal,
        "dry_run": dry_run,
    }
    if result is not None and not dry_run and result.steps:
        part: dict[str, Any] = {
            "steps": [
                {
                    "target": "wait" if o.step.target is None else o.step.target.kind,
                    "status": o.status,
                    **({"reply": hex_bytes(o.reply)} if o.reply else {}),
                }
                for o in result.steps
            ],
            "stored_may_have_changed": result.stored_may_have_changed,
            "verified": result.verified,
            "mismatched_slots": [position(i) for i in result.mismatched_slots],
        }
        if plan.action not in IMAGE_ACTIONS and result.read_back is not None:
            part["read_back"] = hex_bytes(result.read_back)
        document["result"] = part
    return document


# -- known pedals: scan, select, device, forget (spec 005 contracts/cli.md) ----------------------

_UUID_SHAPE = re.compile(
    r"^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$"
)
SELECT_HINT = "Select one: openvave select ID [--name NICKNAME]"
NO_TANK_G = "No Tank-G found."
NO_TANK_G_HINT = (
    "hint: switch the pedal on and close the M-VAVE phone app; a pedal that is connected to the "
    "app\n      or to another program stops advertising."
)
CHOICE_NOTE = (
    "openvave connects for the length of one command; this is a choice, not an open connection."
)


def short_identifier(identifier: str) -> str:
    """A UUID shortened to its first 8 characters plus ``…``; a MAC in full (research R8)."""
    return identifier[:8] + "…" if _UUID_SHAPE.match(identifier) else identifier


TANK_G_NAME = "TANK-Gv2_BLE"

CHOSEN_BY_TEXT = {
    "selected": "(selected)",
    "device_option": "(--device)",
    "environment": "(OPENVAVE_DEVICE)",
    "only_one_found": "(only one found)",
}
"""Reason shown at the end of the ``pedal:`` line, by ``DeviceInfo.chosen_by`` (research R8)."""


def pedal_line(device: DeviceInfo) -> str:
    """``pedal: stage  8F3A21C4…  -58 dBm  (selected)``: which pedal a command uses (stderr,
    human mode, before connecting; spec 005 R8). No nickname: the identifier comes first."""
    parts = [device.nickname] if device.nickname else []
    parts += [short_identifier(device.identifier), rssi_text(device.rssi)]
    reason = CHOSEN_BY_TEXT.get(device.chosen_by or "")
    if reason:
        parts.append(reason)
    line = "pedal: " + "  ".join(parts)
    if device.name != TANK_G_NAME:
        line += f"   name: {device.name or '?'} (not a Tank-G name)"
    return line


def rssi_text(rssi: int | None) -> str:
    return f"{rssi} dBm" if rssi is not None else "? dBm"


def _local_time(moment: datetime) -> str:
    return moment.astimezone().strftime("%Y-%m-%d %H:%M")


def _table(rows: Sequence[Sequence[str]], *, right: Sequence[int] = ()) -> list[str]:
    """Columns joined by two spaces, each padded to its widest cell (``right``: right-aligned);
    trailing spaces removed."""
    if not rows:
        return []
    widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
    lines = []
    for row in rows:
        cells = [
            cell.rjust(widths[i]) if i in right else cell.ljust(widths[i])
            for i, cell in enumerate(row)
        ]
        lines.append("  ".join(cells).rstrip())
    return lines


def _marked(marks: Sequence[bool], lines: Sequence[str]) -> list[str]:
    return [("* " if mark else "  ") + line for mark, line in zip(marks, lines, strict=True)]


def _scan_rows(entries: Sequence[ScanEntry], identified: bool) -> list[str]:
    with_nicknames = any(e.device.nickname for e in entries)
    rows: list[list[str]] = []
    for entry in entries:
        device = entry.device
        row = [device.nickname or ""] if with_nicknames else []
        row += [device.identifier, device.name or "-", rssi_text(device.rssi)]
        extra = ""
        if not entry.tank_g:
            extra = "(not a Tank-G)"
        elif identified:
            extra = (
                f"fw {entry.firmware}"
                if entry.firmware is not None
                else f"fw ? ({entry.identify_error or 'unknown error'})"
            )
        rows.append([*row, extra])
    rssi_column = 3 if with_nicknames else 2
    return _marked([e.selected for e in entries], _table(rows, right=(rssi_column,)))


def human_scan(
    entries: Sequence[ScanEntry], known: KnownDevices | None, *, identified: bool = False
) -> str:
    """``openvave scan`` stdout: rows, a count line, and a line when the default was not seen."""
    lines = _scan_rows(entries, identified)
    pedals = sum(1 for e in entries if e.tank_g)
    if not pedals:
        lines.append(NO_TANK_G)
        return "\n".join(lines)
    count = f"{pedals} {'pedal' if pedals == 1 else 'pedals'} found."
    if any(e.selected for e in entries):
        count += " * = default."
    lines.append(f"{count} {SELECT_HINT}")
    default = known.default if known is not None else None
    if default is not None and not any(e.selected for e in entries):
        if default.nickname:
            lines.append(f"{default.nickname} ({default.identifier}) not seen")
        else:
            lines.append(f"default {default.identifier} not seen")
    return "\n".join(lines)


def scan_json(
    entries: Sequence[ScanEntry],
    known: KnownDevices | None,
    *,
    scanned_at: datetime,
    scan_seconds: float,
    identified: bool = False,
) -> dict[str, Any]:
    """The ``openvave scan --json`` document (``scan.schema.json``)."""
    has_default = known is not None and known.default is not None
    devices = []
    for entry in entries:
        row: dict[str, Any] = {
            "identifier": entry.device.identifier,
            "name": entry.device.name,
            "rssi": entry.device.rssi,
            "tank_g": entry.tank_g,
            "nickname": entry.device.nickname,
            "known": entry.known,
            "selected": entry.selected,
        }
        if identified and entry.tank_g:
            row["firmware"] = entry.firmware
            row["identify_error"] = entry.identify_error
        devices.append(row)
    return {
        "schema_version": SCHEMA_VERSION,
        "command": "scan",
        "scanned_at": scanned_at.isoformat(),
        "scan_seconds": scan_seconds,
        "default_seen": any(e.selected for e in entries) if has_default else None,
        "devices": devices,
    }


def _time_json(moment: datetime | None) -> str | None:
    return moment.isoformat() if moment is not None else None


def known_json(device: KnownDevice) -> dict[str, Any]:
    """One known pedal (``device.schema.json`` ``$defs/known``)."""
    return {
        "identifier": device.identifier,
        "nickname": device.nickname,
        "added_at": device.added_at.isoformat(),
        "selected_at": _time_json(device.selected_at),
        "last_name": device.last_name,
        "last_firmware": device.last_firmware,
        "last_seen_at": _time_json(device.last_seen_at),
    }


def device_document(command: str, known: KnownDevices, **extra: Any) -> dict[str, Any]:
    """The document shared by ``device``, ``select``, ``forget`` and ``device rename``
    (``device.schema.json``); ``extra`` adds the command's own keys."""
    default = known.default
    document: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "command": command,
        "config_path": str(known.path),
        "default": known_json(default) if default is not None else None,
        "devices": [known_json(d) for d in known.devices],
    }
    for key, value in extra.items():
        if isinstance(value, list):
            document[key] = [known_json(v) for v in value]
        elif key == "previous_default":
            document[key] = known_json(value) if value is not None else None
        else:
            document[key] = value
    return document


def _known_label(device: KnownDevice) -> str:
    return f"{device.nickname}  {device.identifier}" if device.nickname else device.identifier


def _known_rows(known: KnownDevices) -> list[str]:
    with_nicknames = any(d.nickname for d in known.devices)
    rows = [([d.nickname or ""] if with_nicknames else []) + [d.identifier] for d in known.devices]
    default = known.default_identifier
    marks = [default is not None and d.identifier == default for d in known.devices]
    return _marked(marks, _table(rows))


def human_device(
    known: KnownDevices, *, environment: str | None, in_range: tuple[bool, int | None] | None
) -> str:
    """``openvave device`` stdout (contracts/cli.md)."""
    default = known.default
    lines: list[str] = []
    if default is None:
        lines.append("No default pedal. Commands use the only Tank-G in range.")
        lines.append("Choose one: openvave scan, then openvave select ID")
    else:
        lines.append(f"Default pedal: {_known_label(default)}")
        parts = []
        if default.selected_at is not None:
            parts.append(f"selected {_local_time(default.selected_at)}")
        if default.last_seen_at is not None:
            seen = f"last seen {_local_time(default.last_seen_at)}"
            details = [d for d in (default.last_name,) if d]
            if default.last_firmware is not None:
                details.append(f"firmware {default.last_firmware}")
            if details:
                seen += f" ({', '.join(details)})"
            parts.append(seen)
        if parts:
            lines.append("  " + ", ".join(parts))
    if environment:
        lines.append(f"OPENVAVE_DEVICE={environment} overrides the default in this shell.")
    if known.devices:
        lines.append("Known pedals:")
        lines += _known_rows(known)
    lines.append(f"Configuration: {known.path}")
    if default is not None:
        lines.append(CHOICE_NOTE)
    if in_range is not None:
        seen_now, rssi = in_range
        if not seen_now:
            lines.append("In range: no")
        else:
            lines.append(f"In range: yes ({rssi} dBm)" if rssi is not None else "In range: yes")
    return "\n".join(lines)


def human_select_device(
    device: KnownDevice,
    *,
    name: str | None,
    rssi: int | None,
    previous: KnownDevice | None,
    path: Path,
) -> str:
    """``openvave select`` stdout: the new default, the one it replaced, where it is saved."""
    details = [d for d in (name,) if d]
    if rssi is not None:
        details.append(f"{rssi} dBm")
    line = f"Default pedal: {_known_label(device)}"
    if details:
        line += f"  ({', '.join(details)})"
    lines = [line]
    if previous is not None and previous.identifier != device.identifier:
        lines.append(f"Was: {_known_label(previous)}")
    lines.append(f"Saved in {path}")
    return "\n".join(lines)


def human_rename(old: str, device: KnownDevice) -> str:
    """``Renamed stage → live  8F3A21C4…``."""
    return f"Renamed {old} → {device.nickname}  {short_identifier(device.identifier)}"


def _short_label(device: KnownDevice) -> str:
    short = short_identifier(device.identifier)
    return f"{device.nickname} {short}" if device.nickname else short


def human_forget_default(device: KnownDevice | None) -> str:
    """``openvave forget`` without a target."""
    if device is None:
        return "No default pedal."
    return (
        f"Forgot the default ({_short_label(device)}). It is still a known pedal; remove it "
        f"with: openvave forget {device.nickname or device.identifier}"
    )


def human_forget_one(device: KnownDevice, *, was_default: bool) -> str:
    """``openvave forget TARGET``."""
    label = (
        f"{device.nickname}  {short_identifier(device.identifier)}"
        if device.nickname
        else short_identifier(device.identifier)
    )
    return f"Forgot {label}" + (" (it was the default)" if was_default else "")


def human_forget_all(count: int, moved_to: Path | None) -> str:
    """``openvave forget --all``."""
    if moved_to is not None:
        return f"Moved the invalid file to {moved_to}; started an empty one."
    return f"Forgot {count} known {'pedal' if count == 1 else 'pedals'}."
