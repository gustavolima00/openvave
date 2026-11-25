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


def test_names_are_not_shown_on_a_bypass_side() -> None:
    """Codex round 2: in bypass the buffer is zeros, not a preset."""
    from openvave.cli.render import change_names_json, names_shown, watch_change_lines
    from openvave.models import PedalState, WatchChange

    normal = PedalState("normal", 1, 1, False)
    bypass = PedalState("bypass", None, None, False)
    assert names_shown(normal, bypass) == (True, False)
    assert names_shown(bypass, normal) == (False, True)
    assert names_shown(None, None) == (True, True)
    change = ByteChange(Region.CURRENT_PRESET, 5, 4, 0, ENTRIES["amp_type"], ())
    names = change_names_json(change, "old", "new", (True, False))
    assert names["position_name_old"] is not None
    assert names["position_name_new"] is None
    event = WatchChange(t=0.0, cycle=1, changes=(change,), regions={})
    (line,) = watch_change_lines(event, 0.0, (True, False))
    assert line.rstrip().endswith("→ #0")
    assert f"#4 ({POSITION_NAMES['amp_type'][4].text}" in line
