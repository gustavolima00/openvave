"""Spec 004 check 1 evidence: the knob-block write is applied in NORMAL mode (fw 96, 2026-11-17).

Two connections by the owner, each: pedal on 1B in normal mode, knob block with gain 60 -> 90,
then preset select 1B. Read straight from the committed frames (no ``openvave`` decoding), so
the claims in ``specs/protocol/app-features.md`` cannot drift from the capture.
"""

from __future__ import annotations

import json

import pytest

from tests.integration.gate_fixtures import FW96

EXCERPTS = ("20261117-gate-normal_knob_gain.jsonl", "20261117-gate-normal_knob_gain_b.jsonl")
ACK = bytes.fromhex("00 59 00 01 00 00 00 ff")
KNOB_WRITE = bytes.fromhex(
    "00 59 22 16 00 00 04 04 00 00 10 0e 00 00 0f 04 5a 3c 46 32 32 00 00 00 00 05 04 07 76"
)
SELECT_1B = bytes.fromhex("00 59 22 09 00 00 04 01 00 00 e0 01 00 00 01 18")
GLOBAL_READ = bytes.fromhex("00 59 23 08 00 00 04 00 00 00 20 04 00 00 d7")
BUFFER_READ = bytes.fromhex("00 59 23 08 00 00 04 00 00 00 10 15 00 00 d6")
STORED_1B = bytes.fromhex("01 00 00 01 0f 04 3c 3c 46 32 32 00 00 00 00 05 04 07 43 16 43")


def exchanges(name: str) -> list[tuple[bytes, bytes]]:
    """(request, reply) pairs in order."""
    records = [json.loads(line) for line in (FW96 / name).read_text().splitlines()]
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


def data(reply: bytes) -> bytes:
    return reply[14:-1]


@pytest.mark.parametrize("name", EXCERPTS)
def test_write_applied_in_normal_mode_and_select_restores(name: str) -> None:
    pairs = exchanges(name)
    writes = [i for i, (tx, _) in enumerate(pairs) if tx[2] == 0x22]
    assert [pairs[i][0] for i in writes] == [KNOB_WRITE, SELECT_1B]
    assert all(pairs[i][1] == ACK for i in writes)
    w1, w2 = writes

    globals_ = [(i, data(rx)) for i, (tx, rx) in enumerate(pairs) if tx == GLOBAL_READ]
    buffers = [(i, data(rx)) for i, (tx, rx) in enumerate(pairs) if tx == BUFFER_READ]
    # mode (global byte 3) is 1 = normal at every read: before, after the write, after the select
    assert globals_ and all(g == bytes([0, 0, 1, 1]) for _, g in globals_)
    assert any(i < w1 for i, _ in globals_) and any(i > w2 for i, _ in globals_)

    before = [b for i, b in buffers if i < w1]
    between = [b for i, b in buffers if w1 < i < w2]
    after = [b for i, b in buffers if i > w2]
    assert before and all(b == STORED_1B for b in before)
    expected = bytearray(STORED_1B)
    expected[6] = 90
    assert between and all(b == bytes(expected) for b in between)  # only gain moved, and stayed
    assert after and after[-1] == STORED_1B


def test_the_two_excerpts_are_separate_connections() -> None:
    for name in EXCERPTS:
        first = exchanges(name)[0]
        assert first[0] == bytes.fromhex("00 59 11 00 00 00 ff")  # each starts with a handshake
