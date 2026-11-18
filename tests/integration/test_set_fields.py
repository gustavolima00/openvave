"""``TankG.plan_set_fields`` / ``set_fields``: several fields over one session (batch edit).

Every write keeps the single-field rules: the knob block is rebuilt from the edit-buffer read
that immediately precedes it, only allowlisted kinds are sent, the confidence gate applies per
write, state refusals refuse the whole batch before anything is sent, and each write is
verified by a re-read before the next one goes out.
"""

from __future__ import annotations

import pytest

from openvave import (
    ConnectionLostError,
    EditPlan,
    EditResult,
    TankG,
    WriteNakError,
    WriteNotAppliedError,
    WriteRefusedError,
)
from openvave.models import Region
from openvave.protocol import build_read
from openvave.protocol.bytemap import type_raw
from tests.support import storage_fixture as sf
from tests.support.audit import unsafe_frames
from tests.support.write_fixture import (
    ACK,
    NORMAL,
    TUNER,
    make_fake,
    write_frame,
    writes,
)

P = sf.PUBLIC_PRESET  # 01 00 00 01 0f 04 3c 3c 46 32 32 00 00 00 00 05 04 07 43 16 43
READ_GLOBAL = build_read(Region.GLOBAL)
READ_BUFFER = build_read(Region.CURRENT_PRESET)
ROOM_18 = type_raw("reverb_decay", "room", 18)


def knob_data(**values: int) -> bytes:
    offsets = {"gain": 6, "treble": 7, "reverb_decay": 15, "mod_fx": 11}
    block = bytearray(P[4:18])
    for name, value in values.items():
        block[offsets[name] - 4] = value
    return bytes(block)


async def test_knob_fields_share_one_knob_block_write() -> None:
    fake = make_fake(NORMAL)
    async with TankG.over(fake) as pedal:
        result = await pedal.set_fields(
            {"gain": 95, "treble": 58, "reverb_decay": ("room", 18)}, experimental=True
        )
    expected = write_frame(0x10000004, knob_data(gain=95, treble=58, reverb_decay=ROOM_18))
    assert writes(fake) == [expected]
    # plan reads (global, edit buffer) → knob write → verify read → final global read
    assert fake.sent[1:] == [READ_GLOBAL, READ_BUFFER, expected, READ_BUFFER, READ_GLOBAL]
    assert isinstance(result, EditResult)
    assert result.applied is True
    assert result.fields_with("applied") == ("gain", "treble", "reverb_decay")
    assert result.after is not None and result.after.data[6] == 95
    assert [(c.offset, c.old, c.new) for c in result.changes] == [
        (6, 60, 95),
        (7, 60, 58),
        (15, 5, ROOM_18),
    ]


async def test_mixed_batch_sends_knob_block_first_then_switch_then_led() -> None:
    fake = make_fake(NORMAL)
    async with TankG.over(fake) as pedal:
        result = await pedal.set_fields(
            [
                ("led_colour", "#2040ff"),
                ("delay_on", "on"),
                ("gain", 95),
                ("mod_on", True),
            ],
            experimental=True,
        )
    knob = write_frame(0x10000004, knob_data(gain=95))
    mod = write_frame(0x10000001, b"\x01")
    delay = write_frame(0x10000002, b"\x01")
    led = write_frame(0x10000012, bytes.fromhex("2040ff"))
    assert writes(fake) == [knob, mod, delay, led]
    # the knob block goes right after the plan's edit-buffer read: nothing in between
    assert fake.sent[1:4] == [READ_GLOBAL, READ_BUFFER, knob]
    # each write is verified by an edit-buffer re-read before the next is sent
    assert fake.sent[4:] == [
        READ_BUFFER,
        mod,
        READ_BUFFER,
        delay,
        READ_BUFFER,
        led,
        READ_BUFFER,
        READ_GLOBAL,
    ]
    assert [w.write.target.kind for w in result.writes] == [
        "knob_block",
        "block_switch",
        "block_switch",
        "led_colour",
    ]
    assert [w.status for w in result.writes] == ["acked"] * 4
    assert all(w.reply == ACK for w in result.writes)
    assert result.fields_with("applied") == ("led_colour", "delay_on", "gain", "mod_on")
    assert unsafe_frames(fake.sent) == []


async def test_plan_reads_only_and_lists_every_frame() -> None:
    fake = make_fake(NORMAL)
    async with TankG.over(fake) as pedal:
        plan = await pedal.plan_set_fields(
            {"gain": 95, "treble": 58, "delay_on": "on", "led_colour": (32, 64, 255)}
        )
    assert writes(fake) == []
    assert isinstance(plan, EditPlan)
    assert plan.reads == (READ_GLOBAL, READ_BUFFER)
    assert [w.frame for w in plan.writes] == [
        write_frame(0x10000004, knob_data(gain=95, treble=58)),
        write_frame(0x10000002, b"\x01"),
        write_frame(0x10000012, bytes([32, 64, 255])),
    ]
    assert plan.writes[0].fields == ("gain", "treble")
    assert [w.confidence for w in plan.writes] == ["confirmed", "observed", "observed"]
    # block_switch and led_colour are 'observed': the batch needs --experimental
    assert plan.refusal == "experimental_required"
    assert plan.refused_field == "delay_on"
    assert [f.refusal for f in plan.fields] == [
        None,
        None,
        "experimental_required",
        "experimental_required",
    ]


async def test_confirmed_only_batch_needs_no_experimental() -> None:
    fake = make_fake(NORMAL)
    async with TankG.over(fake) as pedal:
        result = await pedal.set_fields({"gain": 95, "treble": 58})
    assert result.applied is True
    assert len(writes(fake)) == 1


async def test_experimental_refusal_refuses_the_whole_batch() -> None:
    fake = make_fake(NORMAL)
    async with TankG.over(fake) as pedal:
        with pytest.raises(WriteRefusedError) as info:
            await pedal.set_fields({"gain": 95, "delay_on": "on"})
    assert info.value.reason == "experimental_required"
    assert "delay_on" in str(info.value)
    assert writes(fake) == []


async def test_out_of_range_refuses_the_whole_batch() -> None:
    fake = make_fake(NORMAL)
    async with TankG.over(fake) as pedal:
        plan = await pedal.plan_set_fields({"gain": 95, "treble": 200}, experimental=True)
        with pytest.raises(WriteRefusedError) as info:
            await pedal.set_fields({"gain": 95, "treble": 200}, experimental=True)
    assert plan.refusal == "out_of_range"
    assert plan.refused_field == "treble"
    assert info.value.reason == "out_of_range"
    assert "treble" in str(info.value)
    assert writes(fake) == []


@pytest.mark.parametrize(
    ("mode", "glob", "reason"),
    [
        (TUNER, None, "tuner_mode"),
        (NORMAL, bytes([0, 0, 0xFF, 1]), "bypassed"),
        (NORMAL, bytes([0, 0, 1, 7]), "unrecognised_state"),
    ],
)
async def test_state_refusals(mode: int, glob: bytes | None, reason: str) -> None:
    buffer = bytes(21) if reason == "bypassed" else P
    fake = make_fake(mode, glob=glob, buffer=buffer)
    async with TankG.over(fake) as pedal:
        with pytest.raises(WriteRefusedError) as info:
            await pedal.set_fields({"gain": 95, "treble": 58}, experimental=True, sleep=_no_sleep)
    assert info.value.reason == reason
    assert writes(fake) == []


async def test_edit_mode_is_allowed() -> None:
    fake = make_fake()  # edit mode
    async with TankG.over(fake) as pedal:
        result = await pedal.set_fields({"gain": 95}, experimental=True)
    assert result.applied is True


async def test_unchanged_fields_are_skipped() -> None:
    fake = make_fake(NORMAL)
    async with TankG.over(fake) as pedal:
        result = await pedal.set_fields(
            {"gain": 60, "treble": 58, "amp_on": True, "led_colour": "#431643"},
            experimental=True,
        )
    assert writes(fake) == [write_frame(0x10000004, knob_data(treble=58))]
    assert result.plan.writes[0].fields == ("treble",)
    assert result.fields_with("unchanged") == ("gain", "amp_on", "led_colour")
    assert result.fields_with("applied") == ("treble",)


async def test_all_unchanged_sends_nothing() -> None:
    fake = make_fake(NORMAL)
    async with TankG.over(fake) as pedal:
        result = await pedal.set_fields({"gain": 60, "delay_on": False})
    assert writes(fake) == []
    assert result.plan.no_change is True
    assert result.applied is True
    assert result.writes == ()


async def test_keep_type_uses_the_current_type() -> None:
    fake = make_fake(NORMAL)
    async with TankG.over(fake) as pedal:
        plan = await pedal.plan_set_fields({"reverb_decay": (None, 18), "mod_fx": ("phaser", 2)})
    data = knob_data(
        reverb_decay=type_raw("reverb_decay", "room", 18), mod_fx=type_raw("mod_fx", "phaser", 2)
    )
    assert plan.writes[0].data == data


async def test_keep_type_between_types_is_type_required() -> None:
    buffer = P[:15] + bytes([41]) + P[16:]  # 41 % 44 = 41: between room and spring
    fake = make_fake(NORMAL, buffer=buffer)
    async with TankG.over(fake) as pedal:
        plan = await pedal.plan_set_fields({"gain": 95, "reverb_decay": (None, 18)})
    assert plan.refusal == "type_required"
    assert plan.refused_field == "reverb_decay"


async def test_unknown_field_and_bad_syntax_raise_before_any_read() -> None:
    fake = make_fake(NORMAL)
    async with TankG.over(fake) as pedal:
        sent = len(fake.sent)
        with pytest.raises(WriteRefusedError) as info:
            await pedal.plan_set_fields({"gain": 95, "fuzz": 3})
        assert info.value.reason == "unknown_field"
        with pytest.raises(ValueError, match="delay_on"):
            await pedal.plan_set_fields({"gain": 95, "delay_on": "maybe"})
        with pytest.raises(ValueError, match="twice"):
            await pedal.plan_set_fields([("gain", 95), ("gain", 96)])
        with pytest.raises(ValueError, match="at least one"):
            await pedal.plan_set_fields({})
        assert len(fake.sent) == sent


async def test_plan_equals_what_set_fields_sends() -> None:
    changes = {"gain": 95, "delay_on": "on", "led_colour": "#2040ff"}
    planned = make_fake(NORMAL)
    async with TankG.over(planned) as pedal:
        plan = await pedal.plan_set_fields(changes, experimental=True)
    sent = make_fake(NORMAL)
    async with TankG.over(sent) as pedal:
        await pedal.set_fields(changes, experimental=True)
    assert [w.frame for w in plan.writes] == writes(sent)


# -- failure mid-batch: which fields were applied ------------------------------------------------


async def test_nak_mid_batch_reports_applied_fields() -> None:
    fake = make_fake(NORMAL, faults={"block_switch": "nak"})
    async with TankG.over(fake) as pedal:
        with pytest.raises(WriteNakError) as info:
            await pedal.set_fields(
                {"gain": 95, "delay_on": "on", "led_colour": "#2040ff"}, experimental=True
            )
    edit = info.value.edit
    assert edit is not None
    assert [w.status for w in edit.writes] == ["acked", "nak", "not_sent"]
    assert edit.fields_with("applied") == ("gain",)
    assert edit.fields_with("unknown") == ("delay_on",)
    assert edit.fields_with("not_sent") == ("led_colour",)
    assert edit.applied is False
    # nothing after the NAK: no retry, the LED write never went out
    assert len(writes(fake)) == 2


async def test_connection_lost_mid_batch_reports_applied_fields() -> None:
    fake = make_fake(NORMAL, faults={"led_colour": "disconnect"})
    async with TankG.over(fake) as pedal:
        with pytest.raises(ConnectionLostError) as info:
            await pedal.set_fields(
                {"gain": 95, "delay_on": "on", "led_colour": "#2040ff"}, experimental=True
            )
    edit = info.value.edit
    assert edit is not None
    assert [w.status for w in edit.writes] == ["acked", "acked", "no_reply"]
    assert edit.fields_with("applied") == ("gain", "delay_on")
    assert edit.fields_with("unknown") == ("led_colour",)


async def test_not_applied_stops_the_batch() -> None:
    fake = make_fake(NORMAL, faults={"knob_block": "ignore"})
    async with TankG.over(fake) as pedal:
        with pytest.raises(WriteNotAppliedError) as info:
            await pedal.set_fields({"gain": 95, "delay_on": "on"}, experimental=True)
    edit = info.value.edit
    assert edit is not None
    assert info.value.result is None
    assert [w.status for w in edit.writes] == ["acked", "not_sent"]
    assert edit.writes[0].applied is False
    assert edit.fields_with("not_applied") == ("gain",)
    assert edit.fields_with("not_sent") == ("delay_on",)
    assert "gain" in str(info.value)
    assert len(writes(fake)) == 1


async def test_single_field_errors_carry_no_edit() -> None:
    fake = make_fake(NORMAL, faults={"knob_block": "nak"})
    async with TankG.over(fake) as pedal:
        with pytest.raises(WriteNakError) as info:
            await pedal.set_field("gain", 95)
    assert info.value.edit is None


async def _no_sleep(seconds: float) -> None:
    return None
