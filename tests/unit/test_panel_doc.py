"""The group-enabled table in command-layer.md matches ``PANEL_GROUPS`` (spec 008 FR-030)."""

from __future__ import annotations

import pytest

from openvave.protocol import PANEL_GROUPS
from tests.support.bytemap_doc import COMMAND_LAYER

HEADING = "### Front panel"
NONE = "none"


def group_rows(text: str) -> list[list[str]]:
    """Rows of the first table under :data:`HEADING` (header and separator dropped)."""
    if HEADING not in text:
        raise ValueError(f"heading {HEADING!r} not found")
    after = text.split(HEADING, 1)[1].split("\n### ", 1)[0]
    lines = after.splitlines()
    start = next((i for i, line in enumerate(lines) if line.startswith("|")), None)
    if start is None:
        raise ValueError(f"no table under {HEADING!r}")
    rows = []
    for line in lines[start + 2 :]:
        if not line.startswith("|"):
            break
        rows.append([cell.strip().strip("`") for cell in line.strip().strip("|").split("|")])
    return rows


def doc_rows() -> list[list[str]]:
    return group_rows(COMMAND_LAYER.read_text(encoding="utf-8"))


def test_doc_table_equals_the_groups() -> None:
    expected = [
        [g.name, g.enabled_field or NONE, g.enabled_rule or NONE, g.enabled_confidence or NONE]
        for g in PANEL_GROUPS
    ]
    assert [row[:4] for row in doc_rows()] == expected


def test_six_rules() -> None:
    assert sum(1 for row in doc_rows() if row[1] != NONE) == 6


def test_gate_is_documented_and_cab_cites_session_c() -> None:
    rows = {row[0]: row for row in doc_rows()}
    assert rows["GATE"][3] == "documented"
    assert "gate session C" in rows["CAB"][4]


def test_missing_heading_is_an_error() -> None:
    with pytest.raises(ValueError, match="heading"):
        group_rows("nothing here")
