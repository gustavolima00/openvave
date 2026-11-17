"""Human output shows reverb decay the way the phone app does; JSON keeps the raw value."""

from __future__ import annotations

import pytest

from openvave._jsonform import field_json
from openvave.cli.render import app_reading, field_line
from openvave.models import Region
from openvave.protocol import BYTE_MAP
from openvave.protocol.decode import decode_field

ENTRIES = {e.name: e for e in BYTE_MAP if e.name is not None}


@pytest.mark.parametrize(
    ("raw", "text"),
    [
        (0, "blue 1"),
        (5, "blue 6"),
        (43, "blue X"),
        (44, "orange 1"),
        (86, "orange X"),
        (88, "green 1"),
        (127, "green 40"),
    ],
)
def test_reverb_decay_reading(raw: int, text: str) -> None:
    assert app_reading(decode_field(ENTRIES["reverb_decay"], raw)) == text


def test_other_fields_have_no_reading() -> None:
    for name in ("reverb_mix", "mod_fx", "delay_mix", "gain", "mode"):
        assert app_reading(decode_field(ENTRIES[name], 5)) is None


def test_out_of_range_has_no_reading() -> None:
    assert app_reading(decode_field(ENTRIES["reverb_decay"], 200)) is None


def test_field_line_appends_reading() -> None:
    line = field_line(decode_field(ENTRIES["reverb_decay"], 53))
    assert line.endswith("confirmed  app: orange 10")


def test_json_display_stays_raw() -> None:
    document = field_json(decode_field(ENTRIES["reverb_decay"], 53))
    assert document["display"] == "53"
    assert document["value"] == 53


def test_entries_are_from_the_preset_region() -> None:
    assert ENTRIES["reverb_decay"].region is Region.CURRENT_PRESET
