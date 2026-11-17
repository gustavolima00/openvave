"""Parse the byte map table in ``specs/protocol/command-layer.md`` (research R1).

Independent of ``openvave``: rows come back as plain tuples so the doc↔code test compares two
separately produced descriptions of the map.

Cell grammar (one row per offset, or per flag mask):

- Region: ``global`` | ``preset`` | ``status``
- Offset: decimal; Mask: ``—`` or ``0x..``; Firmware: decimal
- Name: ``—`` or a backticked snake_case name
- Range: ``—``, ``<min>–<max>`` or ``on=<n> off=<n>``
- Control, Confidence: ``—`` or text
- Evidence: ``—`` or backticked paths separated by commas
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from tests.support.captures import REPO_ROOT

COMMAND_LAYER = REPO_ROOT / "specs" / "protocol" / "command-layer.md"
HEADING = "### Preset / global byte map"
COLUMNS = (
    "Region",
    "Offset",
    "Mask",
    "Name",
    "Encoding",
    "Range",
    "Control",
    "Confidence",
    "Firmware",
    "Evidence",
    "Notes",
)
NONE = "—"
RANGE_RE = re.compile(r"^(\d+)–(\d+)$")
SWITCH_RE = re.compile(r"^on=(\d+) off=(\d+)$")
BACKTICKED = re.compile(r"`([^`]+)`")


@dataclass(frozen=True)
class DocRow:
    region: str
    offset: int
    mask: int | None
    name: str | None
    encoding: str
    min: int | None
    max: int | None
    on_value: int | None
    off_value: int | None
    control: str | None
    confidence: str | None
    firmware: int
    evidence: tuple[str, ...]
    notes: str

    def key(self) -> tuple[object, ...]:
        """Everything the code table must agree on (labels and notes are free text)."""
        return (
            self.region,
            self.offset,
            self.mask,
            self.name,
            self.encoding,
            self.min,
            self.max,
            self.on_value,
            self.off_value,
            self.control,
            self.confidence,
            self.firmware,
            self.evidence,
        )


def _opt(cell: str) -> str | None:
    return None if cell == NONE else cell


def _split_row(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def table_lines(text: str) -> list[str]:
    """The table rows (header and separator included) under :data:`HEADING`."""
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
        raise ValueError("byte map table not found under its heading")
    return rows


def parse_row(cells: list[str]) -> DocRow:
    if len(cells) != len(COLUMNS):
        raise ValueError(f"expected {len(COLUMNS)} cells, got {len(cells)}: {cells}")
    c = dict(zip(COLUMNS, cells, strict=True))
    name = _opt(c["Name"])
    if name is not None:
        match = BACKTICKED.fullmatch(name)
        if not match:
            raise ValueError(f"name must be backticked: {name!r}")
        name = match.group(1)
    mask = _opt(c["Mask"])
    lo = hi = on = off = None
    rng = c["Range"]
    if rng != NONE:
        if m := RANGE_RE.match(rng):
            lo, hi = int(m.group(1)), int(m.group(2))
        elif m := SWITCH_RE.match(rng):
            on, off = int(m.group(1)), int(m.group(2))
        else:
            raise ValueError(f"bad range {rng!r}")
    evidence = () if c["Evidence"] == NONE else tuple(BACKTICKED.findall(c["Evidence"]))
    return DocRow(
        region=c["Region"],
        offset=int(c["Offset"]),
        mask=int(mask, 16) if mask is not None else None,
        name=name,
        encoding=c["Encoding"],
        min=lo,
        max=hi,
        on_value=on,
        off_value=off,
        control=_opt(c["Control"]),
        confidence=_opt(c["Confidence"]),
        firmware=int(c["Firmware"]),
        evidence=evidence,
        notes=c["Notes"],
    )


def parse_table(text: str) -> list[DocRow]:
    rows = table_lines(text)
    header = tuple(_split_row(rows[0]))
    if header != COLUMNS:
        raise ValueError(f"unexpected columns {header}")
    return [parse_row(_split_row(line)) for line in rows[2:]]


def load_doc_rows(path: Path = COMMAND_LAYER) -> list[DocRow]:
    return parse_table(path.read_text(encoding="utf-8"))


COMPARISON_HEADING = "### Preset comparison (fw 96)"
CELL_RE = re.compile(r"^`?([0-9a-f]{2})`?$")
BYTE_RE = re.compile(r"^(global|preset|status)\[(\d+)\]$")


def load_comparison(
    path: Path = COMMAND_LAYER,
) -> tuple[list[str], list[tuple[str, int, list[int]]]]:
    """The preset comparison table: preset columns, then (region, offset, hex values) rows."""
    lines = path.read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(COMPARISON_HEADING))
    table: list[str] = []
    for line in lines[start + 1 :]:
        if line.startswith("#"):
            break
        if line.startswith("|"):
            table.append(line)
        elif table:
            break
    header = _split_row(table[0])
    if header[0] != "Byte" or header[-1] != "Field":
        raise ValueError(f"unexpected comparison header {header}")
    header = header[:-1]  # value columns are the presets between Byte and Field
    rows: list[tuple[str, int, list[int]]] = []
    for line in table[2:]:
        cells = _split_row(line)
        match = BYTE_RE.match(cells[0].strip("`"))
        if not match:
            raise ValueError(f"bad byte cell {cells[0]!r}")
        values = []
        for cell in cells[1 : len(header)]:
            hex_match = CELL_RE.match(cell)
            if not hex_match:
                raise ValueError(f"bad value cell {cell!r}")
            values.append(int(hex_match.group(1), 16))
        rows.append((match.group(1), int(match.group(2)), values))
    return header[1:], rows


REVERB_HEADING = "### Reverb decay sections (fw 96"
SPAN_RE = re.compile(r"^(\d+)–(\d+)$")


@dataclass(frozen=True)
class ReverbSectionRow:
    section: str
    raw: tuple[int, int]
    numbered: tuple[int, int]
    x: tuple[int, int] | None
    confidence: str


def _span(cell: str) -> tuple[int, int]:
    match = SPAN_RE.match(cell)
    if not match:
        raise ValueError(f"bad span {cell!r}")
    return int(match.group(1)), int(match.group(2))


def _reverb_tables(path: Path) -> list[list[list[str]]]:
    """Every table under the reverb sections heading, as rows of cells (separators dropped)."""
    lines = path.read_text(encoding="utf-8").splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.startswith(REVERB_HEADING))
    except StopIteration:
        raise ValueError(f"heading {REVERB_HEADING!r} not found") from None
    tables: list[list[list[str]]] = []
    current: list[list[str]] = []
    for line in lines[start + 1 :]:
        if line.startswith("#"):
            break
        if line.startswith("|"):
            cells = _split_row(line)
            if not all(set(c) <= {"-"} for c in cells):
                current.append(cells)
        elif current:
            tables.append(current)
            current = []
    if current:
        tables.append(current)
    return tables


def load_reverb_sections(path: Path = COMMAND_LAYER) -> list[ReverbSectionRow]:
    """The section table: section, raw span, numbered span, X span (or ``—``), confidence."""
    table = _reverb_tables(path)[0]
    if table[0] != ["Section", "Raw", "App 1–40", "App X", "Confidence"]:
        raise ValueError(f"unexpected reverb section header {table[0]}")
    return [
        ReverbSectionRow(
            section=cells[0],
            raw=_span(cells[1]),
            numbered=_span(cells[2]),
            x=None if cells[3] == NONE else _span(cells[3]),
            confidence=cells[4],
        )
        for cells in table[1:]
    ]


def load_reverb_readings(path: Path = COMMAND_LAYER) -> list[tuple[str, int]]:
    """The readings table: (app position, raw byte 15) in column order."""
    header, values = _reverb_tables(path)[1]
    if header[0] != "App" or values[0] != "Raw":
        raise ValueError(f"unexpected reverb readings table {header}, {values}")
    return [(app, int(raw)) for app, raw in zip(header[1:], values[1:], strict=True)]
