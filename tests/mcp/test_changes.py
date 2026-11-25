"""``pedal_changes``: what changed on the pedal since the last read (spec 006 US6, FR-024, R11).

The fake pedal's memory is changed between calls (or during a poll, from the injected poll
sleep), as if the owner turned a knob.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from openvave.transport.fake import FakeTransport
from tests.mcp.conftest import CountingFactory, open_harness, options
from tests.support import choice as ch
from tests.support.write_fixture import EDIT_BUFFER, GLOBAL, NORMAL, make_fake

GAIN = 6  # preset offset of the gain knob (60 in the public preset)


def normal_pedal() -> FakeTransport:
    return make_fake(NORMAL, status=bytes([0]))


def turn(fake: FakeTransport, offset: int, value: int) -> None:
    """The owner moves a control: one byte of the edit buffer changes."""
    buffer = bytearray(fake._memory[EDIT_BUFFER])  # type: ignore[index]
    buffer[offset] = value
    fake._memory[EDIT_BUFFER] = bytes(buffer)  # type: ignore[index]


class PollSleep:
    """Records the poll steps; runs ``action`` on the given step (1-based)."""

    def __init__(self, at: int | None = None, action: object = None) -> None:
        self.calls: list[float] = []
        self.at, self.action = at, action

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)
        if self.at is not None and len(self.calls) == self.at and callable(self.action):
            self.action()


@pytest.fixture(autouse=True)
def _fast(monkeypatch: pytest.MonkeyPatch) -> None:
    ch.no_waits(monkeypatch)


async def test_first_call_takes_the_baseline(tmp_path: Path) -> None:
    async with open_harness(options(tmp_path), CountingFactory(make=normal_pedal)) as h:
        result = await h.ok("pedal_changes")
    assert result["baseline"] is True
    assert result["changed"] is False
    assert result["changes"] == []
    assert result["waited"] == 0
    assert result["state_after"] == "normal"
    assert "baseline" in result["summary"]


async def test_a_turned_knob_is_reported_by_name(tmp_path: Path) -> None:
    factory = CountingFactory(make=normal_pedal)
    async with open_harness(options(tmp_path), factory) as h:
        await h.ok("pedal_changes")
        turn(factory.fake, GAIN, 90)
        result = await h.ok("pedal_changes")
        again = await h.ok("pedal_changes")
    assert result["baseline"] is False
    assert result["changed"] is True
    assert result["changes"] == [
        {
            "region": "current_preset",
            "offset": GAIN,
            "name": "gain",
            "before": 60,
            "after": 90,
            "display_before": "60",
            "display_after": "90",
        }
    ]
    assert "gain 60 → 90" in result["summary"]
    assert again["changed"] is False  # the baseline moved on
    assert again["summary"].startswith("no change")


async def test_typed_knob_change_shows_the_type(tmp_path: Path) -> None:
    factory = CountingFactory(make=normal_pedal)
    async with open_harness(options(tmp_path), factory) as h:
        await h.ok("pedal_changes")
        turn(factory.fake, 15, 44 + 17)  # reverb decay: room 6 -> spring 18
        result = await h.ok("pedal_changes")
    (change,) = result["changes"]
    assert change["name"] == "reverb_decay"
    assert change["display_before"] == "5 (room 6)"
    assert change["display_after"] == "61 (spring 18)"


async def test_state_change_is_reported(tmp_path: Path) -> None:
    factory = CountingFactory(make=normal_pedal)
    async with open_harness(options(tmp_path), factory) as h:
        await h.ok("pedal_changes")
        factory.fake._memory[GLOBAL] = bytes([0, 0, 0xFF, 1])  # type: ignore[index]
        factory.fake._memory[EDIT_BUFFER] = bytes(21)  # type: ignore[index]
        result = await h.ok("pedal_changes")
    assert result["state_before"] == "normal"
    assert result["state_after"] == "bypass"
    regions = {c["region"] for c in result["changes"]}
    assert regions == {"global", "current_preset"}
    assert "normal → bypass" in result["summary"]


async def test_preset_read_sets_the_baseline(tmp_path: Path) -> None:
    factory = CountingFactory(make=normal_pedal)
    async with open_harness(options(tmp_path), factory) as h:
        await h.ok("preset_read")
        turn(factory.fake, GAIN, 61)
        result = await h.ok("pedal_changes")
    assert result["baseline"] is False
    assert [c["name"] for c in result["changes"]] == ["gain"]


async def test_wait_polls_until_a_change(tmp_path: Path) -> None:
    factory = CountingFactory(make=normal_pedal)
    sleep = PollSleep(at=2, action=lambda: turn(factory.fake, GAIN, 99))
    async with open_harness(options(tmp_path), factory, poll_sleep=sleep) as h:
        await h.ok("pedal_changes")
        result = await h.ok("pedal_changes", {"wait_seconds": 10})
    assert result["changed"] is True
    assert result["waited"] == 1.0
    assert sleep.calls == [0.5, 0.5]


async def test_wait_without_change_ends_after_the_wait(tmp_path: Path) -> None:
    sleep = PollSleep()
    async with open_harness(
        options(tmp_path), CountingFactory(make=normal_pedal), poll_sleep=sleep
    ) as h:
        await h.ok("pedal_changes")
        result = await h.ok("pedal_changes", {"wait_seconds": 1.2})
    assert result["changed"] is False
    assert result["waited"] == 1.2
    assert sleep.calls == [0.5, 0.5, pytest.approx(0.2)]


async def test_first_call_with_wait_polls_against_its_own_baseline(tmp_path: Path) -> None:
    factory = CountingFactory(make=normal_pedal)
    sleep = PollSleep(at=1, action=lambda: turn(factory.fake, GAIN, 70))
    async with open_harness(options(tmp_path), factory, poll_sleep=sleep) as h:
        result = await h.ok("pedal_changes", {"wait_seconds": 5})
    assert result["baseline"] is True
    assert result["changed"] is True
    assert [c["name"] for c in result["changes"]] == ["gain"]


@pytest.mark.parametrize("wait", [-1, 30.5, 60])
async def test_wait_is_capped(tmp_path: Path, wait: float) -> None:
    factory = CountingFactory(make=normal_pedal)
    async with open_harness(options(tmp_path), factory) as h:
        text = await h.error("pedal_changes", {"wait_seconds": wait})
    assert text.startswith("invalid_value: ")
    assert "0" in text and "30" in text
    assert factory.calls == 0


async def test_amp_type_change_shows_the_names(tmp_path: Path) -> None:
    """Spec 007 US4: display stays the raw position; names go in new keys and the summary."""
    from openvave._jsonform import position_name_json
    from openvave.protocol.names import position_name

    factory = CountingFactory(make=normal_pedal)
    async with open_harness(options(tmp_path), factory) as h:
        await h.ok("pedal_changes")
        turn(factory.fake, 5, 8)  # amp type 4 -> 8
        result = await h.ok("pedal_changes")
    (change,) = result["changes"]
    before, after = position_name("amp_type", 4), position_name("amp_type", 8)
    assert before is not None and after is not None
    mark = " ?" if after.confidence == "hypothesis" else ""
    assert (change["before"], change["after"]) == (4, 8)
    assert (change["display_before"], change["display_after"]) == ("#4", "#8")
    assert change["position_name_before"] == position_name_json(before)
    assert change["position_name_after"] == position_name_json(after)
    assert f"amp type #4 ({before.text}{mark}) → #8 ({after.text}{mark})" in result["summary"]


async def test_bypass_side_of_a_change_has_no_names(tmp_path: Path) -> None:
    """Codex round 2: the all-zero bypass buffer is not a preset, so amp 0 / cab 0 there are
    not named; the raw diff stays."""
    factory = CountingFactory(make=normal_pedal)
    async with open_harness(options(tmp_path), factory) as h:
        await h.ok("pedal_changes")
        factory.fake._memory[GLOBAL] = bytes([0, 0, 0xFF, 1])  # type: ignore[index]
        factory.fake._memory[EDIT_BUFFER] = bytes(21)  # type: ignore[index]
        result = await h.ok("pedal_changes")
    assert result["state_after"] == "bypass"
    amp = next(c for c in result["changes"] if c["name"] == "amp_type")
    assert (amp["before"], amp["after"]) == (4, 0)
    assert amp["position_name_before"] is not None  # the preset side keeps its name
    assert amp["position_name_after"] is None
    assert "amp type #4 (" in result["summary"]
    assert "→ #0;" in result["summary"] or result["summary"].endswith("→ #0")
