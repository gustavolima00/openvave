"""Notification chunks → frames (T014). Reassembly is tested by splitting real frames (R6)."""

from __future__ import annotations

import pytest

from openvave.protocol.assembler import FrameAssembler
from tests.support import mutations as m
from tests.support.captures import FW96_CONNECT, LABELS, load_capture

CAP = load_capture(FW96_CONNECT)
REPLIES = [CAP.rx(label) for label in LABELS]


def _feed_all(asm: FrameAssembler, chunks: list[bytes]) -> list[bytes]:
    out: list[bytes] = []
    for chunk in chunks:
        out.extend(asm.feed(chunk))
    return out


@pytest.mark.parametrize("label", LABELS)
def test_captured_chunks(label: str) -> None:
    assert _feed_all(FrameAssembler(), CAP.rx_chunks[label]) == [CAP.rx(label)]


@pytest.mark.parametrize("label", LABELS)
def test_every_split(label: str) -> None:
    rx = CAP.rx(label)
    for n in range(1, len(rx) + 1):
        asm = FrameAssembler()
        assert _feed_all(asm, m.split(rx, n)) == [rx], f"n={n}"
        assert asm.pending == 0


def test_two_frames_in_one_chunk() -> None:
    asm = FrameAssembler()
    assert asm.feed(REPLIES[2] + REPLIES[4]) == [REPLIES[2], REPLIES[4]]


def test_frames_split_across_boundary() -> None:
    joined = REPLIES[3] + REPLIES[2]
    asm = FrameAssembler()
    assert _feed_all(asm, m.split(joined, 5)) == [REPLIES[3], REPLIES[2]]


def test_stray_chunk_reported_and_dropped() -> None:
    strays: list[bytes] = []
    asm = FrameAssembler(on_stray=strays.append)
    junk = REPLIES[2][6:]  # tail of a frame without its header
    assert asm.feed(junk) == []
    assert strays == [junk]
    assert asm.pending == 0
    assert asm.feed(REPLIES[2]) == [REPLIES[2]]


def test_stray_remainder_after_frame() -> None:
    strays: list[bytes] = []
    asm = FrameAssembler(on_stray=strays.append)
    assert asm.feed(REPLIES[4] + b"\x42\x42") == [REPLIES[4]]
    assert strays == [b"\x42\x42"]


def test_reset_discards_partial_frame() -> None:
    asm = FrameAssembler()
    head, tail = m.split(REPLIES[1], 2)
    assert asm.feed(head) == []
    assert asm.pending == len(head)
    asm.reset()
    assert asm.pending == 0
    assert asm.feed(REPLIES[2]) == [REPLIES[2]]
