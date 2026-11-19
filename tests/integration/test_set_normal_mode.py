"""``set`` outside edit mode (spec 004 US1, FR-001…FR-004, research R1–R3).

The replay builds a fake pedal from the first replies of the check 1 captures (pedal on 1B,
normal mode) and checks that ``set_field("gain", 90)`` sends the capture's write frame, only
requests the capture also sent, and ends as the capture did (gain 90, mode still normal).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from openvave import TankG, WriteRefusedError
from openvave.models import Region
from openvave.transport.fake import FakeTransport
from tests.integration.gate_fixtures import FW96
from tests.support import storage_fixture as sf
from tests.support.write_fixture import (
    EDIT,
    EDIT_BUFFER,
    GLOBAL,
    NORMAL,
    TUNER,
    demote,
    make_fake,
    write_frame,
    writes,
)

P = sf.PUBLIC_PRESET
EXCERPTS = ("20261117-gate-normal_knob_gain.jsonl", "20261117-gate-normal_knob_gain_b.jsonl")
QUERY_LABEL = "query name/version"


def _records(name: str) -> list[dict[str, object]]:
    return [json.loads(line) for line in (FW96 / name).read_text(encoding="utf-8").splitlines()]


def _replay_fake(name: str) -> tuple[FakeTransport, list[bytes], bytes, bytes]:
    """Fake pedal in the capture's starting state; also the capture's tx frames, write, after."""
    records = _records(name)
    tx = [bytes.fromhex(str(r["hex"])) for r in records if r["event"] == "tx"]
    rx = {  # first reply per label: reversed, so earlier records overwrite later ones
        str(r["label"]): bytes.fromhex(str(r["hex"]))
        for r in reversed(records[1:])
        if r["event"] == "rx"
    }
    glob = rx["global t4 0x20000000 x4"][14:-1]
    buffer = rx["preset t4 0x10000000 x21"][14:-1]
    knob_write = next(f for f in tx if f[2] == 0x22 and f[10] == 0x10)
    buffers = [
        bytes.fromhex(str(r["hex"]))[14:-1]
        for r in records
        if r["event"] == "rx" and str(r["label"]).startswith("preset ")
    ]
    after = next(b for b in buffers if b != buffer)
    query = (tx[0], rx[QUERY_LABEL])
    memory = {0: sf.synthetic_image(), EDIT_BUFFER: buffer, GLOBAL: glob}
    fake = FakeTransport({QUERY_LABEL: query}, memory=memory, apply_writes=True)
    return fake, tx, knob_write, after


@pytest.mark.parametrize("name", EXCERPTS)
async def test_replay_check1_gain_in_normal_mode(name: str) -> None:
    fake, captured_tx, knob_write, after = _replay_fake(name)
    async with TankG.over(fake) as pedal:
        result = await pedal.set_field("gain", 90)  # confirmed: no --experimental needed
    assert writes(fake) == [knob_write]
    assert set(fake.sent) <= set(captured_tx)
    assert result.applied is True
    assert result.after.data == after
    assert result.global_after.data[3] == NORMAL
    assert result.plan.global_before.data[3] == NORMAL
    assert result.plan.refusal is None


async def test_set_in_edit_mode_still_works() -> None:
    fake = make_fake(EDIT)
    async with TankG.over(fake) as pedal:
        result = await pedal.set_field("gain", 90)
    assert result.applied is True
    assert result.global_after.data[3] == EDIT


@pytest.mark.parametrize(
    ("glob", "buffer", "reason"),
    [
        (bytes([0, 0, 1, TUNER]), P, "tuner_mode"),
        (bytes([0, 0, 0xFF, NORMAL]), bytes(21), "bypassed"),
        (bytes([0, 0, 1, 7]), P, "unrecognised_state"),
        (bytes([0, 0, 1, NORMAL]), bytes(21), "unrecognised_state"),
    ],
)
async def test_refused_states_send_reads_only(glob: bytes, buffer: bytes, reason: str) -> None:
    fake = make_fake(NORMAL, buffer=buffer, glob=glob)
    async with TankG.over(fake) as pedal:
        plan = await pedal.plan_set("gain", 90, experimental=True, sleep=_no_sleep)
        assert plan.refusal == reason
        with pytest.raises(WriteRefusedError) as exc:
            await pedal.set_field("gain", 90, experimental=True, sleep=_no_sleep)
    assert exc.value.reason == reason
    assert writes(fake) == []
    assert all(frame[2] in (0x11, 0x23) for frame in fake.sent)


async def _no_sleep(_: float) -> None:
    return None


@pytest.mark.parametrize(("field", "value"), [("mod_on", True), ("led_colour", "#ff0000")])
async def test_observed_writes_need_experimental_in_normal_mode(
    field: str, value: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    demote(monkeypatch, "block_switch", "led_colour")  # every fw 96 row is confirmed since spec 007
    fake = make_fake(NORMAL)
    async with TankG.over(fake) as pedal:
        with pytest.raises(WriteRefusedError) as exc:
            await pedal.set_field(field, value)  # type: ignore[arg-type]
        assert exc.value.reason == "experimental_required"
        result = await pedal.set_field(field, value, experimental=True)  # type: ignore[arg-type]
    assert result.applied is True


async def test_type_value_writes_its_raw_value() -> None:
    fake = make_fake(NORMAL)
    async with TankG.over(fake) as pedal:
        result = await pedal.set_field("reverb_decay", ("spring", 10))
    data = bytearray(P[4:18])
    data[15 - 4] = 53
    assert writes(fake) == [write_frame(0x10000004, bytes(data))]
    assert result.after.data[15] == 53
    assert [(c.region, c.offset, c.old, c.new) for c in result.changes] == [
        (Region.CURRENT_PRESET, 15, 5, 53)
    ]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("gain", ("room", 10)),
        ("reverb_decay", ("orange", 3)),  # app colours are not types
        ("reverb_decay", ("room", 41)),
        ("gain", (None, 10)),
    ],
)
async def test_bad_section_value_is_a_value_error(field: str, value: object) -> None:
    fake = make_fake(NORMAL)
    async with TankG.over(fake) as pedal:
        with pytest.raises(ValueError):
            await pedal.plan_set(field, value)  # type: ignore[arg-type]
    assert writes(fake) == []


def test_capture_files_exist() -> None:
    for name in EXCERPTS:
        assert Path(FW96 / name).is_file()


async def test_none_type_keeps_the_current_type() -> None:
    fake = make_fake(NORMAL)  # decay raw 5 = room 6
    async with TankG.over(fake) as pedal:
        result = await pedal.set_field("reverb_decay", (None, 20))
    assert result.after.data[15] == 19  # room 20


async def test_none_type_in_the_off_zone_is_refused() -> None:
    fake = make_fake(NORMAL, buffer=P[:15] + bytes([86]) + P[16:])
    async with TankG.over(fake) as pedal:
        plan = await pedal.plan_set("reverb_decay", (None, 20))
        assert plan.refusal == "type_required"
        with pytest.raises(WriteRefusedError) as exc:
            await pedal.set_field("reverb_decay", (None, 20))
    assert exc.value.reason == "type_required"
    assert writes(fake) == []
