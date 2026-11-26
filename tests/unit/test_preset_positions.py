"""Strict preset position helpers (spec 008 US3, FR-016–FR-020, SC-004)."""

from __future__ import annotations

from typing import Any

import pytest

import openvave
import openvave.protocol
from openvave import PedalState, preset_index, preset_position
from openvave.protocol.storage import parse_position, position


@pytest.mark.parametrize("index", range(36))
def test_agrees_with_pedal_state(index: int) -> None:
    expected = PedalState(kind="normal", index=index, bank=index // 4).position
    assert preset_position(index) == expected
    assert preset_index(preset_position(index)) == index


def test_examples() -> None:
    assert preset_index("1A") == 0
    assert preset_index("2C") == 6
    assert preset_index("9D") == 35
    assert preset_position(6) == "2C"


@pytest.mark.parametrize(
    "value", ["0A", "10A", "1E", "", "1a", " 1A", "1A ", "6", 6, None, b"1A", "2c", "1A\n"]
)
def test_preset_index_rejects(value: Any) -> None:
    with pytest.raises(ValueError):
        preset_index(value)


@pytest.mark.parametrize("value", [-1, 36, True, False, 1.0, "1", None])
def test_preset_position_rejects(value: Any) -> None:
    with pytest.raises(ValueError):
        preset_position(value)


def test_exported_from_both_namespaces() -> None:
    assert openvave.preset_index is openvave.protocol.preset_index
    assert openvave.preset_position is openvave.protocol.preset_position
    assert "preset_index" in openvave.__all__ and "preset_position" in openvave.__all__


def test_internal_helpers_unchanged() -> None:
    assert parse_position("2c") == 6
    assert parse_position("6") == 6
    assert position(6) == "2C"
    with pytest.raises(TypeError):
        position("6")  # type: ignore[arg-type]
