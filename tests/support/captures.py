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
    """label → notification chunks that made up the (first) reply."""
    all_rx: dict[str, list[bytes]] = field(default_factory=dict)
    """label → every reply frame with that label, in capture order (watch records repeat)."""
    records: list[dict[str, Any]] = field(default_factory=list)
    """Every line of the file, parsed, in order (including ``label``/``change``/``stop``)."""

    @property
    def ordered_tx(self) -> list[bytes]:
        return [tx for tx, _ in self.pairs.values()]

    def tx(self, label: str) -> bytes:
        return self.pairs[label][0]

    def rx(self, label: str) -> bytes:
        """The first reply with this label."""
        return self.pairs[label][1]

    def rx_all(self, label: str) -> list[bytes]:
        """Every reply with this label, in order."""
        return list(self.all_rx[label])


WATCH_EVENTS = frozenset({"label", "change", "stop"})
"""Session-record events (specs/002-preset-byte-map/contracts/session-record.md)."""


def load_capture(path: Path | str) -> Capture:
    """Parse a capture; ``pairs``/``tx()``/``rx()`` keep the first occurrence of each label."""
    meta: dict[str, Any] = {}
    records: list[dict[str, Any]] = []
    all_rx: dict[str, list[bytes]] = {}
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
            records.append(record)
            event = record["event"]
            if event == "meta":
                meta = record
            elif event == "tx":
                current = normalise_label(record["label"])
                tx_by_label.setdefault(current, parse_hex(record["hex"]))
                pending = []
            elif event == "rx-chunk":
                pending.append(parse_hex(record["hex"]))
            elif event == "rx":
                label = normalise_label(record["label"])
                if label != current:
                    raise ValueError(f"{path}: rx {label!r} does not follow its tx")
                frame = parse_hex(record["hex"])
                all_rx.setdefault(label, []).append(frame)
                if label not in pairs:
                    pairs[label] = (tx_by_label[label], frame)
                    chunks[label] = pending
                pending = []
            elif event in WATCH_EVENTS:
                continue
            else:
                raise ValueError(f"{path}: unknown event {event!r}")
    if not meta:
        raise ValueError(f"{path}: missing meta record")
    return Capture(meta=meta, pairs=pairs, rx_chunks=chunks, all_rx=all_rx, records=records)
