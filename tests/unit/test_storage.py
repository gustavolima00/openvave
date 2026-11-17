"""Stored-image layout, positions and the closed StorageRead targets (T001)."""

from __future__ import annotations

import dataclasses

import pytest

from openvave.protocol.storage import (
    EXPECTED_HEADER,
    IMAGE_SIZE,
    PRESET_COUNT,
    PRESET_SIZE,
    STORE_OFFSET,
    StorageRead,
    parse_position,
    position,
)


def test_layout_constants() -> None:
    assert STORE_OFFSET == 2
    assert PRESET_SIZE == 21
    assert PRESET_COUNT == 36
    assert IMAGE_SIZE == 758
    assert EXPECTED_HEADER == bytes.fromhex("a55a")


@pytest.mark.parametrize(
    ("index", "text"), [(0, "1A"), (1, "1B"), (3, "1D"), (4, "2A"), (6, "2C"), (35, "9D")]
)
def test_position(index: int, text: str) -> None:
    assert position(index) == text
    assert parse_position(text) == index


@pytest.mark.parametrize("bad", [-1, 36])
def test_position_out_of_range(bad: int) -> None:
    with pytest.raises(ValueError):
        position(bad)


@pytest.mark.parametrize(("text", "index"), [("2c", 6), ("2C", 6), ("6", 6), ("0", 0), ("35", 35)])
def test_parse_position_accepts(text: str, index: int) -> None:
    assert parse_position(text) == index


@pytest.mark.parametrize("bad", ["10A", "1E", "0A", "36", "-1", "", " ", "2CC", "A2", "1.5"])
def test_parse_position_rejects(bad: str) -> None:
    with pytest.raises(ValueError):
        parse_position(bad)


def test_storage_read_targets() -> None:
    header = StorageRead.header()
    assert (header.type, header.address, header.length, header.index) == (4, 0, 2, None)
    preset = StorageRead.preset(6)
    assert (preset.type, preset.address, preset.length, preset.index) == (4, 2 + 21 * 6, 21, 6)
    last = StorageRead.preset(35)
    assert last.address + last.length == 758
    image = StorageRead.image()
    assert (image.type, image.address, image.length, image.index) == (4, 0, 758, None)


@pytest.mark.parametrize("bad", [36, -1])
def test_storage_read_preset_range(bad: int) -> None:
    with pytest.raises(ValueError):
        StorageRead.preset(bad)


def test_storage_read_has_no_address_constructor() -> None:
    with pytest.raises(TypeError):
        StorageRead(4, 0x10, 21, None)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        StorageRead(type=4, address=0x10, length=21, index=None)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        dataclasses.replace(StorageRead.header(), address=0x10)


def test_storage_read_frozen_and_comparable() -> None:
    assert StorageRead.preset(3) == StorageRead.preset(3)
    with pytest.raises(dataclasses.FrozenInstanceError):
        StorageRead.header().address = 4  # type: ignore[misc]
