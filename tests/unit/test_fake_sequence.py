"""FakeTransport ordered replay: several replies per request label (T017, research R9)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from openvave.errors import ConnectionLostError
from openvave.models import Region
from openvave.protocol import FrameAssembler, build_read
from openvave.transport.fake import FakeTransport
from tests.support.captures import FW96_CONNECT, LABELS, PRESET, load_capture
from tests.support.watch import region_reply, watch_fake, write_watch_capture

CAP = load_capture(FW96_CONNECT)
PRESET_15 = 8 + 15 + 6  # header (6) + echo prefix (8) + data offset 15
SEQUENCE = [{}, {"preset": {15: 64}}, {"preset": {15: 127}}]


class Collector:
    def __init__(self) -> None:
        self.chunks: list[bytes] = []

    def __call__(self, chunk: bytes) -> None:
        self.chunks.append(chunk)


async def _settle() -> None:
    for _ in range(5):
        await asyncio.sleep(0)


async def _open(fake: FakeTransport) -> Collector:
    got = Collector()
    fake.on_notify(got)
    await fake.open()
    return got


async def _replies(fake: FakeTransport, frame: bytes, n: int) -> list[bytes]:
    got = await _open(fake)
    replies = []
    for _ in range(n):
        got.chunks.clear()
        await fake.write(frame)
        await _settle()
        replies.append(b"".join(got.chunks))
    return replies


async def test_capture_with_repeated_labels_served_in_order_then_last_repeats(
    tmp_path: Path,
) -> None:
    path = write_watch_capture(tmp_path / "seq.jsonl", SEQUENCE)
    fake = FakeTransport.from_capture(path)
    replies = await _replies(fake, build_read(Region.CURRENT_PRESET), 5)
    assert [r[PRESET_15] for r in replies] == [5, 64, 127, 127, 127]
    assert replies[0] == CAP.rx(PRESET)


async def test_001_capture_unchanged_one_reply_per_label() -> None:
    fake = FakeTransport.from_capture(FW96_CONNECT)
    got = await _open(fake)
    for label in LABELS:
        for _ in range(3):
            got.chunks.clear()
            await fake.write(CAP.tx(label))
            await _settle()
            assert b"".join(got.chunks) == CAP.rx(label)


async def test_script_with_reply_list() -> None:
    fake = watch_fake(SEQUENCE)
    replies = await _replies(fake, build_read(Region.CURRENT_PRESET), 4)
    assert [r[PRESET_15] for r in replies] == [5, 64, 127, 127]


async def test_split_applies_per_request() -> None:
    fake = watch_fake(SEQUENCE, split=3)
    got = await _open(fake)
    asm = FrameAssembler()
    for expected in (5, 64, 127):
        got.chunks.clear()
        await fake.write(build_read(Region.CURRENT_PRESET))
        await _settle()
        assert len(got.chunks) == 3
        frames = [f for c in got.chunks for f in asm.feed(c)]
        assert [f[PRESET_15] for f in frames] == [expected]


async def test_drop_does_not_consume_a_reply() -> None:
    fake = watch_fake(SEQUENCE, drop={PRESET: 1})
    got = await _open(fake)
    await fake.write(build_read(Region.CURRENT_PRESET))
    await _settle()
    assert got.chunks == []
    await fake.write(build_read(Region.CURRENT_PRESET))
    await _settle()
    assert b"".join(got.chunks)[PRESET_15] == 5


async def test_disconnect_after_applies_per_request() -> None:
    fake = watch_fake(SEQUENCE, disconnect_after=2)
    await _open(fake)
    await fake.write(build_read(Region.CURRENT_PRESET))
    await fake.write(build_read(Region.CURRENT_PRESET))
    with pytest.raises(ConnectionLostError):
        await fake.write(build_read(Region.CURRENT_PRESET))


async def test_replies_override_accepts_a_list() -> None:
    fake = FakeTransport.from_capture(
        FW96_CONNECT, replies={PRESET: [region_reply("preset", {15: 1}), region_reply("preset")]}
    )
    replies = await _replies(fake, build_read(Region.CURRENT_PRESET), 3)
    assert [r[PRESET_15] for r in replies] == [1, 5, 5]


def test_empty_reply_list_rejected() -> None:
    with pytest.raises(ValueError):
        FakeTransport({PRESET: (CAP.tx(PRESET), [])})
