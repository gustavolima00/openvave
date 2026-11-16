"""Human and JSON renderers for CLI output (contracts/cli.md, contracts/*.schema.json)."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from openvave.models import (
    DecodedField,
    DecodedRegion,
    DeviceIdentity,
    DeviceInfo,
    DeviceSnapshot,
    Encoding,
    Region,
    RegionRead,
)
from openvave.protocol.decode import decode_region

SCHEMA_VERSION = 1
LABEL_WIDTH = 11
REGION_LABEL_WIDTH = 14
REGION_SPEC_WIDTH = 32
BYTES_PER_LINE = 16
FIELD_INDENT = "      "
FIELD_OFFSET_WIDTH = 5
FIELD_LABEL_WIDTH = 25
FIELD_DISPLAY_WIDTH = 4
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
        f"{field.display:>{FIELD_DISPLAY_WIDTH}}      "
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
    """Fields shared by every JSON document (``schema_version`` 1)."""
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
