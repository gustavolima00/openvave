"""The closed write surface (spec 003, research R2/R4/R6): pure data, no I/O.

Only four kinds of write exist, all to the volatile edit buffer or the preset-select register:

=================  ====  ===================  ===  ==========================================
Kind               Type  Address              Len  Data
=================  ====  ===================  ===  ==========================================
``knob_block``     4     ``0x10000004``       14   preset bytes 4–17, rebuilt from a fresh read
``block_switch``   4     ``0x10000000 + k``   1    the switch's on/off raw value (k = 0–3)
``led_colour``     4     ``0x10000012``       3    R, G, B (0–255 each)
``preset_select``  4     ``0xE0000000 + i``   1    always ``01`` (i = 0–35)
=================  ====  ===================  ===  ==========================================

:class:`WriteTarget` can only be built by its four constructors, and
:func:`~openvave.protocol.frame.encode_frame` refuses any ``0x22`` body outside this table. There
is no erase, no commit (``0xF0000000``), no stored-area write and no loopback write.

:data:`WRITE_MESSAGES` mirrors the "Write messages" table in ``specs/protocol/command-layer.md``
row for row (``tests/unit/test_writes_doc.py`` fails on any difference). Change both in the same
commit; a promotion there relaxes :func:`sendable_by_default` here.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

from openvave.models import ByteMapEntry, Confidence, Encoding, Region
from openvave.protocol.bytemap import BYTE_MAP

WriteKind = Literal["knob_block", "block_switch", "led_colour", "preset_select"]

WRITE_TYPE = 4
"""Region type byte of every allowlisted write."""
EDIT_BUFFER = 0x10000000
"""Address of the current / edit preset buffer (21 bytes)."""
KNOB_FIRST = 4
"""First preset offset of the knob block."""
KNOB_COUNT = 14
"""Bytes in the knob block (preset offsets 4–17)."""
KNOB_BLOCK_ADDRESS = EDIT_BUFFER + KNOB_FIRST
SWITCH_COUNT = 4
"""Block switches at preset offsets 0–3 (amp, mod, delay, reverb)."""
LED_OFFSET = 18
"""Preset offset of the LED colour (R, G, B at 18–20)."""
LED_LENGTH = 3
LED_ADDRESS = EDIT_BUFFER + LED_OFFSET
SELECT_BASE = 0xE0000000
"""Preset select register: ``01`` to ``SELECT_BASE + i`` loads stored preset ``i``."""
SELECT_DATA = b"\x01"
PRESET_COUNT = 36

_KEY = object()


def _shape(kind: str, argument: int | None) -> tuple[int, int, int] | None:
    """``(type, address, length)`` of a valid target, else ``None``."""
    if kind == "knob_block" and argument is None:
        return (WRITE_TYPE, KNOB_BLOCK_ADDRESS, KNOB_COUNT)
    if kind == "led_colour" and argument is None:
        return (WRITE_TYPE, LED_ADDRESS, LED_LENGTH)
    if isinstance(argument, bool) or not isinstance(argument, int):
        return None
    if kind == "block_switch" and 0 <= argument < SWITCH_COUNT:
        return (WRITE_TYPE, EDIT_BUFFER + argument, 1)
    if kind == "preset_select" and 0 <= argument < PRESET_COUNT:
        return (WRITE_TYPE, SELECT_BASE + argument, 1)
    return None


def _check_argument(name: str, value: int, count: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an int, not {type(value).__name__}")
    if not 0 <= value < count:
        raise ValueError(f"{name} must be 0–{count - 1}, got {value}")


@dataclass(frozen=True)
class WriteTarget:
    """One allowlisted write target. Built only by the four constructors below.

    There is no constructor taking an address, and ``dataclasses.replace`` cannot move a target
    off the allowlist (the shape is re-checked on construction).
    """

    kind: WriteKind
    """``knob_block``, ``block_switch``, ``led_colour`` or ``preset_select``."""
    type: int
    """Region type byte (always 4)."""
    address: int
    """Target address."""
    length: int
    """Number of data bytes the write carries."""
    argument: int | None
    """Switch number ``k`` (0–3) or preset index ``i`` (0–35); ``None`` otherwise."""
    _key: object = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._key is not _KEY:
            raise TypeError("WriteTarget is built only by its constructors (knob_block() …)")
        if _shape(self.kind, self.argument) != (self.type, self.address, self.length):
            raise ValueError(f"not an allowlisted write target: {self!r}")

    @classmethod
    def knob_block(cls) -> WriteTarget:
        """The 14 knob bytes (preset 4–17): type 4, ``0x10000004``, 14 bytes."""
        return cls("knob_block", WRITE_TYPE, KNOB_BLOCK_ADDRESS, KNOB_COUNT, None, _KEY)

    @classmethod
    def block_switch(cls, k: int) -> WriteTarget:
        """Block switch ``k`` (0 amp, 1 mod, 2 delay, 3 reverb): ``0x10000000 + k``, 1 byte."""
        _check_argument("switch", k, SWITCH_COUNT)
        return cls("block_switch", WRITE_TYPE, EDIT_BUFFER + k, 1, k, _KEY)

    @classmethod
    def led_colour(cls) -> WriteTarget:
        """The preset LED colour R, G, B (preset 18–20): ``0x10000012``, 3 bytes."""
        return cls("led_colour", WRITE_TYPE, LED_ADDRESS, LED_LENGTH, None, _KEY)

    @classmethod
    def preset_select(cls, index: int) -> WriteTarget:
        """Load stored preset ``index`` (0–35): ``01`` to ``0xE0000000 + index``."""
        _check_argument("preset index", index, PRESET_COUNT)
        return cls("preset_select", WRITE_TYPE, SELECT_BASE + index, 1, index, _KEY)


def check_write_data(target: WriteTarget, data: bytes) -> None:
    """Raise :class:`ValueError` unless ``data`` fits ``target`` (length; select data ``01``)."""
    if len(data) != target.length:
        raise ValueError(f"{target.kind} takes {target.length} bytes, got {len(data)}")
    if target.kind == "preset_select" and data != SELECT_DATA:
        raise ValueError("preset select data is always 01")


_SHAPES: Mapping[tuple[int, int, int], tuple[str, int | None]] = {
    shape: (kind, arg)
    for kind, args in (
        ("knob_block", (None,)),
        ("led_colour", (None,)),
        ("block_switch", tuple(range(SWITCH_COUNT))),
        ("preset_select", tuple(range(PRESET_COUNT))),
    )
    for arg in args
    if (shape := _shape(kind, arg)) is not None
}


def allowed_write_body(body: bytes) -> bool:
    """True iff ``body`` (type, address LE, length LE, data) is a write to the allowlist."""
    if len(body) < 8:
        return False
    shape = (body[0], int.from_bytes(body[1:5], "little"), int.from_bytes(body[5:8], "little"))
    found = _SHAPES.get(shape)
    if found is None:
        return False
    kind, arg = found
    try:
        target = WriteTarget(kind, *shape, arg, _KEY)  # type: ignore[arg-type]
        check_write_data(target, body[8:])
    except ValueError:
        return False
    return True


def rebuild_knob_block(buffer: bytes, offset: int, value: int) -> bytes:
    """``buffer[4:18]`` with the byte at preset ``offset`` (4–17) set to ``value`` (0–255)."""
    if len(buffer) != Region.CURRENT_PRESET.length:
        raise ValueError(f"buffer must be {Region.CURRENT_PRESET.length} bytes")
    if not KNOB_FIRST <= offset < KNOB_FIRST + KNOB_COUNT:
        raise ValueError(f"knob block covers preset offsets 4–17, not {offset}")
    if not 0 <= value <= 0xFF:
        raise ValueError(f"byte value must be 0–255, got {value}")
    block = bytearray(buffer[KNOB_FIRST : KNOB_FIRST + KNOB_COUNT])
    block[offset - KNOB_FIRST] = value
    return bytes(block)


# -- write messages (mirrors the "Write messages" doc table) -----------------------------------

MessageKind = Literal["knob_block", "block_switch", "led_colour", "preset_select", "ack"]


@dataclass(frozen=True)
class WriteMessage:
    """One row of the "Write messages" table in ``specs/protocol/command-layer.md``."""

    kind: MessageKind
    """A write kind, or ``ack`` for the write acknowledgement."""
    argument: int | None
    """Switch number for ``block_switch`` rows; ``None`` otherwise (one select row for all i)."""
    type: int | None
    """Region type byte; ``None`` for the ACK row."""
    address: int | None
    """Address (the base ``0xE0000000`` for preset select); ``None`` for the ACK row."""
    length: int | None
    """Data length; ``None`` for the ACK row."""
    confidence: Confidence
    """Evidence level of this message as sent by openvave (Constitution II)."""
    firmware: frozenset[int]
    """Firmware versions the evidence covers."""
    evidence: tuple[str, ...] = ()
    """Committed capture paths of this project's own sends."""


_FW96 = frozenset({96})


def _observed(
    kind: MessageKind,
    argument: int | None,
    address: int | None,
    length: int | None,
    *evidence: str,
) -> WriteMessage:
    return WriteMessage(
        kind=kind,
        argument=argument,
        type=None if address is None else WRITE_TYPE,
        address=address,
        length=length,
        confidence="observed",
        firmware=_FW96,
        evidence=tuple(f"captures/fw96/20261117-gate-{e}.jsonl" for e in evidence),
    )


_SWITCH_STEPS = ("switch_amp", "switch_mod", "switch_delay", "switch_reverb")

WRITE_MESSAGES: tuple[WriteMessage, ...] = (
    _observed("knob_block", None, KNOB_BLOCK_ADDRESS, KNOB_COUNT, "knob_gain"),
    *(
        _observed("block_switch", k, EDIT_BUFFER + k, 1, _SWITCH_STEPS[k])
        for k in range(SWITCH_COUNT)
    ),
    _observed("led_colour", None, LED_ADDRESS, LED_LENGTH, "led_colour"),
    _observed("preset_select", None, SELECT_BASE, 1, "select", "select_back"),
    _observed("ack", None, None, None, "knob_gain", "select"),
)
"""Every write message and the ACK, as documented: ``observed`` after gate session A (fw 96)."""

_RANK = {"hypothesis": 0, "observed": 1, "confirmed": 2}


def message_for(
    kind: str, argument: int | None, messages: Sequence[WriteMessage] = WRITE_MESSAGES
) -> WriteMessage:
    """The row for a write. Preset select has one row for every index. ``KeyError`` if none."""
    wanted = None if kind == "preset_select" else argument
    for m in messages:
        if m.kind == kind and m.argument == wanted:
            return m
    raise KeyError(f"no write message for {kind}({argument})")


def sendable_by_default(
    kind: str,
    argument: int | None,
    firmware: int,
    *,
    messages: Sequence[WriteMessage] = WRITE_MESSAGES,
) -> bool:
    """May this write be sent without the experimental opt-in? (research R4)

    True iff its row is ``confirmed``, the ``ack`` row is at least ``observed`` and ``firmware``
    is in the row's firmware set.
    """
    row = message_for(kind, argument, messages)
    ack = message_for("ack", None, messages)
    return (
        row.confidence == "confirmed"
        and _RANK[ack.confidence] >= _RANK["observed"]
        and firmware in row.firmware
    )


# -- fields that can be written (research R6) --------------------------------------------------


@dataclass(frozen=True)
class WritableField:
    """A field ``openvave set`` can change, and how."""

    name: str
    """Machine name (the byte map name, or ``led_colour``)."""
    kind: WriteKind
    """Which write carries it."""
    offset: int
    """First preset offset it occupies."""
    entry: ByteMapEntry | None
    """The byte map row (``None`` for ``led_colour``, whose bytes are still unnamed)."""

    def target(self) -> WriteTarget:
        if self.kind == "block_switch":
            return WriteTarget.block_switch(self.offset)
        if self.kind == "knob_block":
            return WriteTarget.knob_block()
        return WriteTarget.led_colour()


def _writable_fields() -> dict[str, WritableField]:
    fields: dict[str, WritableField] = {}
    for entry in BYTE_MAP:
        if entry.region is not Region.CURRENT_PRESET or entry.name is None:
            continue
        if entry.offset < SWITCH_COUNT and entry.encoding is Encoding.SWITCH:
            fields[entry.name] = WritableField(entry.name, "block_switch", entry.offset, entry)
        elif KNOB_FIRST <= entry.offset < KNOB_FIRST + KNOB_COUNT:
            fields[entry.name] = WritableField(entry.name, "knob_block", entry.offset, entry)
    fields["led_colour"] = WritableField("led_colour", "led_colour", LED_OFFSET, None)
    return fields


WRITABLE_FIELDS: Mapping[str, WritableField] = _writable_fields()
"""``openvave set`` fields: 12 knobs, 2 selectors, 4 switches and ``led_colour``."""
