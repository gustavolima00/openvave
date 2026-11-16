"""TankG.read() / TankG.snapshot() over FakeTransport (T037)."""

from __future__ import annotations

import pytest

from openvave.errors import ConnectionLostError, RequestTimeoutError
from openvave.models import DeviceInfo, Region
from openvave.protocol import decode_frame
from openvave.session import TankG
from openvave.transport.fake import FakeTransport
from tests.support.captures import (
    DEVICE_INFO,
    FW96_CONNECT,
    GLOBAL,
    PRESET,
    STATUS,
    load_capture,
)

CAP = load_capture(FW96_CONNECT)
ECHO_LEN = 8
LABEL_FOR = {
    Region.DEVICE_INFO: DEVICE_INFO,
    Region.GLOBAL: GLOBAL,
    Region.CURRENT_PRESET: PRESET,
    Region.STATUS: STATUS,
}


def recorded_data(region: Region) -> bytes:
    return decode_frame(CAP.rx(LABEL_FOR[region])).body[ECHO_LEN:]


async def test_snapshot_matches_capture() -> None:
    fake = FakeTransport.from_capture(FW96_CONNECT)
    async with TankG.over(fake) as pedal:
        snap = await pedal.snapshot()
    assert list(snap.regions) == [
        Region.DEVICE_INFO,
        Region.GLOBAL,
        Region.CURRENT_PRESET,
        Region.STATUS,
    ]
    for region, read in snap.regions.items():
        assert read.region is region
        assert read.data == recorded_data(region)
    assert snap.identity.name == "TANK-Gv2"
    assert snap.identity.firmware == 96
    assert snap.device is None
    assert fake.sent == CAP.ordered_tx
    assert fake.closed


async def test_snapshot_carries_device() -> None:
    info = DeviceInfo("AAAA", "TANK-Gv2_BLE", -50)
    async with TankG.over(FakeTransport.from_capture(FW96_CONNECT), device=info) as pedal:
        snap = await pedal.snapshot()
    assert snap.device == info


async def test_read_at_is_utc() -> None:
    async with TankG.over(FakeTransport.from_capture(FW96_CONNECT)) as pedal:
        snap = await pedal.snapshot()
    offset = snap.read_at.utcoffset()
    assert offset is not None and offset.total_seconds() == 0


@pytest.mark.parametrize("region", list(Region))
async def test_read_single_region(region: Region) -> None:
    fake = FakeTransport.from_capture(FW96_CONNECT)
    async with TankG.over(fake) as pedal:
        read = await pedal.read(region)
    assert read.region is region
    assert read.data == recorded_data(region)
    assert len(read.data) == region.length
    assert fake.sent == [CAP.ordered_tx[0], CAP.tx(LABEL_FOR[region])]


@pytest.mark.parametrize("bad", [0x10000000, "CURRENT_PRESET", (4, 0x10000000, 21), None])
async def test_read_rejects_non_region(bad: object) -> None:
    fake = FakeTransport.from_capture(FW96_CONNECT)
    async with TankG.over(fake) as pedal:
        with pytest.raises(TypeError):
            await pedal.read(bad)  # type: ignore[arg-type]
    assert fake.sent == [CAP.ordered_tx[0]]


async def test_disconnect_mid_snapshot() -> None:
    fake = FakeTransport.from_capture(FW96_CONNECT, disconnect_after=3)
    snap = None
    with pytest.raises(ConnectionLostError):
        async with TankG.over(fake) as pedal:
            snap = await pedal.snapshot()
    assert snap is None
    assert fake.closed


async def test_dropped_read_times_out_without_retry() -> None:
    fake = FakeTransport.from_capture(FW96_CONNECT, drop={GLOBAL: 1})
    with pytest.raises(RequestTimeoutError):
        async with TankG.over(fake, timeout=0.1) as pedal:
            await pedal.snapshot()
    assert fake.sent.count(CAP.tx(GLOBAL)) == 1
    assert CAP.tx(PRESET) not in fake.sent
    assert fake.closed


async def test_split_replies_same_snapshot() -> None:
    async with TankG.over(FakeTransport.from_capture(FW96_CONNECT)) as pedal:
        whole = await pedal.snapshot()
    async with TankG.over(FakeTransport.from_capture(FW96_CONNECT, split=4)) as pedal:
        split = await pedal.snapshot()
    assert split.regions == whole.regions
    assert split.identity == whole.identity


async def test_read_outside_session_fails() -> None:
    pedal = TankG.over(FakeTransport.from_capture(FW96_CONNECT))
    with pytest.raises(ConnectionLostError):
        await pedal.read(Region.STATUS)
