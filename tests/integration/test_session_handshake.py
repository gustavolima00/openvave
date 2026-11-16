"""TankG connect sequence and handshake over FakeTransport (T027)."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable

import pytest

from openvave.errors import ConnectionLostError, HandshakeError, ProtocolError
from openvave.models import DeviceInfo
from openvave.protocol import decode_frame
from openvave.session import TankG
from openvave.transport.fake import FakeTransport
from tests.support.captures import FW96_CONNECT, QUERY, load_capture
from tests.support.mutations import flip_checksum, set_command, with_payload

CAP = load_capture(FW96_CONNECT)
QUERY_FRAME = bytes.fromhex("00 59 11 00 00 00 ff")


class CorruptFirstReplies:
    """Wraps a FakeTransport and mutates the first ``count`` notifications it delivers."""

    def __init__(self, inner: FakeTransport, mutate: Callable[[bytes], bytes], count: int = 1):
        self.inner = inner
        self._mutate = mutate
        self._left = count

    async def open(self) -> None:
        await self.inner.open()

    async def write(self, frame: bytes) -> None:
        await self.inner.write(frame)

    def on_notify(self, callback: Callable[[bytes], None]) -> None:
        def wrapped(chunk: bytes) -> None:
            if self._left > 0:
                self._left -= 1
                chunk = self._mutate(chunk)
            callback(chunk)

        self.inner.on_notify(wrapped)

    async def close(self) -> None:
        await self.inner.close()


def _queries(fake: FakeTransport) -> int:
    return sum(1 for f in fake.sent if f == QUERY_FRAME)


async def test_identity_from_capture() -> None:
    fake = FakeTransport.from_capture(FW96_CONNECT)
    async with TankG.over(fake) as pedal:
        assert pedal.identity.name == "TANK-Gv2"
        assert pedal.identity.firmware == 96
        assert pedal.identity.firmware_untested is False
        assert pedal.device is None
    assert fake.sent[0] == QUERY_FRAME
    assert fake.sent == [QUERY_FRAME]
    assert fake.closed


async def test_device_is_exposed() -> None:
    info = DeviceInfo("AAAA", "TANK-Gv2_BLE", -50)
    fake = FakeTransport.from_capture(FW96_CONNECT)
    async with TankG.over(fake, device=info) as pedal:
        assert pedal.device == info


async def test_identity_unavailable_before_enter() -> None:
    pedal = TankG.over(FakeTransport.from_capture(FW96_CONNECT))
    with pytest.raises(RuntimeError):
        _ = pedal.identity


async def test_two_drops_then_success() -> None:
    fake = FakeTransport.from_capture(FW96_CONNECT, drop={QUERY: 2})
    async with TankG.over(fake, timeout=0.1) as pedal:
        assert pedal.identity.firmware == 96
    assert _queries(fake) == 3
    assert fake.closed


async def test_three_drops_handshake_error() -> None:
    fake = FakeTransport.from_capture(FW96_CONNECT, drop={QUERY: 3})
    with pytest.raises(HandshakeError):
        async with TankG.over(fake, timeout=0.1):
            pass
    assert _queries(fake) == 3
    assert fake.closed


async def test_bad_checksum_then_good() -> None:
    fake = FakeTransport.from_capture(FW96_CONNECT)
    wrapped = CorruptFirstReplies(fake, flip_checksum)
    async with TankG.over(wrapped, timeout=0.5) as pedal:
        assert pedal.identity.name == "TANK-Gv2"
    assert _queries(fake) == 2


async def test_wrong_command_then_good() -> None:
    fake = FakeTransport.from_capture(FW96_CONNECT)
    wrapped = CorruptFirstReplies(fake, lambda f: set_command(f, 0x23))
    async with TankG.over(wrapped, timeout=0.5) as pedal:
        assert pedal.identity.firmware == 96
    assert _queries(fake) == 2


async def test_bad_identity_every_time() -> None:
    bad = with_payload(CAP.rx(QUERY), b"garbage")
    fake = FakeTransport.from_capture(FW96_CONNECT, replies={QUERY: bad})
    with pytest.raises(HandshakeError) as exc:
        async with TankG.over(fake, timeout=0.5):
            pass
    assert isinstance(exc.value.__cause__, ProtocolError)
    assert _queries(fake) == 3
    assert fake.closed


async def test_no_reply_ever_is_bounded() -> None:
    fake = FakeTransport.from_capture(FW96_CONNECT, drop={QUERY: 100})
    start = time.monotonic()
    with pytest.raises(HandshakeError):
        async with TankG.over(fake, timeout=0.1):
            pass
    assert time.monotonic() - start < 1.0
    assert fake.closed


async def test_split_reply() -> None:
    fake = FakeTransport.from_capture(FW96_CONNECT, split=5)
    async with TankG.over(fake) as pedal:
        assert pedal.identity.firmware == 96


async def test_untested_firmware_warns(caplog: pytest.LogCaptureFixture) -> None:
    original = decode_frame(CAP.rx(QUERY)).body
    fw97 = with_payload(CAP.rx(QUERY), b"TANK-Gv2_097" + original[12:])
    fake = FakeTransport.from_capture(FW96_CONNECT, replies={QUERY: fw97})
    with caplog.at_level(logging.WARNING, logger="openvave"):
        async with TankG.over(fake) as pedal:
            assert pedal.identity.firmware == 97
            assert pedal.identity.firmware_untested is True
    warnings = [r for r in caplog.records if r.name == "openvave" and r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "97" in warnings[0].getMessage()


async def test_connection_lost_propagates() -> None:
    fake = FakeTransport.from_capture(FW96_CONNECT, disconnect_after=0)
    with pytest.raises(ConnectionLostError):
        async with TankG.over(fake):
            pass
    assert fake.closed


async def test_close_on_body_exception() -> None:
    fake = FakeTransport.from_capture(FW96_CONNECT)
    with pytest.raises(ValueError):
        async with TankG.over(fake):
            raise ValueError("boom")
    assert fake.closed


async def test_stray_chunk_ignored() -> None:
    fake = FakeTransport.from_capture(FW96_CONNECT)
    wrapped = CorruptFirstReplies(fake, lambda f: b"\xff\xfe" + f)
    # The stray reply is dropped, the first attempt times out, the retry succeeds.
    async with TankG.over(wrapped, timeout=0.1) as pedal:
        assert pedal.identity.firmware == 96
    assert _queries(fake) == 2


async def test_trace(caplog: pytest.LogCaptureFixture) -> None:
    fake = FakeTransport.from_capture(FW96_CONNECT)
    with caplog.at_level(logging.DEBUG, logger="openvave.trace"):
        async with TankG.over(fake):
            pass
    lines = [r.getMessage() for r in caplog.records if r.name == "openvave.trace"]
    assert lines[0] == "TX 00 59 11 00 00 00 ff"
    assert f"RX {CAP.rx(QUERY).hex(' ')}" in lines


async def test_no_tasks_left() -> None:
    before = asyncio.all_tasks()
    fake = FakeTransport.from_capture(FW96_CONNECT)
    async with TankG.over(fake):
        pass
    await asyncio.sleep(0)
    assert asyncio.all_tasks() == before
