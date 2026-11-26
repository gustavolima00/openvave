"""Panel groups and whether each is enabled (spec 008 US2, FR-026–FR-029, SC-008).

The expected answers are computed here from the raw byte, independently of the library, for every
current-preset read of the committed captures that exercise the rules.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from openvave.models import Region
from openvave.protocol import (
    BYTE_MAP,
    PANEL_CONTROLS,
    PANEL_GROUPS,
    PanelGroup,
    group_enabled,
    panel_group,
)
from tests.support.captures import CAPTURES_DIR, FW96_CONNECT, load_capture

R11 = [
    ("MASTER", None, None, None),
    ("CAB", "ir_cab", "nonzero", "confirmed"),
    ("REVERB", "reverb_on", "switch", "confirmed"),
    ("DELAY", "delay_on", "switch", "confirmed"),
    ("MOD", "mod_on", "switch", "confirmed"),
    ("AMP", "amp_on", "switch", "confirmed"),
    ("GATE", "noise_gate", "nonzero", "documented"),
]
OFFSET = {"ir_cab": 17, "reverb_on": 3, "delay_on": 2, "mod_on": 1, "amp_on": 0, "noise_gate": 4}
"""Preset bytes, from ``specs/protocol/command-layer.md`` (written here, not read from the code)."""

FW96 = CAPTURES_DIR / "fw96"
STEP_CAPTURES = [
    FW96 / f"20261116-step-{field}{suffix}.jsonl"
    for field in ("amp_on", "mod_on", "delay_on", "reverb_on", "ir_cab", "noise_gate")
    for suffix in ("", "-1917")
]
PRESET_ECHO = bytes([4]) + (0x10000000).to_bytes(4, "little") + (21).to_bytes(3, "little")


def preset_reads(path: Path) -> list[bytes]:
    """Every 21-byte current-preset reply of a capture, found by its echo (not by its label)."""
    found = []
    for frames in load_capture(path).all_rx.values():
        for frame in frames:
            if frame[2] == 0x23 and frame[6:14] == PRESET_ECHO:
                found.append(frame[14:-1])
    return found


def expected(name: str, preset: bytes) -> bool | None:
    """The rule of research R11, applied to the raw byte."""
    if not any(preset):
        return None
    if name == "MASTER":
        return None
    if name in ("CAB", "GATE"):
        return preset[OFFSET["ir_cab" if name == "CAB" else "noise_gate"]] != 0
    byte = preset[OFFSET[f"{name.lower()}_on"]]
    return {1: True, 0: False}.get(byte)


def test_seven_groups_in_panel_order() -> None:
    assert [g.order for g in PANEL_GROUPS] == list(range(7))
    assert [g.name for g in PANEL_GROUPS] == [
        "MASTER",
        "CAB",
        "REVERB",
        "DELAY",
        "MOD",
        "AMP",
        "GATE",
    ]
    first_seen = list(dict.fromkeys(c.group for c in PANEL_CONTROLS))
    assert [g.name for g in PANEL_GROUPS] == first_seen


def test_every_control_group_is_a_group() -> None:
    names = {g.name for g in PANEL_GROUPS}
    assert {c.group for c in PANEL_CONTROLS} <= names


def test_rows_equal_research_r11() -> None:
    rows = [(g.name, g.enabled_field, g.enabled_rule, g.enabled_confidence) for g in PANEL_GROUPS]
    assert rows == R11


@pytest.mark.parametrize("group", PANEL_GROUPS, ids=lambda g: g.name)
def test_field_belongs_to_its_group_and_the_three_go_together(group: PanelGroup) -> None:
    trio = (group.enabled_field, group.enabled_rule, group.enabled_confidence)
    assert all(v is None for v in trio) or all(v is not None for v in trio)
    if group.enabled_field is not None:
        owners = [c for c in PANEL_CONTROLS if c.field == group.enabled_field]
        assert [c.group for c in owners] == [group.name]


def test_switch_values_are_the_byte_map_values() -> None:
    entries = {e.name: e for e in BYTE_MAP if e.region is Region.CURRENT_PRESET}
    preset = bytearray(21)
    preset[6] = 60  # not the bypass placeholder
    for group in PANEL_GROUPS:
        if group.enabled_rule != "switch":
            continue
        assert group.enabled_field is not None
        entry = entries[group.enabled_field]
        assert entry.offset == OFFSET[group.enabled_field]
        assert entry.on_value is not None and entry.off_value is not None
        preset[entry.offset] = entry.on_value
        assert group_enabled(group.name, bytes(preset)) is True
        preset[entry.offset] = entry.off_value
        assert group_enabled(group.name, bytes(preset)) is False


@pytest.mark.parametrize(
    "path", [FW96_CONNECT, *STEP_CAPTURES], ids=lambda p: Path(p).name.removesuffix(".jsonl")
)
def test_answers_equal_the_rule_on_every_recorded_preset(path: Path) -> None:
    presets = preset_reads(path)
    assert presets, f"{path} has no preset read"
    for preset in presets:
        for group in PANEL_GROUPS:
            assert group_enabled(group.name, preset) == expected(group.name, preset), (
                group.name,
                preset.hex(" "),
            )


def test_the_step_captures_reach_both_answers() -> None:
    """The captures exercise off and on for each rule, not one side only."""
    seen: dict[str, set[bool | None]] = {}
    for path in STEP_CAPTURES:
        for preset in preset_reads(path):
            for group in PANEL_GROUPS:
                seen.setdefault(group.name, set()).add(group_enabled(group.name, preset))
    for name in ("CAB", "REVERB", "DELAY", "MOD", "AMP", "GATE"):
        assert {True, False} <= seen[name], name


def test_example_preset() -> None:
    preset = bytearray(load_capture(FW96_CONNECT).rx("preset t4 0x10000000 x21")[14:-1])
    preset[2], preset[17], preset[4] = 0, 3, 0
    data = bytes(preset)
    assert group_enabled("DELAY", data) is False
    assert group_enabled("CAB", data) is True
    assert group_enabled("GATE", data) is False
    assert group_enabled("MASTER", data) is None


def test_switch_byte_neither_on_nor_off() -> None:
    preset = bytearray(load_capture(FW96_CONNECT).rx("preset t4 0x10000000 x21")[14:-1])
    preset[OFFSET["delay_on"]] = 2
    assert group_enabled("DELAY", bytes(preset)) is None


@pytest.mark.parametrize("group", PANEL_GROUPS, ids=lambda g: g.name)
def test_bypass_placeholder_gives_no_answer(group: PanelGroup) -> None:
    assert group_enabled(group.name, bytes(21)) is None


@pytest.mark.parametrize("name", ["EQ", "amp", "Gate", ""])
def test_unknown_group(name: str) -> None:
    with pytest.raises(ValueError):
        group_enabled(name, bytes(range(21)))


@pytest.mark.parametrize("size", [0, 20, 22])
def test_wrong_length(size: int) -> None:
    with pytest.raises(ValueError):
        group_enabled("AMP", bytes([1]) * size)


def test_lookup() -> None:
    for group in PANEL_GROUPS:
        assert panel_group(group.name) is group
    assert panel_group("amp") is None
    assert panel_group("EQ") is None


def test_panel_group_is_frozen() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        PANEL_GROUPS[0].name = "X"  # type: ignore[misc]


def test_memoryview_is_counted_in_bytes() -> None:
    wide = memoryview(bytes(range(42))).cast("H")
    assert len(wide) == 21
    with pytest.raises(ValueError):
        group_enabled("AMP", wide)  # type: ignore[arg-type]
    assert group_enabled("AMP", memoryview(bytes([1] + [60] * 20))) is True


def test_not_bytes() -> None:
    with pytest.raises(ValueError):
        group_enabled("AMP", 21)  # type: ignore[arg-type]
