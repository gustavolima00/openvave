"""Parse the "Write messages" table in ``specs/protocol/command-layer.md`` (research R4).

Independent of ``openvave``: rows come back as plain tuples so the doc↔code test compares two
separately produced descriptions of the write surface.

Cell grammar:

- Target: backticked ``kind`` or ``kind(k)`` (k an integer) or ``kind(i)`` (any index → argument
  ``None``)
- Type, Len: decimal or ``—``
- Address: backticked ``0x########`` or ``0x######## + i``, or ``—``
- Confidence: ``confirmed`` | ``observed`` | ``hypothesis``
- Firmware: decimals separated by commas
- Evidence: ``—`` or backticked paths separated by commas
- Data, Reply, Notes: free text
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from tests.support.bytemap_doc import COMMAND_LAYER

HEADING = "### Write messages"
COLUMNS = (
    "Target",
    "Type",
    "Address",
    "Len",
    "Data",
    "Reply",
    "Confidence",
    "Firmware",
    "Evidence",
    "Notes",
)
NONE = "—"
TARGET_RE = re.compile(r"^`([a-z_]+)(?:\((\d+|i)\))?`$")
ADDRESS_RE = re.compile(r"^`0x([0-9a-fA-F]{8})(?: \+ i)?`$")
BACKTICKED = re.compile(r"`([^`]+)`")
CONFIDENCES = ("confirmed", "observed", "hypothesis")


@dataclass(frozen=True)
class WriteRow:
    kind: str
    argument: int | None
    type: int | None
    address: int | None
    length: int | None
    confidence: str
    firmware: frozenset[int]
    evidence: tuple[str, ...]
    notes: str

    def key(self) -> tuple[object, ...]:
        """Everything the code table must agree on (data, reply and notes are free text)."""
        return (
            self.kind,
            self.argument,
            self.type,
            self.address,
            self.length,
            self.confidence,
            self.firmware,
            self.evidence,
        )


def _split_row(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _int(cell: str) -> int | None:
    return None if cell == NONE else int(cell)


def table_lines(text: str) -> list[str]:
    lines = text.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.startswith(HEADING))
    except StopIteration:
        raise ValueError(f"heading {HEADING!r} not found") from None
    rows: list[str] = []
    for line in lines[start + 1 :]:
        if line.startswith("#"):
            break
        if line.startswith("|"):
            rows.append(line)
        elif rows:
            break
    if not rows:
        raise ValueError("write messages table not found under its heading")
    return rows


def parse_row(cells: list[str]) -> WriteRow:
    if len(cells) != len(COLUMNS):
        raise ValueError(f"expected {len(COLUMNS)} cells, got {len(cells)}: {cells}")
    c = dict(zip(COLUMNS, cells, strict=True))
    target = TARGET_RE.match(c["Target"])
    if not target:
        raise ValueError(f"bad target {c['Target']!r}")
    arg = target.group(2)
    address: int | None = None
    if c["Address"] != NONE:
        match = ADDRESS_RE.match(c["Address"])
        if not match:
            raise ValueError(f"bad address {c['Address']!r}")
        address = int(match.group(1), 16)
    if c["Confidence"] not in CONFIDENCES:
        raise ValueError(f"bad confidence {c['Confidence']!r}")
    evidence = () if c["Evidence"] == NONE else tuple(BACKTICKED.findall(c["Evidence"]))
    return WriteRow(
        kind=target.group(1),
        argument=int(arg) if arg is not None and arg != "i" else None,
        type=_int(c["Type"]),
        address=address,
        length=_int(c["Len"]),
        confidence=c["Confidence"],
        firmware=frozenset(int(v) for v in c["Firmware"].split(",")),
        evidence=evidence,
        notes=c["Notes"],
    )


def parse_table(text: str) -> list[WriteRow]:
    rows = table_lines(text)
    header = tuple(_split_row(rows[0]))
    if header != COLUMNS:
        raise ValueError(f"unexpected columns {header}")
    return [parse_row(_split_row(line)) for line in rows[2:]]


def load_write_rows(path: Path = COMMAND_LAYER) -> list[WriteRow]:
    return parse_table(path.read_text(encoding="utf-8"))
