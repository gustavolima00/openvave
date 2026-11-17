"""Gate helpers for the spec 003 hardware write sessions (M2/M3). **Writes to a real pedal.**

Collected only with ``--hardware`` **and** ``OPENVAVE_HW_WRITES=1`` (research R11), so a broad
``pytest --hardware`` never writes. Each run performs one gate step:

1. take a backup (the same-session pre-gate backup, FR-019);
2. plan the write and print the exact frame and the expected result;
3. wait for the operator to type ``send`` on stdin (run pytest with ``-s``);
4. send the one write and report the ACK, re-read and applied flag.

The step comes from ``OPENVAVE_HW_STEP``: ``set <field> <value>`` or ``select <position>``. The
researcher posts the frame and the owner approves that exact write in chat **before** the run.
Leave edit mode on the pedal without saving afterwards, and take the post-gate backup with
``openvave preset backup``.
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import Callable

import pytest

from openvave.cli import parse_field_value
from openvave.models import WritePlan
from openvave.protocol.storage import parse_position
from openvave.session import TankG

pytestmark = [
    pytest.mark.hardware,
    pytest.mark.skipif(
        os.environ.get("OPENVAVE_HW_WRITES") != "1",
        reason="hardware writes need OPENVAVE_HW_WRITES=1 (and --hardware)",
    ),
]

CONFIRM_WORD = "send"


def describe(plan: WritePlan) -> str:
    return (
        f"{plan.action}: frame {plan.frame.hex(' ')}\n"
        f"  edit buffer now {plan.before.data.hex(' ')}\n"
        f"  global now      {plan.global_before.data.hex(' ')}\n"
        f"  refusal {plan.refusal}  confidence {plan.confidence}"
    )


def confirmed(prompt: str, read_line: Callable[[], str] = sys.stdin.readline) -> bool:
    """True only if the operator types exactly ``send``; anything else (or EOF) aborts."""
    print(prompt, flush=True)
    return read_line().strip() == CONFIRM_WORD


async def gate_step(step: str, read_line: Callable[[], str] = sys.stdin.readline) -> None:
    verb, _, rest = step.partition(" ")
    async with asyncio.timeout(120):
        async with TankG.connect() as pedal:
            assert pedal.identity.firmware == 96
            backup = await pedal.backup()
            print(f"pre-gate backup {backup.created_at.isoformat()}: {len(backup.presets)} presets")
            if verb == "set":
                field, _, value_text = rest.partition(" ")
                value = parse_field_value(field, value_text)
                plan = await pedal.plan_set(field, value, experimental=True)
            elif verb == "select":
                index = parse_position(rest)
                plan = await pedal.plan_select(index, experimental=True, discard_edits=True)
            else:
                pytest.fail(f"unknown OPENVAVE_HW_STEP {step!r}")
            print(describe(plan))
            if plan.refusal is not None or plan.no_change:
                pytest.skip(f"nothing to send: refusal={plan.refusal} no_change={plan.no_change}")
            if not confirmed(f"type '{CONFIRM_WORD}' to send this one write:", read_line):
                pytest.skip("not confirmed; nothing sent")
            if verb == "set":
                result = await pedal.set_field(field, value, experimental=True)
            else:
                result = await pedal.select_preset(index, experimental=True, discard_edits=True)
    print(f"reply {result.reply.hex(' ')}  applied {result.applied}")
    for change in result.changes:
        print(f"  {change.region.name.lower()}[{change.offset}] {change.old} -> {change.new}")


async def test_gate_step() -> None:
    step = os.environ.get("OPENVAVE_HW_STEP")
    if not step:
        pytest.skip("set OPENVAVE_HW_STEP to 'set <field> <value>' or 'select <position>'")
    await gate_step(step)
