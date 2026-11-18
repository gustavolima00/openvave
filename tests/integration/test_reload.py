"""``TankG.reload_preset`` (spec 004 US1 FR-005, research R4): discard unsaved edits."""

from __future__ import annotations

import pytest

from openvave import TankG, WriteRefusedError, WriteResult
from openvave.models import Region
from openvave.protocol import build_read, build_storage_read
from openvave.protocol.storage import StorageRead
from tests.support import storage_fixture as sf
from tests.support.write_fixture import EDIT, NORMAL, TUNER, make_fake, write_frame, writes

P = sf.PUBLIC_PRESET
EDITED = P[:6] + bytes([90]) + P[7:]  # gain 60 -> 90, not saved
SELECT_1B = write_frame(0xE0000001, b"\x01")


async def _no_sleep(_: float) -> None:
    return None


async def test_reload_in_normal_mode_selects_the_loaded_preset() -> None:
    fake = make_fake(NORMAL, buffer=EDITED)
    async with TankG.over(fake) as pedal:
        result = await pedal.reload_preset(sleep=_no_sleep)
    assert isinstance(result, WriteResult)
    assert writes(fake) == [SELECT_1B]
    assert result.plan.action == "reload 1B"
    assert result.plan.target.kind == "preset_select"
    assert result.plan.target.argument == 1
    assert result.applied is True
    assert result.after.data == P
    plan_reads = [
        build_read(Region.GLOBAL),
        build_read(Region.CURRENT_PRESET),
        build_storage_read(StorageRead.preset(1)),
    ]
    assert list(result.plan.reads) == plan_reads
    assert fake.sent[1:4] == plan_reads
    assert [(c.offset, c.old, c.new) for c in result.changes] == [(6, 90, 60)]


async def test_nothing_to_discard_sends_nothing() -> None:
    fake = make_fake(NORMAL)  # buffer equals stored 1B
    async with TankG.over(fake) as pedal:
        plan = await pedal.plan_reload()
        result = await pedal.reload_preset(sleep=_no_sleep)
    assert plan.no_change is True
    assert result.plan.no_change is True
    assert result.reply == b""
    assert result.applied is True
    assert writes(fake) == []


async def test_edit_mode_needs_discard_edits() -> None:
    fake = make_fake(EDIT, buffer=EDITED)
    async with TankG.over(fake) as pedal:
        plan = await pedal.plan_reload()
        assert plan.refusal == "edits_would_be_discarded"
        with pytest.raises(WriteRefusedError) as exc:
            await pedal.reload_preset(sleep=_no_sleep)
        assert exc.value.reason == "edits_would_be_discarded"
        assert writes(fake) == []
        result = await pedal.reload_preset(discard_edits=True, sleep=_no_sleep)
    assert writes(fake) == [SELECT_1B]
    assert result.applied is True


async def test_tuner_is_refused() -> None:
    fake = make_fake(TUNER, buffer=EDITED)
    async with TankG.over(fake) as pedal:
        plan = await pedal.plan_reload(sleep=_no_sleep)
        assert plan.refusal == "tuner_mode"
        with pytest.raises(WriteRefusedError) as exc:
            await pedal.reload_preset(sleep=_no_sleep)
    assert exc.value.reason == "tuner_mode"
    assert writes(fake) == []


@pytest.mark.parametrize(
    ("glob", "buffer", "reason"),
    [
        (bytes([0, 0, 0xFF, NORMAL]), bytes(21), "bypassed"),
        (bytes([0, 0, 1, 9]), P, "unrecognised_state"),
    ],
)
async def test_no_loaded_slot_is_refused(glob: bytes, buffer: bytes, reason: str) -> None:
    fake = make_fake(NORMAL, buffer=buffer, glob=glob)
    async with TankG.over(fake) as pedal:
        with pytest.raises(WriteRefusedError) as exc:
            await pedal.plan_reload(sleep=_no_sleep)
        assert exc.value.reason == reason
        with pytest.raises(WriteRefusedError):
            await pedal.reload_preset(sleep=_no_sleep)
    assert writes(fake) == []
    if reason == "bypassed":
        assert "bypass off <position>" in str(exc.value)
