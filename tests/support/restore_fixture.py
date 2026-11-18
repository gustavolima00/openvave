"""Synthetic backups for the restore tests (spec 004 US4, T046/T047).

A backup built here holds the synthetic stored image of ``storage_fixture`` (preset 1B is the
public fw96 preset, every other preset synthetic), so no factory content reaches git (FR-037).
"""

from __future__ import annotations

import copy
from datetime import UTC, datetime
from typing import Any

from openvave.backup import stored_preset
from openvave.models import Backup, DeviceIdentity
from openvave.protocol import parse_identity
from tests.support import storage_fixture as sf


def identity(firmware: int = 96) -> DeviceIdentity:
    base = parse_identity(sf.QUERY_RX[6:-1])
    if firmware == base.firmware:
        return base
    return DeviceIdentity(raw=base.raw, name=base.name, firmware=firmware, firmware_untested=True)


def image_with(base: bytes | None = None, **slots: bytes) -> bytes:
    """The synthetic image (or ``base``) with some presets replaced (``s2=...`` → index 2)."""
    image = bytearray(sf.synthetic_image() if base is None else base)
    for name, data in slots.items():
        start = 2 + 21 * int(name[1:])
        image[start : start + 21] = data
    return bytes(image)


def backup(image: bytes | None = None, firmware: int = 96) -> Backup:
    """A valid :class:`Backup` of ``image`` (default: the synthetic image)."""
    image = sf.synthetic_image() if image is None else image
    return Backup(
        identity=identity(firmware),
        created_at=datetime(2026, 11, 18, 10, 0, tzinfo=UTC),
        header=image[:2],
        image=image,
        presets=tuple(
            stored_preset(i, image[2 + 21 * i : 23 + 21 * i], firmware) for i in range(36)
        ),
    )


def document(image: bytes | None = None, firmware: int = 96) -> dict[str, Any]:
    """The backup file document of :func:`backup` (a fresh deep copy each call)."""
    return copy.deepcopy(backup(image, firmware).to_document())
