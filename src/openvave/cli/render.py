"""Human and JSON renderers for CLI output (contracts/cli.md, contracts/*.schema.json)."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from openvave.models import (
    ByteChange,
    DecodedField,
    DecodedRegion,
    DeviceIdentity,
    DeviceInfo,
    DeviceSnapshot,
    Encoding,
    Region,
    RegionRead,
    WatchChange,
    WatchStart,
)
from openvave.protocol.decode import decode_field, decode_region

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


def hex_bytes(data: bytes) -> str:
    """Lowercase, space-separated hex (same format as ``captures/``)."""
    return data.hex(" ")


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


def human_info(snapshot: DeviceSnapshot) -> str:
    """Identity block, a blank line, then device info / global / status blocks."""
    firmware = snapshot.identity.firmware
    blocks = [human_region(snapshot.regions[r], firmware) for r in INFO_HUMAN_REGIONS]
    return human_identity(snapshot.identity, snapshot.device) + "\n\n" + "\n".join(blocks)


def human_preset(read: RegionRead, identity: DeviceIdentity) -> str:
    """``Current preset  (TANK-Gv2, firmware 96)   type 4 @ …`` then hex dump and known fields."""
    decoded = decode_region(read, identity.firmware)
    header = (
        f"{REGION_TITLES[read.region]}  ({identity.name}, firmware {identity.firmware})   "
        f"{region_spec(read.region)}{_map_note(decoded)}"
    )
    return "\n".join([header, *hex_dump(read.data), *field_lines(decoded)])


def device_json(device: DeviceInfo | None) -> dict[str, Any] | None:
    if device is None:
        return None
    return {"identifier": device.identifier, "name": device.name, "rssi": device.rssi}


def identity_json(identity: DeviceIdentity) -> dict[str, Any]:
    return {
        "name": identity.name,
        "firmware": identity.firmware,
        "firmware_untested": identity.firmware_untested,
        "raw": hex_bytes(identity.raw),
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


def field_json(field: DecodedField) -> dict[str, Any]:
    """One ``fields[]`` item: the 001 keys plus the additive 002 keys (decoded-field schema)."""
    entry = field.entry
    ranged = entry.min is not None and entry.max is not None
    return {
        "offset": entry.offset,
        "size": 1,
        "name": entry.name,
        "value": field.value,
        "confidence": entry.confidence,
        "raw": field.raw,
        "mask": entry.mask,
        "encoding": entry.encoding.value,
        "range": {"min": entry.min, "max": entry.max} if ranged else None,
        "display": field.display,
        "interpreted": field.interpreted,
        "out_of_range": field.out_of_range,
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


def watch_header(start: WatchStart, interval: float, record: str | None) -> list[str]:
    """Start block: what is watched, where it is recorded, and each region's baseline bytes.

    Decoded fields are appended for global and status (``preset dump`` shows the preset's).
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
    return lines


def watch_label_line(text: str) -> str:
    return f"── label: {text} ──"


def _change_cells(change: ByteChange) -> tuple[str, str, str]:
    """(label, old, new) in the field's display form, or raw hex for unknown/flag bytes."""
    if change.field is not None:
        old = decode_field(change.field, change.old).display
        new = decode_field(change.field, change.new).display
        return change.field.label, old, new
    name = " / ".join(e.label for e in change.fields) if change.fields else "unknown"
    return name, f"0x{change.old:02x}", f"0x{change.new:02x}"


def watch_change_lines(event: WatchChange, t: float) -> list[str]:
    """``+9.51s  preset[15]  reverb decay   5 → 64``; time printed once, co-moving marked."""
    lines = []
    count = len(event.changes)
    cells = [_change_cells(change) for change in event.changes]
    # Labels longer than the column widen it for this event, so values stay aligned.
    width = max([WATCH_NAME_WIDTH, *(len(name) + 1 for name, _, _ in cells)])
    for i, (change, (name, old, new)) in enumerate(zip(event.changes, cells, strict=True)):
        time_cell = f"+{t:.2f}s" if i == 0 else ""
        location = f"{WATCH_REGION_KEYS[change.region]}[{change.offset}]"
        line = (
            f"{time_cell:>{WATCH_TIME_WIDTH}}  {location:<{WATCH_LOCATION_WIDTH}}"
            f"{name:<{width}}{old:>{WATCH_VALUE_WIDTH}} → {new}"
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
    start: WatchStart, t: float, interval: float, record: str | None
) -> dict[str, Any]:
    firmware = start.identity.firmware
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
    )


def watch_label_json(text: str, t: float) -> dict[str, Any]:
    return _watch_event("label", t, text=text)


def watch_change_json(event: WatchChange, t: float, label: str | None) -> dict[str, Any]:
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
    )


def watch_stop_json(
    t: float, reason: str, error: str | None, changes: int, cycles: int
) -> dict[str, Any]:
    return _watch_event("stop", t, reason=reason, error=error, changes=changes, cycles=cycles)


def json_line(document: dict[str, Any]) -> str:
    """One JSON Lines record (``watch --json``)."""
    return json.dumps(document, ensure_ascii=False)
