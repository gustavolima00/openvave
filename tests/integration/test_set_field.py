"""``TankG.plan_set`` / ``set_field`` over a fake pedal (T027, US2, FR-007…FR-015, SC-003)."""

from __future__ import annotations

import pytest

from openvave import (
    ProtocolError,
    TankG,
    WriteNakError,
    WriteNotAppliedError,
    WritePlan,
    WriteRefusedError,
    WriteResult,
)
from openvave.models import Region
from openvave.protocol import build_read
from openvave.transport.fake import FakeTransport
from tests.support import storage_fixture as sf
from tests.support.audit import unsafe_frames
from tests.support.write_fixture import (
    ACK,
    EDIT,
    EDIT_BUFFER,
    FW97_QUERY_RX,
    NORMAL,
    TUNER,
    demote,
    make_fake,
    nak,
    write_frame,
    writes,
)

P = sf.PUBLIC_PRESET  # 01 00 00 01 0f 04 3c 3c 46 32 32 00 00 00 00 05 04 07 43 16 43
GAIN_90_DATA = P[4:6] + bytes([90]) + P[7:18]
READS = [build_read(Region.GLOBAL), build_read(Region.CURRENT_PRESET)]


def change_tuples(result: WriteResult) -> tuple[tuple[Region, int, int, int], ...]:
    return tuple((c.region, c.offset, c.old, c.new) for c in result.changes)


async def test_knob_write_rebuilds_the_block_and_verifies() -> None:
    fake = make_fake()
    async with TankG.over(fake) as pedal:
        result = await pedal.set_field("gain", 90, experimental=True)
    assert isinstance(result, WriteResult)
    expected = write_frame(0x10000004, GAIN_90_DATA)
    assert writes(fake) == [expected]
    sent = fake.sent[1:]  # after the handshake
    # plan reads (global, edit buffer) → write → re-read edit buffer, then global
    assert sent == [*READS, expected, READS[1], READS[0]]
    assert result.plan.frame == expected
    assert result.plan.data == GAIN_90_DATA
    assert result.plan.target.kind == "knob_block"
    assert result.plan.before.data == P
    assert result.reply == ACK
    assert result.after.data[6] == 90
    assert result.applied is True
    assert change_tuples(result) == ((Region.CURRENT_PRESET, 6, 60, 90),)


async def test_block_write_differs_from_buffer_only_at_the_target() -> None:
    fake = make_fake()
    async with TankG.over(fake) as pedal:
        result = await pedal.set_field("treble", 0, experimental=True)
    data = result.plan.data
    diffs = [i for i in range(14) if data[i] != P[4 + i]]
    assert diffs == [3]


async def test_switch_write() -> None:
    fake = make_fake()
    async with TankG.over(fake) as pedal:
        result = await pedal.set_field("mod_on", True, experimental=True)
    assert writes(fake) == [write_frame(0x10000001, b"\x01")]
    assert result.plan.target.kind == "block_switch"
    assert result.plan.target.argument == 1
    assert result.applied is True
    assert change_tuples(result) == ((Region.CURRENT_PRESET, 1, 0, 1),)


async def test_switch_accepts_on_off_text() -> None:
    fake = make_fake()
    async with TankG.over(fake) as pedal:
        await pedal.set_field("amp_on", "off", experimental=True)
    assert writes(fake) == [write_frame(0x10000000, b"\x00")]


@pytest.mark.parametrize("value", [(255, 0, 0), "#ff0000", "#FF0000", "255,0,0"])
async def test_led_colour_write(value: object) -> None:
    fake = make_fake()
    async with TankG.over(fake) as pedal:
        result = await pedal.set_field("led_colour", value, experimental=True)
    assert writes(fake) == [write_frame(0x10000012, bytes.fromhex("ff 00 00"))]
    assert result.applied is True
    assert result.after.data[18:21] == bytes.fromhex("ff 00 00")


async def test_no_change_sends_nothing() -> None:
    fake = make_fake()
    async with TankG.over(fake) as pedal:
        plan = await pedal.plan_set("gain", 60)
        result = await pedal.set_field("gain", 60, experimental=True)
    assert plan.no_change is True
    assert result.plan.no_change is True
    assert writes(fake) == []


async def test_tuner_mode_is_refused() -> None:
    # spec 004: normal mode is allowed (check 1); tuner mode is refused before any write
    fake = make_fake(TUNER)
    async with TankG.over(fake) as pedal:
        plan = await pedal.plan_set("gain", 90, experimental=True)
        with pytest.raises(WriteRefusedError) as exc:
            await pedal.set_field("gain", 90, experimental=True)
    assert plan.refusal == "tuner_mode"
    assert exc.value.reason == "tuner_mode"
    assert exc.value.exit_code == 1
    assert writes(fake) == []


async def test_normal_mode_is_allowed() -> None:
    fake = make_fake(NORMAL)
    async with TankG.over(fake) as pedal:
        result = await pedal.set_field("gain", 90)
    assert result.applied is True


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("gain", 128),
        ("gain", -1),
        ("amp_type", 9),
        ("ir_cab", 9),
        ("led_colour", (256, 0, 0)),
        ("led_colour", (0, -1, 0)),
    ],
)
async def test_out_of_range_is_refused_before_any_write(field: str, value: object) -> None:
    fake = make_fake()
    async with TankG.over(fake) as pedal:
        plan = await pedal.plan_set(field, value, experimental=True)
        with pytest.raises(WriteRefusedError) as exc:
            await pedal.set_field(field, value, experimental=True)
    assert plan.refusal == "out_of_range"
    assert plan.frame == b""
    assert exc.value.reason == "out_of_range"
    assert writes(fake) == []


@pytest.mark.parametrize("field", ["knob_unknown", "mode", "bank", "volume_2", ""])
async def test_unknown_field(field: str) -> None:
    fake = make_fake()
    async with TankG.over(fake) as pedal:
        with pytest.raises(WriteRefusedError) as exc:
            await pedal.set_field(field, 1, experimental=True)
    assert exc.value.reason == "unknown_field"
    assert writes(fake) == []


async def test_confirmed_knob_block_needs_no_opt_in() -> None:
    # spec 003 M3: knob block confirmed by gate sessions A and B on fw 96 (SC-005)
    fake = make_fake()
    async with TankG.over(fake) as pedal:
        plan = await pedal.plan_set("gain", 90)
        result = await pedal.set_field("gain", 90)
    assert plan.refusal is None
    assert plan.confidence == "confirmed"
    assert result.applied is True
    assert len(writes(fake)) == 1


async def test_experimental_required_until_confirmed(monkeypatch: pytest.MonkeyPatch) -> None:
    demote(monkeypatch, "block_switch")  # every fw 96 row is confirmed since spec 007
    fake = make_fake()
    async with TankG.over(fake) as pedal:
        plan = await pedal.plan_set("mod_on", True)
        with pytest.raises(WriteRefusedError) as exc:
            await pedal.set_field("mod_on", True)
    assert plan.refusal == "experimental_required"
    assert plan.confidence == "observed"
    assert exc.value.reason == "experimental_required"
    assert "--experimental" in str(exc.value)
    assert "observed" in str(exc.value)
    assert writes(fake) == []


async def test_untested_firmware_is_refused() -> None:
    fake = make_fake(query_rx=FW97_QUERY_RX)
    async with TankG.over(fake) as pedal:
        assert pedal.identity.firmware == 97
        with pytest.raises(WriteRefusedError) as exc:
            await pedal.set_field("gain", 90)
    assert exc.value.reason == "untested_firmware"
    assert writes(fake) == []


async def test_untested_firmware_with_experimental_is_sent() -> None:
    fake = make_fake(query_rx=FW97_QUERY_RX)
    async with TankG.over(fake) as pedal:
        result = await pedal.set_field("gain", 90, experimental=True)
    assert result.applied is True


async def test_nak_stops_without_reread() -> None:
    frame = write_frame(0x10000004, GAIN_90_DATA)
    fake = make_fake(script={"gain write": (frame, nak())})
    async with TankG.over(fake) as pedal:
        with pytest.raises(WriteNakError) as exc:
            await pedal.set_field("gain", 90, experimental=True)
    assert exc.value.reply == nak()
    assert isinstance(exc.value, ProtocolError)
    assert fake.sent[-1] == frame
    assert writes(fake) == [frame]


async def test_ack_without_effect_is_not_applied() -> None:
    frame = write_frame(0x10000004, GAIN_90_DATA)
    fake = make_fake(apply_writes=False, script={"gain write": (frame, ACK)})
    async with TankG.over(fake) as pedal:
        with pytest.raises(WriteNotAppliedError) as exc:
            await pedal.set_field("gain", 90, experimental=True)
    assert exc.value.exit_code == 8
    result = exc.value.result
    assert result.applied is False
    assert result.changes == ()
    assert result.reply == ACK
    assert writes(fake) == [frame]


async def test_every_changed_byte_is_reported() -> None:
    # The pedal copies the physical knob position when a block is switched (cli.md): simulate a
    # switch write that also moves the gain byte.
    frame = write_frame(0x10000001, b"\x01")
    moved = bytearray(P)
    moved[1] = 1
    moved[6] = 99

    class CoMoving(FakeTransport):
        async def write(self, f: bytes) -> None:
            if f == frame and self._memory is not None:
                self._memory[EDIT_BUFFER] = bytes(moved)
            await super().write(f)

    fake = make_fake(apply_writes=False, script={"switch": (frame, ACK)}, cls=CoMoving)
    async with TankG.over(fake) as pedal:
        result = await pedal.set_field("mod_on", True, experimental=True)
    assert result.applied is True
    assert change_tuples(result) == (
        (Region.CURRENT_PRESET, 1, 0, 1),
        (Region.CURRENT_PRESET, 6, 60, 99),
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [("gain", 90), ("delay_on", True), ("led_colour", (1, 2, 3)), ("ir_cab", 0)],
)
async def test_dry_run_frames_equal_sent_frames(field: str, value: object) -> None:
    fake = make_fake()
    async with TankG.over(fake) as pedal:
        plan = await pedal.plan_set(field, value, experimental=True)
        assert isinstance(plan, WritePlan)
        assert writes(fake) == []
        assert plan.reads == tuple(READS)
        result = await pedal.set_field(field, value, experimental=True)
    assert writes(fake) == [plan.frame]
    assert result.plan.frame == plan.frame
    assert result.plan.reads == plan.reads


async def test_plan_shows_mode_and_buffer() -> None:
    fake = make_fake(EDIT)
    async with TankG.over(fake) as pedal:
        plan = await pedal.plan_set("gain", 90, experimental=True)
    assert plan.action == "set gain"
    assert plan.global_before.data == bytes([0, 0, 1, 0])
    assert plan.before.data == P
    assert plan.refusal is None
    assert plan.no_change is False


async def test_no_forbidden_frames() -> None:
    fake = make_fake()
    async with TankG.over(fake) as pedal:
        for field, value in (("gain", 1), ("reverb_on", False), ("led_colour", "#010203")):
            await pedal.set_field(field, value, experimental=True)
    assert unsafe_frames(fake.sent) == []
    assert all(f[2] in (0x11, 0x22, 0x23) for f in fake.sent)
