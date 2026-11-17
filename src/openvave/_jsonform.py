"""Pure JSON forms shared by the CLI renderers and the backup document (no I/O, no CLI code)."""

from __future__ import annotations

from typing import Any

from openvave.models import DecodedField, DeviceIdentity


def hex_bytes(data: bytes) -> str:
    """Lowercase, space-separated hex (same format as ``captures/``)."""
    return data.hex(" ")


def identity_json(identity: DeviceIdentity) -> dict[str, Any]:
    """Handshake result: name, firmware, untested flag and the raw payload as hex."""
    return {
        "name": identity.name,
        "firmware": identity.firmware,
        "firmware_untested": identity.firmware_untested,
        "raw": hex_bytes(identity.raw),
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
