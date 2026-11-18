"""The "Write messages" doc table and ``WRITE_MESSAGES`` agree row for row (T024, research R4)."""

from __future__ import annotations

from openvave.protocol.writes import WRITE_MESSAGES, WriteMessage
from tests.integration.gate_fixtures import ALL_STEPS, RECORDED, ROW_STEPS, STEPS_BY_NAME
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
    altered = text[:start] + section.replace("| observed |", "| confirmed |", 1)
    assert altered != text
    rows = [row.key() for row in parse_table(altered)]
    assert rows != [code_key(m) for m in WRITE_MESSAGES]


def test_required_rows_exist() -> None:
    keys = {(row.kind, row.argument) for row in load_write_rows()}
    expected = {("knob_block", None), ("led_colour", None), ("preset_select", None), ("ack", None)}
    expected |= {("block_switch", k) for k in range(4)}
    expected |= {("bypass", None), ("loopback", None)}  # spec 004 M1
    expected |= {("stored_slot", None), ("commit", None), ("stored_image", None)}  # spec 004 M2
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
    bypass, loopback = rows[("bypass", None)], rows[("loopback", None)]
    assert (bypass.type, bypass.address, bypass.length) == (4, 0xE1000000, 1)
    assert (loopback.type, loopback.address, loopback.length) == (4, 0xD0000000, 1)


def test_bypass_and_loopback_are_observed_by_gate_session_a() -> None:
    # spec 004 T083: promoted by openvave's own sends in gate session A (check 2 stays in Notes)
    rows = {(row.kind, row.argument): row for row in load_write_rows()}
    for key, steps in (
        (("bypass", None), ("bypass",)),
        (("loopback", None), ("loopback_off", "loopback_on")),
    ):
        row = rows[key]
        assert (row.confidence, row.firmware) == ("observed", frozenset({96}))
        assert row.evidence == tuple(f"captures/fw96/20261118-gate-{s}.jsonl" for s in steps)


def test_persistent_rows_match_the_allowlist() -> None:
    rows = {(row.kind, row.argument): row for row in load_write_rows()}
    slot, commit, image = (rows[(k, None)] for k in ("stored_slot", "commit", "stored_image"))
    assert (slot.type, slot.address, slot.length) == (4, 0x2, 21)
    assert (commit.type, commit.address, commit.length) == (4, 0xF0000000, 0)
    assert (image.type, image.address, image.length) == (4, 0x0, 758)


def test_persistent_rows_are_observed_by_gate_session_a() -> None:
    # spec 004 T083: checks 3 and 4 (poc sends) stay in Notes; Evidence is openvave's gate
    rows = {(row.kind, row.argument): row for row in load_write_rows()}
    for kind, steps in (
        ("stored_slot", ("save", "restore_slot")),
        ("commit", ("save", "restore_slot", "image_noop", "restore_all")),
        ("stored_image", ("image_noop", "restore_all")),
    ):
        row = rows[(kind, None)]
        assert (row.confidence, row.firmware) == ("observed", frozenset({96}))
        assert row.evidence == tuple(f"captures/fw96/20261118-gate-{s}.jsonl" for s in steps)
        assert "persistent" in row.notes.lower()


def test_slot_address_cell_parses() -> None:
    from tests.support.writes_doc import parse_row

    cells = [
        "`stored_slot(i)`", "4", "`0x00000002 + 21·i`", "21", "21 bytes", "ACK",
        "hypothesis", "96", "—", "persistent",
    ]  # fmt: skip
    row = parse_row(cells)
    assert (row.kind, row.argument, row.address) == ("stored_slot", None, 2)


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


def _sessions(row: WriteRow) -> set[str]:
    """Gate sessions (``A``/``B``) of the excerpts a row cites."""
    by_file = {path: step for step, path in RECORDED.items()}
    session = {s.step: s.session for s in ALL_STEPS}
    return {session[by_file[p.rsplit("/", 1)[-1]]] for p in row.evidence}


def test_confirmed_rows_cite_two_gate_sessions() -> None:
    # spec 003 M3 (T062): two captures of one session are not "two independent sessions"
    confirmed = [row for row in load_write_rows() if row.confidence == "confirmed"]
    assert confirmed
    for row in confirmed:
        assert _sessions(row) >= {"A", "B"}, row.kind


def _spec004_rule(row: WriteRow) -> list[str]:
    """A spec 004 row above ``hypothesis`` must cite a committed 004 gate excerpt of its own
    steps (T070, FR-036): a poc check capture is not openvave's own send."""
    if row.kind not in ROW_STEPS or row.confidence not in ("observed", "confirmed"):
        return []
    by_file = {path: step for step, path in RECORDED.items()}
    cited = [by_file.get(p.rsplit("/", 1)[-1]) for p in row.evidence]
    ok = [
        step
        for step, path in zip(cited, row.evidence, strict=True)
        if step is not None
        and STEPS_BY_NAME[step].spec == "004"
        and step in ROW_STEPS[row.kind]
        and "-gate-" in path
        and (REPO_ROOT / path).is_file()
    ]
    return [] if ok else [f"{row.kind}: {row.confidence} without a 004 gate excerpt of its steps"]


def test_spec004_rows_cite_their_gate_excerpts() -> None:
    problems = [p for row in load_write_rows() for p in _spec004_rule(row)]
    assert problems == []


def test_spec004_rule_covers_the_five_rows() -> None:
    assert set(ROW_STEPS) == {"bypass", "loopback", "stored_slot", "commit", "stored_image"}
    check2 = "captures/fw96/20261117-check2-bypass.jsonl"
    poc = WriteRow("bypass", None, 4, 0xE1000000, 1, "observed", frozenset({96}), (check2,), "")
    assert _spec004_rule(poc) == ["bypass: observed without a 004 gate excerpt of its steps"]
    spec003 = "captures/fw96/20261117-gate-select.jsonl"
    wrong = WriteRow("commit", None, 4, 0xF0000000, 0, "observed", frozenset({96}), (spec003,), "")
    assert _spec004_rule(wrong)
    hypothesis = WriteRow("loopback", None, 4, 0xD0000000, 1, "hypothesis", frozenset({96}), (), "")
    assert _spec004_rule(hypothesis) == []
