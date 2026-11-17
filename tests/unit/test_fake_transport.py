"""FakeTransport replays a capture (T021)."""

from __future__ import annotations

import asyncio

import pytest

from openvave.errors import ConnectionLostError
from openvave.models import Region
from openvave.protocol import FrameAssembler, build_query, build_read, encode_frame
from openvave.transport import Transport
from openvave.transport.fake import FakeTransport
from tests.support import storage_fixture as sf
from tests.support.captures import FW96_CONNECT, GLOBAL, LABELS, QUERY, load_capture

CAP = load_capture(FW96_CONNECT)


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


def test_is_a_transport() -> None:
    assert isinstance(FakeTransport.from_capture(FW96_CONNECT), Transport)


async def test_answers_each_request_with_captured_reply() -> None:
    fake = FakeTransport.from_capture(FW96_CONNECT)
    got = await _open(fake)
    for label in LABELS:
        got.chunks.clear()
        await fake.write(CAP.tx(label))
        await _settle()
        assert b"".join(got.chunks) == CAP.rx(label)
    assert fake.sent == CAP.ordered_tx


async def test_accepts_str_path() -> None:
    fake = FakeTransport.from_capture(str(FW96_CONNECT))
    got = await _open(fake)
    await fake.write(build_query())
    await _settle()
    assert got.chunks == [CAP.rx(QUERY)]


async def test_split() -> None:
    fake = FakeTransport.from_capture(FW96_CONNECT, split=4)
    got = await _open(fake)
    await fake.write(build_read(Region.CURRENT_PRESET))
    await _settle()
    assert len(got.chunks) == 4
    asm = FrameAssembler()
    frames = [f for c in got.chunks for f in asm.feed(c)]
    assert frames == [CAP.rx(LABELS[3])]


async def test_drop() -> None:
    fake = FakeTransport.from_capture(FW96_CONNECT, drop={QUERY: 2})
    got = await _open(fake)
    for _ in range(2):
        await fake.write(build_query())
        await _settle()
        assert got.chunks == []
    await fake.write(build_query())
    await _settle()
    assert got.chunks == [CAP.rx(QUERY)]
    assert fake.sent == [build_query()] * 3


async def test_disconnect_after() -> None:
    fake = FakeTransport.from_capture(FW96_CONNECT, disconnect_after=2)
    await _open(fake)
    await fake.write(build_query())
    await fake.write(build_read(Region.DEVICE_INFO))
    with pytest.raises(ConnectionLostError):
        await fake.write(build_read(Region.GLOBAL))


async def test_replies_override() -> None:
    other = CAP.rx(LABELS[4])
    fake = FakeTransport.from_capture(FW96_CONNECT, replies={GLOBAL: other})
    got = await _open(fake)
    await fake.write(build_read(Region.GLOBAL))
    await _settle()
    assert got.chunks == [other]


async def test_unknown_request_fails_the_test() -> None:
    fake = FakeTransport.from_capture(FW96_CONNECT)
    await _open(fake)
    unknown = encode_frame(0x23, bytes.fromhex("04 00 00 00 30 01 00 00"))
    with pytest.raises(AssertionError):
        await fake.write(unknown)


async def test_write_before_open_fails() -> None:
    fake = FakeTransport.from_capture(FW96_CONNECT)
    with pytest.raises(AssertionError):
        await fake.write(build_query())


async def test_close_is_idempotent() -> None:
    fake = FakeTransport.from_capture(FW96_CONNECT)
    await _open(fake)
    await fake.close()
    await fake.close()
    assert fake.closed
    with pytest.raises(ConnectionLostError):
        await fake.write(build_query())


def test_unknown_option_label_rejected() -> None:
    with pytest.raises(KeyError):
        FakeTransport.from_capture(FW96_CONNECT, drop={"no such label": 1})


# -- memory and chunk_size (spec 003, T004) -------------------------------------------------------


def _memory_fake(**options: object) -> FakeTransport:
    script = {QUERY: (CAP.tx(QUERY), CAP.rx(QUERY))}
    return FakeTransport(script, memory={0: sf.synthetic_image()}, **options)  # type: ignore[arg-type]


async def test_memory_answers_reads_inside_a_block() -> None:
    fake = _memory_fake()
    got = await _open(fake)
    for label, (tx, rx) in sf.storage_replies(sf.synthetic_image()).items():
        got.chunks.clear()
        await fake.write(tx)
        await _settle()
        assert b"".join(got.chunks) == rx, label


async def test_memory_sub_block_read() -> None:
    fake = _memory_fake()
    got = await _open(fake)
    image = sf.synthetic_image()
    await fake.write(sf.read_request(100, 5))
    await _settle()
    assert b"".join(got.chunks) == sf.read_reply(100, image[100:105])


async def test_memory_outside_block_is_unanswered() -> None:
    fake = _memory_fake()
    got = await _open(fake)
    for tx in (sf.read_request(757, 2), sf.read_request(0x10000000, 21)):
        await fake.write(tx)
    await _settle()
    assert got.chunks == []
    assert len(fake.sent) == 2


async def test_memory_ignores_other_types() -> None:
    fake = _memory_fake()
    got = await _open(fake)
    tx = sf.frame(0x23, bytes([5]) + (0).to_bytes(4, "little") + (2).to_bytes(3, "little"))
    await fake.write(tx)
    await _settle()
    assert got.chunks == []


async def test_script_takes_precedence_over_memory() -> None:
    image = sf.synthetic_image()
    tx = sf.read_request(0, 2)
    other = sf.read_reply(0, b"\x00\x00")
    script = {QUERY: (CAP.tx(QUERY), CAP.rx(QUERY)), "header": (tx, other)}
    fake = FakeTransport(script, memory={0: image})
    got = await _open(fake)
    await fake.write(tx)
    await _settle()
    assert b"".join(got.chunks) == other


async def test_unknown_request_without_memory_still_asserts() -> None:
    fake = FakeTransport.from_capture(FW96_CONNECT)
    await _open(fake)
    with pytest.raises(AssertionError):
        await fake.write(sf.read_request(0, 2))


async def test_chunk_size_splits_image_reply() -> None:
    fake = _memory_fake(chunk_size=182)
    got = await _open(fake)
    await fake.write(sf.read_request(0, 758))
    await _settle()
    assert [len(c) for c in got.chunks] == [182, 182, 182, 182, 45]
    assert len(b"".join(got.chunks)) == 773


async def test_chunk_size_and_split_exclusive() -> None:
    with pytest.raises(ValueError):
        _memory_fake(chunk_size=182, split=2)
    with pytest.raises(ValueError):
        _memory_fake(chunk_size=0)


async def test_from_capture_accepts_memory_and_chunk_size() -> None:
    fake = FakeTransport.from_capture(
        FW96_CONNECT, memory={0: sf.synthetic_image()}, chunk_size=182
    )
    got = await _open(fake)
    await fake.write(sf.read_request(0, 758))
    await _settle()
    assert len(got.chunks) == 5
