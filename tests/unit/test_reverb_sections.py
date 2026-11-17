"""Reverb decay sections of preset byte 15 (command-layer.md "Reverb decay sections")."""

from __future__ import annotations

import json

import pytest

from openvave.models import Region
from openvave.protocol import (
    BYTE_MAP,
    REVERB_SECTION_SIZE,
    REVERB_SECTION_STEPS,
    REVERB_SECTIONS,
    reverb_decay_parts,
)
from tests.support import reverb_fixture as rf
from tests.support.bytemap_doc import load_reverb_readings, load_reverb_sections


def app_position(label: str) -> tuple[str, int | None]:
    section, position = label.split()
    return section, None if position == "X" else int(position)


def test_sections_cover_the_decay_byte() -> None:
    (decay,) = [e for e in BYTE_MAP if e.region is Region.CURRENT_PRESET and e.offset == 15]
    assert decay.name == "reverb_decay"
    assert (decay.min, decay.max) == (0, 127)
    seen = [reverb_decay_parts(raw)[0] for raw in range(128)]
    assert sorted(set(seen), key=REVERB_SECTIONS.index) == list(REVERB_SECTIONS)
    assert seen == sorted(seen, key=REVERB_SECTIONS.index)


@pytest.mark.parametrize(
    ("raw", "parts"),
    [
        (0, ("blue", 1)),
        (39, ("blue", 40)),
        (40, ("blue", None)),
        (43, ("blue", None)),
        (44, ("orange", 1)),
        (83, ("orange", 40)),
        (87, ("orange", None)),
        (88, ("green", 1)),
        (127, ("green", 40)),
    ],
)
def test_boundaries(raw: int, parts: tuple[str, int | None]) -> None:
    assert reverb_decay_parts(raw) == parts


@pytest.mark.parametrize("raw", [-1, 128, 255])
def test_out_of_range_is_refused(raw: int) -> None:
    with pytest.raises(ValueError, match="0-127"):
        reverb_decay_parts(raw)


def test_readings_decode_to_their_app_positions() -> None:
    for label, raw in rf.READINGS:
        assert reverb_decay_parts(raw) == app_position(label), label


def test_doc_section_table_equals_code() -> None:
    rows = load_reverb_sections()
    assert [r.section for r in rows] == list(REVERB_SECTIONS)
    for row in rows:
        values = range(row.raw[0], row.raw[1] + 1)
        numbered = [v for v in values if reverb_decay_parts(v)[1] is not None]
        crossed = [v for v in values if reverb_decay_parts(v)[1] is None]
        assert all(reverb_decay_parts(v)[0] == row.section for v in values), row
        assert (numbered[0], numbered[-1]) == row.numbered, row
        assert len(numbered) == REVERB_SECTION_STEPS
        assert ((crossed[0], crossed[-1]) if crossed else None) == row.x, row
        assert row.confidence == "observed"
    assert rows[0].raw == (0, REVERB_SECTION_SIZE - 1)
    assert rows[-1].raw[1] == 127


def test_doc_readings_equal_fixture() -> None:
    assert load_reverb_readings() == list(rf.READINGS)


def test_committed_capture_matches_generator() -> None:
    committed = [
        json.loads(line)
        for line in rf.REVERB_CAPTURE.read_text(encoding="utf-8").splitlines()
        if line
    ]
    assert committed == json.loads(json.dumps(rf.capture_lines()))
