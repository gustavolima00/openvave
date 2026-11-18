"""``TankG.plan_restore`` / ``restore`` (spec 004 US4, FR-019…FR-024, R10, T047).

Restoring one slot is the save sequence with the file's bytes; restoring all writes the file's
758-byte image, commits and selects the preset that was loaded, then verifies with a full read.
The check 4 run 2 replay restores 1C from a backup whose 1C holds the public bytes.
"""

from __future__ import annotations

import pytest

from openvave import TankG, WriteNotAppliedError, WriteRefusedError
from tests.support import restore_fixture as rf
from tests.support import storage_fixture as sf
from tests.support.write_fixture import EDIT, NORMAL, make_fake, write_frame, writes

pytestmark = pytest.mark.persistent_writes

P = sf.PUBLIC_PRESET
GAIN_90 = P[:6] + bytes([90]) + P[7:]
COMMIT = bytes.fromhex("00 59 22 08 00 00 04 00 00 00 f0 00 00 00 0b")
SELECT_1B = bytes.fromhex("00 59 22 09 00 00 04 01 00 00 e0 01 00 00 01 18")
SELECT_1C = bytes.fromhex("00 59 22 09 00 00 04 02 00 00 e0 01 00 00 01 17")
RESTORE_1C = bytes.fromhex(
    "00 59 22 1d 00 00 04 2c 00 00 00 15 00 00 "
    "01 00 00 01 0f 04 3c 3c 46 32 32 00 00 00 00 05 04 07 43 16 43 d7"
)


async def no_sleep(_: float) -> None:
    return None


def stored_image(fake: object) -> bytes:
    return bytes(fake._memory[0])  # type: ignore[attr-defined]


def keep(_: object) -> None:
    return None


async def test_check4_run2_replay_restores_one_slot() -> None:
    # after the power cycle: pedal on 1C, stored 1C = gain 90, the backup holds the original 1C
    pedal_image = rf.image_with(s2=GAIN_90)
    fake = make_fake(NORMAL, glob=bytes([0, 0, 2, NORMAL]), buffer=GAIN_90, image=pedal_image)
    backup = rf.backup(rf.image_with(s2=P))
    async with TankG.over(fake) as pedal:  # type: ignore[arg-type]
        plan = await pedal.plan_restore(backup, slot=2)
        result = await pedal.restore(
            backup, slot=2, unsafe=True, experimental=True, on_backup=keep, sleep=no_sleep
        )
    assert plan.action == "restore_slot" and plan.changed_slots == (2,)
    assert plan.before == GAIN_90 and plan.after == P
    assert writes(fake) == [RESTORE_1C, COMMIT, SELECT_1C]  # type: ignore[arg-type]
    assert result.verified is True
    assert result.read_back == P
    assert stored_image(fake) == backup.image


async def test_restore_all_writes_the_image_and_selects_the_loaded_preset() -> None:
    pedal_image = rf.image_with(s2=GAIN_90, s9=GAIN_90, s35=GAIN_90)
    fake = make_fake(NORMAL, image=pedal_image)
    backup = rf.backup()
    calls: list[int] = []
    async with TankG.over(fake) as pedal:  # type: ignore[arg-type]
        plan = await pedal.plan_restore(backup, all=True)
        result = await pedal.restore(
            backup,
            all=True,
            unsafe=True,
            experimental=True,
            on_backup=lambda b: calls.append(len(writes(fake))),  # type: ignore[arg-type]
            sleep=no_sleep,
        )
    assert plan.action == "restore_all"
    assert plan.changed_slots == (2, 9, 35)
    assert (plan.target_index, plan.return_index) == (None, 1)
    assert plan.diff == ()
    assert plan.before == pedal_image and plan.after == backup.image
    image_frame = write_frame(0, backup.image)
    assert plan.steps[0].frame == image_frame and len(image_frame) == 773
    assert writes(fake) == [image_frame, COMMIT, SELECT_1B]  # type: ignore[arg-type]
    assert calls == [0]
    assert result.verified is True
    assert result.mismatched_slots == ()
    assert stored_image(fake) == backup.image
    assert fake.commits == 1  # type: ignore[attr-defined]
    assert fake._memory[0x20000000] == bytes([0, 0, 1, NORMAL])  # type: ignore[attr-defined]


@pytest.mark.parametrize("kwargs", [{"slot": 2}, {"all": True}])
async def test_nothing_sent_when_the_pedal_matches(kwargs: dict[str, object]) -> None:
    fake = make_fake(NORMAL)
    backup = rf.backup()
    calls: list[object] = []
    async with TankG.over(fake) as pedal:  # type: ignore[arg-type]
        plan = await pedal.plan_restore(backup, **kwargs)  # type: ignore[arg-type]
        result = await pedal.restore(
            backup,
            unsafe=True,
            experimental=True,
            on_backup=calls.append,
            sleep=no_sleep,
            **kwargs,  # type: ignore[arg-type]
        )
    assert plan.no_change is True and plan.changed_slots == () and plan.steps == ()
    assert result.steps == () and result.backup is None and calls == []
    assert writes(fake) == []  # type: ignore[arg-type]


async def test_restore_slot_diff_is_byte_level() -> None:
    fake = make_fake(NORMAL, image=rf.image_with(s2=GAIN_90))
    backup = rf.backup(rf.image_with(s2=P))
    async with TankG.over(fake) as pedal:  # type: ignore[arg-type]
        plan = await pedal.plan_restore(backup, slot=2)
    assert [(c.offset, c.old, c.new) for c in plan.diff] == [(6, 90, 60)]
    assert plan.diff[0].field is not None and plan.diff[0].field.name == "gain"


async def test_unsaved_edits_need_discard_edits() -> None:
    # 1B loaded with gain 90 in the buffer (stored 1B has 60); restoring ends with a select
    fake = make_fake(NORMAL, buffer=GAIN_90, image=rf.image_with(s2=GAIN_90))
    backup = rf.backup()
    async with TankG.over(fake) as pedal:  # type: ignore[arg-type]
        plan = await pedal.plan_restore(backup, all=True, unsafe=True, experimental=True)
        with pytest.raises(WriteRefusedError) as err:
            await pedal.restore(
                backup, all=True, unsafe=True, experimental=True, on_backup=keep, sleep=no_sleep
            )
        assert writes(fake) == []  # type: ignore[arg-type]
        result = await pedal.restore(
            backup,
            all=True,
            unsafe=True,
            experimental=True,
            discard_edits=True,
            on_backup=keep,
            sleep=no_sleep,
        )
    assert plan.refusal == err.value.reason == "edits_would_be_discarded"
    assert "--discard-edits" in str(err.value)
    assert result.verified


async def test_firmware_mismatch_needs_experimental() -> None:
    fake = make_fake(NORMAL, image=rf.image_with(s2=GAIN_90))
    backup = rf.backup(firmware=97)
    async with TankG.over(fake) as pedal:  # type: ignore[arg-type]
        refused = await pedal.plan_restore(backup, slot=2, unsafe=True)
        allowed = await pedal.plan_restore(backup, slot=2, unsafe=True, experimental=True)
    assert refused.refusal == "firmware_mismatch"
    assert allowed.refusal is None


async def test_unsafe_required_for_restore() -> None:
    fake = make_fake(NORMAL, image=rf.image_with(s2=GAIN_90))
    async with TankG.over(fake) as pedal:  # type: ignore[arg-type]
        with pytest.raises(WriteRefusedError) as err:
            await pedal.restore(
                rf.backup(), all=True, experimental=True, on_backup=keep, sleep=no_sleep
            )
    assert err.value.reason == "unsafe_required"
    assert {f[2] for f in fake.sent} <= {0x11, 0x23}  # type: ignore[attr-defined]


async def test_restore_refused_in_edit_mode() -> None:
    fake = make_fake(EDIT, image=rf.image_with(s2=GAIN_90))
    async with TankG.over(fake) as pedal:  # type: ignore[arg-type]
        plan = await pedal.plan_restore(rf.backup(), all=True, unsafe=True, experimental=True)
    assert plan.refusal == "edit_mode"


async def test_verification_mismatch_names_the_slots() -> None:
    # the pedal stores the image with its last byte flipped: preset 9D differs on read-back
    fake = make_fake(NORMAL, image=rf.image_with(s2=GAIN_90), faults={"stored_image": "corrupt"})
    backup = rf.backup()
    async with TankG.over(fake) as pedal:  # type: ignore[arg-type]
        with pytest.raises(WriteNotAppliedError) as err:
            await pedal.restore(
                backup, all=True, unsafe=True, experimental=True, on_backup=keep, sleep=no_sleep
            )
    sequence = err.value.sequence
    assert sequence is not None
    assert sequence.mismatched_slots == (35,)
    assert sequence.verified is False and sequence.stored_may_have_changed is True
    assert [o.status for o in sequence.steps] == ["acked", "waited", "acked", "waited", "acked"]
    assert err.value.exit_code == 8


@pytest.mark.parametrize(
    "kwargs", [{}, {"slot": 2, "all": True}, {"slot": 36}, {"slot": -1}], ids=str
)
async def test_bad_arguments(kwargs: dict[str, object]) -> None:
    fake = make_fake(NORMAL)
    async with TankG.over(fake) as pedal:  # type: ignore[arg-type]
        with pytest.raises(ValueError):
            await pedal.plan_restore(rf.backup(), **kwargs)  # type: ignore[arg-type]
    assert writes(fake) == []  # type: ignore[arg-type]


# -- spec 004 M4 (T085): after gate session B confirms the rows -----------------------------------


def _confirmed(*kinds: str) -> bool:
    from openvave.protocol.writes import message_for

    return all(message_for(k, None).confidence == "confirmed" for k in kinds)


@pytest.mark.xfail(
    not _confirmed("stored_slot", "commit"),
    strict=True,
    reason="stored_slot and commit are confirmed by gate session B (T090)",
)
async def test_restore_slot_runs_with_unsafe_alone_once_confirmed() -> None:
    pedal_image = rf.image_with(s2=GAIN_90)
    fake = make_fake(NORMAL, glob=bytes([0, 0, 2, NORMAL]), buffer=GAIN_90, image=pedal_image)
    backup = rf.backup(rf.image_with(s2=P))
    async with TankG.over(fake) as pedal:  # type: ignore[arg-type]
        plan = await pedal.plan_restore(backup, slot=2, unsafe=True)
        result = await pedal.restore(backup, slot=2, unsafe=True, on_backup=keep, sleep=no_sleep)
    assert plan.refusal is None
    assert writes(fake) == [RESTORE_1C, COMMIT, SELECT_1C]  # type: ignore[arg-type]
    assert result.verified is True


async def test_restore_without_unsafe_is_refused_even_once_confirmed() -> None:
    fake = make_fake(NORMAL, image=rf.image_with(s2=GAIN_90))
    async with TankG.over(fake) as pedal:  # type: ignore[arg-type]
        with pytest.raises(WriteRefusedError) as err:
            await pedal.restore(rf.backup(), slot=2, on_backup=keep, sleep=no_sleep)
    assert err.value.reason == "unsafe_required"
    assert writes(fake) == []  # type: ignore[arg-type]
