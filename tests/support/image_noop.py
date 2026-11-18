"""The no-op image write of spec 004 M3 (T077): the image just read, written back unchanged.

``plan_restore`` with a backup equal to the pedal is a no-change plan (nothing would be sent), so
the gate forces its sequence: image write of the image just read → 300 ms → commit → 100 ms →
select of the loaded preset. Shared by the hardware helper (``tests/hardware/test_hw_persistent``)
and the replay of its excerpt (``tests/integration/test_gate_replay``), so both run the same plan.
"""

from __future__ import annotations

import dataclasses

from openvave import Backup, TankG
from openvave.models import SequencePlan
from openvave.protocol.writes import WriteTarget
from openvave.session import _sequence_steps, _write_step


async def noop_image_plan(pedal: TankG, current: Backup) -> SequencePlan:
    """The forced restore-all plan that writes ``current.image`` back (reads only until run)."""
    plan = await pedal.plan_restore(current, all=True, unsafe=True, experimental=True)
    assert plan.no_change and plan.refusal is None, (plan.no_change, plan.refusal)
    assert plan.return_index is not None
    steps = _sequence_steps(
        _write_step(WriteTarget.stored_image(), current.image), plan.return_index
    )
    return dataclasses.replace(plan, no_change=False, steps=steps)
