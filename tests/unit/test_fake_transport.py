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
from tests.support.write_fixture import ACK, NORMAL, make_fake, write_frame

GLOBAL_ADDR, BUFFER_ADDR = 0x20000000, 0x10000000

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


# -- bypass and loopback (spec 004 T025) --------------------------------------------------------


async def _write_and_settle(fake: FakeTransport, frame: bytes, got: Collector) -> bytes:
    got.chunks.clear()
    await fake.write(frame)
    await _settle()
    return b"".join(got.chunks)


async def test_bypass_write_zeroes_buffer_and_sets_slot_ff() -> None:
    fake = make_fake(NORMAL)
    got = await _open(fake)
    assert await _write_and_settle(fake, write_frame(0xE1000001, b"\x01"), got) == ACK
    glob = await _write_and_settle(fake, sf.read_request(GLOBAL_ADDR, 4), got)
    assert glob == sf.read_reply(GLOBAL_ADDR, bytes([0, 0, 0xFF, NORMAL]))
    buffer = await _write_and_settle(fake, sf.read_request(BUFFER_ADDR, 21), got)
    assert buffer == sf.read_reply(BUFFER_ADDR, bytes(21))


async def test_select_leaves_bypass() -> None:
    fake = make_fake(NORMAL)
    got = await _open(fake)
    await _write_and_settle(fake, write_frame(0xE1000001, b"\x01"), got)
    assert await _write_and_settle(fake, write_frame(0xE0000001, b"\x01"), got) == ACK
    glob = await _write_and_settle(fake, sf.read_request(GLOBAL_ADDR, 4), got)
    assert glob == sf.read_reply(GLOBAL_ADDR, bytes([0, 0, 1, NORMAL]))
    buffer = await _write_and_settle(fake, sf.read_request(BUFFER_ADDR, 21), got)
    assert buffer == sf.read_reply(BUFFER_ADDR, sf.PUBLIC_PRESET)


@pytest.mark.parametrize("value", [b"\x00", b"\x01"])
async def test_loopback_write_stores_the_byte(value: bytes) -> None:
    fake = make_fake(NORMAL, status=b"\x01" if value == b"\x00" else b"\x00")
    got = await _open(fake)
    assert await _write_and_settle(fake, write_frame(0xD0000000, value), got) == ACK
    status = await _write_and_settle(fake, sf.read_request(0xD0000000, 1), got)
    assert status == sf.read_reply(0xD0000000, value)
    glob = await _write_and_settle(fake, sf.read_request(GLOBAL_ADDR, 4), got)
    assert glob == sf.read_reply(GLOBAL_ADDR, bytes([0, 0, 1, NORMAL]))  # nothing else moved


# -- stored area, commit, scripted step failures (spec 004 M2, T042) ---------------------------

NAK = sf.frame(0x00, b"\x01")
GAIN_90 = sf.PUBLIC_PRESET[:6] + bytes([90]) + sf.PUBLIC_PRESET[7:]


def _slot(index: int) -> int:
    return 2 + 21 * index


async def _stored(fake: FakeTransport, got: Collector, index: int) -> bytes:
    reply = await _write_and_settle(fake, sf.read_request(_slot(index), 21), got)
    return reply[14:-1]


@pytest.mark.persistent_writes
async def test_slot_write_changes_the_stored_area() -> None:
    fake = make_fake(NORMAL)
    got = await _open(fake)
    assert await _write_and_settle(fake, write_frame(_slot(2), GAIN_90), got) == ACK
    assert await _stored(fake, got, 2) == GAIN_90
    assert await _stored(fake, got, 1) == sf.PUBLIC_PRESET  # neighbours untouched
    assert await _stored(fake, got, 3) == sf.synthetic_preset(3)
    assert fake.commits == 0


@pytest.mark.persistent_writes
async def test_commit_is_counted_and_changes_nothing() -> None:
    fake = make_fake(NORMAL)
    got = await _open(fake)
    image = await _write_and_settle(fake, sf.read_request(0, 758), got)
    assert await _write_and_settle(fake, write_frame(0xF0000000, b""), got) == ACK
    assert fake.commits == 1
    assert await _write_and_settle(fake, sf.read_request(0, 758), got) == image


@pytest.mark.persistent_writes
async def test_image_write_replaces_the_stored_area() -> None:
    fake = make_fake(NORMAL)
    got = await _open(fake)
    image = sf.synthetic_image()
    new = image[:2] + GAIN_90 * 36
    assert await _write_and_settle(fake, write_frame(0, new), got) == ACK
    reply = await _write_and_settle(fake, sf.read_request(0, 758), got)
    assert reply[14:-1] == new


@pytest.mark.persistent_writes
async def test_select_loads_from_the_written_stored_area() -> None:
    fake = make_fake(NORMAL)
    got = await _open(fake)
    await _write_and_settle(fake, write_frame(_slot(2), GAIN_90), got)
    await _write_and_settle(fake, write_frame(0xE0000002, b"\x01"), got)
    buffer = await _write_and_settle(fake, sf.read_request(BUFFER_ADDR, 21), got)
    assert buffer[14:-1] == GAIN_90
    glob = await _write_and_settle(fake, sf.read_request(GLOBAL_ADDR, 4), got)
    assert glob[14:-1] == bytes([0, 0, 2, NORMAL])


@pytest.mark.persistent_writes
async def test_fault_nak_does_not_apply() -> None:
    fake = make_fake(NORMAL, faults={"stored_slot": "nak"})
    got = await _open(fake)
    assert await _write_and_settle(fake, write_frame(_slot(2), GAIN_90), got) == NAK
    assert await _stored(fake, got, 2) == sf.synthetic_preset(2)
    # a fault fires once: the next slot write is applied
    assert await _write_and_settle(fake, write_frame(_slot(2), GAIN_90), got) == ACK
    assert await _stored(fake, got, 2) == GAIN_90


@pytest.mark.persistent_writes
async def test_fault_no_reply_applies_but_answers_nothing() -> None:
    fake = make_fake(NORMAL, faults={"commit": "no_reply"})
    got = await _open(fake)
    assert await _write_and_settle(fake, write_frame(0xF0000000, b""), got) == b""
    assert fake.commits == 1


@pytest.mark.persistent_writes
async def test_fault_disconnect_applies_then_drops_the_link() -> None:
    fake = make_fake(NORMAL, faults={"stored_slot": "disconnect"})
    lost: list[bool] = []
    fake.on_disconnect(lambda: lost.append(True))
    got = await _open(fake)
    assert await _write_and_settle(fake, write_frame(_slot(2), GAIN_90), got) == b""
    assert lost == [True]
    assert fake.closed is True
    with pytest.raises(ConnectionLostError):
        await fake.write(sf.read_request(_slot(2), 21))


@pytest.mark.persistent_writes
async def test_fault_corrupt_and_ignore() -> None:
    fake = make_fake(NORMAL, faults={"stored_slot": "corrupt", "preset_select": "ignore"})
    got = await _open(fake)
    assert await _write_and_settle(fake, write_frame(_slot(2), GAIN_90), got) == ACK
    stored = await _stored(fake, got, 2)
    assert stored != GAIN_90 and stored[:20] == GAIN_90[:20]
    assert await _write_and_settle(fake, write_frame(0xE0000002, b"\x01"), got) == ACK
    glob = await _write_and_settle(fake, sf.read_request(GLOBAL_ADDR, 4), got)
    assert glob[14:-1] == bytes([0, 0, 1, NORMAL])  # select ignored: still on 1B


def test_unknown_fault_kind_or_action_is_rejected() -> None:
    with pytest.raises(ValueError):
        make_fake(NORMAL, faults={"stored_slot": "explode"})
    with pytest.raises(ValueError):
        make_fake(NORMAL, faults={"erase": "nak"})


# -- lose_link (spec 005 T048) ----------------------------------------------------------------


async def test_lose_link_runs_the_disconnect_callback_and_later_writes_fail() -> None:
    fake = FakeTransport.from_capture(FW96_CONNECT)
    lost: list[str] = []
    fake.on_disconnect(lambda: lost.append("lost"))
    await _open(fake)
    await fake.write(CAP.tx(QUERY))
    fake.lose_link()
    assert lost == ["lost"]
    assert fake.closed
    with pytest.raises(ConnectionLostError):
        await fake.write(CAP.tx(QUERY))
    assert fake.sent == [CAP.tx(QUERY)]


async def test_lose_link_without_callback() -> None:
    fake = FakeTransport.from_capture(FW96_CONNECT)
    await _open(fake)
    fake.lose_link()
    with pytest.raises(ConnectionLostError):
        await fake.write(CAP.tx(QUERY))


async def test_lose_link_is_a_noop_when_closed() -> None:
    fake = FakeTransport.from_capture(FW96_CONNECT)
    lost: list[str] = []
    fake.on_disconnect(lambda: lost.append("lost"))
    fake.lose_link()  # never opened
    await _open(fake)
    await fake.close()
    fake.lose_link()
    assert lost == []


async def test_reopen_after_lose_link() -> None:
    fake = FakeTransport.from_capture(FW96_CONNECT)
    got = await _open(fake)
    fake.lose_link()
    await fake.close()
    await fake.open()
    await fake.write(CAP.tx(QUERY))
    await _settle()
    assert got.chunks == [CAP.rx(QUERY)]
