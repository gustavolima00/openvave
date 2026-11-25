"""Pure JSON forms shared by the CLI renderers and the backup document (no I/O, no CLI code)."""

from __future__ import annotations

from typing import Any

from openvave.models import DecodedField, DeviceIdentity
from openvave.protocol.names import NAMED_FIELDS, NAMES_FIRMWARE, PositionName, position_name


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
    document = {
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
    if entry.name in NAMED_FIELDS:
        name = None if field.out_of_range else position_name(entry.name, field.value)
        document["position_name"] = None if name is None else position_name_json(name)
    return document


def position_name_json(name: PositionName) -> dict[str, Any]:
    """The model an amp type or IR cab position is named after (spec 007 US4; additive key).

    ``confidence`` is the name's own (``hypothesis`` until matched on the pedal), not the
    byte's; ``factory`` is true for IR cabs, whose slots a user can overwrite; ``firmware`` is
    the firmware the names are kept for (96), so a result from another firmware shows that the
    names are the fw 96 fallback."""
    return {
        "name": name.name,
        "detail": name.detail,
        "text": name.text,
        "factory": name.factory,
        "source": name.source,
        "confidence": name.confidence,
        "firmware": NAMES_FIRMWARE,
    }
