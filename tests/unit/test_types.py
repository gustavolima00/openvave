"""Knob types: reverb decay as ROOM / SPRING / CLOUD (Tank-G manual; spec 004 R3, FR-003/FR-004).

The manual says the RVB DECAY knob runs through three processes, ROOM, SPRING, CLOUD, and that
the knob between two processes turns the reverb off. The measured split (raw ``// 44``, 40
positions each, 4 raw values between) is in ``test_reverb_sections.py``.
"""

from __future__ import annotations

import pytest

from openvave.protocol import (
    REVERB_SECTIONS,
    REVERB_TYPES,
    TYPED_FIELDS,
    reverb_decay_parts,
    type_parts,
    type_raw,
)


@pytest.mark.parametrize(
    ("type_name", "position", "raw"),
    [
        ("room", 1, 0),
        ("room", 40, 39),
        ("spring", 1, 44),
        ("spring", 10, 53),
        ("spring", 40, 83),
        ("cloud", 1, 88),
        ("cloud", 40, 127),
    ],
)
def test_type_raw(type_name: str, position: int, raw: int) -> None:
    assert type_raw("reverb_decay", type_name, position) == raw
    assert type_parts("reverb_decay", raw) == (type_name, position)


@pytest.mark.parametrize("raw", [40, 41, 42, 43, 84, 85, 86, 87])
def test_between_types_is_off(raw: int) -> None:
    assert type_parts("reverb_decay", raw) == (None, None)


def test_round_trip_for_every_type_and_position() -> None:
    pairs = [(t, p) for t in REVERB_TYPES for p in range(1, 41)]
    assert len(pairs) == 120
    for type_name, position in pairs:
        assert type_parts("reverb_decay", type_raw("reverb_decay", type_name, position)) == (
            type_name,
            position,
        )


def test_types_follow_the_app_colours_in_knob_order() -> None:
    """Manual order (ROOM, SPRING, CLOUD) = measured section order (blue, orange, green)."""
    assert REVERB_TYPES == ("room", "spring", "cloud")
    for raw in range(128):
        colour, position = reverb_decay_parts(raw)
        expected = REVERB_TYPES[REVERB_SECTIONS.index(colour)] if position is not None else None
        assert type_parts("reverb_decay", raw) == (expected, position)


def test_type_name_is_case_insensitive() -> None:
    assert type_raw("reverb_decay", "Spring", 10) == type_raw("reverb_decay", "SPRING", 10) == 53


@pytest.mark.parametrize(
    ("field", "type_name", "position"),
    [
        ("reverb_decay", "hall", 1),
        ("reverb_decay", "orange", 1),  # app colours are not types
        ("reverb_decay", "room", 0),
        ("reverb_decay", "room", 41),
        ("gain", "room", 1),
        ("mod_fx", "room", 1),  # each knob has its own types
    ],
)
def test_bad_input_is_refused(field: str, type_name: str, position: int) -> None:
    with pytest.raises(ValueError):
        type_raw(field, type_name, position)


@pytest.mark.parametrize("raw", [-1, 128])
def test_type_parts_range(raw: int) -> None:
    with pytest.raises(ValueError):
        type_parts("reverb_decay", raw)


def test_typed_fields() -> None:
    assert dict(TYPED_FIELDS) == {
        "mod_fx": ("chorus", "phaser", "tremolo"),
        "delay_mix": ("analog", "tape", "dual"),
        "reverb_decay": REVERB_TYPES,
    }


# -- MOD FX and DLY MIX (spec 004 T022: app readings, 2026-11-17) ------------------------------


MOD_TYPES = ("chorus", "phaser", "tremolo")
DELAY_TYPES = ("analog", "tape", "dual")
COLOURS = {"blue": 0, "orange": 1, "green": 2}


def test_mod_fx_and_delay_mix_have_their_manual_types() -> None:
    assert TYPED_FIELDS["mod_fx"] == MOD_TYPES
    assert TYPED_FIELDS["delay_mix"] == DELAY_TYPES


@pytest.mark.parametrize("field", ["mod_fx", "delay_mix"])
def test_app_readings_decode_to_their_types(field: str) -> None:
    from tests.support import knob_types_fixture as kf

    types = TYPED_FIELDS[field]
    for app, raw in kf.READINGS[field]:
        colour, position = app.split()
        expected = (None, None) if position == "X" else (types[COLOURS[colour]], int(position))
        assert type_parts(field, raw) == expected, (field, app, raw)


def test_committed_knob_types_capture_matches_generator() -> None:
    import json

    from tests.support import knob_types_fixture as kf

    committed = [
        json.loads(line)
        for line in kf.KNOB_TYPES_CAPTURE.read_text(encoding="utf-8").splitlines()
        if line
    ]
    assert committed == json.loads(json.dumps(kf.capture_lines()))


@pytest.mark.parametrize(
    ("field", "type_name", "position", "raw"),
    [
        ("mod_fx", "chorus", 1, 0),
        ("mod_fx", "phaser", 20, 63),
        ("mod_fx", "tremolo", 40, 127),
        ("delay_mix", "analog", 40, 39),
        ("delay_mix", "tape", 1, 44),
        ("delay_mix", "dual", 1, 88),
    ],
)
def test_type_raw_for_mod_and_delay(field: str, type_name: str, position: int, raw: int) -> None:
    assert type_raw(field, type_name, position) == raw
