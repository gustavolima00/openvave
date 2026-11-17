"""Spec 004 check 2 evidence: the app's BYPASS write on fw 96 (one session, 2026-11-17).

Pedal on 1B in normal mode: ``01`` to ``0xE1000001`` (ACK), then select 1B. Read straight from
the committed frames (no ``openvave`` decoding). The bypass frame is not in openvave's write
allowlist, so the excerpt is not a ``-gate-`` file; this test checks it instead.
"""

from __future__ import annotations

import json

from tests.integration.gate_fixtures import FW96
from tests.support.audit import unsafe_frames

EXCERPT = FW96 / "20261117-check2-bypass.jsonl"
ACK = bytes.fromhex("00 59 00 01 00 00 00 ff")
BYPASS_1B = bytes.fromhex("00 59 22 09 00 00 04 01 00 00 e1 01 00 00 01 17")
SELECT_1B = bytes.fromhex("00 59 22 09 00 00 04 01 00 00 e0 01 00 00 01 18")
GLOBAL_READ = bytes.fromhex("00 59 23 08 00 00 04 00 00 00 20 04 00 00 d7")
BUFFER_READ = bytes.fromhex("00 59 23 08 00 00 04 00 00 00 10 15 00 00 d6")
STATUS_READ = bytes.fromhex("00 59 23 08 00 00 04 00 00 00 d0 01 00 00 2a")
STORED_1B = bytes.fromhex("01 00 00 01 0f 04 3c 3c 46 32 32 00 00 00 00 05 04 07 43 16 43")


def exchanges() -> list[tuple[bytes, bytes]]:
    records = [json.loads(line) for line in EXCERPT.read_text().splitlines()]
    assert records[0]["event"] == "meta" and records[0]["firmware"] == 96
    out: list[tuple[bytes, bytes]] = []
    request: bytes | None = None
    for r in records[1:]:
        if r["event"] == "tx":
            request = bytes.fromhex(r["hex"])
        elif r["event"] == "rx":
            assert request is not None
            out.append((request, bytes.fromhex(r["hex"])))
            request = None
    return out


def reads(pairs: list[tuple[bytes, bytes]], request: bytes, lo: int, hi: int) -> list[bytes]:
    return [rx[14:-1] for i, (tx, rx) in enumerate(pairs) if tx == request and lo < i < hi]


def test_bypass_zeroes_the_buffer_and_select_restores() -> None:
    pairs = exchanges()
    writes = [i for i, (tx, _) in enumerate(pairs) if tx[2] == 0x22]
    assert [pairs[i][0] for i in writes] == [BYPASS_1B, SELECT_1B]
    assert all(pairs[i][1] == ACK for i in writes)
    w1, w2 = writes
    end = len(pairs)

    assert set(reads(pairs, GLOBAL_READ, -1, w1)) == {bytes([0, 0, 1, 1])}
    assert set(reads(pairs, BUFFER_READ, -1, w1)) == {STORED_1B}
    # bypass state: slot reads ff, mode stays normal, the edit buffer is all zero; it holds
    between_global = reads(pairs, GLOBAL_READ, w1, w2)
    between_buffer = reads(pairs, BUFFER_READ, w1, w2)
    assert len(between_global) >= 2 and set(between_global) == {bytes([0, 0, 0xFF, 1])}
    assert len(between_buffer) >= 2 and set(between_buffer) == {bytes(21)}
    assert set(reads(pairs, STATUS_READ, -1, end)) == {b"\x01"}  # status byte untouched
    # undo: select 1B reloads the stored preset, slot back to 1
    assert reads(pairs, GLOBAL_READ, w2, end)[-1] == bytes([0, 0, 1, 1])
    assert reads(pairs, BUFFER_READ, w2, end)[-1] == STORED_1B


def test_only_the_bypass_write_is_outside_the_allowlist() -> None:
    sent = [tx for tx, _ in exchanges()]
    assert unsafe_frames(sent) == [BYPASS_1B]
