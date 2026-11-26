"""The front panel as data (spec 008 US2, FR-010–FR-015, SC-003).

The order is read from the drawing's own description text, so the drawing and the data cannot
drift; labels and groups are the table of research R5.
"""

from __future__ import annotations

import dataclasses
import re

import pytest

from openvave.models import Encoding, Region
from openvave.protocol import BYTE_MAP, PANEL_CONTROLS, PanelControl, panel_control
from tests.support.captures import REPO_ROOT

DRAWING = REPO_ROOT / "docs" / "images" / "tankg-controls.svg"

R5 = [
    ("MASTER", "MASTER", "knob", None, None),
    ("IR CAB", "CAB", "selector", "ir_cab", 17),
    ("RVB MIX", "REVERB", "knob", "reverb_mix", 16),
    ("RVB DECAY", "REVERB", "knob", "reverb_decay", 15),
    ("DLY TIME", "DELAY", "knob", "delay_time", 14),
    ("DLY MIX", "DELAY", "knob", "delay_mix", 13),
    ("MOD SPEED", "MOD", "knob", "mod_speed", 12),
    ("MOD FX", "MOD", "knob", "mod_fx", 11),
    ("VOLUME", "AMP", "knob", "volume", 10),
    ("BASS", "AMP", "knob", "bass", 9),
    ("MIDDLE", "AMP", "knob", "middle", 8),
    ("TREBLE", "AMP", "knob", "treble", 7),
    ("GAIN", "AMP", "knob", "gain", 6),
    ("TYPE", "AMP", "selector", "amp_type", 5),
    ("NOISE GATE", "GATE", "knob", "noise_gate", 4),
    ("A/REVERB", "REVERB", "footswitch", "reverb_on", 3),
    ("B/DELAY", "DELAY", "footswitch", "delay_on", 2),
    ("C/MOD", "MOD", "footswitch", "mod_on", 1),
    ("D/AMP", "AMP", "footswitch", "amp_on", 0),
]
KIND = {Encoding.CONTINUOUS: "knob", Encoding.SELECTOR: "selector", Encoding.SWITCH: "footswitch"}
LED = {"led_red", "led_green", "led_blue"}


def drawing_order() -> list[str]:
    """Field names in the order of the ``<desc>`` text of the drawing (``master`` for MASTER)."""
    text = DRAWING.read_text(encoding="utf-8")
    match = re.search(r"<desc[^>]*>(.*?)</desc>", text, re.S)
    assert match is not None, "the drawing has no <desc>"
    return re.findall(r"\b(master|[a-z]+_[a-z_]+)\b", match.group(1))


def test_nineteen_controls_with_order_equal_to_index() -> None:
    assert len(PANEL_CONTROLS) == 19
    assert [c.order for c in PANEL_CONTROLS] == list(range(19))


def test_order_equals_the_drawing() -> None:
    order = drawing_order()
    assert len(order) == 19
    assert [c.field or "master" for c in PANEL_CONTROLS] == order


def test_rows_equal_research_r5() -> None:
    assert [(c.label, c.group, c.kind, c.field, c.offset) for c in PANEL_CONTROLS] == R5


def test_every_front_panel_field_has_exactly_one_control() -> None:
    entries = [
        e
        for e in BYTE_MAP
        if e.region is Region.CURRENT_PRESET and e.encoding in KIND and e.name not in LED
    ]
    assert len(entries) == 17
    for entry in entries:
        matches = [c for c in PANEL_CONTROLS if c.field == entry.name]
        assert len(matches) == 1, entry.name
        assert matches[0].offset == entry.offset
        assert matches[0].kind == KIND[entry.encoding]
    assert {c.field for c in PANEL_CONTROLS if c.field} == {e.name for e in entries}


def test_master_is_the_only_control_without_a_byte() -> None:
    without = [c for c in PANEL_CONTROLS if c.field is None or c.offset is None]
    assert len(without) == 1
    assert without[0].order == 0 and without[0].label == "MASTER"
    assert without[0].field is None and without[0].offset is None


@pytest.mark.parametrize("control", PANEL_CONTROLS, ids=lambda c: c.label)
def test_lookup_by_field(control: PanelControl) -> None:
    if control.field is not None:
        assert panel_control(control.field) is control


@pytest.mark.parametrize("field", ["led_red", "led_green", "led_blue", "mode", "loopback", "nope"])
def test_lookup_without_a_control(field: str) -> None:
    assert panel_control(field) is None


def test_lookup_of_none() -> None:
    assert panel_control(None) is None


def test_panel_control_is_frozen() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        PANEL_CONTROLS[1].label = "X"  # type: ignore[misc]
