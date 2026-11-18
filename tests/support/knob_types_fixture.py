"""MOD FX and DLY MIX app readings (spec 004 T022, 2026-11-17, fw 96).

The owner set the M-VAVE phone app's MOD FX knob, then its DLY MIX knob, to section boundaries
on preset 1A in normal mode, closed the app each time, and read the edit buffer with
``openvave preset dump``. The app draws both knobs in three colours like reverb decay; the Tank-G
manual names the types (MOD FX: chorus, phaser, tremolo; DLY MIX: analog, tape, dual). The
committed capture rebuilds those reads as frames:

- byte 11 (MOD FX) or byte 13 (DLY MIX) is each reading exactly as printed;
- every other byte is preset 1B from ``captures/fw96/20261116-probe-connect.jsonl`` (the reads
  were on 1A; only the measured byte matters, and 1B is already public);
- each read is preceded by a ``label`` event naming the knob and app position.

DLY MIX ``blue 1`` was not read. Frames are built here without ``openvave`` code.

Regenerate the committed capture with::

    uv run python -m tests.support.knob_types_fixture captures/fw96/20261117-knob-types-app.jsonl
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from tests.support.captures import CAPTURES_DIR, FW96_CONNECT, PRESET, QUERY, load_capture
from tests.support.storage_fixture import read_reply, read_request

KNOB_TYPES_CAPTURE = CAPTURES_DIR / "fw96" / "20261117-knob-types-app.jsonl"
PRESET_ADDRESS = 0x10000000
OFFSETS = {"mod_fx": 11, "delay_mix": 13}

READINGS: dict[str, tuple[tuple[str, int], ...]] = {
    "mod_fx": (
        ("blue 40", 39),
        ("blue X", 41),
        ("orange 1", 44),
        ("orange 40", 83),
        ("orange X", 84),
        ("green 1", 88),
        ("green 40", 127),
        ("blue 1", 0),
    ),
    "delay_mix": (
        ("blue 40", 39),
        ("blue X", 41),
        ("orange 1", 44),
        ("orange 40", 83),
        ("orange X", 87),
        ("green 1", 88),
        ("green 40", 127),
    ),
}
"""Per field: (app position, raw byte), in the order the owner read them."""

_CONNECT = load_capture(FW96_CONNECT)
PUBLIC_1B = _CONNECT.rx(PRESET)[14:-1]


def preset_with(field: str, raw: int) -> bytes:
    data = bytearray(PUBLIC_1B)
    data[OFFSETS[field]] = raw
    return bytes(data)


def capture_lines() -> list[dict[str, object]]:
    lines: list[dict[str, object]] = [
        {
            "event": "meta",
            "firmware": 96,
            "device": "TANK-Gv2",
            "platform": "transcribed",
            "att_mtu": 185,
            "date": "2026-11-17",
            "tool": "tests/support/knob_types_fixture.py",
            "sanitized": [],
            "note": (
                "bytes 11 (MOD FX) and 13 (DLY MIX) transcribed from the owner's `openvave "
                "preset dump` reads after setting each app position on 1A; frames rebuilt, "
                "other bytes = 1B from 20261116-probe-connect"
            ),
        }
    ]
    t = 0.0

    def pair(label: str, tx: bytes, rx: bytes) -> None:
        nonlocal t
        t += 0.05
        lines.append({"t": round(t, 4), "event": "tx", "label": label, "hex": tx.hex(" ")})
        t += 0.01
        lines.append({"t": round(t, 4), "event": "rx-chunk", "hex": rx.hex(" ")})
        lines.append(
            {"t": round(t, 4), "event": "rx", "label": label, "hex": rx.hex(" "), "cmd": rx[2]}
        )

    pair(QUERY, _CONNECT.tx(QUERY), _CONNECT.rx(QUERY))
    for field, readings in READINGS.items():
        for app, raw in readings:
            t += 1.0
            lines.append({"t": round(t, 4), "event": "label", "text": f"app {field} {app}"})
            pair(
                PRESET,
                read_request(PRESET_ADDRESS, len(PUBLIC_1B)),
                read_reply(PRESET_ADDRESS, preset_with(field, raw)),
            )
    return lines


def write_capture(path: Path) -> None:
    text = "".join(json.dumps(line) + "\n" for line in capture_lines())
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":  # pragma: no cover - maintenance entry point
    if len(sys.argv) != 2:
        sys.exit("usage: python -m tests.support.knob_types_fixture OUT")
    write_capture(Path(sys.argv[1]))
