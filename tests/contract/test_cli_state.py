"""The pedal state in ``info``, ``preset dump`` and ``watch`` (spec 004 T011, FR-011, R13)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import openvave.session
from openvave.cli import main
from openvave.transport.fake import FakeTransport
from tests.contract.test_cli_set import factory_for
from tests.contract.test_cli_watch import VALIDATOR, run_watch, strip_time
from tests.support import storage_fixture as sf
from tests.support.captures import FW96_CONNECT, GLOBAL, PRESET

BYPASS_GLOBAL = bytes([0, 0, 0xFF, 1])
BYPASS_LINE = "state: bypass (all blocks off; the pedal does not report the loaded slot)"
BYPASS_CYCLE = {"global": {2: 0xFF}, "preset": dict.fromkeys(range(21), 0)}


@pytest.fixture(autouse=True)
def no_confirm_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    async def no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(openvave.session, "STATE_SLEEP", no_sleep)


def bypassed(bank: int = 0) -> FakeTransport:
    glob = bytes([bank, bank, 0xFF, 1])
    return FakeTransport.from_capture(
        FW96_CONNECT,
        replies={
            GLOBAL: sf.read_reply(0x20000000, glob),
            PRESET: sf.read_reply(0x10000000, bytes(21)),
        },
    )


def run(
    capsys: pytest.CaptureFixture[str], argv: list[str], fake: FakeTransport | None = None
) -> tuple[int, str, str]:
    code = main(
        argv, transport_factory=factory_for(fake or FakeTransport.from_capture(FW96_CONNECT))
    )
    out, err = capsys.readouterr()
    return code, out, err


@pytest.mark.parametrize("argv", [["info"], ["preset", "dump"]])
def test_normal_state_line(capsys: pytest.CaptureFixture[str], argv: list[str]) -> None:
    code, out, err = run(capsys, argv)
    assert code == 0, err
    assert "state: normal, preset 1B" in out.splitlines()


@pytest.mark.parametrize("argv", [["info"], ["preset", "dump"]])
def test_bypass_state_lines(capsys: pytest.CaptureFixture[str], argv: list[str]) -> None:
    code, out, err = run(capsys, argv, bypassed(bank=2))
    assert code == 0, err
    lines = out.splitlines()
    assert BYPASS_LINE in lines
    assert "bank 3, slot not reported" in lines
    assert "reverb decay" not in out and "gain" not in out  # no decoded preset fields


def test_dump_in_bypass_shows_the_raw_buffer(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err = run(capsys, ["preset", "dump"], bypassed())
    assert code == 0, err
    lines = out.splitlines()
    assert "  00: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00" in lines
    assert "  10: 00 00 00 00 00" in lines
    assert not any(line.startswith("      [") for line in lines)


@pytest.mark.parametrize(
    ("argv", "key"), [(["info", "--json"], "regions"), (["preset", "dump", "--json"], "preset")]
)
def test_json_pedal_state(capsys: pytest.CaptureFixture[str], argv: list[str], key: str) -> None:
    code, out, err = run(capsys, argv)
    assert code == 0, err
    normal = json.loads(out)
    assert normal["pedal_state"] == "normal"
    code, out, err = run(capsys, argv, bypassed())
    assert code == 0, err
    doc = json.loads(out)
    assert doc["pedal_state"] == "bypass"
    assert doc["schema_version"] == 2
    # ``fields`` keep their meaning: they still describe the bytes that were read
    if key == "preset":
        assert [f["name"] for f in doc["preset"]["fields"]] == [
            f["name"] for f in normal["preset"]["fields"]
        ]
        assert doc["preset"]["data"] == bytes(21).hex(" ")


def test_watch_header_and_loading(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    run_ = run_watch(
        capsys,
        monkeypatch,
        tmp_path,
        ["--no-record", "--duration", "1.4"],
        cycles=[{}, BYPASS_CYCLE, {}],
    )
    assert run_.code == 0, run_.err
    lines = run_.out.splitlines()
    assert "  state   normal, preset 1B" in lines[:6]
    states = [strip_time(line) for line in lines if "state: " in line]
    assert states == ["  state: loading", "  state: normal, preset 1B"]


def test_watch_two_cycles_are_bypass(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    run_ = run_watch(
        capsys,
        monkeypatch,
        tmp_path,
        ["--no-record", "--duration", "1.4"],
        cycles=[{}, BYPASS_CYCLE, BYPASS_CYCLE],
    )
    assert run_.code == 0, run_.err
    lines = run_.out.splitlines()
    states = [strip_time(line) for line in lines if "state: " in line]
    assert states == ["  state: loading", "  state: bypass"]
    # the loading line comes after the byte changes that caused it
    loading = next(i for i, line in enumerate(lines) if "state: loading" in line)
    assert any("preset[" in line or "slot" in line for line in lines[:loading])


def test_watch_json_carries_pedal_state(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    run_ = run_watch(
        capsys,
        monkeypatch,
        tmp_path,
        ["--no-record", "--json", "--duration", "1.4"],
        cycles=[{}, BYPASS_CYCLE, {}],
    )
    assert run_.code == 0, run_.err
    events = run_.events
    for event in events:
        VALIDATOR.validate(event)
    start = events[0]
    changes = [e for e in events if e["event"] == "change"]
    assert start["pedal_state"] == "normal"
    assert [e["pedal_state"] for e in changes] == ["loading", "normal"]
