"""Replay every gate-session write excerpt through the library (spec 003 M2 T047; 004 M3 T068).

For each step the library call recorded in the excerpt's ``meta.replay`` runs against
``FakeTransport.from_capture``: it must send exactly the recorded request sequence, its write
frames must equal an independent encoding of the intended writes, and the result must be
``applied`` (one write, ACK) or ``verified`` (a spec 004 save / restore sequence). Steps not yet
recorded are strict ``xfail`` (see ``gate_fixtures``).

Spec 004 expectations, from the excerpt's own reads: bypass writes ``01`` to ``0xE1000000 + i``
for the preset ``i`` the first global read shows; save writes the first edit-buffer read to the
slot, then the commit (``0xF0000000`` × 0) and the select of that slot; restore and the no-op image
write send the file's bytes (the excerpt's slot / image write, whose file the excerpt cannot hold
otherwise), the commit and the select. Persistent steps are marked ``persistent_writes``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from openvave import Backup, SequenceResult, TankG, WriteResult
from openvave.transport.fake import FakeTransport
from tests.integration.gate_fixtures import (
    RECORDED,
    SPEC003_STEPS,
    SPEC004_STEPS,
    SPEC007_STEPS,
    GateStep,
    excerpt_path,
)
from tests.support import restore_fixture as rf
from tests.support.image_noop import noop_image_plan
from tests.support.write_fixture import ACK, EDIT_BUFFER, write_frame, writes

KNOB_ADDRESS = EDIT_BUFFER + 4
SELECT_BASE = 0xE0000000
BYPASS_BASE = 0xE1000000
STATUS = 0xD0000000
COMMIT = write_frame(0xF0000000, b"")


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
    marks: list[Any] = []
    if step.step not in RECORDED:
        marks.append(pytest.mark.xfail(strict=True, reason="gate excerpt not recorded yet"))
    if step.persistent:
        marks.append(pytest.mark.persistent_writes)
    return pytest.param(step, id=step.step, marks=marks)


@pytest.mark.parametrize("step", [_param(s) for s in SPEC003_STEPS])
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


# -- spec 004 (M3, T068) ------------------------------------------------------------------------


def _loaded(records: list[dict[str, Any]]) -> int:
    """The preset index the first global read shows (``browse bank, bank, slot, mode``)."""
    for r in records:
        if r["event"] == "rx" and r["label"].startswith("global "):
            data = bytes.fromhex(r["hex"])[14:-1]
            return data[1] * 4 + data[2]
    raise AssertionError("no global read in the excerpt")


def _payload(frame: bytes) -> bytes:
    return frame[14:-1]


def _select(index: int) -> bytes:
    return write_frame(SELECT_BASE + index, b"\x01")


def file_backup(step: GateStep, call: dict[str, Any], sent: list[bytes]) -> Backup | None:
    """The backup file a restore step used, rebuilt from its slot or image write."""
    if step.kind == "restore_all":
        return rf.backup(_payload(sent[0]))
    if step.kind == "restore_slot":
        return rf.backup(rf.image_with(**{f"s{call['slot']}": _payload(sent[0])}))
    return None


def expected_writes_004(
    step: GateStep, call: dict[str, Any], records: list[dict[str, Any]], sent: list[bytes]
) -> list[bytes]:
    """The write frames of ``step``, encoded without ``openvave``."""
    loaded = _loaded(records)
    if step.kind == "bypass":
        return [write_frame(BYPASS_BASE + loaded, b"\x01")]
    if step.kind == "bypass_off":
        return [_select(call["index"])]
    if step.kind == "loopback":
        return [write_frame(STATUS, b"\x01" if call["on"] else b"\x00")]
    if step.kind in ("block_switch", "led_colour"):
        return [expected_write(step, call, _first_preset(records))]
    if step.kind == "save":
        to = loaded if call["to"] is None else call["to"]
        return [write_frame(2 + 21 * to, _first_preset(records)), COMMIT, _select(to)]
    if step.kind == "restore_slot":
        backup = file_backup(step, call, sent)
        assert backup is not None
        data = backup.presets[call["slot"]].data
        return [write_frame(2 + 21 * call["slot"], data), COMMIT, _select(call["slot"])]
    assert step.kind in ("restore_all", "image_noop")
    image = _payload(sent[0])
    assert len(image) == 758 and image[:2] == b"\xa5\x5a"
    return [write_frame(0, image), COMMIT, _select(loaded)]


async def _run_004(
    pedal: TankG, call: dict[str, Any], backup: Backup | None
) -> WriteResult | SequenceResult:
    """Run the library call recorded in ``meta.replay`` (the CLI's own call for that command)."""
    name = call["call"]
    if name == "set_field":
        return await pedal.set_field(call["field"], call["value"], experimental=True)
    if name == "bypass_on":
        return await pedal.bypass_on(
            discard_edits=call["discard_edits"], experimental=True, sleep=_no_sleep
        )
    if name == "bypass_off":
        return await pedal.bypass_off(call["index"], experimental=True, sleep=_no_sleep)
    if name == "set_loopback":
        return await pedal.set_loopback(call["on"], experimental=True, sleep=_no_sleep)
    if name == "save_preset":
        return await pedal.save_preset(
            call["to"], unsafe=True, experimental=True, on_backup=_ignore, sleep=_no_sleep
        )
    if name == "restore":
        assert backup is not None
        return await pedal.restore(
            backup,
            slot=call.get("slot"),
            all=call.get("all", False),
            unsafe=True,
            experimental=True,
            discard_edits=call["discard_edits"],
            on_backup=_ignore,
            sleep=_no_sleep,
        )
    assert name == "image_noop", name
    current = await pedal.backup()
    plan = await noop_image_plan(pedal, current)
    return await pedal._run_sequence(plan, True, _ignore, None, _no_sleep)


def _ignore(_: object) -> None:
    return None


async def replay_004(step: GateStep, path: Path) -> WriteResult | SequenceResult:
    """Replay one spec 004 excerpt and check frames and outcome (also used on rehearsal output)."""
    records = _records(path)
    meta, call = records[0], records[0]["replay"]
    assert meta["event"] == "meta" and meta["step"] == step.step and meta["firmware"] == 96
    recorded_tx = [bytes.fromhex(r["hex"]) for r in records if r["event"] == "tx"]
    recorded_writes = [f for f in recorded_tx if f[2] == 0x22]
    expected = expected_writes_004(step, call, records, recorded_writes)
    assert recorded_writes == expected

    fake = FakeTransport.from_capture(path)
    async with TankG.over(fake) as pedal:
        result = await _run_004(pedal, call, file_backup(step, call, recorded_writes))

    assert fake.sent == recorded_tx
    assert writes(fake) == recorded_writes
    if isinstance(result, SequenceResult):
        assert result.verified is True
        assert [o.status for o in result.steps if o.status != "waited"] == ["acked"] * 3
    else:
        assert result.reply == ACK
        assert result.applied is True
    return result


@pytest.mark.parametrize("step", [_param(s) for s in SPEC004_STEPS + SPEC007_STEPS])
async def test_gate_004_step_replays(step: GateStep) -> None:
    await replay_004(step, excerpt_path(step))
