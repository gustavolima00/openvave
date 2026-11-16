"""``TankG.watch()`` over FakeTransport sequences (T019, US1)."""

from __future__ import annotations

import asyncio
import inspect
from pathlib import Path

import pytest

from openvave.cli.render import WATCH_REGION_KEYS
from openvave.errors import ConnectionLostError
from openvave.models import Region, WatchChange, WatchStart
from openvave.protocol import build_query, build_read
from openvave.session import TankG
from openvave.transport.fake import FakeTransport
from tests.support.captures import CAPTURES_DIR, DEVICE_INFO, load_capture
from tests.support.watch import BASE, SleepRecorder, watch_fake, watch_script

WATCHED = (Region.GLOBAL, Region.CURRENT_PRESET, Region.STATUS)
CYCLE_FRAMES = [build_read(r) for r in WATCHED]
REVERB_SWEEP = [{}, {"preset": {15: 64}}, {"preset": {15: 127}}]


async def collect(fake: FakeTransport, **kwargs: object) -> list[WatchStart | WatchChange]:
    sleep = kwargs.pop("sleep", SleepRecorder())
    async with TankG.over(fake) as pedal:
        return [e async for e in pedal.watch(sleep=sleep, **kwargs)]  # type: ignore[arg-type]


async def test_reverb_decay_sweep_yields_start_then_one_change_per_step() -> None:
    fake = watch_fake(REVERB_SWEEP)
    events = await collect(fake, cycles=4)
    assert [type(e) for e in events] == [WatchStart, WatchChange, WatchChange]
    start, first, second = events
    assert isinstance(start, WatchStart)
    assert list(start.regions) == list(WATCHED)
    assert start.identity.firmware == 96
    assert start.regions[Region.CURRENT_PRESET].read.data[15] == 5
    for change, (old, new), cycle in ((first, (5, 64), 2), (second, (64, 127), 3)):
        assert isinstance(change, WatchChange)
        assert change.cycle == cycle
        assert len(change.changes) == 1
        byte = change.changes[0]
        assert (byte.region, byte.offset, byte.old, byte.new) == (
            Region.CURRENT_PRESET,
            15,
            old,
            new,
        )
        assert byte.field is not None and byte.field.name == "reverb_decay"
        assert change.regions[Region.CURRENT_PRESET].read.data[15] == new
    assert [e.t for e in events] == sorted(e.t for e in events)
    assert all(e.t >= 0 for e in events)


async def test_only_query_and_reads_in_cycle_order() -> None:
    fake = watch_fake(REVERB_SWEEP)
    await collect(fake, cycles=4)
    assert fake.sent[0] == build_query()
    assert fake.sent[1:] == CYCLE_FRAMES * 4
    assert {f[2] for f in fake.sent} <= {0x11, 0x23}


async def test_co_moving_bytes_are_one_event() -> None:
    fake = watch_fake([{}, {"preset": {16: 90, 17: 8}}])
    events = await collect(fake, cycles=2)
    assert len(events) == 2
    change = events[1]
    assert isinstance(change, WatchChange)
    assert [(c.offset, c.old, c.new) for c in change.changes] == [(16, 4, 90), (17, 7, 8)]


async def test_changes_in_several_regions_in_region_order() -> None:
    fake = watch_fake([{}, {"global": {3: 0}, "preset": {15: 6}, "status": {0: 2}}])
    events = await collect(fake, cycles=2)
    change = events[1]
    assert isinstance(change, WatchChange)
    assert [(c.region, c.offset) for c in change.changes] == [
        (Region.GLOBAL, 3),
        (Region.CURRENT_PRESET, 15),
        (Region.STATUS, 0),
    ]


async def test_no_event_for_unchanged_cycles() -> None:
    fake = watch_fake([{}])
    events = await collect(fake, cycles=5)
    assert [type(e) for e in events] == [WatchStart]


async def test_interval_below_minimum_is_value_error() -> None:
    fake = watch_fake([{}])
    async with TankG.over(fake) as pedal:
        with pytest.raises(ValueError):
            pedal.watch(interval=0.1)
        with pytest.raises(ValueError):
            pedal.watch(cycles=0)
        pedal.watch(interval=0.2)  # the minimum itself is accepted
    assert fake.sent == [build_query()]


@pytest.mark.parametrize(
    "regions",
    [
        (Region.DEVICE_INFO,),
        (Region.GLOBAL, Region.DEVICE_INFO),
        (),
        (Region.GLOBAL, Region.GLOBAL),
        (0x20000000,),
    ],
    ids=["device_info", "with_device_info", "empty", "duplicate", "address"],
)
async def test_bad_regions_are_value_error(regions: tuple[Region, ...]) -> None:
    fake = watch_fake([{}])
    async with TankG.over(fake) as pedal:
        with pytest.raises(ValueError):
            pedal.watch(regions=regions)
    assert fake.sent == [build_query()]


def test_default_regions_and_interval() -> None:
    params = inspect.signature(TankG.watch).parameters
    assert params["interval"].default == 0.5
    assert tuple(params["regions"].default) == WATCHED
    assert params["cycles"].default is None
    assert params["sleep"].default is asyncio.sleep


async def test_device_info_never_read() -> None:
    fake = watch_fake(REVERB_SWEEP)
    await collect(fake, cycles=3)
    assert BASE.tx(DEVICE_INFO) not in fake.sent


async def test_custom_region_subset() -> None:
    fake = watch_fake(REVERB_SWEEP)
    events = await collect(fake, cycles=2, regions=(Region.CURRENT_PRESET,))
    assert fake.sent[1:] == [build_read(Region.CURRENT_PRESET)] * 2
    assert list(events[0].regions) == [Region.CURRENT_PRESET]


async def test_sleeps_between_cycles_not_after_the_last() -> None:
    recorder = SleepRecorder()
    await collect(watch_fake([{}]), cycles=3, sleep=recorder, interval=0.5)
    assert len(recorder.calls) == 2
    assert all(0 < s <= 0.5 for s in recorder.calls)


class SlowFake(FakeTransport):
    """Each request takes ``delay`` real seconds; fails if two requests are ever in flight."""

    def __init__(self, delay: float) -> None:
        super().__init__(watch_script([{}]))
        self.delay = delay
        self.in_flight = 0
        self.max_in_flight = 0

    async def write(self, frame: bytes) -> None:
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        await asyncio.sleep(self.delay)
        await super().write(frame)

    def _deliver(self, reply: bytes) -> None:
        self.in_flight -= 1
        super()._deliver(reply)


async def test_overrunning_cycle_starts_next_at_once_without_overlap() -> None:
    fake = SlowFake(delay=0.08)  # 3 reads ≈ 0.24 s > interval 0.2 s
    recorder = SleepRecorder()
    events = await collect(fake, cycles=3, sleep=recorder, interval=0.2)
    assert recorder.calls == []
    assert fake.max_in_flight == 1
    assert len(fake.sent) == 1 + 3 * 3
    assert [type(e) for e in events] == [WatchStart]


async def test_connection_lost_propagates_and_transport_closes() -> None:
    fake = watch_fake(REVERB_SWEEP, disconnect_after=1 + 3 * 2)
    events: list[WatchStart | WatchChange] = []
    with pytest.raises(ConnectionLostError):
        async with TankG.over(fake) as pedal:
            async for event in pedal.watch(sleep=SleepRecorder()):
                events.append(event)
    assert [type(e) for e in events] == [WatchStart, WatchChange]
    assert fake.closed


async def test_break_stops_and_closes() -> None:
    fake = watch_fake(REVERB_SWEEP)
    async with TankG.over(fake) as pedal:
        async for event in pedal.watch(sleep=SleepRecorder()):
            assert isinstance(event, WatchStart)
            break
    assert fake.closed
    assert len(fake.sent) == 1 + 3


# -- replay of committed hardware excerpts (T032) ------------------------------------------------

REVERB_DECAY_STEP = CAPTURES_DIR / "fw96" / "20261116-step-reverb_decay.jsonl"


def recorded_changes(path: Path) -> list[list[tuple[str, int, int, int]]]:
    """The excerpt's own ``change`` lines, grouped per cycle, in order."""
    by_cycle: dict[int, list[tuple[str, int, int, int]]] = {}
    for record in load_capture(path).records:
        if record["event"] == "change":
            change = (record["region"], record["offset"], record["old"], record["new"])
            by_cycle.setdefault(record["cycle"], []).append(change)
    return list(by_cycle.values())


async def replayed_changes(path: Path) -> list[list[tuple[str, int, int, int]]]:
    cycles = len(load_capture(path).rx_all("global"))
    events = await collect(FakeTransport.from_capture(path), cycles=cycles)
    assert isinstance(events[0], WatchStart)
    return [
        [(WATCH_REGION_KEYS[c.region], c.offset, c.old, c.new) for c in e.changes]
        for e in events[1:]
        if isinstance(e, WatchChange)
    ]


async def test_reverb_decay_excerpt_replays_to_the_recorded_changes() -> None:
    replayed = await replayed_changes(REVERB_DECAY_STEP)
    assert replayed == recorded_changes(REVERB_DECAY_STEP)
    values = [new for cycle in replayed for (_, _, _, new) in cycle]
    assert {(region, offset) for cycle in replayed for (region, offset, _, _) in cycle} == {
        ("preset", 15)
    }
    assert min(values) == 0 and max(values) == 127
