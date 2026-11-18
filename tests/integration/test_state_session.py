"""``TankG.state()`` and ``snapshot().pedal_state`` (spec 004 US2 reporting, R1, R13)."""

from __future__ import annotations

from openvave import PedalState, TankG
from openvave.models import Region
from openvave.protocol import build_read
from openvave.transport.fake import FakeTransport
from tests.support import storage_fixture as sf
from tests.support.captures import FW96_CONNECT, GLOBAL, PRESET
from tests.support.write_fixture import NORMAL, make_fake

P = sf.PUBLIC_PRESET
BYPASS_GLOBAL = bytes([0, 0, 0xFF, NORMAL])
GLOBAL_READ = build_read(Region.GLOBAL)
BUFFER_READ = build_read(Region.CURRENT_PRESET)


class Sleeps:
    def __init__(self) -> None:
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


def _bypassed() -> FakeTransport:
    return make_fake(NORMAL, buffer=bytes(21), glob=BYPASS_GLOBAL)


async def test_normal_state_needs_one_read_of_each() -> None:
    fake = make_fake(NORMAL)
    sleeps = Sleeps()
    async with TankG.over(fake) as pedal:
        state = await pedal.state(sleep=sleeps)
    assert state == PedalState(kind="normal", index=1, bank=0)
    assert fake.sent[1:] == [GLOBAL_READ, BUFFER_READ]
    assert sleeps.calls == []


async def test_bypass_is_confirmed_by_a_second_read_300_ms_later() -> None:
    fake = _bypassed()
    sleeps = Sleeps()
    async with TankG.over(fake) as pedal:
        state = await pedal.state(sleep=sleeps)
    assert state == PedalState(kind="bypass", index=None, bank=0)
    assert sleeps.calls == [0.3]
    assert fake.sent[1:] == [GLOBAL_READ, BUFFER_READ, GLOBAL_READ, BUFFER_READ]


async def test_a_loading_read_takes_the_state_of_the_second_read() -> None:
    # first read of each region looks like bypass (loading), the second shows 1B loaded
    script_global = (
        sf.read_reply(0x20000000, BYPASS_GLOBAL),
        sf.read_reply(0x20000000, bytes([0, 0, 1, NORMAL])),
    )
    script_buffer = sf.read_reply(0x10000000, bytes(21)), sf.read_reply(0x10000000, P)
    fake = make_fake(
        NORMAL,
        script={
            "global": (GLOBAL_READ, script_global),
            "buffer": (BUFFER_READ, script_buffer),
        },
    )
    sleeps = Sleeps()
    async with TankG.over(fake) as pedal:
        state = await pedal.state(sleep=sleeps)
    assert state == PedalState(kind="normal", index=1, bank=0)
    assert sleeps.calls == [0.3]


async def test_snapshot_carries_the_pedal_state() -> None:
    fake = FakeTransport.from_capture(FW96_CONNECT)  # 1B in normal mode
    async with TankG.over(fake) as pedal:
        snapshot = await pedal.snapshot()
    assert snapshot.pedal_state == PedalState(kind="normal", index=1, bank=0)


async def test_snapshot_confirms_bypass() -> None:
    fake = FakeTransport.from_capture(
        FW96_CONNECT,
        replies={
            GLOBAL: sf.read_reply(0x20000000, BYPASS_GLOBAL),
            PRESET: sf.read_reply(0x10000000, bytes(21)),
        },
    )
    sleeps = Sleeps()
    async with TankG.over(fake) as pedal:
        snapshot = await pedal.snapshot(sleep=sleeps)
    assert snapshot.pedal_state is not None
    assert snapshot.pedal_state.kind == "bypass"
    assert sleeps.calls == [0.3]
    assert snapshot.regions[Region.GLOBAL].data == BYPASS_GLOBAL
