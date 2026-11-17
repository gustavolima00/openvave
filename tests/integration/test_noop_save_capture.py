"""Spec 004 check 3 evidence: the app's save sequence as a no-op on fw 96 (one session, 2026-11-17).

Pedal on 1B in normal mode: stored slot 1B (``0x17`` x21) rewritten with its own bytes, then the
empty commit write to ``0xF0000000``, then select 1B. Read straight from the committed frames (no
``openvave`` decoding). Slot write and commit are not in openvave's write allowlist, so the
excerpt is not a ``-gate-`` file; this test checks it instead.
"""

from __future__ import annotations

import json

from tests.integration.gate_fixtures import FW96
from tests.support.audit import unsafe_frames

EXCERPT = FW96 / "20261117-check3-noop_save.jsonl"
ACK = bytes.fromhex("00 59 00 01 00 00 00 ff")
STORED_1B = bytes.fromhex("01 00 00 01 0f 04 3c 3c 46 32 32 00 00 00 00 05 04 07 43 16 43")
SLOT_WRITE_1B = bytes.fromhex("00 59 22 1d 00 00 04 17 00 00 00 15 00 00") + STORED_1B + b"\xec"
COMMIT = bytes.fromhex("00 59 22 08 00 00 04 00 00 00 f0 00 00 00 0b")
SELECT_1B = bytes.fromhex("00 59 22 09 00 00 04 01 00 00 e0 01 00 00 01 18")
STORED_READ_1B = bytes.fromhex("00 59 23 08 00 00 04 17 00 00 00 15 00 00 cf")
GLOBAL_READ = bytes.fromhex("00 59 23 08 00 00 04 00 00 00 20 04 00 00 d7")
BUFFER_READ = bytes.fromhex("00 59 23 08 00 00 04 00 00 00 10 15 00 00 d6")


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


def test_save_sequence_acked_and_nothing_changed() -> None:
    pairs = exchanges()
    writes = [(tx, rx) for tx, rx in pairs if tx[2] == 0x22]
    assert [tx for tx, _ in writes] == [SLOT_WRITE_1B, COMMIT, SELECT_1B]
    assert all(rx == ACK for _, rx in writes)
    stored = [rx[14:-1] for tx, rx in pairs if tx == STORED_READ_1B]
    assert len(stored) >= 3 and set(stored) == {STORED_1B}  # before, after the write, at the end
    assert {rx[14:-1] for tx, rx in pairs if tx == GLOBAL_READ} == {bytes([0, 0, 1, 1])}
    assert {rx[14:-1] for tx, rx in pairs if tx == BUFFER_READ} == {STORED_1B}


def test_only_slot_write_and_commit_are_outside_the_allowlist() -> None:
    assert unsafe_frames([tx for tx, _ in exchanges()]) == [SLOT_WRITE_1B, COMMIT]
