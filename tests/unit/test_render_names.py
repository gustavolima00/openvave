"""Amp type and IR cab names in human and JSON output (spec 007 US4, FR-012).

Expected texts are built from ``POSITION_NAMES`` so that switching lists stays a data change.
"""

from __future__ import annotations

import pytest

from openvave._jsonform import field_json
from openvave.cli.render import field_line, name_reading, with_reading
from openvave.models import ByteChange, Region
from openvave.protocol import BYTE_MAP
from openvave.protocol.decode import decode_field
from openvave.protocol.names import POSITION_NAMES, PositionName, position_name

ENTRIES = {e.name: e for e in BYTE_MAP if e.name is not None}


def short(name: PositionName) -> str:
    return name.text + (" ?" if name.confidence == "hypothesis" else "")


def long(name: PositionName) -> str:
    kind = "factory IR" if name.factory else name.detail
    return f"{name.text}, {kind} ({name.source}, {name.confidence})"


@pytest.mark.parametrize(
    ("field", "raw"),
    [(f, r) for f in ("amp_type", "ir_cab") for r in range(1, 9)] + [("amp_type", 0)],
)
def test_field_line_shows_the_name_and_keeps_the_raw_position(field: str, raw: int) -> None:
    name = position_name(field, raw)
    assert name is not None
    line = field_line(decode_field(ENTRIES[field], raw))
    assert f"#{raw}" in line
    assert line.endswith(f"confirmed  name: {long(name)}")
    assert name_reading(decode_field(ENTRIES[field], raw)) == long(name)


def test_cab_off_has_no_name() -> None:
    field = decode_field(ENTRIES["ir_cab"], 0)
    assert field.display == "off"
    assert name_reading(field) is None
    assert "name:" not in field_line(field)


def test_out_of_range_and_other_fields_have_no_name() -> None:
    assert name_reading(decode_field(ENTRIES["amp_type"], 9)) is None
    assert name_reading(decode_field(ENTRIES["gain"], 4)) is None


def test_with_reading_short_form() -> None:
    name = POSITION_NAMES["amp_type"][4]
    assert with_reading(decode_field(ENTRIES["amp_type"], 4)) == f"#4 ({short(name)})"
    assert with_reading(decode_field(ENTRIES["ir_cab"], 0)) == "off"
    assert with_reading(decode_field(ENTRIES["reverb_decay"], 53)) == "53 (spring 10)"
    assert with_reading(decode_field(ENTRIES["gain"], 60)) == "60"


def test_hypothesis_names_are_marked() -> None:
    assert short(POSITION_NAMES["ir_cab"][7]).endswith(" ?")


def test_json_adds_position_name_and_keeps_display_raw() -> None:
    name = POSITION_NAMES["ir_cab"][7]
    document = field_json(decode_field(ENTRIES["ir_cab"], 7))
    assert document["display"] == "#7"
    assert document["value"] == 7
    assert document["position_name"] == {
        "name": name.name,
        "detail": name.detail,
        "text": name.text,
        "factory": True,
        "source": name.source,
        "confidence": "hypothesis",
        "firmware": 96,
    }


def test_json_position_name_null_without_a_name() -> None:
    assert field_json(decode_field(ENTRIES["ir_cab"], 0))["position_name"] is None
    assert field_json(decode_field(ENTRIES["amp_type"], 200))["position_name"] is None
    assert "position_name" not in field_json(decode_field(ENTRIES["gain"], 60))


def test_change_names_for_json_carry_confidence_and_factory_flag() -> None:
    from openvave._jsonform import position_name_json
    from openvave.cli.render import change_names_json

    change = ByteChange(Region.CURRENT_PRESET, 5, 4, 8, ENTRIES["amp_type"], ())
    assert change_names_json(change, "old", "new") == {
        "position_name_old": position_name_json(POSITION_NAMES["amp_type"][4]),
        "position_name_new": position_name_json(POSITION_NAMES["amp_type"][8]),
    }
    gain = ByteChange(Region.CURRENT_PRESET, 6, 60, 90, ENTRIES["gain"], ())
    assert change_names_json(gain, "old", "new") == {}
    off = ByteChange(Region.CURRENT_PRESET, 17, 0, 7, ENTRIES["ir_cab"], ())
    names = change_names_json(off, "before", "after")
    assert names["position_name_before"] is None
    assert names["position_name_after"]["factory"] is True
    assert names["position_name_after"]["confidence"] == POSITION_NAMES["ir_cab"][7].confidence


def test_names_are_not_shown_on_the_bypass_placeholder() -> None:
    """Codex rounds 2 and 3: the bypass buffer (21 zero bytes) is not a preset."""
    from openvave.cli.render import (
        change_names_json,
        is_placeholder,
        names_for,
        names_for_event,
        region_json,
        watch_change_lines,
    )
    from openvave.models import RegionRead, WatchChange
    from openvave.protocol.decode import decode_region

    preset = bytes.fromhex("01 00 00 01 0f 04 3c 3c 46 32 32 00 00 00 00 05 04 07 43 16 43")
    zeros = bytes(21)
    assert is_placeholder(zeros) and not is_placeholder(preset) and not is_placeholder(None)
    assert not is_placeholder(bytes(4))  # a zero global block is not the edit buffer
    assert names_for(preset, zeros) == (True, False)
    assert names_for(zeros, preset) == (False, True)
    assert names_for(None, None) == (True, True)

    change = ByteChange(Region.CURRENT_PRESET, 5, 4, 0, ENTRIES["amp_type"], ())
    names = change_names_json(change, "old", "new", (True, False))
    assert names["position_name_old"] is not None
    assert names["position_name_new"] is None

    regions = {Region.CURRENT_PRESET: decode_region(RegionRead(Region.CURRENT_PRESET, zeros), 96)}
    event = WatchChange(t=0.0, cycle=1, changes=(change,), regions=regions)
    assert names_for_event(event) == (True, False)  # before = zeros with amp 4: a preset side
    (line,) = watch_change_lines(event, 0.0, names_for_event(event))
    assert line.rstrip().endswith("→ #0")
    assert f"#4 ({POSITION_NAMES['amp_type'][4].text}" in line

    fields = {
        f["name"]: f for f in region_json(RegionRead(Region.CURRENT_PRESET, zeros), 96)["fields"]
    }
    assert fields["amp_type"]["position_name"] is None
    named = {
        f["name"]: f for f in region_json(RegionRead(Region.CURRENT_PRESET, preset), 96)["fields"]
    }
    assert named["amp_type"]["position_name"] is not None


def test_text_dump_of_the_placeholder_buffer_has_no_names() -> None:
    """Codex round 4: text and JSON agree on the all-zero buffer (also when unrecognised)."""
    from openvave.cli.render import field_lines
    from openvave.models import RegionRead
    from openvave.protocol.decode import decode_region

    zeros = decode_region(RegionRead(Region.CURRENT_PRESET, bytes(21)), 96)
    assert not any("name:" in line for line in field_lines(zeros))
    assert any(line.rstrip().endswith("selector   confirmed") for line in field_lines(zeros))
