"""Synthetic stored image for spec 003 tests (research R10).

The real stored image read from the pedal on 2026-11-17 is most likely factory content and stays
in ``captures/private/`` (Constitution VI). Tests use this synthetic image instead:

- header ``a5 5a`` (what the pedal returned on 2026-11-17);
- preset 1 (1B) = the current preset of the public fw96 connect capture
  (``captures/fw96/20261116-probe-connect.jsonl``, which is stored preset 1B);
- every other preset ``i`` follows the deterministic pattern of :func:`synthetic_preset`, with
  every mapped byte inside its byte-map range.

Frames are built here without ``openvave`` code, so a fixture cannot hide a library bug.

Regenerate the committed capture with::

    uv run python -m tests.support.storage_fixture captures/fw96/20261117-storage-synthetic.jsonl
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from tests.support.captures import FW96_CONNECT, PRESET, QUERY, load_capture

HEADER = bytes.fromhex("a5 5a")
STORE_OFFSET = 2
PRESET_SIZE = 21
PRESET_COUNT = 36
IMAGE_SIZE = STORE_OFFSET + PRESET_SIZE * PRESET_COUNT
PUBLIC_INDEX = 1
"""Stored preset 1B: the only real preset in the image (already public in captures/fw96/)."""
CHUNK = 182
"""Notification payload size seen on hardware at ATT MTU 185."""
SYNTHETIC_CAPTURE = Path(__file__).resolve().parents[2] / (
    "captures/fw96/20261117-storage-synthetic.jsonl"
)

_CONNECT = load_capture(FW96_CONNECT)
QUERY_TX = _CONNECT.tx(QUERY)
QUERY_RX = _CONNECT.rx(QUERY)
PUBLIC_PRESET = _CONNECT.rx(PRESET)[14:-1]

HEADER_LABEL = "storage header t4 0x00000000 x2"
IMAGE_LABEL = "storage image t4 0x00000000 x758"


def position(index: int) -> str:
    return f"{index // 4 + 1}{'ABCD'[index % 4]}"


def preset_label(index: int) -> str:
    return f"stored preset {position(index)} t4 0x{STORE_OFFSET + PRESET_SIZE * index:08x} x21"


def synthetic_preset(index: int) -> bytes:
    """Pattern for preset ``index`` (not 1B).

    Offsets 0–3 (block switches): bit 0–3 of ``index`` (1 = on, 0 = off). Offset 4 (noise gate):
    ``3·i mod 128``. Offset 5 (amp type): ``i mod 9``. Offsets 6–16 (knobs):
    ``(7·i + 11·offset) mod 128``. Offset 17 (IR cab): ``(i + 3) mod 9``. Offsets 18–20 (unknown):
    ``i``, ``0x40 + i``, ``0x80 + i``.
    """
    data = [(index >> bit) & 1 for bit in range(4)]
    data += [(3 * index) % 128, index % 9]
    data += [(7 * index + 11 * offset) % 128 for offset in range(6, 17)]
    data += [(index + 3) % 9, index, 0x40 + index, 0x80 + index]
    assert len(data) == PRESET_SIZE
    return bytes(data)


def synthetic_presets() -> list[bytes]:
    return [
        PUBLIC_PRESET if i == PUBLIC_INDEX else synthetic_preset(i) for i in range(PRESET_COUNT)
    ]


def synthetic_image(header: bytes = HEADER) -> bytes:
    """758 bytes: ``header`` + the 36 synthetic presets."""
    return header + b"".join(synthetic_presets())


def _checksum(body: bytes) -> int:
    return (~sum(body)) & 0xFF


def frame(command: int, body: bytes) -> bytes:
    return (
        b"\x00\x59"
        + bytes([command])
        + len(body).to_bytes(3, "little")
        + body
        + bytes([_checksum(body)])
    )


def read_request(address: int, length: int) -> bytes:
    return frame(0x23, bytes([4]) + address.to_bytes(4, "little") + length.to_bytes(3, "little"))


def read_reply(address: int, data: bytes) -> bytes:
    echo = bytes([4]) + address.to_bytes(4, "little") + len(data).to_bytes(3, "little")
    return frame(0x23, echo + data)


def storage_replies(image: bytes) -> dict[str, tuple[bytes, bytes]]:
    """``label → (request, reply)`` for the header, the 36 presets and the whole image, in order."""
    if len(image) != IMAGE_SIZE:
        raise ValueError(f"image must be {IMAGE_SIZE} bytes")
    pairs = {HEADER_LABEL: (read_request(0, 2), read_reply(0, image[:2]))}
    for i in range(PRESET_COUNT):
        address = STORE_OFFSET + PRESET_SIZE * i
        pairs[preset_label(i)] = (
            read_request(address, PRESET_SIZE),
            read_reply(address, image[address : address + PRESET_SIZE]),
        )
    pairs[IMAGE_LABEL] = (read_request(0, IMAGE_SIZE), read_reply(0, image))
    return pairs


def capture_lines(image: bytes) -> list[dict[str, object]]:
    """The committed capture: meta, handshake, then every storage request/reply."""
    lines: list[dict[str, object]] = [
        {
            "event": "meta",
            "firmware": 96,
            "device": "TANK-Gv2",
            "platform": "synthetic",
            "att_mtu": 185,
            "date": "2026-11-17",
            "tool": "tests/support/storage_fixture.py",
            "sanitized": [],
            "note": "synthetic stored image (R10); preset 1B from 20261116-probe-connect",
        }
    ]
    t = 0.0
    pairs = {"query name/version": (QUERY_TX, QUERY_RX), **storage_replies(image)}
    for label, (tx, rx) in pairs.items():
        t += 0.05
        lines.append({"t": round(t, 4), "event": "tx", "label": label, "hex": tx.hex(" ")})
        for start in range(0, len(rx), CHUNK):
            t += 0.01
            chunk = rx[start : start + CHUNK]
            lines.append({"t": round(t, 4), "event": "rx-chunk", "hex": chunk.hex(" ")})
        lines.append(
            {"t": round(t, 4), "event": "rx", "label": label, "hex": rx.hex(" "), "cmd": rx[2]}
        )
    return lines


def write_capture(path: Path) -> None:
    text = "".join(json.dumps(line) + "\n" for line in capture_lines(synthetic_image()))
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":  # pragma: no cover - maintenance entry point
    if len(sys.argv) != 2:
        sys.exit("usage: python -m tests.support.storage_fixture OUT")
    write_capture(Path(sys.argv[1]))
