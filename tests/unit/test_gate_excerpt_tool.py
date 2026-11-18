"""``tests/support/gate_excerpt.py`` turns a CLI ``--trace`` into a replayable excerpt (M2 prep).

The round trip runs the real write path against the fake pedal with the trace logger on, cuts
an excerpt from that text, and replays it with ``FakeTransport.from_capture``: the replay must
send the same frames and reach the same result. This proves the tool before the gate session.

Spec 004 M3 (T069): the same round trip for every session-A step, on a fake whose stored presets
stand in for the owner's (neither public nor synthetic): the excerpt must pass the gate replay of
``tests/integration/test_gate_replay.py`` and hold none of those bytes (FR-037).
"""

from __future__ import annotations

import io
import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from openvave import TankG
from openvave.transport.fake import FakeTransport
from tests.integration import test_gate_replay as replay
from tests.integration.gate_fixtures import STEPS_BY_NAME
from tests.support import gate_excerpt as ge
from tests.support import restore_fixture as rf
from tests.support import storage_fixture as sf
from tests.support.write_fixture import ACK, EDIT, NORMAL, make_fake, write_frame


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


# -- spec 004 M3 (T069): sequences, sanitising, refusal -----------------------------------------

P = sf.PUBLIC_PRESET
GAIN_90 = P[:6] + bytes([90]) + P[7:]
"""1B with gain 90: public (spec 004 check 4 selected it as 1C)."""


def private_preset(index: int) -> bytes:
    """A stand-in for the owner's stored preset ``index``: neither public nor synthetic."""
    return bytes((index * 13 + k * 7 + 5) % 127 for k in range(21))


PRIVATE_IMAGE = rf.image_with(sf.HEADER + b"".join(private_preset(i) for i in range(36)), s1=P)
"""The pedal of the rehearsal: 1B is the public preset (loaded), every other slot private."""
BYPASSED = bytes([0, 0, 0xFF, NORMAL])


def _fake(step: str) -> FakeTransport:
    if step == "bypass_off":
        return make_fake(NORMAL, buffer=bytes(21), glob=BYPASSED)
    if step == "loopback_off":
        return make_fake(NORMAL, status=b"\x01")
    if step == "save":
        return make_fake(NORMAL, buffer=GAIN_90, image=PRIVATE_IMAGE)
    if step in ("restore_slot", "restore_all"):
        return make_fake(NORMAL, image=rf.image_with(PRIVATE_IMAGE, s2=GAIN_90))
    return make_fake(NORMAL, image=PRIVATE_IMAGE)


CASES_004 = [
    ("bypass", ["bypass_on"]),
    ("bypass_off", ["bypass_off", "1B"]),
    ("normal_switch_mod", ["set", "mod_on", "on"]),
    ("normal_led_colour", ["set", "led_colour", "#ff0000"]),
    ("loopback_off", ["loopback", "off"]),
    ("save", ["save", "1C"]),
    ("restore_slot", ["restore_slot", "1C"]),
    ("image_noop", ["image_noop"]),
    ("restore_all", ["restore_all"]),
]


def _case(step: str, args: list[str]) -> object:
    marks = [pytest.mark.persistent_writes] if STEPS_BY_NAME[step].persistent else []
    return pytest.param(step, args, id=step, marks=marks)


@pytest.mark.parametrize(("step", "args"), [_case(*c) for c in CASES_004])
async def test_round_trip_004(step: str, args: list[str], tmp_path: Path) -> None:
    """Live run on the fake → trace → excerpt → the gate replay passes, no private byte left."""
    gate = STEPS_BY_NAME[step]
    call = ge.parse_call(args)
    live = _fake(step)
    with captured_trace() as text:
        async with TankG.over(live) as pedal:
            await replay._run_004(pedal, call, rf.backup(PRIVATE_IMAGE))
    out = tmp_path / f"20261118-gate-{step}.jsonl"
    ge.write(ge.build(text.getvalue(), step, "2026-11-18", call), out)

    await replay.replay_004(gate, out)
    written = out.read_text("utf-8")
    for i in range(36):
        assert private_preset(i).hex(" ") not in written, f"slot {i} leaked"
    lines = [json.loads(line) for line in written.splitlines()]
    assert ge.leaks(lines, ge.public_presets()) == []
    assert bool(lines[0]["sanitized"]) == gate.persistent  # the backup reads all 36 slots


def test_parse_call_004() -> None:
    assert ge.parse_call(["bypass_on"]) == {
        "call": "bypass_on",
        "discard_edits": False,
        "experimental": True,
    }
    assert ge.parse_call(["bypass_off", "1B"])["index"] == 1
    assert ge.parse_call(["loopback", "off"])["on"] is False
    assert ge.parse_call(["save"])["to"] is None
    assert ge.parse_call(["save", "1C"]) == {
        "call": "save_preset",
        "to": 2,
        "experimental": True,
        "unsafe": True,
    }
    assert ge.parse_call(["restore_slot", "2"])["slot"] == 2
    assert ge.parse_call(["restore_all", "--discard-edits"])["discard_edits"] is True
    assert ge.parse_call(["image_noop"])["call"] == "image_noop"
    for bad in (["bypass_off"], ["loopback", "maybe"], ["save", "10A"], ["restore_all", "-x"]):
        with pytest.raises(ValueError):
            ge.parse_call(bad)


def test_labels_004() -> None:
    assert ge.label(write_frame(0xE1000001, b"\x01")) == "write bypass 1B t4 0xE1000001 x1"
    assert ge.label(write_frame(0xD0000000, b"\x00")) == "write loopback t4 0xD0000000 x1"
    assert ge.label(write_frame(0xF0000000, b"")) == "write commit t4 0xF0000000 x0"
    assert ge.label(write_frame(0x2C, P)) == "write stored_slot 1C t4 0x0000002C x21"
    assert ge.label(write_frame(0, sf.synthetic_image())) == (
        "write stored_image t4 0x00000000 x758"
    )
    assert ge.label(sf.read_request(0xD0000000, 1)) == "status t4 0xD0000000 x1"
    assert ge.label(sf.read_request(0, 758)) == "storage image t4 0x00000000 x758"


def _reply(address: int, data: bytes) -> bytes:
    return sf.frame(
        0x23, bytes([4]) + address.to_bytes(4, "little") + len(data).to_bytes(3, "little") + data
    )


def test_image_read_and_write_are_replaced_and_rechunked() -> None:
    """A whole-image reply in 5 notifications and an image write: same map, valid frames."""
    reply = _reply(0, PRIVATE_IMAGE)
    chunks = [reply[i : i + 182] for i in range(0, len(reply), 182)]
    frames = [
        ("tx", sf.read_request(0, 758)),
        *(("rx-chunk", c) for c in chunks),
        ("rx", reply),
        ("tx", write_frame(0, PRIVATE_IMAGE)),
        ("rx", ACK),
    ]
    out, mapping = ge.sanitise(frames, ge.public_presets())
    new_reply, new_write = out[len(chunks) + 1][1], out[-2][1]
    assert [len(f) for k, f in out if k == "rx-chunk"] == [len(c) for c in chunks]
    assert b"".join(f for k, f in out if k == "rx-chunk") == new_reply
    assert new_reply == _reply(0, new_reply[14:-1])  # checksum recomputed
    assert new_write == write_frame(0, new_reply[14:-1])  # same map for read and write
    image = new_reply[14:-1]
    assert image[:2] == sf.HEADER and image[2 + 21 : 2 + 42] == P  # public 1B kept
    assert image[2 + 42 : 2 + 63] == sf.synthetic_preset(2)
    assert len(mapping.replaced) == 35


def test_build_refuses_non_public_preset_left() -> None:
    """A field write after a replaced edit buffer cannot be sanitised: the tool refuses."""
    trace = "\n".join(
        [
            f"TX {sf.QUERY_TX.hex(' ')}",
            f"RX {sf.QUERY_RX.hex(' ')}",
            f"TX {sf.read_request(0x10000000, 21).hex(' ')}",
            f"RX {_reply(0x10000000, private_preset(5)).hex(' ')}",
            f"TX {write_frame(0x10000004, private_preset(5)[4:18]).hex(' ')}",
            f"RX {ACK.hex(' ')}",
        ]
    )
    with pytest.raises(ValueError, match="field write without a public edit buffer"):
        ge.build(trace, "x", "2026-11-18", ge.parse_call(["set", "gain", "90"]))


def test_leaks_reports_private_data() -> None:
    lines = ge.records([("tx", write_frame(0x2C, private_preset(2))), ("rx", ACK)])
    assert ge.leaks(lines, ge.public_presets()) == ["tx write stored_slot 1C t4 0x0000002C x21"]
    assert ge.leaks(lines, ge.public_presets() | {private_preset(2)}) == []


def test_hook_log_input() -> None:
    """The JSONL frame log of the persistent hardware helper parses like a trace."""
    log = "\n".join(
        json.dumps({"t": 0.1, "event": e, "hex": f.hex(" ")})
        for e, f in (("tx", sf.QUERY_TX), ("rx-chunk", sf.QUERY_RX), ("rx", sf.QUERY_RX))
    )
    assert ge.parse_trace(log) == [
        ("tx", sf.QUERY_TX),
        ("rx-chunk", sf.QUERY_RX),
        ("rx", sf.QUERY_RX),
    ]
