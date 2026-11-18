"""Human output shows reverb decay as type and position (manual: ROOM, SPRING, CLOUD); JSON
keeps the raw value."""

from __future__ import annotations

import pytest

from openvave._jsonform import field_json
from openvave.cli.render import field_line, type_reading
from openvave.models import Region
from openvave.protocol import BYTE_MAP
from openvave.protocol.decode import decode_field

ENTRIES = {e.name: e for e in BYTE_MAP if e.name is not None}


@pytest.mark.parametrize(
    ("raw", "text"),
    [
        (0, "room 1"),
        (5, "room 6"),
        (43, "off"),
        (44, "spring 1"),
        (86, "off"),
        (88, "cloud 1"),
        (127, "cloud 40"),
    ],
)
def test_reverb_decay_reading(raw: int, text: str) -> None:
    assert type_reading(decode_field(ENTRIES["reverb_decay"], raw)) == text


def test_other_fields_have_no_reading() -> None:
    for name in ("reverb_mix", "gain", "mode", "mod_speed", "delay_time"):
        assert type_reading(decode_field(ENTRIES[name], 5)) is None


def test_out_of_range_has_no_reading() -> None:
    assert type_reading(decode_field(ENTRIES["reverb_decay"], 200)) is None


def test_field_line_appends_reading() -> None:
    line = field_line(decode_field(ENTRIES["reverb_decay"], 53))
    assert line.endswith("confirmed  type: spring 10")


def test_json_display_stays_raw() -> None:
    document = field_json(decode_field(ENTRIES["reverb_decay"], 53))
    assert document["display"] == "53"
    assert document["value"] == 53


def test_entries_are_from_the_preset_region() -> None:
    assert ENTRIES["reverb_decay"].region is Region.CURRENT_PRESET


@pytest.mark.parametrize(
    ("name", "raw", "text"),
    [("mod_fx", 63, "phaser 20"), ("mod_fx", 41, "off"), ("delay_mix", 127, "dual 40")],
)
def test_mod_and_delay_readings(name: str, raw: int, text: str) -> None:
    assert type_reading(decode_field(ENTRIES[name], raw)) == text
