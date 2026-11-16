"""Human and JSON renderers for CLI output (contracts/cli.md, contracts/*.schema.json)."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from openvave.models import DeviceIdentity, DeviceInfo

SCHEMA_VERSION = 1
LABEL_WIDTH = 11


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


def dumps(document: dict[str, Any]) -> str:
    return json.dumps(document, indent=2)
