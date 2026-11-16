"""``openvave watch --record``: capture-format JSONL, flushed per event, replayable (T021)."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from openvave import __version__
from openvave.cli import main
from openvave.models import DeviceInfo, Region, WatchChange, WatchStart
from openvave.session import TankG
from openvave.transport import Transport
from openvave.transport.fake import FakeTransport
from tests.support.captures import load_capture
from tests.support.watch import (
    Cycle,
    FakeClock,
    GatedFake,
    ScriptedStdin,
    SleepRecorder,
    cycle_write,
    watch_script,
)

PEDAL = DeviceInfo("3F1A-UUID", "TANK-Gv2_BLE", -58)
RECORD = "captures/private/session.jsonl"
SWEEP: list[Cycle] = [{}, {}, {"preset": {15: 64}}, {"preset": {15: 127}}]
LABEL = "reverb decay min→max"
STDIN = [(cycle_write(2), LABEL), (cycle_write(5), "q")]


def run_record(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    cycles: Sequence[Cycle] = SWEEP,
    stdin: Sequence[tuple[int, str]] = STDIN,
    hooks: Mapping[int, Callable[[], None]] | None = None,
    argv: Sequence[str] = (),
    **options: Any,
) -> tuple[int, list[dict[str, Any]]]:
    monkeypatch.chdir(tmp_path)
    scripted = ScriptedStdin(stdin)
    fake = GatedFake(watch_script(cycles), scripted, hooks=hooks, **options)

    async def factory(
        device_id: str | None, scan_timeout: float
    ) -> tuple[Transport, DeviceInfo | None]:
        return fake, PEDAL

    code = main(
        ["watch", "--record", RECORD, *argv],
        transport_factory=factory,
        stdin=scripted,
        clock=FakeClock(),
    )
    lines = (tmp_path / RECORD).read_text(encoding="utf-8").splitlines()
    return code, [json.loads(line) for line in lines]


def test_record_lines(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, records = run_record(monkeypatch, tmp_path)
    assert code == 0, capsys.readouterr().err
    meta = records[0]
    assert meta["event"] == "meta"
    assert meta["tool"] == f"openvave watch {__version__}"
    assert meta["tool"].startswith("openvave watch")
    assert meta["firmware"] == 96
    assert meta["device"] == "TANK-Gv2"
    assert meta["interval"] == 0.5
    assert meta["sanitized"] == []
    assert {"platform", "att_mtu", "date"} <= set(meta)
    events = [r["event"] for r in records]
    assert events[1:4] == ["tx", "rx-chunk", "rx"]
    assert records[1]["label"] == records[3]["label"] == "query"
    assert events.count("meta") == 1
    assert events[-1] == "stop"
    assert records[-1]["reason"] == "quit"
    assert records[-1]["error"] is None
    tx_labels = [r["label"] for r in records if r["event"] == "tx"]
    assert tx_labels[0] == "query"
    assert tx_labels[1:7] == ["global", "preset", "status"] * 2
    assert set(tx_labels[1:]) == {"global", "preset", "status"}
    for record in records[1:]:
        assert isinstance(record["t"], (int, float)) and record["t"] >= 0
        if record["event"] in ("tx", "rx-chunk", "rx"):
            bytes.fromhex(record["hex"])
    rx = [r for r in records if r["event"] == "rx"]
    assert all(r["cmd"] in (0x11, 0x23) for r in rx)
    labels = [r for r in records if r["event"] == "label"]
    assert [r["text"] for r in labels] == [LABEL]
    changes = [r for r in records if r["event"] == "change"]
    assert [
        (c["cycle"], c["region"], c["offset"], c["old"], c["new"], c["label"]) for c in changes
    ] == [(3, "preset", 15, 5, 64, LABEL), (4, "preset", 15, 64, 127, LABEL)]
    times = [r["t"] for r in records[1:]]
    assert times == sorted(times)


def test_changes_before_any_label_have_null_label(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    code, records = run_record(monkeypatch, tmp_path, stdin=[], argv=["--duration", "2"])
    assert code == 0
    changes = [r for r in records if r["event"] == "change"]
    assert changes and all(c["label"] is None for c in changes)
    assert records[-1]["reason"] == "duration"


def test_record_is_flushed_while_running(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    seen: list[list[str]] = []

    def read_record() -> None:
        text = (tmp_path / RECORD).read_text(encoding="utf-8")
        seen.append([json.loads(line)["event"] for line in text.splitlines()])

    # cycle 3 shows the first change; read the file during cycle 4's first request
    code, _ = run_record(monkeypatch, tmp_path, hooks={cycle_write(4): read_record})
    assert code == 0
    assert len(seen) == 1
    assert seen[0][0] == "meta"
    assert "label" in seen[0]
    assert "change" in seen[0]
    assert "stop" not in seen[0]


def test_record_ends_with_stop_on_connection_lost(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    code, records = run_record(monkeypatch, tmp_path, stdin=[], disconnect_after=1 + 3 * 3)
    assert code == 6
    assert [r["event"] for r in records].count("change") == 1
    assert records[-1]["event"] == "stop"
    assert records[-1]["reason"] == "connection_lost"
    assert records[-1]["error"]


def test_excerpt_replays_to_the_same_change(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    code, records = run_record(monkeypatch, tmp_path)
    assert code == 0
    # meta + handshake + cycles 2 and 3 (the cycle before the step and the one showing it)
    status_rx = [i for i, r in enumerate(records) if r["event"] == "rx" and r["label"] == "status"]
    global_tx = [i for i, r in enumerate(records) if r["event"] == "tx" and r["label"] == "global"]
    query_end = next(i for i, r in enumerate(records) if r["event"] == "rx")
    excerpt = records[: query_end + 1] + records[global_tx[1] : status_rx[2] + 1]
    path = tmp_path / "excerpt.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in excerpt), encoding="utf-8")

    cap = load_capture(path)  # the test loader accepts it too
    assert len(cap.rx_all("preset")) == 2

    async def replay() -> list[WatchStart | WatchChange]:
        fake = FakeTransport.from_capture(path)
        async with TankG.over(fake) as pedal:
            return [e async for e in pedal.watch(sleep=SleepRecorder(), cycles=2)]

    events = asyncio.run(replay())
    change = events[-1]
    assert isinstance(change, WatchChange)
    recorded = next(r for r in records if r["event"] == "change")
    assert [(c.region, c.offset, c.old, c.new) for c in change.changes] == [
        (Region.CURRENT_PRESET, recorded["offset"], recorded["old"], recorded["new"])
    ]
