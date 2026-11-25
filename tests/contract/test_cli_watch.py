"""``openvave watch``: human output, JSON Lines, stopping, options, errors (T020, US1)."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import jsonschema
import pytest
from referencing import Registry, Resource

from openvave.cli import main
from openvave.models import DeviceInfo, Region
from openvave.protocol import BYTE_MAP
from openvave.transport import Transport
from tests.support.captures import REPO_ROOT
from tests.support.watch import (
    Cycle,
    FakeClock,
    GatedFake,
    ScriptedStdin,
    cycle_write,
    watch_script,
)

CONTRACTS = REPO_ROOT / "specs" / "002-preset-byte-map" / "contracts"
WATCH_SCHEMA = json.loads((CONTRACTS / "watch-event.schema.json").read_text(encoding="utf-8"))
FIELD_SCHEMA = json.loads((CONTRACTS / "decoded-field.schema.json").read_text(encoding="utf-8"))
REGISTRY = Registry().with_resources(
    [
        ("decoded-field.schema.json", Resource.from_contents(FIELD_SCHEMA)),
        (FIELD_SCHEMA["$id"], Resource.from_contents(FIELD_SCHEMA)),
    ]
)
VALIDATOR = jsonschema.Draft202012Validator(WATCH_SCHEMA, registry=REGISTRY)
PEDAL = DeviceInfo("3F1A-UUID", "TANK-Gv2_BLE", -58)
BYTE_MAP_LABELS = {
    e.offset: e.label for e in BYTE_MAP if e.region is Region.CURRENT_PRESET and e.name
}
HINT = "hint: no preset byte changed in 30 s and the pedal is not in edit mode"

# The contracts/cli.md walkthrough: edit mode on, reverb decay sweep, a co-moving step.
WALKTHROUGH: list[Cycle] = [
    {},
    {},
    {"global": {3: 0}},
    {"global": {3: 0}, "preset": {15: 64}},
    {"global": {3: 0}, "preset": {15: 127}},
    {"global": {3: 0}, "preset": {15: 127, 16: 90, 17: 8}},
]
WALKTHROUGH_STDIN = [
    (cycle_write(3), "edit mode on"),
    (cycle_write(4), "reverb decay min→max"),
    (cycle_write(6), "reverb mix only"),
    (cycle_write(7), "q"),
]


class Run:
    def __init__(self, code: int, out: str, err: str, fake: GatedFake, cwd: Path) -> None:
        self.code, self.out, self.err, self.fake, self.cwd = code, out, err, fake, cwd

    @property
    def events(self) -> list[dict[str, Any]]:
        return [json.loads(line) for line in self.out.splitlines() if line.strip()]

    def records(self) -> list[Path]:
        return sorted((self.cwd / "captures" / "private").glob("*.jsonl"))


def run_watch(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    argv: Sequence[str],
    *,
    cycles: Sequence[Cycle] = ({},),
    stdin: Sequence[tuple[int, str]] = (),
    connect_seconds: float = 0.0,
    **fake_options: Any,
) -> Run:
    monkeypatch.chdir(tmp_path)
    scripted = ScriptedStdin(stdin)
    fake = GatedFake(watch_script(cycles), scripted, **fake_options)
    clock = FakeClock()

    async def factory(
        device_id: str | None, scan_timeout: float
    ) -> tuple[Transport, DeviceInfo | None]:
        clock.now += connect_seconds  # scanning and connecting take time
        return fake, PEDAL

    code = main(["watch", *argv], transport_factory=factory, stdin=scripted, clock=clock)
    out, err = capsys.readouterr()
    return Run(code, out, err, fake, tmp_path)


def strip_time(line: str) -> str:
    """Drop the 7-character time column (fake clock values vary by microseconds)."""
    assert re.match(r"^ *(\+\d+\.\d\ds)? {2}", line), line
    return line[7:]


def test_human_walkthrough(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    run = run_watch(
        capsys,
        monkeypatch,
        tmp_path,
        ["--no-record"],
        cycles=WALKTHROUGH,
        stdin=WALKTHROUGH_STDIN,
    )
    assert run.code == 0, run.err
    lines = run.out.splitlines()
    assert lines[:5] == [
        "Watching TANK-Gv2 (firmware 96), every 0.5 s. "
        "Type a label and Enter before each step; q to quit.",
        "  global  00 00 01 01   browsed bank = 0, bank = 0, slot = 1, mode = normal",
        "  preset  01 00 00 01 0f 04 3c 3c 46 32 32 00 00 00 00 05 04 07 43 16 43",
        "  status  01   loopback = on",
        "  state   normal, preset 1B",  # spec 004 R13
    ]
    body = lines[5:-1]
    assert body[0] == "── label: edit mode on ──"
    assert strip_time(body[1]) == "  global[3]   mode              normal → edit"
    assert re.match(r"^ *\+\d+\.\d\ds  ", body[1])
    assert strip_time(body[2]) == "  state: edit, preset 1B"
    assert body[3] == "── label: reverb decay min→max ──"
    assert strip_time(body[4]) == "  preset[15]  reverb decay      5 (room 6) → 64 (spring 21)"
    assert strip_time(body[5]) == "  preset[15]  reverb decay      64 (spring 21) → 127 (cloud 40)"
    assert body[6] == "── label: reverb mix only ──"
    # Named cab positions (spec 007 US4, from the names table) widen the value column.
    from openvave.protocol.names import position_name

    def cab(raw: int) -> str:
        name = position_name("ir_cab", raw)
        assert name is not None
        return f"#{raw} ({name.text}{' ?' if name.confidence == 'hypothesis' else ''})"

    width = max(4, len(cab(7)))
    assert strip_time(body[7]) == (
        f"  preset[16]  {'reverb mix':<18}{'4':>{width}} → 90     (co-moving: 2)"
    )
    assert body[8] == f"         preset[17]  {'IR cab':<18}{cab(7):>{width}} → {cab(8)}"
    assert len(body) == 9  # q is not a label; no heartbeat lines
    assert re.fullmatch(r"Stopped after \d+\.\d s: 5 changes in \d+ cycles\.", lines[-1])
    assert "Recording" not in run.out
    assert run.records() == []


def test_led_byte_shows_its_name(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    run = run_watch(
        capsys,
        monkeypatch,
        tmp_path,
        ["--no-record", "--duration", "1"],
        cycles=[{}, {"preset": {19: 0x10}}],
    )
    assert run.code == 0, run.err
    change = [line for line in run.out.splitlines() if "preset[19]" in line]
    # an unknown byte would show raw hex; since spec 007 every fw 96 preset byte is named
    assert [strip_time(c) for c in change] == ["  preset[19]  LED green           22 → 16"]


def test_json_lines_validate(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    run = run_watch(
        capsys,
        monkeypatch,
        tmp_path,
        ["--json", "--no-record"],
        cycles=WALKTHROUGH,
        stdin=WALKTHROUGH_STDIN,
    )
    assert run.code == 0, run.err
    events = run.events
    for event in events:
        VALIDATOR.validate(event)
        assert event["schema_version"] == 2
    assert events[0]["event"] == "start"
    assert events[-1]["event"] == "stop"
    assert events[-1]["reason"] == "quit"
    assert events[-1]["error"] is None
    assert events[-1]["changes"] == 5
    start = events[0]
    assert start["interval"] == 0.5
    assert start["record"] is None
    assert start["identity"]["firmware"] == 96
    assert list(start["regions"]) == ["global", "current_preset", "status"]
    assert start["regions"]["current_preset"]["data"].startswith("01 00 00 01 0f")
    kinds = [e["event"] for e in events]
    assert kinds == [
        "start",
        "label",
        "change",
        "label",
        "change",
        "change",
        "label",
        "change",
        "stop",
    ]
    changes = [e for e in events if e["event"] == "change"]
    assert changes[0]["label"] == "edit mode on"
    assert changes[0]["changes"] == [
        {"region": "global", "offset": 3, "old": 1, "new": 0, "field": "mode"}
    ]
    assert [c["cycle"] for c in changes] == [3, 4, 5, 6]
    assert changes[3]["label"] == "reverb mix only"
    assert [(c["offset"], c["field"]) for c in changes[3]["changes"]] == [
        (16, "reverb_mix"),
        (17, "ir_cab"),
    ]
    from openvave._jsonform import position_name_json
    from openvave.protocol.names import position_name

    cab = changes[3]["changes"][1]
    names = [position_name("ir_cab", cab[k]) for k in ("old", "new")]
    assert [cab["position_name_old"], cab["position_name_new"]] == [
        None if n is None else position_name_json(n) for n in names
    ]
    assert "position_name_old" not in changes[3]["changes"][0]
    times = [e["t"] for e in events]
    assert times == sorted(times)


def test_duration_with_empty_stdin(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    run = run_watch(capsys, monkeypatch, tmp_path, ["--json", "--no-record", "--duration", "1"])
    assert run.code == 0, run.err
    stop = run.events[-1]
    assert stop["reason"] == "duration"
    assert stop["t"] == pytest.approx(1.0, abs=0.01)
    assert stop["cycles"] >= 2


@pytest.mark.parametrize("word", ["q", "quit", "  q  "])
def test_q_and_quit_stop(
    word: str,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    run = run_watch(
        capsys,
        monkeypatch,
        tmp_path,
        ["--json", "--no-record"],
        stdin=[(cycle_write(2), word)],
    )
    assert run.code == 0, run.err
    assert [e["event"] for e in run.events] == ["start", "stop"]
    assert run.events[-1]["reason"] == "quit"


def test_eof_on_stdin_does_not_stop(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    run = run_watch(
        capsys,
        monkeypatch,
        tmp_path,
        ["--json", "--no-record", "--duration", "3"],
        stdin=[(cycle_write(2), "only label")],
    )
    assert run.code == 0, run.err
    stop = run.events[-1]
    assert stop["reason"] == "duration"
    assert stop["cycles"] >= 6
    assert [e["text"] for e in run.events if e["event"] == "label"] == ["only label"]


def test_blank_lines_are_not_labels(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    run = run_watch(
        capsys,
        monkeypatch,
        tmp_path,
        ["--json", "--no-record", "--duration", "2"],
        stdin=[(cycle_write(2), "   "), (cycle_write(3), "  padded label  ")],
    )
    assert [e["text"] for e in run.events if e["event"] == "label"] == ["padded label"]


@pytest.mark.parametrize(
    "argv",
    [
        ["--interval", "0.1"],
        ["--interval", "0"],
        ["--duration", "0"],
        ["--record", "captures/fw96/x.jsonl"],
        ["--record", "captures/x.jsonl"],
        ["--record", "captures/private/x.jsonl", "--no-record"],
    ],
    ids=["interval", "interval0", "duration0", "record_fw96", "record_captures", "both"],
)
def test_usage_errors_exit_2_before_connecting(
    argv: list[str],
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    run = run_watch(capsys, monkeypatch, tmp_path, argv)
    assert run.code == 2
    assert run.fake.sent == []
    assert not run.fake.opened
    assert run.err.strip()
    assert not (tmp_path / "captures").exists() or run.records() == []


def test_interval_minimum_accepted(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    run = run_watch(
        capsys,
        monkeypatch,
        tmp_path,
        ["--json", "--no-record", "--interval", "0.2", "--duration", "1"],
    )
    assert run.code == 0, run.err
    assert run.events[0]["interval"] == 0.2


def test_no_record_writes_no_file(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    run = run_watch(capsys, monkeypatch, tmp_path, ["--no-record", "--duration", "1"])
    assert run.code == 0, run.err
    assert list(tmp_path.iterdir()) == []


def test_default_record_path(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    run = run_watch(capsys, monkeypatch, tmp_path, ["--duration", "1"])
    assert run.code == 0, run.err
    records = run.records()
    assert len(records) == 1
    assert re.fullmatch(r"\d{8}-\d{6}-watch\.jsonl", records[0].name)
    relative = f"captures/private/{records[0].name}"
    assert run.out.splitlines()[1] == f"Recording to {relative}"
    assert run.out.splitlines()[-1].endswith(f"Record: {relative}")


def test_record_path_outside_captures_and_parents_created(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    run = run_watch(
        capsys,
        monkeypatch,
        tmp_path,
        ["--json", "--record", "out/deep/session.jsonl", "--duration", "1"],
    )
    assert run.code == 0, run.err
    assert (tmp_path / "out" / "deep" / "session.jsonl").is_file()
    assert run.events[0]["record"] == "out/deep/session.jsonl"


def test_connection_lost_exit_6_with_stop_event(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    run = run_watch(
        capsys,
        monkeypatch,
        tmp_path,
        ["--json", "--no-record"],
        cycles=[{}, {"preset": {15: 64}}],
        disconnect_after=1 + 3 * 3,
    )
    assert run.code == 6
    assert [e["event"] for e in run.events] == ["start", "change", "stop"]
    stop = run.events[-1]
    assert stop["reason"] == "connection_lost"
    assert stop["error"]
    assert "error:" in run.err
    assert run.fake.closed


def test_connection_lost_human_summary(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    run = run_watch(capsys, monkeypatch, tmp_path, ["--no-record"], disconnect_after=1 + 3 * 2)
    assert run.code == 6
    assert run.out.splitlines()[-1].startswith("Stopped after ")
    assert "error: simulated disconnect" in run.err


def test_edit_mode_hint_once(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    run = run_watch(
        capsys,
        monkeypatch,
        tmp_path,
        ["--no-record", "--duration", "65"],
        stdin=[(cycle_write(2), "some knob")],
    )
    assert run.code == 0, run.err
    assert run.err.count(HINT) == 1


def test_no_hint_without_label(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    run = run_watch(capsys, monkeypatch, tmp_path, ["--no-record", "--duration", "35"])
    assert run.code == 0, run.err
    assert HINT not in run.err


def test_no_hint_in_edit_mode(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    run = run_watch(
        capsys,
        monkeypatch,
        tmp_path,
        ["--no-record", "--duration", "35"],
        cycles=[{"global": {3: 0}}],
        stdin=[(cycle_write(2), "some knob")],
    )
    assert HINT not in run.err


def test_no_hint_when_preset_changes(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    run = run_watch(
        capsys,
        monkeypatch,
        tmp_path,
        ["--no-record", "--duration", "35"],
        cycles=[{}, {}, {"preset": {15: 9}}],
        stdin=[(cycle_write(2), "some knob")],
    )
    assert HINT not in run.err


def test_only_query_and_reads_sent(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    run = run_watch(capsys, monkeypatch, tmp_path, ["--no-record", "--duration", "2"])
    assert {f[2] for f in run.fake.sent} <= {0x11, 0x23}
    assert run.fake.closed


def test_long_labels_keep_the_value_column_aligned(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    run = run_watch(
        capsys,
        monkeypatch,
        tmp_path,
        ["--no-record", "--duration", "1"],
        cycles=[{}, {"preset": {6: 74, 7: 0x50, 15: 9}}],
    )
    assert run.code == 0, run.err
    lines = [line for line in run.out.splitlines() if "preset[" in line and "→" in line]
    assert len(lines) == 3
    arrows = {line.index("→") for line in lines}
    assert len(arrows) == 1, lines
    assert re.search(re.escape(BYTE_MAP_LABELS[6]) + r" +60 → 74", lines[0]), lines[0]


def test_duration_counts_from_the_first_poll_not_from_connecting(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    run = run_watch(
        capsys,
        monkeypatch,
        tmp_path,
        ["--json", "--no-record", "--duration", "2"],
        connect_seconds=5.0,
    )
    assert run.code == 0, run.err
    stop = run.events[-1]
    assert stop["reason"] == "duration"
    assert stop["t"] == pytest.approx(7.0, abs=0.01)  # t still counts from the tool's start
    assert stop["cycles"] >= 4
