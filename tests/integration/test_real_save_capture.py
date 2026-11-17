"""Spec 004 check 4 evidence: a real save persists across a power cycle (fw 96, 2026-11-17).

Run 1: stored slot 1C (``0x2C`` x21) written with gain 60 -> 90, empty commit to ``0xF0000000``,
select 1C. The owner then switched the pedal off and on. Run 2: stored 1C still reads gain 90;
the original bytes are written back, committed, then 1C and 1B are selected. Read straight from
the committed frames (no ``openvave`` decoding).
"""

from __future__ import annotations

import json

from tests.integration.gate_fixtures import FW96
from tests.support.audit import unsafe_frames

SAVE = FW96 / "20261117-check4-real_save.jsonl"
VERIFY = FW96 / "20261117-check4-verify_restore.jsonl"
ACK = bytes.fromhex("00 59 00 01 00 00 00 ff")
ORIGINAL_1C = bytes.fromhex("01 00 00 01 0f 04 3c 3c 46 32 32 00 00 00 00 05 04 07 43 16 43")
CHANGED_1C = ORIGINAL_1C[:6] + bytes([90]) + ORIGINAL_1C[7:]
SLOT_1C = bytes.fromhex("00 59 22 1d 00 00 04 2c 00 00 00 15 00 00")
SAVE_WRITE = SLOT_1C + CHANGED_1C + b"\xb9"
RESTORE_WRITE = SLOT_1C + ORIGINAL_1C + b"\xd7"
COMMIT = bytes.fromhex("00 59 22 08 00 00 04 00 00 00 f0 00 00 00 0b")
SELECT_1C = bytes.fromhex("00 59 22 09 00 00 04 02 00 00 e0 01 00 00 01 17")
SELECT_1B = bytes.fromhex("00 59 22 09 00 00 04 01 00 00 e0 01 00 00 01 18")
STORED_READ_1C = bytes.fromhex("00 59 23 08 00 00 04 2c 00 00 00 15 00 00 ba")
BUFFER_READ = bytes.fromhex("00 59 23 08 00 00 04 00 00 00 10 15 00 00 d6")


def exchanges(path: object) -> list[tuple[bytes, bytes]]:
    records = [json.loads(line) for line in open(str(path), encoding="utf-8")]
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


def stored_1c(pairs: list[tuple[bytes, bytes]]) -> list[bytes]:
    return [rx[14:-1] for tx, rx in pairs if tx == STORED_READ_1C]


def writes(pairs: list[tuple[bytes, bytes]]) -> list[bytes]:
    assert all(rx == ACK for tx, rx in pairs if tx[2] == 0x22)
    return [tx for tx, _ in pairs if tx[2] == 0x22]


def test_run1_saves_gain_90_into_1c() -> None:
    pairs = exchanges(SAVE)
    assert writes(pairs) == [SAVE_WRITE, COMMIT, SELECT_1C]
    # before, read back before the commit, and after the select
    assert stored_1c(pairs) == [ORIGINAL_1C, CHANGED_1C, CHANGED_1C]
    assert [rx[14:-1] for tx, rx in pairs if tx == BUFFER_READ][-1] == CHANGED_1C


def test_run2_after_power_cycle_reads_the_save_then_restores() -> None:
    pairs = exchanges(VERIFY)
    first = stored_1c(pairs)[0]
    assert first == CHANGED_1C  # persisted across the owner's power cycle
    assert writes(pairs) == [RESTORE_WRITE, COMMIT, SELECT_1C, SELECT_1B]
    assert stored_1c(pairs)[-1] == ORIGINAL_1C


def test_only_slot_writes_and_commits_are_outside_the_allowlist() -> None:
    assert unsafe_frames([tx for tx, _ in exchanges(SAVE)]) == [SAVE_WRITE, COMMIT]
    assert unsafe_frames([tx for tx, _ in exchanges(VERIFY)]) == [RESTORE_WRITE, COMMIT]
