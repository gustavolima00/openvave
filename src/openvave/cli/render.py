"""Human and JSON renderers for CLI output (contracts/cli.md, contracts/*.schema.json)."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from openvave.models import (
    KNOWN_FIELDS,
    DeviceIdentity,
    DeviceInfo,
    DeviceSnapshot,
    Region,
    RegionRead,
)

SCHEMA_VERSION = 1
LABEL_WIDTH = 11
REGION_LABEL_WIDTH = 14
REGION_SPEC_WIDTH = 32
BYTES_PER_LINE = 16

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


def field_lines(read: RegionRead, indent: str = "      ") -> list[str]:
    """``[offset] label = value   (confidence)`` for every known field of the region."""
    return [
        f"{indent}[{spec.offset}] {spec.label} = {read.data[spec.offset]}   ({spec.confidence})"
        for spec in KNOWN_FIELDS[read.region]
        if spec.offset < len(read.data)
    ]


def human_region(read: RegionRead) -> str:
    """Header, hex dump and known-field lines for one region (meanings are unconfirmed)."""
    region = read.region
    header = (
        f"{REGION_TITLES[region]:<{REGION_LABEL_WIDTH}}"
        f"{region_spec(region):<{REGION_SPEC_WIDTH}}[meaning: unknown]"
    )
    return "\n".join([header, *hex_dump(read.data), *field_lines(read)])


def human_info(snapshot: DeviceSnapshot) -> str:
    """Identity block, a blank line, then device info / global / status blocks."""
    blocks = [human_region(snapshot.regions[r]) for r in INFO_HUMAN_REGIONS]
    return human_identity(snapshot.identity, snapshot.device) + "\n\n" + "\n".join(blocks)


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


def region_json(read: RegionRead) -> dict[str, Any]:
    region = read.region
    return {
        "type": region.type,
        "address": f"0x{region.address:08x}",
        "length": region.length,
        "data": hex_bytes(read.data),
        "fields": [
            {
                "offset": spec.offset,
                "size": 1,
                "name": spec.name,
                "value": read.data[spec.offset],
                "confidence": spec.confidence,
            }
            for spec in KNOWN_FIELDS[region]
            if spec.offset < len(read.data)
        ],
    }


def info_json(snapshot: DeviceSnapshot) -> dict[str, Any]:
    """The ``openvave info --json`` document (``contracts/info.schema.json``)."""
    document = envelope("info", snapshot.read_at, snapshot.device, snapshot.identity)
    document["regions"] = {
        region.name.lower(): region_json(read) for region, read in snapshot.regions.items()
    }
    return document


def dumps(document: dict[str, Any]) -> str:
    return json.dumps(document, indent=2)
