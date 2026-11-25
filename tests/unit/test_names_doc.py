"""The names table in command-layer.md and the evidence record match ``protocol/names.py``."""

from __future__ import annotations

import re

import pytest

from openvave.protocol.names import (
    EVIDENCE,
    NAME_SOURCES,
    NAMED_FIELDS,
    POSITION_NAMES,
    source_list,
)
from tests.support.bytemap_doc import COMMAND_LAYER
from tests.support.captures import REPO_ROOT

HEADING = "### Amp type and IR cab names"


def names_rows(text: str) -> list[list[str]]:
    """Rows of the first table under :data:`HEADING` (header and separator dropped)."""
    if HEADING not in text:
        raise ValueError(f"heading {HEADING!r} not found")
    after = text.split(HEADING, 1)[1]
    lines = after.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("|"))
    rows = []
    for line in lines[start + 2 :]:
        if not line.startswith("|"):
            break
        rows.append([cell.strip().strip("`") for cell in line.strip().strip("|").split("|")])
    return rows


def expected_rows() -> list[list[str]]:
    rows = []
    for field in NAMED_FIELDS:
        for raw in range(9):
            name = POSITION_NAMES[field].get(raw)
            if name is None:
                continue
            rows.append(
                [
                    field,
                    str(raw),
                    name.name,
                    name.detail,
                    "factory IR" if name.factory else "—",
                    name.source,
                    name.confidence,
                ]
            )
    return rows


def test_doc_table_equals_the_names_table() -> None:
    assert names_rows(COMMAND_LAYER.read_text(encoding="utf-8")) == expected_rows()


def test_missing_heading_is_an_error() -> None:
    with pytest.raises(ValueError, match="heading"):
        names_rows("nothing here")


def _evidence_rows() -> set[tuple[str, ...]]:
    text = (REPO_ROOT / EVIDENCE).read_text(encoding="utf-8")
    rows = set()
    for line in text.splitlines():
        if line.startswith("|"):
            rows.add(tuple(cell.strip() for cell in line.strip().strip("|").split("|")))
    return rows


@pytest.mark.parametrize("source", ["manual-am3", "manual-2024"])
def test_manual_names_are_transcribed_in_the_evidence_record(source: str) -> None:
    """Each manual name is a row of the record: printed slot, "Based on <name>", type."""
    rows = _evidence_rows()
    printed = {"clean": "Clean", "overdrive": "Overdrive", "distortion": "Dist"}
    for raw, item in enumerate(source_list(source, "amp_type")):
        assert item is not None
        assert (str(raw + 1), f"Based on {item[0]}", printed[item[1]]) in rows, item
    for raw, item in enumerate(source_list(source, "ir_cab")):
        if item is None:
            assert (str(raw), "The IR CAB turn off", "None") in rows
            continue
        assert (str(raw), f"Based on {item[0]}", item[1]) in rows, item


def test_card_names_are_transcribed_in_the_evidence_record() -> None:
    text = (REPO_ROOT / EVIDENCE).read_text(encoding="utf-8")
    for field in NAMED_FIELDS:
        for raw, item in enumerate(source_list("preset-card-2026", field)):
            if item is None:
                continue
            code = re.split(r" \(", item[0])[0]
            number = raw + 1 if field == "amp_type" else raw
            assert f"| {number}{code} |" in text, (field, raw, code)


def test_every_source_is_cited_in_the_evidence_record() -> None:
    text = (REPO_ROOT / EVIDENCE).read_text(encoding="utf-8")
    assert "TANK-G NEW PRESET" in text
    assert "figure 5" in text and "figure 6" in text
    assert set(NAME_SOURCES) == {"manual-am3", "manual-2024", "preset-card-2026"}
    assert "UWE-Twins 335" in text and "amps_da_tank_g" in text
