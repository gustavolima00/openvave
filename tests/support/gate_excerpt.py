"""Turn the ``--trace`` output of one gate write into a committed excerpt (spec 003 M2/M3).

The CLI's ``--trace`` writes ``TX <hex>``, ``RX chunk <hex>`` and ``RX <hex>`` lines to stderr
(``openvave.trace``). For a gate step the owner keeps that stderr in ``captures/private/``; this
tool turns it into ``captures/fw96/<date>-gate-<step>.jsonl``: a ``meta`` line (firmware, date,
step, the library call to replay) and labelled ``tx``/``rx-chunk``/``rx`` lines that replay with
``FakeTransport.from_capture``. Labels are derived from the frames only (command, type, address,
length), never from ``openvave`` code, so a decoding bug cannot hide in the fixture. Frames are
copied unchanged; every other stderr line (warnings, the CLI's own messages) is dropped.

Usage (raw traces stay in ``captures/private/``, git-ignored)::

    uv run python -m tests.support.gate_excerpt TRACE STEP DATE OUT \\
        set FIELD VALUE                      # e.g. set gain 90 / set mod_on true
    uv run python -m tests.support.gate_excerpt TRACE STEP DATE OUT \\
        select INDEX [--discard-edits]

The replayed call always passes ``experimental=True`` (gate session A sends ``hypothesis`` rows).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

QUERY, READ, WRITE, REPLY = 0x11, 0x23, 0x22, 0x00
GLOBAL, EDIT_BUFFER, DEVICE, SELECT_BASE = 0x20000000, 0x10000000, 0xD0000000, 0xE0000000
STORE_END = 0x2F6
"""Stored image: header at 0 (2 bytes), 36 presets of 21 bytes from offset 2."""
PRESET_SIZE = 21
TOOL = "tests/support/gate_excerpt.py"


def position(index: int) -> str:
    bank, slot = divmod(index, 4)
    return f"{bank + 1}{'ABCD'[slot]}"


def _shape(frame: bytes) -> tuple[int, int, int]:
    body = frame[6:-1]
    return body[0], int.from_bytes(body[1:5], "little"), int.from_bytes(body[5:8], "little")


def label(frame: bytes) -> str:
    """A label for a request frame, from its bytes alone."""
    command = frame[2]
    if command == QUERY:
        return "query name/version"
    if command not in (READ, WRITE) or len(frame) < 15:
        return f"cmd 0x{command:02x} {frame.hex(' ')}"
    kind, address, length = _shape(frame)
    where = f"t{kind} 0x{address:08X} x{length}"
    if command == WRITE:
        if address >= SELECT_BASE:
            return f"write preset_select {position(address - SELECT_BASE)} {where}"
        if address == EDIT_BUFFER + 4:
            return f"write knob_block {where}"
        if address == EDIT_BUFFER + 18:
            return f"write led_colour {where}"
        if EDIT_BUFFER <= address < EDIT_BUFFER + 4:
            return f"write block_switch {address - EDIT_BUFFER} {where}"
        return f"write {where}"
    if address == GLOBAL:
        return f"global {where}"
    if address == EDIT_BUFFER:
        return f"preset {where}"
    if address == DEVICE:
        return f"device {where}"
    if address == 0 and length == 2:
        return f"storage header {where}"
    if address < STORE_END and length == PRESET_SIZE and (address - 2) % PRESET_SIZE == 0:
        return f"stored preset {position((address - 2) // PRESET_SIZE)} {where}"
    return f"read {where}"


def parse_trace(text: str) -> list[tuple[str, bytes]]:
    """``(kind, frame)`` for every ``TX``/``RX chunk``/``RX`` line, in order."""
    out: list[tuple[str, bytes]] = []
    for line in text.splitlines():
        line = line.strip()
        for prefix, kind in (("RX chunk ", "rx-chunk"), ("RX stray ", "rx-stray"), ("TX ", "tx")):
            if line.startswith(prefix):
                out.append((kind, bytes.fromhex(line[len(prefix) :])))
                break
        else:
            if line.startswith("RX "):
                out.append(("rx", bytes.fromhex(line[3:])))
    return out


def records(frames: list[tuple[str, bytes]]) -> list[dict[str, Any]]:
    """Labelled JSONL records. A reply belongs to the request before it (the session is serial)."""
    out: list[dict[str, Any]] = []
    pending: str | None = None
    for kind, frame in frames:
        if kind == "tx":
            pending = label(frame)
            out.append({"event": "tx", "label": pending, "hex": frame.hex(" ")})
        elif kind == "rx-chunk":
            out.append({"event": "rx-chunk", "hex": frame.hex(" ")})
        elif kind == "rx":
            if pending is None:
                raise ValueError(f"reply before any request: {frame.hex(' ')}")
            out.append({"event": "rx", "label": pending, "hex": frame.hex(" "), "cmd": frame[2]})
            pending = None
        else:  # rx-stray: kept as a note, never replayed
            out.append({"event": "rx-stray", "hex": frame.hex(" ")})
    return out


def parse_call(args: list[str]) -> dict[str, Any]:
    """The call to replay: ``set FIELD VALUE`` or ``select INDEX [--discard-edits]``."""
    if len(args) == 3 and args[0] == "set":
        value: Any = args[2]
        if value.lower() in ("true", "false", "on", "off"):
            value = value.lower() in ("true", "on")
        elif value.lstrip("-").isdigit():
            value = int(value)
        return {"call": "set_field", "field": args[1], "value": value, "experimental": True}
    if args and args[0] == "select" and len(args) in (2, 3):
        discard = args[2:] == ["--discard-edits"]
        if len(args) == 3 and not discard:
            raise ValueError(f"unknown option {args[2]!r}")
        return {
            "call": "select_preset",
            "index": int(args[1]),
            "discard_edits": discard,
            "experimental": True,
        }
    raise ValueError("expected `set FIELD VALUE` or `select INDEX [--discard-edits]`")


def build(text: str, step: str, date: str, call: dict[str, Any]) -> list[dict[str, Any]]:
    body = records(parse_trace(text))
    query = next((r for r in body if r["event"] == "rx" and r["cmd"] == QUERY), None)
    if query is None:
        raise ValueError("no handshake reply in the trace")
    name = bytes.fromhex(query["hex"])[6:-1].split(b"\x00", 1)[0].decode("ascii")
    model, _, fw = name.rpartition("_")
    meta = {
        "event": "meta",
        "firmware": int(fw),
        "device": model,
        "date": date,
        "step": step,
        "tool": TOOL,
        "sanitized": [],
        "replay": call,
    }
    return [meta, *body]


def write(lines: list[dict[str, Any]], out: Path) -> None:
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in lines), "utf-8")


def main(argv: list[str]) -> int:
    if len(argv) < 5:
        print(__doc__, file=sys.stderr)
        return 2
    trace, step, date, out = Path(argv[0]), argv[1], argv[2], Path(argv[3])
    lines = build(trace.read_text(encoding="utf-8"), step, date, parse_call(argv[4:]))
    write(lines, out)
    writes = [r for r in lines if r.get("event") == "tx" and r["label"].startswith("write")]
    print(f"{out}: {len(lines)} lines, {len(writes)} write frame(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
