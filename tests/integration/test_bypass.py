"""``TankG.bypass_on`` / ``bypass_off`` (spec 004 US2, FR-007…FR-010, T026).

The replay serves the check 2 capture's replies in order (pedal on 1B, normal mode): the bypass
write, the bypass state on the re-reads, then select 1B. The other tests use the fake pedal of
``write_fixture`` (bypass write → slot ``ff`` and a zero buffer; select leaves bypass).
"""

from __future__ import annotations

import pytest

from openvave import TankG, WriteNakError, WriteNotAppliedError, WriteRefusedError, WriteResult
from openvave.models import Region
from openvave.protocol import build_read, build_storage_read
from openvave.protocol.storage import StorageRead
from openvave.transport.fake import FakeTransport
from tests.integration.gate_fixtures import FW96
from tests.support import storage_fixture as sf
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

P = sf.PUBLIC_PRESET
EDITED = P[:6] + bytes([90]) + P[7:]
CHECK2 = FW96 / "20261117-check2-bypass.jsonl"
BYPASS_1B = bytes.fromhex("00 59 22 09 00 00 04 01 00 00 e1 01 00 00 01 17")
SELECT_1B = bytes.fromhex("00 59 22 09 00 00 04 01 00 00 e0 01 00 00 01 18")
BYPASSED = bytes([0, 0, 0xFF, NORMAL])


async def _no_sleep(_: float) -> None:
    return None


def _capture_writes() -> list[bytes]:
    import json

    records = [json.loads(line) for line in CHECK2.read_text(encoding="utf-8").splitlines()]
    return [
        bytes.fromhex(r["hex"])
        for r in records
        if r["event"] == "tx" and bytes.fromhex(r["hex"])[2] == 0x22
    ]


async def test_check2_replay_bypass_on_then_off() -> None:
    fake = FakeTransport.from_capture(CHECK2)
    async with TankG.over(fake) as pedal:
        on = await pedal.bypass_on(experimental=True, sleep=_no_sleep)
        off = await pedal.bypass_off(1, experimental=True, sleep=_no_sleep)
    assert writes(fake) == _capture_writes() == [BYPASS_1B, SELECT_1B]
    assert on.applied is True
    assert on.return_index == 1
    assert on.plan.target.kind == "bypass"
    assert on.plan.frame == BYPASS_1B
    assert on.after.data == bytes(21)
    assert on.global_after.data == BYPASSED
    assert off.applied is True
    assert off.plan.target.kind == "preset_select"
    assert off.plan.frame == SELECT_1B
    assert off.after.data == P
    assert off.global_after.data == bytes([0, 0, 1, NORMAL])


async def test_bypass_on_plan_reads_and_result() -> None:
    fake = make_fake(NORMAL)
    async with TankG.over(fake) as pedal:
        plan = await pedal.plan_bypass_on()
        result = await pedal.bypass_on(experimental=True, sleep=_no_sleep)
    assert plan.refusal == "experimental_required"
    assert plan.confidence == "hypothesis"
    assert plan.action == "bypass on 1B"
    assert plan.frame == BYPASS_1B
    assert list(plan.reads) == [
        build_read(Region.GLOBAL),
        build_read(Region.CURRENT_PRESET),
        build_storage_read(StorageRead.preset(1)),
    ]
    assert isinstance(result, WriteResult)
    assert result.reply == ACK
    assert result.applied is True
    assert result.return_index == 1
    assert writes(fake) == [BYPASS_1B]
    assert [(c.region, c.offset, c.new) for c in result.changes][:1] == [(Region.GLOBAL, 2, 0xFF)]


async def test_bypass_on_needs_experimental() -> None:
    fake = make_fake(NORMAL)
    async with TankG.over(fake) as pedal:
        with pytest.raises(WriteRefusedError) as exc:
            await pedal.bypass_on(sleep=_no_sleep)
    assert exc.value.reason == "experimental_required"
    assert "hypothesis" in str(exc.value)
    assert writes(fake) == []


async def test_bypass_on_with_unsaved_edits_needs_discard_edits() -> None:
    fake = make_fake(NORMAL, buffer=EDITED)
    async with TankG.over(fake) as pedal:
        plan = await pedal.plan_bypass_on(experimental=True)
        assert plan.refusal == "edits_would_be_discarded"
        with pytest.raises(WriteRefusedError) as exc:
            await pedal.bypass_on(experimental=True, sleep=_no_sleep)
        assert exc.value.reason == "edits_would_be_discarded"
        assert writes(fake) == []
        result = await pedal.bypass_on(discard_edits=True, experimental=True, sleep=_no_sleep)
    assert result.applied is True
    assert writes(fake) == [BYPASS_1B]


@pytest.mark.parametrize(
    ("mode", "glob", "reason"),
    [
        (EDIT, None, "edit_mode"),
        (TUNER, None, "tuner_mode"),
        (NORMAL, bytes([0, 0, 1, 9]), "unrecognised_state"),
    ],
)
async def test_bypass_on_refused_per_state(mode: int, glob: bytes | None, reason: str) -> None:
    fake = make_fake(mode, glob=glob)
    async with TankG.over(fake) as pedal:
        with pytest.raises(WriteRefusedError) as exc:
            await pedal.bypass_on(discard_edits=True, experimental=True, sleep=_no_sleep)
    assert exc.value.reason == reason
    assert writes(fake) == []


async def test_already_bypassed_sends_nothing() -> None:
    fake = make_fake(NORMAL, buffer=bytes(21), glob=BYPASSED)
    async with TankG.over(fake) as pedal:
        plan = await pedal.plan_bypass_on(sleep=_no_sleep)
        result = await pedal.bypass_on(experimental=True, sleep=_no_sleep)
    assert plan.no_change is True
    assert plan.refusal is None
    assert result.plan.no_change is True
    assert result.reply == b""
    assert result.applied is True
    assert result.return_index is None
    assert writes(fake) == []


async def test_bypass_on_nak_is_not_retried() -> None:
    fake = make_fake(NORMAL, script={"bypass": (BYPASS_1B, nak(1))})
    async with TankG.over(fake) as pedal:
        with pytest.raises(WriteNakError):
            await pedal.bypass_on(experimental=True, sleep=_no_sleep)
    assert writes(fake) == [BYPASS_1B]


async def test_bypass_on_acked_but_not_bypassed() -> None:
    fake = make_fake(NORMAL, script={"bypass": (BYPASS_1B, ACK)})  # ACK, state unchanged
    async with TankG.over(fake) as pedal:
        with pytest.raises(WriteNotAppliedError) as exc:
            await pedal.bypass_on(experimental=True, sleep=_no_sleep)
    assert exc.value.exit_code == 8
    assert exc.value.result.applied is False
    assert exc.value.result.return_index == 1
    assert writes(fake) == [BYPASS_1B]


async def test_bypass_off_selects_the_position() -> None:
    fake = make_fake(NORMAL, buffer=bytes(21), glob=BYPASSED)
    async with TankG.over(fake) as pedal:
        plan = await pedal.plan_bypass_off(1, sleep=_no_sleep)
        result = await pedal.bypass_off(1, experimental=True, sleep=_no_sleep)
    assert plan.refusal is None  # preset select is confirmed
    assert plan.action == "bypass off 1B"
    assert result.applied is True
    assert writes(fake) == [SELECT_1B]
    assert result.after.data == P


async def test_bypass_off_to_another_position() -> None:
    fake = make_fake(NORMAL, buffer=bytes(21), glob=BYPASSED)
    async with TankG.over(fake) as pedal:
        result = await pedal.bypass_off(6, sleep=_no_sleep)
    assert result.applied is True
    assert writes(fake) == [write_frame(0xE0000006, b"\x01")]
    assert result.global_after.data == bytes([1, 1, 2, NORMAL])


@pytest.mark.parametrize(
    ("mode", "glob", "buffer", "reason"),
    [
        (NORMAL, None, P, "not_bypassed"),
        (EDIT, None, P, "edit_mode"),
        (TUNER, None, P, "tuner_mode"),
        (NORMAL, bytes([0, 0, 1, 9]), P, "unrecognised_state"),
    ],
)
async def test_bypass_off_only_in_bypass(
    mode: int, glob: bytes | None, buffer: bytes, reason: str
) -> None:
    fake = make_fake(mode, glob=glob, buffer=buffer)
    async with TankG.over(fake) as pedal:
        with pytest.raises(WriteRefusedError) as exc:
            await pedal.bypass_off(1, experimental=True, sleep=_no_sleep)
    assert exc.value.reason == reason
    assert writes(fake) == []
    if reason == "not_bypassed":
        assert "preset select" in str(exc.value)


async def test_bypass_off_index_out_of_range() -> None:
    fake = make_fake(NORMAL, buffer=bytes(21), glob=BYPASSED)
    async with TankG.over(fake) as pedal:
        with pytest.raises(ValueError):
            await pedal.bypass_off(36, sleep=_no_sleep)
    assert writes(fake) == []


async def test_bypass_off_nak() -> None:
    fake = make_fake(
        NORMAL, buffer=bytes(21), glob=BYPASSED, script={"select": (SELECT_1B, nak(1))}
    )
    async with TankG.over(fake) as pedal:
        with pytest.raises(WriteNakError):
            await pedal.bypass_off(1, sleep=_no_sleep)
    assert writes(fake) == [SELECT_1B]


async def test_reload_refusal_in_bypass_points_to_bypass_off() -> None:
    fake = make_fake(NORMAL, buffer=bytes(21), glob=BYPASSED)
    async with TankG.over(fake) as pedal:
        with pytest.raises(WriteRefusedError) as exc:
            await pedal.reload_preset(sleep=_no_sleep)
    assert exc.value.reason == "bypassed"
    assert "bypass off <position>" in str(exc.value)
