"""The "Write messages" doc table and ``WRITE_MESSAGES`` agree row for row (T024, research R4)."""

from __future__ import annotations

from openvave.protocol.writes import WRITE_MESSAGES, WriteMessage
from tests.support.bytemap_doc import COMMAND_LAYER
from tests.support.captures import REPO_ROOT
from tests.support.writes_doc import HEADING, WriteRow, load_write_rows, parse_table


def code_key(m: WriteMessage) -> tuple[object, ...]:
    return (
        m.kind,
        m.argument,
        m.type,
        m.address,
        m.length,
        m.confidence,
        m.firmware,
        m.evidence,
    )


def test_doc_and_code_tables_are_equal() -> None:
    doc = [row.key() for row in load_write_rows()]
    code = [code_key(m) for m in WRITE_MESSAGES]
    assert doc == code


def test_an_altered_doc_is_detected() -> None:
    text = COMMAND_LAYER.read_text(encoding="utf-8")
    start = text.index(HEADING)
    section = text[start:]
    altered = text[:start] + section.replace("| hypothesis |", "| observed |", 1)
    assert altered != text
    rows = [row.key() for row in parse_table(altered)]
    assert rows != [code_key(m) for m in WRITE_MESSAGES]


def test_required_rows_exist() -> None:
    keys = {(row.kind, row.argument) for row in load_write_rows()}
    expected = {("knob_block", None), ("led_colour", None), ("preset_select", None), ("ack", None)}
    expected |= {("block_switch", k) for k in range(4)}
    assert expected <= keys


def test_targets_match_the_allowlist() -> None:
    rows = {(row.kind, row.argument): row for row in load_write_rows()}
    assert (rows[("knob_block", None)].address, rows[("knob_block", None)].length) == (
        0x10000004,
        14,
    )
    for k in range(4):
        row = rows[("block_switch", k)]
        assert (row.type, row.address, row.length) == (4, 0x10000000 + k, 1)
    assert (rows[("led_colour", None)].address, rows[("led_colour", None)].length) == (
        0x10000012,
        3,
    )
    assert rows[("preset_select", None)].address == 0xE0000000


def _evidence_rule(row: WriteRow) -> list[str]:
    problems = [p for p in row.evidence if not (REPO_ROOT / p).is_file()]
    problems += [p for p in row.evidence if not p.startswith("captures/")]
    if row.confidence in ("observed", "confirmed") and not row.evidence:
        problems.append(f"{row.kind}: {row.confidence} without evidence")
    if row.confidence == "confirmed" and len(set(row.evidence)) < 2:
        problems.append(f"{row.kind}: confirmed with fewer than 2 captures")
    return problems


def test_evidence_rules() -> None:
    problems = [p for row in load_write_rows() for p in _evidence_rule(row)]
    assert problems == []


def test_evidence_rule_catches_unbacked_promotion() -> None:
    row = WriteRow("knob_block", None, 4, 0x10000004, 14, "confirmed", frozenset({96}), (), "")
    assert _evidence_rule(row)
