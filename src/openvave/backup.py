"""Backup ↔ JSON document (``specs/003-preset-backup-edit-writes/contracts/backup.schema.json``).

Pure: builds and reads plain ``dict`` documents; writing the file is the caller's job (the CLI
writes it atomically). The document carries no device identifier or MAC (research R7).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from openvave._jsonform import field_json, hex_bytes, identity_json
from openvave.models import Backup, DeviceIdentity, Region, RegionRead, StoredPreset
from openvave.protocol.decode import decode_region
from openvave.protocol.storage import (
    PRESET_COUNT,
    PRESET_SIZE,
    SLOTS,
    STORAGE_TYPE,
    STORE_OFFSET,
    position,
)

KIND = "openvave.preset-backup"
FORMAT_VERSION = 1


def stored_preset(index: int, data: bytes, firmware: int) -> StoredPreset:
    """A :class:`StoredPreset` with ``data`` decoded by the current-preset byte map."""
    return StoredPreset(
        index=index,
        position=position(index),
        data=data,
        decoded=decode_region(RegionRead(Region.CURRENT_PRESET, data), firmware),
    )


def _preset_json(preset: StoredPreset) -> dict[str, Any]:
    return {
        "index": preset.index,
        "position": preset.position,
        "bank": preset.index // 4 + 1,
        "slot": SLOTS[preset.index % 4],
        "raw": hex_bytes(preset.data),
        "fields": [field_json(f) for f in preset.decoded.fields],
        "unknown_offsets": list(preset.decoded.unknown_offsets),
    }


def to_document(backup: Backup, tool_version: str) -> dict[str, Any]:
    """The backup file document; ``tool_version`` is recorded as ``"openvave <version>"``."""
    return {
        "kind": KIND,
        "format_version": FORMAT_VERSION,
        "created_at": backup.created_at.isoformat(),
        "tool": f"openvave {tool_version}",
        "identity": identity_json(backup.identity),
        "layout": {
            "type": STORAGE_TYPE,
            "address": "0x00000000",
            "store_offset": STORE_OFFSET,
            "preset_size": PRESET_SIZE,
            "preset_count": PRESET_COUNT,
        },
        "header": hex_bytes(backup.header),
        "image": hex_bytes(backup.image),
        "presets": [_preset_json(p) for p in backup.presets],
        "warnings": list(backup.warnings),
    }


def from_document(document: Mapping[str, Any]) -> Backup:
    """Rebuild a :class:`Backup`. Decoded fields are recomputed from ``raw``, not trusted.

    Raises :class:`ValueError` for another ``kind`` / ``format_version`` or a malformed document,
    and :class:`~openvave.errors.ProtocolError` (``backup_mismatch``) when ``image`` disagrees
    with the presets.
    """
    if document.get("kind") != KIND:
        raise ValueError(f"not an openvave preset backup (kind {document.get('kind')!r})")
    if document.get("format_version") != FORMAT_VERSION:
        raise ValueError(f"unsupported backup format_version {document.get('format_version')!r}")
    try:
        ident = document["identity"]
        identity = DeviceIdentity(
            raw=bytes.fromhex(ident["raw"]),
            name=ident["name"],
            firmware=int(ident["firmware"]),
            firmware_untested=bool(ident["firmware_untested"]),
        )
        presets = tuple(
            stored_preset(int(p["index"]), bytes.fromhex(p["raw"]), identity.firmware)
            for p in document["presets"]
        )
        created_at = datetime.fromisoformat(document["created_at"])
        header = bytes.fromhex(document["header"])
        image = bytes.fromhex(document["image"])
        warnings = tuple(str(w) for w in document["warnings"])
    except (KeyError, TypeError) as err:
        raise ValueError(f"malformed backup document: {err!r}") from err
    return Backup(
        identity=identity,
        created_at=created_at,
        header=header,
        image=image,
        presets=presets,
        warnings=warnings,
    )
