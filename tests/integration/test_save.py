"""``TankG.plan_save`` / ``save_preset`` (spec 004 US3, FR-012…FR-018, R8, R9, T044).

The fake pedal of ``write_fixture`` applies slot writes to its stored area, counts commits and
loads presets from the stored area on select. The check 4 replay puts the public 1B bytes in 1C
(as on the owner's pedal, where 1B and 1C held the same bytes) and gain 90 in the edit buffer, so
``save_preset(to=2)`` must send exactly the capture's three writes.
"""

from __future__ import annotations

import json

import pytest

from openvave import Backup, ProtocolError, TankG, WriteRefusedError
from openvave.models import SequencePlan, SequenceResult
from tests.integration.gate_fixtures import FW96
from tests.support import storage_fixture as sf
from tests.support.write_fixture import EDIT, NORMAL, TUNER, make_fake, write_frame, writes

pytestmark = pytest.mark.persistent_writes

P = sf.PUBLIC_PRESET
GAIN_90 = P[:6] + bytes([90]) + P[7:]
CHECK3 = FW96 / "20261117-check3-noop_save.jsonl"
CHECK4 = FW96 / "20261117-check4-real_save.jsonl"
COMMIT = bytes.fromhex("00 59 22 08 00 00 04 00 00 00 f0 00 00 00 0b")
SELECT_1C = bytes.fromhex("00 59 22 09 00 00 04 02 00 00 e0 01 00 00 01 17")


def image_with(**slots: bytes) -> bytes:
    """The synthetic image with some presets replaced (``s2=...`` → index 2)."""
    presets = sf.synthetic_presets()
    for name, data in slots.items():
        presets[int(name[1:])] = data
    return sf.HEADER + b"".join(presets)


def stored(fake: object, index: int) -> bytes:
    image = fake._memory[0]  # type: ignore[attr-defined]
    start = 2 + 21 * index
    return bytes(image[start : start + 21])


def capture_writes(path: object) -> list[bytes]:
    records = [json.loads(line) for line in open(str(path), encoding="utf-8")]
    frames = [bytes.fromhex(r["hex"]) for r in records if r["event"] == "tx"]
    return [f for f in frames if f[2] == 0x22]


class Log:
    """Records writes and sleeps in one timeline."""

    def __init__(self, fake: object) -> None:
        self.events: list[tuple[str, object]] = []
        original = fake.write  # type: ignore[attr-defined]

        async def write(frame: bytes) -> None:
            if frame[2] == 0x22:
                self.events.append(("write", bytes(frame)))
            await original(frame)

        fake.write = write  # type: ignore[attr-defined]

    async def sleep(self, seconds: float) -> None:
        self.events.append(("sleep", seconds))


class Backups:
    """An ``on_backup`` callback that records each call and the writes sent before it."""

    def __init__(self, fake: object) -> None:
        self.fake = fake
        self.calls: list[Backup] = []
        self.writes_before: list[int] = []

    def __call__(self, backup: Backup) -> None:
        self.calls.append(backup)
        self.writes_before.append(len(writes(self.fake)))  # type: ignore[arg-type]


async def no_sleep(_: float) -> None:
    return None


def check4_fake() -> object:
    return make_fake(NORMAL, buffer=GAIN_90, image=image_with(s2=P))


async def test_check4_replay_sends_the_capture_writes_with_the_waits() -> None:
    fake = check4_fake()
    log = Log(fake)
    backups = Backups(fake)
    async with TankG.over(fake) as pedal:  # type: ignore[arg-type]
        result = await pedal.save_preset(
            to=2, unsafe=True, experimental=True, on_backup=backups, sleep=log.sleep
        )
    expected = capture_writes(CHECK4)
    assert writes(fake) == expected == [write_frame(0x2C, GAIN_90), COMMIT, SELECT_1C]  # type: ignore[arg-type]
    timeline = [e for e in log.events if e[0] == "write" or e[1] in (0.3, 0.1)]
    first_select_wait = timeline.index(("write", SELECT_1C)) + 1
    assert timeline[:first_select_wait] == [
        ("write", expected[0]),
        ("sleep", 0.3),
        ("write", COMMIT),
        ("sleep", 0.1),
        ("write", SELECT_1C),
    ]
    assert isinstance(result, SequenceResult)
    assert result.verified is True
    assert result.stored_may_have_changed is True
    assert result.read_back == GAIN_90
    assert [o.status for o in result.steps] == ["acked", "waited", "acked", "waited", "acked"]
    assert backups.writes_before == [0] and len(backups.calls) == 1
    assert result.backup is backups.calls[0]
    assert stored(fake, 2) == GAIN_90
    assert fake.commits == 1  # type: ignore[attr-defined]
    assert fake._memory[0x20000000] == bytes([0, 0, 2, NORMAL])  # type: ignore[attr-defined]


async def test_check4_slot_is_read_back_before_the_commit() -> None:
    fake = check4_fake()
    async with TankG.over(fake) as pedal:  # type: ignore[arg-type]
        await pedal.save_preset(
            to=2, unsafe=True, experimental=True, on_backup=lambda b: None, sleep=no_sleep
        )
    sent = fake.sent  # type: ignore[attr-defined]
    slot_write = sent.index(write_frame(0x2C, GAIN_90))
    commit = sent.index(COMMIT)
    assert sf.read_request(0x2C, 21) in sent[slot_write + 1 : commit]


async def test_check3_state_nothing_to_save() -> None:
    # check 3: on 1B in normal mode, the buffer equals stored 1B
    fake = make_fake(NORMAL)
    backups = Backups(fake)
    async with TankG.over(fake) as pedal:  # type: ignore[arg-type]
        plan = await pedal.plan_save()
        result = await pedal.save_preset(
            unsafe=True, experimental=True, on_backup=backups, sleep=no_sleep
        )
    assert plan.no_change is True and plan.steps == ()
    assert plan.target_index == 1 and plan.changed_slots == ()
    assert result.steps == () and result.verified is True
    assert result.stored_may_have_changed is False
    assert result.backup is None
    assert backups.calls == []
    assert writes(fake) == []  # type: ignore[arg-type]
    assert set(capture_writes(CHECK3)) >= {COMMIT}  # the capture really is a save sequence


async def test_plan_save_reads_only_and_describes_the_sequence() -> None:
    fake = make_fake(NORMAL, buffer=GAIN_90)
    async with TankG.over(fake) as pedal:  # type: ignore[arg-type]
        plan = await pedal.plan_save(to=2)
    assert isinstance(plan, SequencePlan)
    assert writes(fake) == []  # type: ignore[arg-type]
    assert plan.action == "save"
    assert plan.state.kind == "normal" and plan.state.index == 1
    assert (plan.target_index, plan.return_index) == (2, 2)
    assert plan.before == sf.synthetic_preset(2) and plan.after == GAIN_90
    assert plan.changed_slots == (2,)
    assert plan.no_change is False
    assert plan.refusal == "unsafe_required"
    assert [s.kind for s in plan.steps] == ["write", "wait", "write", "wait", "write"]
    assert [s.target.kind for s in plan.steps if s.target is not None] == [
        "stored_slot",
        "commit",
        "preset_select",
    ]
    assert [s.seconds for s in plan.steps if s.kind == "wait"] == [0.3, 0.1]
    assert plan.steps[0].frame == write_frame(0x2C, GAIN_90)
    assert plan.reads == tuple(f for f in fake.sent if f[2] == 0x23)  # type: ignore[attr-defined]
    offsets = {c.offset for c in plan.diff}
    assert offsets == {i for i in range(21) if GAIN_90[i] != sf.synthetic_preset(2)[i]}


async def test_save_to_the_loaded_slot() -> None:
    fake = make_fake(NORMAL, buffer=GAIN_90)
    async with TankG.over(fake) as pedal:  # type: ignore[arg-type]
        result = await pedal.save_preset(
            unsafe=True, experimental=True, on_backup=lambda b: None, sleep=no_sleep
        )
    assert result.plan.target_index == 1 and result.verified
    assert stored(fake, 1) == GAIN_90
    assert writes(fake)[0] == write_frame(0x17, GAIN_90)  # type: ignore[arg-type]


async def test_save_to_another_slot_leaves_the_loaded_one() -> None:
    fake = make_fake(NORMAL, buffer=GAIN_90)
    async with TankG.over(fake) as pedal:  # type: ignore[arg-type]
        result = await pedal.save_preset(
            to=5, unsafe=True, experimental=True, on_backup=lambda b: None, sleep=no_sleep
        )
    assert result.verified
    assert stored(fake, 1) == P
    assert stored(fake, 5) == GAIN_90
    assert fake._memory[0x20000000] == bytes([1, 1, 1, NORMAL])  # type: ignore[attr-defined]
    assert fake._memory[0x10000000] == GAIN_90  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("glob", "buffer", "reason"),
    [
        (bytes([0, 0, 1, EDIT]), GAIN_90, "edit_mode"),
        (bytes([0, 0, 1, TUNER]), GAIN_90, "tuner_mode"),
        (bytes([0, 0, 1, 7]), GAIN_90, "unrecognised_state"),
    ],
)
async def test_save_refused_by_state(glob: bytes, buffer: bytes, reason: str) -> None:
    fake = make_fake(NORMAL, glob=glob, buffer=buffer)
    async with TankG.over(fake) as pedal:  # type: ignore[arg-type]
        plan = await pedal.plan_save(to=2, unsafe=True, experimental=True)
        with pytest.raises(WriteRefusedError) as err:
            await pedal.save_preset(
                to=2, unsafe=True, experimental=True, on_backup=lambda b: None, sleep=no_sleep
            )
    assert plan.refusal == reason
    assert err.value.reason == reason
    assert writes(fake) == []  # type: ignore[arg-type]


async def test_save_refused_when_bypassed() -> None:
    fake = make_fake(NORMAL, glob=bytes([0, 0, 0xFF, NORMAL]), buffer=bytes(21))
    async with TankG.over(fake) as pedal:  # type: ignore[arg-type]
        with pytest.raises(WriteRefusedError) as without_to:
            await pedal.plan_save(sleep=no_sleep)
        plan = await pedal.plan_save(to=2, unsafe=True, experimental=True, sleep=no_sleep)
    assert without_to.value.reason == "bypassed"
    assert plan.refusal == "bypassed"
    assert writes(fake) == []  # type: ignore[arg-type]


async def test_unsafe_required() -> None:
    fake = make_fake(NORMAL, buffer=GAIN_90)
    async with TankG.over(fake) as pedal:  # type: ignore[arg-type]
        with pytest.raises(WriteRefusedError) as err:
            await pedal.save_preset(
                to=2, experimental=True, on_backup=lambda b: None, sleep=no_sleep
            )
    assert err.value.reason == "unsafe_required"
    assert "--unsafe" in str(err.value) and "overwrite" in str(err.value)
    assert "--experimental" not in str(err.value)
    assert {f[2] for f in fake.sent} <= {0x11, 0x23}  # type: ignore[attr-defined]


async def test_both_opt_ins_missing_names_both() -> None:
    fake = make_fake(NORMAL, buffer=GAIN_90)
    async with TankG.over(fake) as pedal:  # type: ignore[arg-type]
        with pytest.raises(WriteRefusedError) as err:
            await pedal.save_preset(to=2, on_backup=lambda b: None, sleep=no_sleep)
    assert err.value.reason == "unsafe_required"
    assert "--unsafe" in str(err.value) and "--experimental" in str(err.value)
    assert writes(fake) == []  # type: ignore[arg-type]


async def test_experimental_required_while_rows_are_hypothesis() -> None:
    fake = make_fake(NORMAL, buffer=GAIN_90)
    async with TankG.over(fake) as pedal:  # type: ignore[arg-type]
        plan = await pedal.plan_save(to=2, unsafe=True)
        with pytest.raises(WriteRefusedError) as err:
            await pedal.save_preset(to=2, unsafe=True, on_backup=lambda b: None, sleep=no_sleep)
    assert plan.refusal == err.value.reason == "experimental_required"
    assert "--experimental" in str(err.value)
    assert writes(fake) == []  # type: ignore[arg-type]


async def test_on_backup_raising_stops_before_any_write() -> None:
    fake = make_fake(NORMAL, buffer=GAIN_90)

    def fail(_: Backup) -> None:
        raise OSError("disk full")

    async with TankG.over(fake) as pedal:  # type: ignore[arg-type]
        with pytest.raises(OSError, match="disk full"):
            await pedal.save_preset(
                to=2, unsafe=True, experimental=True, on_backup=fail, sleep=no_sleep
            )
    assert writes(fake) == []  # type: ignore[arg-type]
    assert stored(fake, 2) == sf.synthetic_preset(2)


async def test_async_on_backup_is_awaited() -> None:
    fake = make_fake(NORMAL, buffer=GAIN_90)
    seen: list[int] = []

    async def store(_: Backup) -> None:
        seen.append(len(writes(fake)))  # type: ignore[arg-type]

    async with TankG.over(fake) as pedal:  # type: ignore[arg-type]
        await pedal.save_preset(
            to=2, unsafe=True, experimental=True, on_backup=store, sleep=no_sleep
        )
    assert seen == [0]


async def test_backup_mismatch_stops_before_any_write() -> None:
    other = image_with(s7=GAIN_90)
    script = {sf.IMAGE_LABEL: (sf.read_request(0, 758), sf.read_reply(0, other))}
    fake = make_fake(NORMAL, buffer=GAIN_90, script=script)
    backups = Backups(fake)
    async with TankG.over(fake) as pedal:  # type: ignore[arg-type]
        with pytest.raises(ProtocolError) as err:
            await pedal.save_preset(
                to=2, unsafe=True, experimental=True, on_backup=backups, sleep=no_sleep
            )
    assert err.value.reason == "backup_mismatch"
    assert backups.calls == []
    assert writes(fake) == []  # type: ignore[arg-type]


def test_on_backup_is_required() -> None:
    import inspect

    for name in ("save_preset", "restore"):
        parameter = inspect.signature(getattr(TankG, name)).parameters["on_backup"]
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
        assert parameter.default is inspect.Parameter.empty
