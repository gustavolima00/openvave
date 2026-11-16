"""Hex trace on logger ``openvave.trace`` (T023, FR-018)."""

from __future__ import annotations

import logging

import pytest

from openvave import trace
from tests.support.captures import FW96_CONNECT, GLOBAL, load_capture

CAP = load_capture(FW96_CONNECT)


def test_line_format(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, logger="openvave.trace")
    trace.trace_tx(CAP.tx(GLOBAL))
    trace.trace_rx_chunk(CAP.rx(GLOBAL)[:5])
    trace.trace_rx(CAP.rx(GLOBAL))
    records = [r for r in caplog.records if r.name == "openvave.trace"]
    assert all(r.levelno == logging.DEBUG for r in records)
    assert [r.getMessage() for r in records] == [
        "TX 00 59 23 08 00 00 04 00 00 00 20 04 00 00 d7",
        "RX chunk 00 59 23 0c 00",
        "RX 00 59 23 0c 00 00 04 00 00 00 20 04 00 00 00 00 01 01 d5",
    ]


def test_silent_without_handler(capsys: pytest.CaptureFixture[str]) -> None:
    trace.trace_tx(CAP.tx(GLOBAL))
    trace.trace_rx(CAP.rx(GLOBAL))
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


def test_trace_hook_sees_every_frame_and_is_removed() -> None:
    seen: list[tuple[str, bytes]] = []
    with trace.trace_hook(lambda kind, data: seen.append((kind, data))):
        trace.trace_tx(CAP.tx(GLOBAL))
        trace.trace_rx_chunk(CAP.rx(GLOBAL)[:5])
        trace.trace_rx(CAP.rx(GLOBAL))
        trace.trace_rx_stray(b"\x01")
    trace.trace_tx(CAP.tx(GLOBAL))
    assert seen == [
        ("tx", CAP.tx(GLOBAL)),
        ("rx-chunk", CAP.rx(GLOBAL)[:5]),
        ("rx", CAP.rx(GLOBAL)),
        ("rx-stray", b"\x01"),
    ]
