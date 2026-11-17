"""``TankG.plan_select`` / ``select_preset`` over a fake pedal (T028, US3, FR-016/017, R9)."""

from __future__ import annotations

import pytest

from openvave import TankG, WriteNakError, WriteNotAppliedError, WriteRefusedError
from openvave.models import Region
from openvave.protocol import build_read, build_storage_read
from openvave.protocol.storage import StorageRead, parse_position
from tests.support import storage_fixture as sf
from tests.support.audit import unsafe_frames
from tests.support.write_fixture import (
    ACK,
    EDIT,
    NORMAL,
    TUNER,
    make_fake,
    nak,
    write_frame,
    writes,
)

GLOBAL_READ = build_read(Region.GLOBAL)
PRESET_READ = build_read(Region.CURRENT_PRESET)
SELECT_6 = bytes.fromhex("00 59 22 09 00 00 04 06 00 00 e0 01 00 00 01 13")


class Sleeps:
    def __init__(self) -> None:
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


async def test_select_6_from_1b() -> None:
    fake = make_fake(NORMAL, select_transient=1)
    sleep = Sleeps()
    async with TankG.over(fake) as pedal:
        result = await pedal.select_preset(6, experimental=True, sleep=sleep)
    assert writes(fake) == [SELECT_6]
    assert fake.sent[1:] == [
        GLOBAL_READ,
        PRESET_READ,
        SELECT_6,
        GLOBAL_READ,  # slot ff: still loading
        GLOBAL_READ,  # 01 01 02 01
        PRESET_READ,
        build_storage_read(StorageRead.preset(6)),
    ]
    assert sleep.calls == [0.1, 0.1]
    assert result.reply == ACK
    assert result.global_after.data == bytes.fromhex("01 01 02 01")
    assert result.after.data == sf.synthetic_preset(6)
    assert result.applied is True
    assert result.plan.action == "select 2C"
    assert result.plan.target.kind == "preset_select"
    assert result.plan.target.argument == 6
    regions = {c.region for c in result.changes}
    assert regions == {Region.GLOBAL, Region.CURRENT_PRESET}


async def test_select_without_transient_reads_global_once() -> None:
    fake = make_fake(TUNER)
    sleep = Sleeps()
    async with TankG.over(fake) as pedal:
        result = await pedal.select_preset(0, experimental=True, sleep=sleep)
    assert fake.sent.count(GLOBAL_READ) == 2
    assert sleep.calls == [0.1]
    assert result.applied is True


async def test_edit_mode_requires_discard_edits() -> None:
    fake = make_fake(EDIT)
    async with TankG.over(fake) as pedal:
        plan = await pedal.plan_select(6, experimental=True)
        with pytest.raises(WriteRefusedError) as exc:
            await pedal.select_preset(6, experimental=True, sleep=Sleeps())
    assert plan.refusal == "edits_would_be_discarded"
    assert exc.value.reason == "edits_would_be_discarded"
    assert writes(fake) == []


async def test_edit_mode_with_discard_edits_is_sent() -> None:
    fake = make_fake(EDIT)
    async with TankG.over(fake) as pedal:
        result = await pedal.select_preset(6, discard_edits=True, experimental=True, sleep=Sleeps())
    assert writes(fake) == [SELECT_6]
    assert result.applied is True


async def test_confirmed_select_needs_no_opt_in() -> None:
    # spec 003 M3: preset select confirmed by gate sessions A and B on fw 96 (SC-005)
    fake = make_fake(NORMAL, select_transient=1)
    async with TankG.over(fake) as pedal:
        plan = await pedal.plan_select(6)
        result = await pedal.select_preset(6, sleep=Sleeps())
    assert plan.refusal is None
    assert plan.confidence == "confirmed"
    assert writes(fake) == [SELECT_6]
    assert result.applied is True


async def test_slot_stuck_at_ff_is_not_applied() -> None:
    fake = make_fake(NORMAL, select_transient=100)
    sleep = Sleeps()
    async with TankG.over(fake) as pedal:
        with pytest.raises(WriteNotAppliedError) as exc:
            await pedal.select_preset(6, experimental=True, sleep=sleep)
    assert fake.sent.count(GLOBAL_READ) == 1 + 10
    assert len(sleep.calls) == 10
    assert exc.value.result.applied is False
    assert writes(fake) == [SELECT_6]


async def test_bank_slot_mismatch_is_not_applied() -> None:
    # ACK, but the fake does not apply the select: the pedal stays on 1B.
    fake = make_fake(NORMAL, apply_writes=False, script={"select": (SELECT_6, ACK)})
    async with TankG.over(fake) as pedal:
        with pytest.raises(WriteNotAppliedError) as exc:
            await pedal.select_preset(6, experimental=True, sleep=Sleeps())
    result = exc.value.result
    assert result.applied is False
    assert result.global_after.data == bytes([0, 0, 1, NORMAL])


async def test_nak() -> None:
    fake = make_fake(NORMAL, script={"select": (SELECT_6, nak(2))})
    async with TankG.over(fake) as pedal:
        with pytest.raises(WriteNakError) as exc:
            await pedal.select_preset(6, experimental=True, sleep=Sleeps())
    assert exc.value.reply == nak(2)
    assert fake.sent[-1] == SELECT_6


@pytest.mark.parametrize("index", [0, 6, 35])
async def test_dry_run_frames_equal_sent_frames(index: int) -> None:
    fake = make_fake(NORMAL)
    async with TankG.over(fake) as pedal:
        plan = await pedal.plan_select(index, experimental=True)
        assert writes(fake) == []
        assert plan.reads == (GLOBAL_READ, PRESET_READ)
        result = await pedal.select_preset(index, experimental=True, sleep=Sleeps())
    assert plan.frame == write_frame(0xE0000000 + index, b"\x01")
    assert writes(fake) == [plan.frame]
    assert result.plan.frame == plan.frame
    assert unsafe_frames(fake.sent) == []


@pytest.mark.parametrize("index", [-1, 36])
async def test_invalid_index(index: int) -> None:
    fake = make_fake(NORMAL)
    async with TankG.over(fake) as pedal:
        with pytest.raises(ValueError):
            await pedal.plan_select(index)
    assert writes(fake) == []


@pytest.mark.parametrize("text", ["10A", "1E", "0A", "36", ""])
def test_parse_position_errors_before_connecting(text: str) -> None:
    with pytest.raises(ValueError):
        parse_position(text)
