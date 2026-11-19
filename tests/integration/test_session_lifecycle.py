"""``TankG.open()`` / ``close()`` and the lost-link state (spec 005 T049, US6, research R10).

Data model "Session lifecycle": closed --open()--> open --close()--> closed; open --link lost-->
lost --close()--> closed. Lost: every operation raises ``ConnectionLostError`` at once and sends
nothing; nothing reconnects; ``open()`` on an open or lost session raises ``RuntimeError``.
"""

from __future__ import annotations

import asyncio

import pytest

from openvave.errors import ConnectionLostError
from openvave.models import DeviceInfo, Region
from openvave.protocol import build_read
from openvave.session import TankG
from openvave.transport import Transport
from openvave.transport.fake import FakeTransport
from tests.support.write_fixture import make_fake, writes

QUERY_FRAME = bytes.fromhex("00 59 11 00 00 00 ff")


class CountingSource:
    """A transport source that counts its calls and opens of the fake it hands out."""

    def __init__(self, fake: FakeTransport, device: DeviceInfo | None = None) -> None:
        self.fake = fake
        self.device = device
        self.calls = 0
        self.opens = 0
        original = fake.open

        async def counted_open() -> None:
            self.opens += 1
            await original()

        fake.open = counted_open  # type: ignore[method-assign]

    async def __call__(self) -> tuple[Transport, DeviceInfo | None]:
        self.calls += 1
        return self.fake, self.device


def _queries(fake: FakeTransport) -> int:
    return sum(1 for frame in fake.sent if frame == QUERY_FRAME)


async def _settle() -> None:
    for _ in range(5):
        await asyncio.sleep(0)


async def test_open_close_without_async_with() -> None:
    fake = make_fake()
    source = CountingSource(fake)
    pedal = TankG(source)
    await pedal.open()
    try:
        for _ in range(3):
            await pedal.read(Region.GLOBAL)
        await pedal.read(Region.CURRENT_PRESET)
        await pedal.set_field("gain", 90, experimental=True)
    finally:
        await pedal.close()
    assert source.calls == 1
    assert source.opens == 1
    assert _queries(fake) == 1
    assert len(writes(fake)) == 1
    assert fake.closed


async def test_is_connected_across_states() -> None:
    fake = make_fake()
    pedal = TankG.over(fake)
    assert pedal.is_connected is False
    await pedal.open()
    assert pedal.is_connected is True
    await pedal.close()
    assert pedal.is_connected is False


async def test_close_twice_and_close_before_open() -> None:
    fake = make_fake()
    pedal = TankG.over(fake)
    await pedal.close()  # never opened: harmless
    await pedal.open()
    await pedal.close()
    await pedal.close()
    assert fake.closed
    assert pedal.is_connected is False


async def test_open_twice_raises() -> None:
    fake = make_fake()
    source = CountingSource(fake)
    pedal = TankG(source)
    await pedal.open()
    try:
        with pytest.raises(RuntimeError):
            await pedal.open()
        assert source.calls == 1
        assert pedal.is_connected is True
    finally:
        await pedal.close()


async def test_async_with_on_an_open_session_raises() -> None:
    fake = make_fake()
    pedal = TankG.over(fake)
    await pedal.open()
    try:
        with pytest.raises(RuntimeError):
            async with pedal:
                pass
        assert pedal.is_connected is True  # the failed enter did not close it
    finally:
        await pedal.close()


async def test_operation_on_a_closed_session_raises_as_in_0_4_0() -> None:
    # 0.4.0 raises ConnectionLostError("session is closed") outside a session; kept unchanged
    fake = make_fake()
    pedal = TankG.over(fake)
    with pytest.raises(ConnectionLostError, match="session is closed"):
        await pedal.read(Region.GLOBAL)
    await pedal.open()
    await pedal.close()
    sent = len(fake.sent)
    with pytest.raises(ConnectionLostError, match="session is closed"):
        await pedal.read(Region.GLOBAL)
    assert len(fake.sent) == sent


async def test_lost_link_between_operations_fails_fast() -> None:
    fake = make_fake()
    pedal = TankG.over(fake)
    await pedal.open()
    try:
        await pedal.read(Region.GLOBAL)
        fake.lose_link()
        assert pedal.is_connected is False
        sent = list(fake.sent)
        with pytest.raises(ConnectionLostError):
            await pedal.read(Region.GLOBAL)
        with pytest.raises(ConnectionLostError):
            await pedal.set_field("gain", 90, experimental=True)
        with pytest.raises(ConnectionLostError):
            await pedal.state()
        assert fake.sent == sent  # nothing was written after the loss
    finally:
        await pedal.close()
    assert pedal.is_connected is False


async def test_lost_link_during_a_pending_request() -> None:
    fake = make_fake()  # no status block: a STATUS read gets no reply
    pedal = TankG.over(fake)
    await pedal.open()
    try:
        pending = asyncio.create_task(pedal.read(Region.STATUS))
        await _settle()
        assert fake.sent[-1] == build_read(Region.STATUS)
        fake.lose_link()
        with pytest.raises(ConnectionLostError):
            await pending
        sent = list(fake.sent)
        with pytest.raises(ConnectionLostError):
            await pedal.read(Region.CURRENT_PRESET)
        assert fake.sent == sent
        assert pedal.is_connected is False
    finally:
        await pedal.close()


async def test_write_raising_connection_lost_marks_the_session_lost() -> None:
    fake = make_fake()
    pedal = TankG.over(fake)
    await pedal.open()
    try:
        fake._disconnect_after = len(fake.sent)  # the next write drops the link
        with pytest.raises(ConnectionLostError):
            await pedal.read(Region.GLOBAL)
        assert pedal.is_connected is False
        with pytest.raises(ConnectionLostError):
            await pedal.read(Region.GLOBAL)
    finally:
        await pedal.close()


async def test_open_on_a_lost_session_raises() -> None:
    fake = make_fake()
    source = CountingSource(fake)
    pedal = TankG(source)
    await pedal.open()
    fake.lose_link()
    with pytest.raises(RuntimeError):
        await pedal.open()
    assert source.calls == 1
    await pedal.close()


async def test_close_then_open_after_a_lost_link_reconnects() -> None:
    fake = make_fake()
    source = CountingSource(fake)
    pedal = TankG(source)
    await pedal.open()
    fake.lose_link()
    await pedal.close()
    await pedal.open()
    try:
        assert source.calls == 2
        assert source.opens == 2
        assert _queries(fake) == 2
        assert pedal.is_connected is True
        await pedal.read(Region.GLOBAL)
    finally:
        await pedal.close()


async def test_nothing_reconnects_on_its_own() -> None:
    fake = make_fake()
    source = CountingSource(fake)
    pedal = TankG(source)
    await pedal.open()
    fake.lose_link()
    for _ in range(3):
        with pytest.raises(ConnectionLostError):
            await pedal.read(Region.GLOBAL)
    await pedal.close()
    assert source.calls == 1
    assert source.opens == 1


async def test_identity_and_device_after_open() -> None:
    fake = make_fake()
    device = DeviceInfo("AA:BB:CC:DD:EE:01", "TANK-Gv2_BLE", -50, "stage", "selected")
    pedal = TankG(CountingSource(fake, device))
    await pedal.open()
    try:
        assert pedal.identity.name == "TANK-Gv2"
        assert pedal.identity.firmware == 96
        assert pedal.device == device
    finally:
        await pedal.close()


async def test_failed_open_leaves_the_session_closed() -> None:
    fake = make_fake()
    fake._disconnect_after = 0  # the handshake write drops the link
    source = CountingSource(fake)
    pedal = TankG(source)
    with pytest.raises(ConnectionLostError):
        await pedal.open()
    assert pedal.is_connected is False
    assert fake.closed
    fake._disconnect_after = None
    await pedal.open()  # closed, so it may be opened again
    try:
        assert pedal.is_connected is True
    finally:
        await pedal.close()


async def test_async_with_closes_on_exit_and_on_exception() -> None:
    fake = make_fake()
    pedal = TankG.over(fake)
    async with pedal:
        assert pedal.is_connected is True
    assert fake.closed
    assert pedal.is_connected is False

    fake2 = make_fake()
    pedal2 = TankG.over(fake2)
    with pytest.raises(ValueError, match="boom"):
        async with pedal2:
            raise ValueError("boom")
    assert fake2.closed
    assert pedal2.is_connected is False


async def test_async_with_can_be_reused_after_close() -> None:
    fake = make_fake()
    pedal = TankG.over(fake)
    async with pedal:
        await pedal.read(Region.GLOBAL)
    async with pedal:
        await pedal.read(Region.GLOBAL)
    assert _queries(fake) == 2
