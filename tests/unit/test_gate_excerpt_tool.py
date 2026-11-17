"""``tests/support/gate_excerpt.py`` turns a CLI ``--trace`` into a replayable excerpt (M2 prep).

The round trip runs the real write path against the fake pedal with the trace logger on, cuts
an excerpt from that text, and replays it with ``FakeTransport.from_capture``: the replay must
send the same frames and reach the same result. This proves the tool before the gate session.
"""

from __future__ import annotations

import io
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from openvave import TankG
from openvave.transport.fake import FakeTransport
from tests.support import gate_excerpt as ge
from tests.support.write_fixture import EDIT, NORMAL, make_fake, write_frame


@contextmanager
def captured_trace() -> Iterator[io.StringIO]:
    """What ``--trace`` would print on stderr, plus a non-trace line, as the CLI interleaves."""
    out = io.StringIO()
    logger = logging.getLogger("openvave.trace")
    handler = logging.StreamHandler(out)
    handler.setFormatter(logging.Formatter("%(message)s"))
    saved = logger.level, logger.propagate
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    out.write("warning: something unrelated on stderr\n")
    try:
        yield out
    finally:
        logger.removeHandler(handler)
        logger.setLevel(saved[0])
        logger.propagate = saved[1]


async def _no_sleep(_: float) -> None:
    return None


def test_labels() -> None:
    assert ge.label(bytes.fromhex("00 59 11 00 00 00 ff")) == "query name/version"
    assert ge.label(write_frame(0x10000004, bytes(14))) == "write knob_block t4 0x10000004 x14"
    assert ge.label(write_frame(0x10000002, b"\x01")) == "write block_switch 2 t4 0x10000002 x1"
    assert ge.label(write_frame(0x10000012, bytes(3))) == "write led_colour t4 0x10000012 x3"
    assert ge.label(write_frame(0xE0000006, b"\x01")) == ("write preset_select 2C t4 0xE0000006 x1")


def test_parse_call() -> None:
    assert ge.parse_call(["set", "gain", "90"])["value"] == 90
    assert ge.parse_call(["set", "mod_on", "true"])["value"] is True
    assert ge.parse_call(["set", "led_colour", "#ff0000"])["value"] == "#ff0000"
    assert ge.parse_call(["select", "6", "--discard-edits"]) == {
        "call": "select_preset",
        "index": 6,
        "discard_edits": True,
        "experimental": True,
    }
    with pytest.raises(ValueError):
        ge.parse_call(["erase"])


@pytest.mark.parametrize(
    ("args", "mode"),
    [
        (["set", "gain", "90"], EDIT),
        (["set", "mod_on", "true"], EDIT),
        (["set", "led_colour", "#ff0000"], EDIT),
        (["select", "6"], NORMAL),
    ],
)
async def test_round_trip(args: list[str], mode: int, tmp_path: Path) -> None:
    call = ge.parse_call(args)

    async def run(fake: FakeTransport) -> object:
        async with TankG.over(fake) as pedal:
            if call["call"] == "set_field":
                return await pedal.set_field(call["field"], call["value"], experimental=True)
            return await pedal.select_preset(call["index"], experimental=True, sleep=_no_sleep)

    live = make_fake(mode)
    with captured_trace() as text:
        before = await run(live)
    out = tmp_path / "20261117-gate-x.jsonl"
    ge.write(ge.build(text.getvalue(), "x", "2026-11-17", call), out)

    replay = FakeTransport.from_capture(out)
    after = await run(replay)
    assert replay.sent == live.sent
    assert after == before
