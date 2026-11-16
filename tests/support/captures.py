"""Load committed captures (``captures/**/*.jsonl``) as test fixtures.

This is the only way tests obtain real frames (FR-022). It deliberately does not use
``openvave`` code, so fixture loading cannot hide a bug in the library.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
CAPTURES_DIR = REPO_ROOT / "captures"
FW96_CONNECT = CAPTURES_DIR / "fw96" / "20261116-probe-connect.jsonl"

# Labels of the fw96 connect capture, in capture order (whitespace-normalised).
QUERY = "query name/version"
DEVICE_INFO = "device info t5 0xD0000000 x32"
GLOBAL = "global t4 0x20000000 x4"
PRESET = "preset t4 0x10000000 x21"
STATUS = "status t4 0xD0000000 x1"
LABELS = (QUERY, DEVICE_INFO, GLOBAL, PRESET, STATUS)


def normalise_label(label: str) -> str:
    """Collapse runs of whitespace (the POC padded labels for column alignment)."""
    return " ".join(label.split())


def parse_hex(text: str) -> bytes:
    return bytes.fromhex(text)


@dataclass
class Capture:
    meta: dict[str, Any]
    pairs: dict[str, tuple[bytes, bytes]]
    """label → (request frame, reply frame), in capture order."""
    rx_chunks: dict[str, list[bytes]] = field(default_factory=dict)
    """label → notification chunks that made up the reply."""

    @property
    def ordered_tx(self) -> list[bytes]:
        return [tx for tx, _ in self.pairs.values()]

    def tx(self, label: str) -> bytes:
        return self.pairs[label][0]

    def rx(self, label: str) -> bytes:
        return self.pairs[label][1]


def load_capture(path: Path | str) -> Capture:
    meta: dict[str, Any] = {}
    tx_by_label: dict[str, bytes] = {}
    pairs: dict[str, tuple[bytes, bytes]] = {}
    chunks: dict[str, list[bytes]] = {}
    pending: list[bytes] = []
    current: str | None = None
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            record = json.loads(line)
            event = record["event"]
            if event == "meta":
                meta = record
            elif event == "tx":
                current = normalise_label(record["label"])
                tx_by_label[current] = parse_hex(record["hex"])
                pending = []
            elif event == "rx-chunk":
                pending.append(parse_hex(record["hex"]))
            elif event == "rx":
                label = normalise_label(record["label"])
                if label != current:
                    raise ValueError(f"{path}: rx {label!r} does not follow its tx")
                pairs[label] = (tx_by_label[label], parse_hex(record["hex"]))
                chunks[label] = pending
                pending = []
            else:
                raise ValueError(f"{path}: unknown event {event!r}")
    if not meta:
        raise ValueError(f"{path}: missing meta record")
    return Capture(meta=meta, pairs=pairs, rx_chunks=chunks)
