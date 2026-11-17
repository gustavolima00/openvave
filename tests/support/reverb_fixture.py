"""Reverb decay sections: the owner's app readings of preset byte 15 (2026-11-17, fw 96).

On 2026-11-17 the owner set the M-VAVE phone app's Decay knob to section boundaries on preset 1B
in edit mode, closed the app, and read the edit buffer with ``openvave preset dump --json`` (no
session record was written). The committed capture rebuilds those reads as frames:

- byte 15 is each reading exactly as printed;
- every other byte is preset 1B from ``captures/fw96/20261116-probe-connect.jsonl``. The first two
  dumps printed the whole buffer, which matched 1B except byte 15; later dumps printed byte 15
  only, so the other bytes there are assumed unchanged;
- each read is preceded by a ``label`` event naming the app position.

Frames are built here without ``openvave`` code, so the fixture cannot hide a library bug.

Regenerate the committed capture with::

    uv run python -m tests.support.reverb_fixture captures/fw96/20261117-reverb-sections-app.jsonl
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from tests.support.captures import CAPTURES_DIR, FW96_CONNECT, PRESET, QUERY, load_capture
from tests.support.storage_fixture import read_reply, read_request

REVERB_CAPTURE = CAPTURES_DIR / "fw96" / "20261117-reverb-sections-app.jsonl"
PRESET_ADDRESS = 0x10000000
DECAY_OFFSET = 15

READINGS: tuple[tuple[str, int], ...] = (
    ("blue 1", 0),
    ("blue 40", 39),
    ("blue X", 43),
    ("orange 1", 44),
    ("orange 40", 83),
    ("orange X", 86),
    ("green 1", 88),
    ("green 40", 127),
)
"""(app Decay position, raw preset byte 15), in the order the owner read them."""

_CONNECT = load_capture(FW96_CONNECT)
PUBLIC_1B = _CONNECT.rx(PRESET)[14:-1]


def preset_with_decay(raw: int) -> bytes:
    data = bytearray(PUBLIC_1B)
    data[DECAY_OFFSET] = raw
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
            "tool": "tests/support/reverb_fixture.py",
            "sanitized": [],
            "note": (
                "byte 15 transcribed from the owner's `openvave preset dump` reads of the 1B "
                "edit buffer after setting each app Decay position; frames rebuilt, other bytes "
                "= 1B from 20261116-probe-connect"
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
    for app, raw in READINGS:
        t += 1.0
        lines.append({"t": round(t, 4), "event": "label", "text": f"app decay {app}"})
        pair(
            PRESET,
            read_request(PRESET_ADDRESS, len(PUBLIC_1B)),
            read_reply(PRESET_ADDRESS, preset_with_decay(raw)),
        )
    return lines


def write_capture(path: Path) -> None:
    text = "".join(json.dumps(line) + "\n" for line in capture_lines())
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":  # pragma: no cover - maintenance entry point
    if len(sys.argv) != 2:
        sys.exit("usage: python -m tests.support.reverb_fixture OUT")
    write_capture(Path(sys.argv[1]))
