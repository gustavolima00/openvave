"""Every failure point of a save sequence (spec 004 FR-031, R15, SC-008, T045).

Each case asserts the error class (and so the exit code), the per-step statuses, whether stored
presets may have changed, and that nothing at all is sent after the failing step (no retry).
"""

from __future__ import annotations

import pytest

from openvave import (
    ConnectionLostError,
    OpenvaveError,
    RequestTimeoutError,
    TankG,
    WriteNakError,
    WriteNotAppliedError,
)
from openvave.models import SequenceResult
from tests.support import storage_fixture as sf
from tests.support.write_fixture import NORMAL, make_fake, write_frame, writes

pytestmark = pytest.mark.persistent_writes

P = sf.PUBLIC_PRESET
GAIN_90 = P[:6] + bytes([90]) + P[7:]
SLOT = write_frame(0x2C, GAIN_90)
COMMIT = write_frame(0xF0000000, b"")
SELECT = write_frame(0xE0000002, b"\x01")
FRAMES = {"stored_slot": SLOT, "commit": COMMIT, "preset_select": SELECT}

ACKED, WAITED, NAK, NO_REPLY, NOT_SENT = "acked", "waited", "nak", "no_reply", "not_sent"


async def no_sleep(_: float) -> None:
    return None


async def run(faults: dict[str, str], timeout: float = 2.0) -> tuple[object, OpenvaveError]:
    fake = make_fake(NORMAL, buffer=GAIN_90, faults=faults)
    async with TankG.over(fake, timeout=timeout) as pedal:  # type: ignore[arg-type]
        with pytest.raises(OpenvaveError) as err:
            await pedal.save_preset(
                to=2, unsafe=True, experimental=True, on_backup=lambda b: None, sleep=no_sleep
            )
    return fake, err.value


CASES = [
    # (fault, error class, exit code, step statuses, failing write)
    ({"stored_slot": "nak"}, WriteNakError, 7, [NAK, NOT_SENT, NOT_SENT, NOT_SENT, NOT_SENT]),
    ({"commit": "nak"}, WriteNakError, 7, [ACKED, WAITED, NAK, NOT_SENT, NOT_SENT]),
    ({"preset_select": "nak"}, WriteNakError, 7, [ACKED, WAITED, ACKED, WAITED, NAK]),
    (
        {"stored_slot": "disconnect"},
        ConnectionLostError,
        6,
        [NO_REPLY, NOT_SENT, NOT_SENT, NOT_SENT, NOT_SENT],
    ),
    (
        {"commit": "disconnect"},
        ConnectionLostError,
        6,
        [ACKED, WAITED, NO_REPLY, NOT_SENT, NOT_SENT],
    ),
    (
        {"preset_select": "disconnect"},
        ConnectionLostError,
        6,
        [ACKED, WAITED, ACKED, WAITED, NO_REPLY],
    ),
]


@pytest.mark.parametrize(("faults", "error", "code", "statuses"), CASES)
async def test_failure_reports_every_step_and_sends_nothing_after(
    faults: dict[str, str], error: type[OpenvaveError], code: int, statuses: list[str]
) -> None:
    fake, err = await run(faults)
    assert type(err) is error
    assert err.exit_code == code
    sequence = err.sequence
    assert isinstance(sequence, SequenceResult)
    assert [o.status for o in sequence.steps] == statuses
    assert sequence.stored_may_have_changed is True  # the slot write reached the transport
    assert sequence.verified is False
    assert sequence.backup is not None
    failing = FRAMES[next(iter(faults))]
    sent = fake.sent  # type: ignore[attr-defined]
    assert sent[-1] == failing  # nothing follows the failing write: no retry, no read
    assert writes(fake).count(failing) == 1  # type: ignore[arg-type]


async def test_no_reply_to_the_commit_times_out() -> None:
    fake, err = await run({"commit": "no_reply"}, timeout=0.05)
    assert isinstance(err, RequestTimeoutError) and err.exit_code == 6
    assert [o.status for o in err.sequence.steps] == [ACKED, WAITED, NO_REPLY, NOT_SENT, NOT_SENT]
    assert err.sequence.stored_may_have_changed is True
    assert fake.sent[-1] == COMMIT  # type: ignore[attr-defined]


async def test_slot_read_back_mismatch_stops_before_the_commit() -> None:
    fake, err = await run({"stored_slot": "corrupt"})
    assert isinstance(err, WriteNotAppliedError) and err.exit_code == 8
    sequence = err.sequence
    assert [o.status for o in sequence.steps] == [ACKED, NOT_SENT, NOT_SENT, NOT_SENT, NOT_SENT]
    assert sequence.stored_may_have_changed is True
    assert sequence.read_back is not None and sequence.read_back != GAIN_90
    assert COMMIT not in fake.sent  # type: ignore[attr-defined]
    assert writes(fake) == [SLOT]  # type: ignore[arg-type]
    assert "commit" in str(err) or "read back" in str(err)


async def test_final_verification_mismatch() -> None:
    # the select is acknowledged but ignored: the pedal stays on 1B
    fake, err = await run({"preset_select": "ignore"})
    assert isinstance(err, WriteNotAppliedError) and err.exit_code == 8
    sequence = err.sequence
    assert [o.status for o in sequence.steps] == [ACKED, WAITED, ACKED, WAITED, ACKED]
    assert sequence.verified is False
    assert sequence.stored_may_have_changed is True
    assert sequence.read_back == GAIN_90
    assert writes(fake) == [SLOT, COMMIT, SELECT]  # type: ignore[arg-type]


async def test_a_nak_on_the_first_write_never_reaches_the_commit() -> None:
    fake, _ = await run({"stored_slot": "nak"})
    assert fake.commits == 0  # type: ignore[attr-defined]
    assert writes(fake) == [SLOT]  # type: ignore[arg-type]
