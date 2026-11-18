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
    EXPECTED_HEADER,
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


def restore_problems(document: Any, firmware: int | None = None) -> list[str]:
    """Why ``document`` cannot be restored to a pedal running ``firmware`` (spec 004 FR-020).

    Checks the kind, ``format_version`` 1, 36 presets of 21 bytes with positions 1A–9D each once,
    the header ``a5 5a`` and that the image equals header + presets. With ``firmware`` given, a
    file from another firmware adds a problem starting ``firmware_mismatch`` (the only one the
    experimental opt-in may override). An empty list means the file can be restored. Pure: the
    CLI calls it with ``firmware=None`` before connecting.
    """
    if not isinstance(document, Mapping):
        return ["not an openvave backup document (expected a JSON object)"]
    problems: list[str] = []
    if document.get("kind") != KIND:
        problems.append(f"kind {document.get('kind')!r} is not an openvave preset backup ({KIND})")
    if document.get("format_version") != FORMAT_VERSION:
        problems.append(
            f"format_version {document.get('format_version')!r} is not supported "
            f"(expected {FORMAT_VERSION})"
        )
    try:
        header = bytes.fromhex(document["header"])
        image = bytes.fromhex(document["image"])
        file_firmware = int(document["identity"]["firmware"])
        entries = list(document["presets"])
    except (KeyError, TypeError, ValueError) as err:
        problems.append(f"malformed backup document: {err!r}")
        return problems
    if len(entries) != PRESET_COUNT:
        problems.append(f"expected {PRESET_COUNT} presets, found {len(entries)}")
    presets: dict[int, bytes] = {}
    for n, entry in enumerate(entries):
        try:
            index = int(entry["index"])
            raw = bytes.fromhex(entry["raw"])
        except (KeyError, TypeError, ValueError) as err:
            problems.append(f"preset entry {n} is malformed: {err!r}")
            continue
        if not 0 <= index < PRESET_COUNT:
            problems.append(f"preset entry {n} has index {index} (expected 0–{PRESET_COUNT - 1})")
            continue
        if index in presets:
            problems.append(f"preset index {index} (position {position(index)}) appears twice")
        if len(raw) != PRESET_SIZE:
            problems.append(
                f"preset {position(index)} has {len(raw)} bytes, expected {PRESET_SIZE} bytes"
            )
        presets[index] = raw
    expected_image = STORE_OFFSET + PRESET_SIZE * PRESET_COUNT
    if len(image) != expected_image:
        problems.append(f"image has {len(image)} bytes, expected {expected_image}")
    if header != EXPECTED_HEADER:
        problems.append(f"header {header.hex(' ') or '(empty)'} is not {EXPECTED_HEADER.hex(' ')}")
    if len(image) == expected_image and len(presets) == PRESET_COUNT:
        differing = [] if image[:STORE_OFFSET] == header else ["header"]
        for index, raw in sorted(presets.items()):
            start = STORE_OFFSET + PRESET_SIZE * index
            if image[start : start + PRESET_SIZE] != raw:
                differing.append(position(index))
        if differing:
            problems.append("image differs from header + presets at " + ", ".join(differing))
    if firmware is not None and file_firmware != firmware:
        problems.append(
            f"firmware_mismatch: the file is from firmware {file_firmware}, "
            f"the pedal runs {firmware}"
        )
    return problems
