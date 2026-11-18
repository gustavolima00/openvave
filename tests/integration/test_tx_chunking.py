"""A request longer than one Bluetooth write is split by the BLE transport and reassembled by the
fake pedal (spec 004 R11, T043). Only the 773-byte image write needs it; every other request
fits in one write."""

from __future__ import annotations

import asyncio

import pytest

from openvave.transport.ble import split_frame
from openvave.transport.fake import FakeTransport
from tests.support import storage_fixture as sf
from tests.support.write_fixture import ACK, NORMAL, make_fake, write_frame

IMAGE_FRAME = write_frame(0, sf.synthetic_image())


def test_image_frame_is_773_bytes() -> None:
    assert len(IMAGE_FRAME) == 773


def test_split_at_mtu_185() -> None:
    chunks = split_frame(IMAGE_FRAME, 185)
    assert [len(c) for c in chunks] == [182, 182, 182, 182, 45]
    assert b"".join(chunks) == IMAGE_FRAME


def test_split_at_mtu_247() -> None:
    chunks = split_frame(IMAGE_FRAME, 247)
    assert [len(c) for c in chunks] == [244, 244, 244, 41]
    assert b"".join(chunks) == IMAGE_FRAME


@pytest.mark.parametrize("size", [7, 36, 182])
def test_short_frames_go_in_one_write(size: int) -> None:
    frame = bytes(range(size))
    assert split_frame(frame, 185) == [frame]


def test_split_needs_a_usable_mtu() -> None:
    with pytest.raises(ValueError):
        split_frame(IMAGE_FRAME, 3)


async def _settle() -> None:
    for _ in range(5):
        await asyncio.sleep(0)


async def _open(fake: FakeTransport) -> list[bytes]:
    got: list[bytes] = []
    fake.on_notify(got.append)
    await fake.open()
    return got


@pytest.mark.persistent_writes
async def test_fake_reassembles_a_chunked_image_write() -> None:
    fake = make_fake(NORMAL)
    got = await _open(fake)
    new = sf.synthetic_image()[:2] + bytes(range(21)) * 36
    frame = write_frame(0, new)
    for chunk in split_frame(frame, 185):
        await fake.write(chunk)
        await _settle()
    assert fake.sent == [frame]  # one request, reassembled by its length field
    assert b"".join(got) == ACK  # one ACK, after the last chunk
    got.clear()
    await fake.write(sf.read_request(0, 758))
    await _settle()
    assert b"".join(got)[14:-1] == new


async def test_whole_frames_are_unchanged_by_reassembly() -> None:
    fake = make_fake(NORMAL)
    await _open(fake)
    for frame in (sf.read_request(0x20000000, 4), sf.read_request(0x10000000, 21)):
        await fake.write(frame)
    assert fake.sent == [sf.read_request(0x20000000, 4), sf.read_request(0x10000000, 21)]
