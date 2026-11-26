"""The simulated pedal through the public session API (spec 008 US1, FR-004–FR-007, FR-009).

Each case runs twice: on ``FakeTransport.simulated(<connect capture>)`` and on the internal write
fixture built for the same starting state (``make_fake(NORMAL, status=b"\\x01")``: 1B, normal
mode, loopback on, synthetic stored image). Results, sent frames and a final backup must be
equal (SC-002). The fixture is the oracle; the simulated pedal is the code under test.
"""

from __future__ import annotations

import dataclasses
import functools
from collections.abc import Awaitable, Callable
from datetime import datetime
from enum import Enum
from typing import Any

import pytest

from openvave import (
    Backup,
    FakeTransport,
    OpenvaveError,
    Region,
    TankG,
    WriteNakError,
)
from tests.support import storage_fixture as sf
from tests.support.captures import FW96_CONNECT, PRESET, load_capture
from tests.support.write_fixture import NORMAL, make_fake, write_frame

CAP = load_capture(FW96_CONNECT)
TIMEOUT = 0.3
"""Short session timeout: ``no_reply`` faults wait for it."""

Scenario = Callable[[TankG, FakeTransport], Awaitable[Any]]


async def no_sleep(_: float) -> None:
    return None


def keep(_: Backup) -> None:
    return None


def simulated(**options: Any) -> FakeTransport:
    return FakeTransport.simulated(FW96_CONNECT, **options)


def oracle(*, chunk_size: int | None = None, **options: Any) -> FakeTransport:
    """The write fixture (it has no ``chunk_size`` option: pass it to the class it builds)."""
    cls = functools.partial(FakeTransport, chunk_size=chunk_size)
    return make_fake(NORMAL, status=b"\x01", cls=cls, **options)  # type: ignore[arg-type]


def normal(value: Any) -> Any:
    """A comparable form: dataclasses as dicts, timestamps blanked, errors by class and fields."""
    if isinstance(value, datetime):
        return "<time>"
    if isinstance(value, BaseException):
        fields = {k: normal(v) for k, v in vars(value).items()}
        return (type(value).__name__, str(value), fields)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return (
            type(value).__name__,
            {f.name: normal(getattr(value, f.name)) for f in dataclasses.fields(value)},
        )
    if isinstance(value, dict):
        return {normal(k): normal(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [normal(v) for v in value]
    if isinstance(value, Enum):
        return value.name
    return value


async def run(fake: FakeTransport, *scenarios: Scenario) -> list[Any]:
    """Each scenario in its own session (a lost link ends a session); errors are results."""
    out: list[Any] = []
    for scenario in scenarios:
        try:
            async with TankG.over(fake, timeout=TIMEOUT) as pedal:  # type: ignore[arg-type]
                out.append(normal(await scenario(pedal, fake)))
        except OpenvaveError as err:
            out.append(normal(err))
    async with TankG.over(fake, timeout=TIMEOUT) as pedal:  # type: ignore[arg-type]
        out.append(normal(await pedal.backup()))
    return out


async def compare(*scenarios: Scenario, **options: Any) -> tuple[list[Any], FakeTransport]:
    sim, ref = simulated(**options), oracle(**options)
    got = await run(sim, *scenarios)
    want = await run(ref, *scenarios)
    assert got == want
    assert sim.sent == ref.sent
    assert sim.commits == ref.commits
    return got, sim


# -- volatile operations ------------------------------------------------------------------------


async def test_opening_state_and_current_preset() -> None:
    async def scenario(pedal: TankG, _: FakeTransport) -> Any:
        state = await pedal.state(sleep=no_sleep)
        preset = await pedal.read(Region.CURRENT_PRESET)
        assert (state.kind, state.position) == ("normal", "1B")
        assert preset.data == CAP.rx(PRESET)[14:-1]
        return state, preset

    await compare(scenario)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("gain", 90),
        ("reverb_decay", ("spring", 10)),
        ("delay_on", False),
        ("led_colour", (255, 0, 0)),
    ],
)
async def test_set_field(field: str, value: Any) -> None:
    async def scenario(pedal: TankG, _: FakeTransport) -> Any:
        result = await pedal.set_field(field, value, sleep=no_sleep)
        assert result.applied
        return result

    await compare(scenario)


async def test_set_fields() -> None:
    async def scenario(pedal: TankG, _: FakeTransport) -> Any:
        changes = {"gain": 95, "treble": 10, "delay_on": False, "led_colour": "#00ff00"}
        return await pedal.set_fields(changes, sleep=no_sleep)

    await compare(scenario)


async def test_select_reload_bypass_and_loopback() -> None:
    async def select(pedal: TankG, _: FakeTransport) -> Any:
        result = await pedal.select_preset(6, sleep=no_sleep)
        state = await pedal.state(sleep=no_sleep)
        assert state.position == "2C"
        assert (await pedal.read(Region.CURRENT_PRESET)).data == sf.synthetic_preset(6)
        return result, state

    async def edit_then_reload(pedal: TankG, _: FakeTransport) -> Any:
        await pedal.set_field("gain", 1, sleep=no_sleep)
        return await pedal.reload_preset(discard_edits=True, sleep=no_sleep)

    async def bypass(pedal: TankG, _: FakeTransport) -> Any:
        on = await pedal.bypass_on(sleep=no_sleep)
        state = await pedal.state(sleep=no_sleep)
        assert state.kind == "bypass"
        off = await pedal.bypass_off(6, sleep=no_sleep)
        return on, state, off

    async def loopback(pedal: TankG, _: FakeTransport) -> Any:
        result = await pedal.set_loopback(False, sleep=no_sleep)
        assert (await pedal.read(Region.STATUS)).data == b"\x00"
        return result

    await compare(select, edit_then_reload, bypass, loopback)


async def test_backup() -> None:
    async def scenario(pedal: TankG, _: FakeTransport) -> Any:
        backup = await pedal.backup()
        assert len(backup.presets) == 36
        assert backup.presets[1].data == sf.PUBLIC_PRESET
        assert backup.image == sf.synthetic_image()
        return backup

    await compare(scenario)


async def test_backup_with_chunked_replies() -> None:
    async def scenario(pedal: TankG, _: FakeTransport) -> Any:
        return await pedal.backup()

    await compare(scenario, chunk_size=182)


async def test_select_transient_shows_the_loading_state() -> None:
    async def scenario(pedal: TankG, _: FakeTransport) -> Any:
        return await pedal.select_preset(6, sleep=no_sleep)

    glob = sf.read_request(0x20000000, 4)
    select = write_frame(0xE0000006, b"\x01")

    def global_reads_after_select(fake: FakeTransport) -> int:
        at = fake.sent.index(select)
        return fake.sent[at:].count(glob)

    _, plain = await compare(scenario)
    _, slow = await compare(scenario, select_transient=2)
    assert global_reads_after_select(slow) == global_reads_after_select(plain) + 2


# -- persistent operations ----------------------------------------------------------------------


@pytest.mark.persistent_writes
async def test_save_in_place_and_to_another_slot() -> None:
    async def in_place(pedal: TankG, _: FakeTransport) -> Any:
        await pedal.set_field("gain", 90, sleep=no_sleep)
        return await pedal.save_preset(unsafe=True, on_backup=keep, sleep=no_sleep)

    async def to_other(pedal: TankG, _: FakeTransport) -> Any:
        await pedal.set_field("bass", 3, sleep=no_sleep)
        return await pedal.save_preset(to=20, unsafe=True, on_backup=keep, sleep=no_sleep)

    got, sim = await compare(in_place, to_other)
    final = got[-1]
    assert sim.commits == 2
    image = final[1]["image"]
    assert image[2 + 21 * 1 + 6] == 90
    assert image[2 + 21 * 20 + 9] == 3


@pytest.mark.persistent_writes
async def test_restore_slot_and_all() -> None:
    saved: list[Backup] = []

    async def take(pedal: TankG, _: FakeTransport) -> Any:
        saved.clear()
        saved.append(await pedal.backup())
        await pedal.set_field("gain", 90, sleep=no_sleep)
        await pedal.save_preset(unsafe=True, on_backup=keep, sleep=no_sleep)
        await pedal.set_field("gain", 80, sleep=no_sleep)
        return await pedal.save_preset(to=5, unsafe=True, on_backup=keep, sleep=no_sleep)

    async def restore_slot(pedal: TankG, _: FakeTransport) -> Any:
        return await pedal.restore(
            saved[0], slot=1, unsafe=True, discard_edits=True, on_backup=keep, sleep=no_sleep
        )

    async def restore_all(pedal: TankG, _: FakeTransport) -> Any:
        return await pedal.restore(
            saved[0], all=True, unsafe=True, discard_edits=True, on_backup=keep, sleep=no_sleep
        )

    got, _ = await compare(take, restore_slot, restore_all)
    assert got[-1][1]["image"] == sf.synthetic_image()


@pytest.mark.persistent_writes
async def test_copy_swap_export_import() -> None:
    async def copy(pedal: TankG, _: FakeTransport) -> Any:
        return await pedal.copy_preset(0, 10, unsafe=True, on_backup=keep, sleep=no_sleep)

    async def swap(pedal: TankG, _: FakeTransport) -> Any:
        return await pedal.swap_presets(2, 3, unsafe=True, on_backup=keep, sleep=no_sleep)

    async def export_import(pedal: TankG, _: FakeTransport) -> Any:
        exported = await pedal.export_preset(7)
        assert exported.data == sf.synthetic_preset(7)
        imported = await pedal.import_preset(
            exported, 30, unsafe=True, on_backup=keep, sleep=no_sleep
        )
        return exported, imported

    got, _ = await compare(copy, swap, export_import)
    image = got[-1][1]["image"]
    assert image[2 + 21 * 10 : 23 + 21 * 10] == sf.synthetic_preset(0)
    assert image[2 + 21 * 2 : 23 + 21 * 2] == sf.synthetic_preset(3)
    assert image[2 + 21 * 30 : 23 + 21 * 30] == sf.synthetic_preset(7)


# -- faults -------------------------------------------------------------------------------------

ACTIONS = ["nak", "no_reply", "disconnect", "corrupt", "ignore"]


@pytest.mark.parametrize("action", ACTIONS)
async def test_volatile_fault_once(action: str) -> None:
    async def knob(pedal: TankG, _: FakeTransport) -> Any:
        return await pedal.set_field("gain", 90, sleep=no_sleep)

    async def knob_again(pedal: TankG, _: FakeTransport) -> Any:
        result = await pedal.set_field("gain", 91, sleep=no_sleep)
        assert result.applied
        return result

    got, _ = await compare(knob, knob_again, faults={"knob_block": action})
    first = got[0]
    assert isinstance(first, tuple) and first[0].endswith("Error"), first


@pytest.mark.persistent_writes
@pytest.mark.parametrize("action", ACTIONS)
async def test_persistent_fault_once(action: str) -> None:
    async def save(pedal: TankG, _: FakeTransport) -> Any:
        await pedal.set_field("gain", 90, sleep=no_sleep)
        return await pedal.save_preset(to=2, unsafe=True, on_backup=keep, sleep=no_sleep)

    async def save_again(pedal: TankG, _: FakeTransport) -> Any:
        await pedal.set_field("gain", 91, sleep=no_sleep)
        result = await pedal.save_preset(to=3, unsafe=True, on_backup=keep, sleep=no_sleep)
        assert result.verified
        return result

    got, _ = await compare(save, save_again, faults={"stored_slot": action})
    first = got[0]
    assert isinstance(first, tuple) and first[0].endswith("Error"), first


async def test_nak_is_a_write_nak_error() -> None:
    fake = simulated(faults={"knob_block": "nak"})
    async with TankG.over(fake, timeout=TIMEOUT) as pedal:  # type: ignore[arg-type]
        with pytest.raises(WriteNakError):
            await pedal.set_field("gain", 90, sleep=no_sleep)


# -- sent and the allowlist ---------------------------------------------------------------------


async def test_sent_holds_every_request_in_order() -> None:
    fake = simulated()
    async with TankG.over(fake, timeout=TIMEOUT) as pedal:  # type: ignore[arg-type]
        await pedal.set_field("gain", 90, sleep=no_sleep)
    assert fake.sent[0] == CAP.tx("query name/version")
    knob = [f for f in fake.sent if f[2] == 0x22]
    assert len(knob) == 1 and knob[0][6:11] == bytes.fromhex("04 04 00 00 10")
    assert fake.sent.index(knob[0]) > 0


async def test_frame_outside_the_allowlist_raises() -> None:
    """A write to the global block is not on the allowlist. It goes through the unaudited
    ``write`` (``tests/conftest.py`` wraps it with ``functools.wraps``), so the session audit
    does not record this deliberate violation."""
    fake = simulated()
    await fake.open()
    write = FakeTransport.write.__wrapped__  # type: ignore[attr-defined]
    with pytest.raises(AssertionError, match="allowlist"):
        await write(fake, write_frame(0x20000000, bytes([0, 0, 2, 1])))
