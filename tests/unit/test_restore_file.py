"""Restore input checks: ``restore_problems(document, firmware)`` (spec 004 FR-020, R10, T046)."""

from __future__ import annotations

from typing import Any

import pytest

from openvave.backup import restore_problems
from tests.support import restore_fixture as rf


def problems(document: dict[str, Any], firmware: int | None = 96) -> list[str]:
    return restore_problems(document, firmware)


def test_a_valid_synthetic_backup_has_none() -> None:
    assert problems(rf.document()) == []
    assert problems(rf.document(), None) == []


def test_wrong_format_version() -> None:
    doc = rf.document()
    doc["format_version"] = 2
    assert any("format_version" in p for p in problems(doc))


def test_wrong_kind() -> None:
    doc = rf.document()
    doc["kind"] = "something.else"
    assert any("kind" in p for p in problems(doc))


def test_35_presets() -> None:
    doc = rf.document()
    del doc["presets"][-1]
    assert any("36 presets" in p for p in problems(doc))


def test_a_20_byte_preset() -> None:
    doc = rf.document()
    doc["presets"][3]["raw"] = doc["presets"][3]["raw"][:-3]
    assert any("21 bytes" in p and "1D" in p for p in problems(doc))


def test_duplicate_position() -> None:
    doc = rf.document()
    doc["presets"][4]["index"] = 3
    assert any("index" in p or "position" in p for p in problems(doc))


def test_image_differs_from_header_and_presets() -> None:
    doc = rf.document()
    raw = bytearray.fromhex(doc["presets"][5]["raw"])
    raw[6] ^= 0x01
    doc["presets"][5]["raw"] = raw.hex(" ")
    found = problems(doc)
    assert any("image" in p and "2B" in p for p in found)


def test_header_00_00() -> None:
    image = bytes(2) + rf.sf.synthetic_image()[2:]
    found = problems(rf.document(image))
    assert any("header" in p and "a5 5a" in p for p in found)


def test_firmware_mismatch() -> None:
    doc = rf.document(firmware=97)
    assert any(p.startswith("firmware_mismatch") for p in problems(doc, 96))
    assert problems(doc, 97) == []
    assert problems(doc, None) == []  # not known before connecting


def test_malformed_hex() -> None:
    doc = rf.document()
    doc["image"] = "zz"
    assert problems(doc)


@pytest.mark.parametrize("key", ["image", "presets", "identity", "header"])
def test_missing_keys(key: str) -> None:
    doc = rf.document()
    del doc[key]
    assert problems(doc)
