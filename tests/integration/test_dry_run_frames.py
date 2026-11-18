"""For every write action, the frames a plan (dry run) shows are the frames the real run sends
(spec 004 SC-006, FR-028, T051). Each case plans on one fake pedal and runs on an identical one.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import pytest

from openvave import TankG
from openvave.models import SequencePlan, WritePlan
from tests.support import restore_fixture as rf
from tests.support import storage_fixture as sf
from tests.support.write_fixture import NORMAL, make_fake, writes

pytestmark = pytest.mark.persistent_writes

P = sf.PUBLIC_PRESET
GAIN_90 = P[:6] + bytes([90]) + P[7:]
BACKUP = rf.backup()
BYPASSED = bytes([0, 0, 0xFF, NORMAL])


async def no_sleep(_: float) -> None:
    return None


def keep(_: object) -> None:
    return None


Call = Callable[[TankG], Awaitable[Any]]

CASES: dict[str, tuple[dict[str, Any], Call, Call]] = {
    "set": (
        {},
        lambda p: p.plan_set("gain", 90),
        lambda p: p.set_field("gain", 90, sleep=no_sleep),
    ),
    "reload": (
        {"buffer": GAIN_90},
        lambda p: p.plan_reload(),
        lambda p: p.reload_preset(sleep=no_sleep),
    ),
    "bypass_on": (
        {},
        lambda p: p.plan_bypass_on(),
        lambda p: p.bypass_on(experimental=True, sleep=no_sleep),
    ),
    "bypass_off": (
        {"glob": BYPASSED, "buffer": bytes(21)},
        lambda p: p.plan_bypass_off(1, sleep=no_sleep),
        lambda p: p.bypass_off(1, sleep=no_sleep),
    ),
    "loopback": (
        {"status": b"\x01"},
        lambda p: p.plan_loopback(False),
        lambda p: p.set_loopback(False, experimental=True),
    ),
    "save": (
        {"buffer": GAIN_90},
        lambda p: p.plan_save(to=2),
        lambda p: p.save_preset(
            to=2, unsafe=True, experimental=True, on_backup=keep, sleep=no_sleep
        ),
    ),
    "restore_slot": (
        {"image": rf.image_with(s2=GAIN_90)},
        lambda p: p.plan_restore(BACKUP, slot=2),
        lambda p: p.restore(
            BACKUP, slot=2, unsafe=True, experimental=True, on_backup=keep, sleep=no_sleep
        ),
    ),
    "restore_all": (
        {"image": rf.image_with(s2=GAIN_90, s30=GAIN_90)},
        lambda p: p.plan_restore(BACKUP, all=True),
        lambda p: p.restore(
            BACKUP, all=True, unsafe=True, experimental=True, on_backup=keep, sleep=no_sleep
        ),
    ),
}


def planned_frames(plan: WritePlan | SequencePlan) -> list[bytes]:
    if isinstance(plan, SequencePlan):
        return [s.frame for s in plan.steps if s.kind == "write"]
    return [plan.frame]


@pytest.mark.parametrize("name", sorted(CASES))
async def test_dry_run_frames_equal_sent_frames(name: str) -> None:
    setup, plan_call, run_call = CASES[name]
    async with TankG.over(make_fake(NORMAL, **setup)) as pedal:
        plan = await plan_call(pedal)
    fake = make_fake(NORMAL, **setup)
    async with TankG.over(fake) as pedal:
        await run_call(pedal)
    assert planned_frames(plan)
    assert planned_frames(plan) == writes(fake)
