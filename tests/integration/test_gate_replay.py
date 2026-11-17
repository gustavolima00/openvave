"""Replay every gate-session write excerpt through the library (spec 003 M2, T047, US4).

For each step the library call recorded in the excerpt's ``meta.replay`` runs against
``FakeTransport.from_capture``: it must send exactly the recorded request sequence, its one
write frame must equal an independent encoding of the intended write, the reply must be the ACK
and the result ``applied``. Steps not yet recorded are strict ``xfail`` (see ``gate_fixtures``).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from openvave import TankG, WriteResult
from openvave.transport.fake import FakeTransport
from tests.integration.gate_fixtures import RECORDED, SESSION_A, GateStep, excerpt_path
from tests.support.write_fixture import ACK, EDIT_BUFFER, write_frame, writes

KNOB_ADDRESS = EDIT_BUFFER + 4
SELECT_BASE = 0xE0000000


async def _no_sleep(_: float) -> None:
    return None


def _records(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _first_preset(records: list[dict[str, Any]]) -> bytes:
    """Edit-buffer bytes of the first edit-buffer reply (the plan's read)."""
    for r in records:
        if r["event"] == "rx" and r["label"].startswith("preset "):
            return bytes.fromhex(r["hex"])[14:-1]
    raise AssertionError("no edit-buffer read in the excerpt")


def _rgb(value: Any) -> bytes:
    text = str(value).lstrip("#")
    if "," in text:
        return bytes(int(p) for p in text.split(","))
    return bytes.fromhex(text)


def expected_write(step: GateStep, call: dict[str, Any], before: bytes) -> bytes:
    """The write frame for ``call``, encoded without ``openvave``."""
    if step.kind == "preset_select":
        return write_frame(SELECT_BASE + call["index"], b"\x01")
    assert step.offset is not None
    if step.kind == "knob_block":
        block = bytearray(before[4:18])
        block[step.offset - 4] = call["value"]
        return write_frame(KNOB_ADDRESS, bytes(block))
    if step.kind == "block_switch":
        return write_frame(EDIT_BUFFER + step.offset, bytes([int(bool(call["value"]))]))
    return write_frame(EDIT_BUFFER + step.offset, _rgb(call["value"]))


def _param(step: GateStep) -> Any:
    marks = []
    if step.step not in RECORDED:
        marks.append(pytest.mark.xfail(strict=True, reason="gate excerpt not recorded yet"))
    return pytest.param(step, id=step.step, marks=marks)


@pytest.mark.parametrize("step", [_param(s) for s in SESSION_A])
async def test_gate_step_replays(step: GateStep) -> None:
    path = excerpt_path(step)
    records = _records(path)
    meta, call = records[0], records[0]["replay"]
    assert meta["event"] == "meta" and meta["step"] == step.step and meta["firmware"] == 96
    recorded_tx = [bytes.fromhex(r["hex"]) for r in records if r["event"] == "tx"]
    recorded_writes = [f for f in recorded_tx if f[2] == 0x22]
    assert len(recorded_writes) == 1, "a gate step sends exactly one write"

    fake = FakeTransport.from_capture(path)
    async with TankG.over(fake) as pedal:
        result: WriteResult
        if call["call"] == "set_field":
            result = await pedal.set_field(call["field"], call["value"], experimental=True)
        else:
            result = await pedal.select_preset(
                call["index"],
                discard_edits=call["discard_edits"],
                experimental=True,
                sleep=_no_sleep,
            )

    assert fake.sent == recorded_tx
    assert writes(fake) == recorded_writes
    assert recorded_writes[0] == expected_write(step, call, _first_preset(records))
    assert result.reply == ACK
    assert result.applied is True
