"""``TankG.set_loopback`` (spec 004 US5, FR-026, T027).

Read the flag (``0xD0000000`` × 1), one 1-byte write, ACK, re-read; never followed by a commit.
The fake pedal stores the written byte in its status block (``write_fixture``, ``status=``).
"""

from __future__ import annotations

import pytest

from openvave import TankG, WriteNakError, WriteNotAppliedError, WriteRefusedError
from openvave.models import Region
from openvave.protocol import build_read
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

LOOPBACK_OFF = bytes.fromhex("00 59 22 09 00 00 04 00 00 00 d0 01 00 00 00 2a")
LOOPBACK_ON = bytes.fromhex("00 59 22 09 00 00 04 00 00 00 d0 01 00 00 01 29")
COMMIT = write_frame(0xF0000000, b"")


async def _no_sleep(_: float) -> None:
    return None


async def test_loopback_off_reads_writes_and_rereads() -> None:
    fake = make_fake(NORMAL, status=b"\x01")
    async with TankG.over(fake) as pedal:
        result = await pedal.set_loopback(False, experimental=True, sleep=_no_sleep)
    plan = result.plan
    assert plan.action == "loopback off"
    assert plan.target.kind == "loopback"
    assert plan.data == b"\x00"
    assert plan.frame == LOOPBACK_OFF
    assert plan.before.region is Region.STATUS
    assert plan.before.data == b"\x01"
    assert plan.reads[-1] == build_read(Region.STATUS)
    assert result.reply == ACK
    assert result.after.region is Region.STATUS
    assert result.after.data == b"\x00"
    assert result.applied is True
    assert [(c.region, c.old, c.new) for c in result.changes] == [(Region.STATUS, 1, 0)]
    assert writes(fake) == [LOOPBACK_OFF]
    assert fake.sent[-1] == build_read(Region.STATUS)  # the re-read; no commit after the write
    assert COMMIT not in fake.sent


async def test_loopback_on() -> None:
    fake = make_fake(NORMAL, status=b"\x00")
    async with TankG.over(fake) as pedal:
        result = await pedal.set_loopback(True, experimental=True, sleep=_no_sleep)
    assert result.applied is True
    assert writes(fake) == [LOOPBACK_ON]


@pytest.mark.parametrize(("on", "status"), [(False, b"\x00"), (True, b"\x01")])
async def test_no_change_when_equal(on: bool, status: bytes) -> None:
    fake = make_fake(NORMAL, status=status)
    async with TankG.over(fake) as pedal:
        plan = await pedal.plan_loopback(on, sleep=_no_sleep)
        result = await pedal.set_loopback(on, experimental=True, sleep=_no_sleep)
    assert plan.no_change is True
    assert result.plan.no_change is True
    assert result.reply == b""
    assert writes(fake) == []


async def test_refused_without_experimental() -> None:
    fake = make_fake(NORMAL, status=b"\x01")
    async with TankG.over(fake) as pedal:
        plan = await pedal.plan_loopback(False, sleep=_no_sleep)
        with pytest.raises(WriteRefusedError) as exc:
            await pedal.set_loopback(False, sleep=_no_sleep)
    assert plan.refusal == "experimental_required"
    assert plan.confidence == "observed"
    assert exc.value.reason == "experimental_required"
    assert "--experimental" in str(exc.value)
    assert "observed" in str(exc.value)
    assert writes(fake) == []


@pytest.mark.parametrize(
    ("mode", "glob", "buffer"),
    [
        (EDIT, None, None),
        (TUNER, None, None),
        (NORMAL, bytes([0, 0, 0xFF, NORMAL]), bytes(21)),  # bypass
    ],
)
async def test_allowed_in_every_recognised_state(
    mode: int, glob: bytes | None, buffer: bytes | None
) -> None:
    extra = {} if buffer is None else {"buffer": buffer}
    fake = make_fake(mode, glob=glob, status=b"\x01", **extra)  # type: ignore[arg-type]
    async with TankG.over(fake) as pedal:
        result = await pedal.set_loopback(False, experimental=True, sleep=_no_sleep)
    assert result.applied is True
    assert writes(fake) == [LOOPBACK_OFF]


async def test_refused_in_unrecognised_state() -> None:
    fake = make_fake(NORMAL, glob=bytes([0, 0, 1, 9]), status=b"\x01")
    async with TankG.over(fake) as pedal:
        with pytest.raises(WriteRefusedError) as exc:
            await pedal.set_loopback(False, experimental=True, sleep=_no_sleep)
    assert exc.value.reason == "unrecognised_state"
    assert writes(fake) == []


async def test_nak_is_not_retried() -> None:
    fake = make_fake(NORMAL, status=b"\x01", script={"loopback": (LOOPBACK_OFF, nak(1))})
    async with TankG.over(fake) as pedal:
        with pytest.raises(WriteNakError):
            await pedal.set_loopback(False, experimental=True, sleep=_no_sleep)
    assert writes(fake) == [LOOPBACK_OFF]


async def test_acked_but_not_applied() -> None:
    fake = make_fake(NORMAL, status=b"\x01", script={"loopback": (LOOPBACK_OFF, ACK)})
    async with TankG.over(fake) as pedal:
        with pytest.raises(WriteNotAppliedError) as exc:
            await pedal.set_loopback(False, experimental=True, sleep=_no_sleep)
    assert exc.value.result.applied is False
    assert exc.value.result.after.data == b"\x01"
    assert writes(fake) == [LOOPBACK_OFF]
