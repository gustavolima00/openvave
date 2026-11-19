"""``identify(entries)``: firmware of each Tank-G found by a scan (spec 005 T016, research R7).

Each pedal is connected in turn through an injected transport factory; only the confirmed ``0x11``
query is sent; a failure is recorded on its row and the next pedal is still tried.
"""

from __future__ import annotations

from openvave.errors import ConnectionLostError
from openvave.models import DeviceInfo, ScanEntry
from openvave.transport import Transport
from openvave.transport.ble import identify
from openvave.transport.fake import FakeTransport
from tests.support.captures import FW96_CONNECT, QUERY, load_capture
from tests.support.scanner import SPEAKER, TANK, UUID_1, UUID_2, UUID_3

CAP = load_capture(FW96_CONNECT)


def entry(identifier: str, name: str = TANK, rssi: int | None = -60) -> ScanEntry:
    return ScanEntry(DeviceInfo(identifier, name, rssi), tank_g=name == TANK)


class FailingOpen(FakeTransport):
    async def open(self) -> None:
        raise ConnectionLostError("connect failed: out of range")


async def test_each_pedal_is_identified_in_order_with_one_query() -> None:
    fakes = {u: FakeTransport.from_capture(FW96_CONNECT) for u in (UUID_1, UUID_2)}
    order: list[str] = []

    async def factory(device: DeviceInfo) -> Transport:
        order.append(device.identifier)
        return fakes[device.identifier]

    result = await identify([entry(UUID_1), entry(UUID_2)], transport_factory=factory)
    assert order == [UUID_1, UUID_2]
    assert [e.firmware for e in result] == [96, 96]
    assert [e.identify_error for e in result] == [None, None]
    for fake in fakes.values():
        assert fake.sent == [CAP.tx(QUERY)]  # the handshake only
        assert fake.closed


async def test_a_failure_is_recorded_and_the_next_pedal_is_tried() -> None:
    good = FakeTransport.from_capture(FW96_CONNECT)

    async def factory(device: DeviceInfo) -> Transport:
        if device.identifier == UUID_1:
            return FailingOpen.from_capture(FW96_CONNECT)
        return good

    result = await identify([entry(UUID_1), entry(UUID_2)], transport_factory=factory)
    assert result[0].firmware is None
    assert result[0].identify_error == "connect failed: out of range"
    assert result[1].firmware == 96 and result[1].identify_error is None
    assert good.sent == [CAP.tx(QUERY)]


async def test_a_handshake_without_reply_is_recorded() -> None:
    silent = FakeTransport.from_capture(FW96_CONNECT, drop={QUERY: 99})

    async def factory(device: DeviceInfo) -> Transport:
        return silent

    result = await identify([entry(UUID_3)], timeout=0.05, transport_factory=factory)
    assert result[0].firmware is None
    assert result[0].identify_error
    assert all(frame == CAP.tx(QUERY) for frame in silent.sent)


async def test_a_factory_error_is_recorded() -> None:
    async def factory(device: DeviceInfo) -> Transport:
        raise ConnectionLostError("connect failed: busy")

    result = await identify([entry(UUID_1)], transport_factory=factory)
    assert result[0].identify_error == "connect failed: busy"


async def test_other_advertisers_are_skipped() -> None:
    seen: list[str] = []

    async def factory(device: DeviceInfo) -> Transport:
        seen.append(device.identifier)
        return FakeTransport.from_capture(FW96_CONNECT)

    rows = [entry(UUID_1), entry(SPEAKER, "Some Speaker", -30)]
    result = await identify(rows, transport_factory=factory)
    assert seen == [UUID_1]
    assert result[1] == rows[1]  # untouched
