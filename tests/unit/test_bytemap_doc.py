"""The ``command-layer.md`` byte map table equals ``BYTE_MAP`` (research R1, Constitution I)."""

from __future__ import annotations

import pytest

from openvave.models import ByteMapEntry, Region
from openvave.protocol import BYTE_MAP
from tests.support.bytemap_doc import COMMAND_LAYER, DocRow, parse_table

REGION_NAMES = {Region.GLOBAL: "global", Region.CURRENT_PRESET: "preset", Region.STATUS: "status"}


def code_key(e: ByteMapEntry) -> tuple[object, ...]:
    return (
        REGION_NAMES[e.region],
        e.offset,
        e.mask,
        e.name,
        e.encoding.value,
        e.min,
        e.max,
        e.on_value,
        e.off_value,
        e.control,
        e.confidence,
        e.firmware,
        e.evidence,
    )


def compare(doc_rows: list[DocRow]) -> list[str]:
    """Human-readable differences; empty when doc and code agree."""
    doc = {r.key() for r in doc_rows}
    code = {code_key(e) for e in BYTE_MAP}
    problems = [f"only in doc:  {row}" for row in sorted(doc - code, key=repr)]
    problems += [f"only in code: {row}" for row in sorted(code - doc, key=repr)]
    if len(doc_rows) != len(doc):
        problems.append("duplicate rows in doc table")
    return problems


def doc_text() -> str:
    return COMMAND_LAYER.read_text(encoding="utf-8")


def test_doc_table_equals_byte_map() -> None:
    rows = parse_table(doc_text())
    assert len(rows) == len(BYTE_MAP)
    assert compare(rows) == []


def test_altered_doc_is_detected() -> None:
    text = doc_text()
    rows = parse_table(text)
    decay = next(r for r in rows if r.name == "reverb_decay")
    line = next(
        line
        for line in text.splitlines()
        if line.startswith("| preset | 15 |") and "`reverb_decay`" in line
    )
    altered = text.replace(line, line.replace("| 0–127 |", "| 0–100 |", 1))
    assert altered != text
    problems = compare(parse_table(altered))
    assert problems
    assert any("only in doc" in p and "reverb_decay" in p and "100" in p for p in problems)
    assert decay.max == 127


def test_missing_heading_is_an_error() -> None:
    with pytest.raises(ValueError, match="heading"):
        parse_table(doc_text().replace("### Preset / global byte map", "### Something else"))
