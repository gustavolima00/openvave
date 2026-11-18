"""The closed write surface (spec 003 research R2/R4/R6, spec 004 R5/R7): pure data, no I/O.

Only these kinds of write exist. The first six are volatile (edit buffer, select and bypass
registers, the status flag); the last three are **persistent** (they change stored presets):

=================  ====  ===================  ===  ==========================================
Kind               Type  Address              Len  Data
=================  ====  ===================  ===  ==========================================
``knob_block``     4     ``0x10000004``       14   preset bytes 4–17, rebuilt from a fresh read
``block_switch``   4     ``0x10000000 + k``   1    the switch's on/off raw value (k = 0–3)
``led_colour``     4     ``0x10000012``       3    R, G, B (0–255 each)
``preset_select``  4     ``0xE0000000 + i``   1    always ``01`` (i = 0–35)
``bypass``         4     ``0xE1000000 + i``   1    always ``01`` (i = 0–35, the loaded preset)
``loopback``       4     ``0xD0000000``       1    ``00`` (off) or ``01`` (on)
``stored_slot``    4     ``2 + 21·i``         21   21 preset bytes (i = 0–35)
``commit``         4     ``0xF0000000``       0    empty
``stored_image``   4     ``0x00000000``       758  header + 36 presets, starting ``a5 5a``
=================  ====  ===================  ===  ==========================================

:class:`WriteTarget` can only be built by its constructors, and
:func:`~openvave.protocol.frame.encode_frame` refuses any ``0x22`` body outside this table: erase
(``0x21``), type 6, the global block, the whole edit buffer, a stored address that is not a slot
start and any other length stay unencodable. :attr:`WriteTarget.persistent` marks the three
stored-preset kinds; the session sends them only from its save/restore sequence runner, only with
``unsafe=True`` and after the automatic backup (spec 004 R5, R9).

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

WriteKind = Literal[
    "knob_block",
    "block_switch",
    "led_colour",
    "preset_select",
    "bypass",
    "loopback",
    "stored_slot",
    "commit",
    "stored_image",
]

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
BYPASS_BASE = 0xE1000000
"""Bypass register: ``01`` to ``BYPASS_BASE + i`` bypasses the pedal with preset ``i`` loaded
(spec 004 check 2: slot then reads ``ff`` and the edit buffer all zero)."""
BYPASS_DATA = b"\x01"
LOOPBACK_ADDRESS = 0xD0000000
"""The 1-byte status flag the app calls loopback (spec 004 US5): ``1`` mixes the pedal's Bluetooth
audio into the USB recording, ``0`` leaves it out (owner, 2026-11-18)."""
LOOPBACK_VALUES = (b"\x00", b"\x01")
STORE_OFFSET = 2
"""Stored preset ``i`` starts at ``STORE_OFFSET + PRESET_SIZE·i`` (after the 2-byte header)."""
PRESET_SIZE = 21
COMMIT_ADDRESS = 0xF0000000
"""Empty write that makes the stored area permanent (spec 004 checks 3 and 4, R8)."""
IMAGE_ADDRESS = 0x00000000
IMAGE_SIZE = STORE_OFFSET + PRESET_SIZE * PRESET_COUNT
"""758: header + 36 presets."""
IMAGE_HEADER = bytes.fromhex("a5 5a")
PERSISTENT_KINDS = frozenset({"stored_slot", "commit", "stored_image"})
"""Kinds that change stored presets (:attr:`WriteTarget.persistent`)."""
INDEXED_KINDS = frozenset({"preset_select", "bypass", "stored_slot"})
"""Kinds with one "Write messages" row for every preset index."""

_KEY = object()


def _shape(kind: str, argument: int | None) -> tuple[int, int, int] | None:
    """``(type, address, length)`` of a valid target, else ``None``."""
    if kind == "knob_block" and argument is None:
        return (WRITE_TYPE, KNOB_BLOCK_ADDRESS, KNOB_COUNT)
    if kind == "led_colour" and argument is None:
        return (WRITE_TYPE, LED_ADDRESS, LED_LENGTH)
    if kind == "loopback" and argument is None:
        return (WRITE_TYPE, LOOPBACK_ADDRESS, 1)
    if kind == "commit" and argument is None:
        return (WRITE_TYPE, COMMIT_ADDRESS, 0)
    if kind == "stored_image" and argument is None:
        return (WRITE_TYPE, IMAGE_ADDRESS, IMAGE_SIZE)
    if isinstance(argument, bool) or not isinstance(argument, int):
        return None
    if kind == "block_switch" and 0 <= argument < SWITCH_COUNT:
        return (WRITE_TYPE, EDIT_BUFFER + argument, 1)
    if kind == "preset_select" and 0 <= argument < PRESET_COUNT:
        return (WRITE_TYPE, SELECT_BASE + argument, 1)
    if kind == "bypass" and 0 <= argument < PRESET_COUNT:
        return (WRITE_TYPE, BYPASS_BASE + argument, 1)
    if kind == "stored_slot" and 0 <= argument < PRESET_COUNT:
        return (WRITE_TYPE, STORE_OFFSET + PRESET_SIZE * argument, PRESET_SIZE)
    return None


def _check_argument(name: str, value: int, count: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an int, not {type(value).__name__}")
    if not 0 <= value < count:
        raise ValueError(f"{name} must be 0–{count - 1}, got {value}")


@dataclass(frozen=True)
class WriteTarget:
    """One allowlisted write target. Built only by the constructors below.

    There is no constructor taking an address, and ``dataclasses.replace`` cannot move a target
    off the allowlist (the shape is re-checked on construction).
    """

    kind: WriteKind
    """``knob_block``, ``block_switch``, ``led_colour``, ``preset_select``, ``bypass``,
    ``loopback``, or one of the persistent kinds ``stored_slot``, ``commit``, ``stored_image``."""
    type: int
    """Region type byte (always 4)."""
    address: int
    """Target address."""
    length: int
    """Number of data bytes the write carries."""
    argument: int | None
    """Switch number ``k`` (0–3) or preset index ``i`` (0–35, select, bypass and stored slot);
    ``None`` otherwise."""
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

    @classmethod
    def bypass(cls, index: int) -> WriteTarget:
        """Bypass with preset ``index`` (0–35) loaded: ``01`` to ``0xE1000000 + index``.

        Volatile; selecting a preset leaves bypass (spec 004 check 2).
        """
        _check_argument("preset index", index, PRESET_COUNT)
        return cls("bypass", WRITE_TYPE, BYPASS_BASE + index, 1, index, _KEY)

    @classmethod
    def loopback(cls) -> WriteTarget:
        """The loopback flag: ``00`` / ``01`` to ``0xD0000000``, 1 byte. Never committed."""
        return cls("loopback", WRITE_TYPE, LOOPBACK_ADDRESS, 1, None, _KEY)

    @classmethod
    def stored_slot(cls, index: int) -> WriteTarget:
        """Stored preset ``index`` (0–35): ``2 + 21·index``, 21 bytes. **Persistent.**

        Changes the stored area; the commit makes it permanent (spec 004 check 4).
        """
        _check_argument("preset index", index, PRESET_COUNT)
        address = STORE_OFFSET + PRESET_SIZE * index
        return cls("stored_slot", WRITE_TYPE, address, PRESET_SIZE, index, _KEY)

    @classmethod
    def commit(cls) -> WriteTarget:
        """The empty commit write to ``0xF0000000``. **Persistent.**"""
        return cls("commit", WRITE_TYPE, COMMIT_ADDRESS, 0, None, _KEY)

    @classmethod
    def stored_image(cls) -> WriteTarget:
        """The whole stored image (header + 36 presets): ``0x0``, 758 bytes. **Persistent.**"""
        return cls("stored_image", WRITE_TYPE, IMAGE_ADDRESS, IMAGE_SIZE, None, _KEY)

    @property
    def persistent(self) -> bool:
        """Does a write to this target change stored presets? True for ``stored_slot``,
        ``commit`` and ``stored_image``."""
        return self.kind in PERSISTENT_KINDS


def check_write_data(target: WriteTarget, data: bytes) -> None:
    """Raise :class:`ValueError` unless ``data`` fits ``target``.

    Length must match; select and bypass data is always ``01``; loopback data ``00`` or ``01``;
    a stored image starts with the header ``a5 5a``.
    """
    if len(data) != target.length:
        raise ValueError(f"{target.kind} takes {target.length} bytes, got {len(data)}")
    if target.kind == "preset_select" and data != SELECT_DATA:
        raise ValueError("preset select data is always 01")
    if target.kind == "bypass" and data != BYPASS_DATA:
        raise ValueError("bypass data is always 01")
    if target.kind == "loopback" and data not in LOOPBACK_VALUES:
        raise ValueError("loopback data is 00 or 01")
    if target.kind == "stored_image" and data[:2] != IMAGE_HEADER:
        raise ValueError("a stored image starts with the header a5 5a")


_SHAPES: Mapping[tuple[int, int, int], tuple[str, int | None]] = {
    shape: (kind, arg)
    for kind, args in (
        ("knob_block", (None,)),
        ("led_colour", (None,)),
        ("loopback", (None,)),
        ("commit", (None,)),
        ("stored_image", (None,)),
        ("block_switch", tuple(range(SWITCH_COUNT))),
        ("preset_select", tuple(range(PRESET_COUNT))),
        ("bypass", tuple(range(PRESET_COUNT))),
        ("stored_slot", tuple(range(PRESET_COUNT))),
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

MessageKind = Literal[
    "knob_block",
    "block_switch",
    "led_colour",
    "preset_select",
    "bypass",
    "loopback",
    "stored_slot",
    "commit",
    "stored_image",
    "ack",
]


@dataclass(frozen=True)
class WriteMessage:
    """One row of the "Write messages" table in ``specs/protocol/command-layer.md``."""

    kind: MessageKind
    """A write kind, or ``ack`` for the write acknowledgement."""
    argument: int | None
    """Switch number for ``block_switch`` rows; ``None`` otherwise (one select, one bypass and
    one stored-slot row for all i)."""
    type: int | None
    """Region type byte; ``None`` for the ACK row."""
    address: int | None
    """Address (the base ``0xE0000000`` / ``0xE1000000`` / ``0x2`` for select / bypass / stored
    slot); ``None`` for the ACK row."""
    length: int | None
    """Data length; ``None`` for the ACK row."""
    confidence: Confidence
    """Evidence level of this message as sent by openvave (Constitution II)."""
    firmware: frozenset[int]
    """Firmware versions the evidence covers."""
    evidence: tuple[str, ...] = ()
    """Committed capture paths of this project's own sends."""


_FW96 = frozenset({96})


def _row(
    confidence: Confidence,
    kind: MessageKind,
    argument: int | None,
    address: int | None,
    length: int | None,
    *evidence: str,
    date: str = "20261117",
) -> WriteMessage:
    return WriteMessage(
        kind=kind,
        argument=argument,
        type=None if address is None else WRITE_TYPE,
        address=address,
        length=length,
        confidence=confidence,
        firmware=_FW96,
        evidence=tuple(f"captures/fw96/{date}-gate-{e}.jsonl" for e in evidence),
    )


_SWITCH_STEPS = ("switch_amp", "switch_mod", "switch_delay", "switch_reverb")
_SPEC004_A = "20261118"
"""Date of spec 004 gate session A (its excerpts are ``captures/fw96/20261118-gate-<step>``)."""

WRITE_MESSAGES: tuple[WriteMessage, ...] = (
    _row(
        "confirmed", "knob_block", None, KNOB_BLOCK_ADDRESS, KNOB_COUNT, "knob_gain", "knob_treble"
    ),
    *(
        _row("observed", "block_switch", k, EDIT_BUFFER + k, 1, _SWITCH_STEPS[k])
        for k in range(SWITCH_COUNT)
    ),
    _row("observed", "led_colour", None, LED_ADDRESS, LED_LENGTH, "led_colour"),
    _row(
        "confirmed",
        "preset_select",
        None,
        SELECT_BASE,
        1,
        "select",
        "select_back",
        "select_b",
        "select_b_back",
    ),
    _row("observed", "bypass", None, BYPASS_BASE, 1, "bypass", date=_SPEC004_A),
    _row(
        "observed",
        "loopback",
        None,
        LOOPBACK_ADDRESS,
        1,
        "loopback_off",
        "loopback_on",
        date=_SPEC004_A,
    ),
    _row(
        "observed",
        "stored_slot",
        None,
        STORE_OFFSET,
        PRESET_SIZE,
        "save",
        "restore_slot",
        date=_SPEC004_A,
    ),
    _row(
        "observed",
        "commit",
        None,
        COMMIT_ADDRESS,
        0,
        "save",
        "restore_slot",
        "image_noop",
        "restore_all",
        date=_SPEC004_A,
    ),
    _row(
        "observed",
        "stored_image",
        None,
        IMAGE_ADDRESS,
        IMAGE_SIZE,
        "image_noop",
        "restore_all",
        date=_SPEC004_A,
    ),
    _row("confirmed", "ack", None, None, None, "knob_gain", "select", "knob_treble", "select_b"),
)
"""Every write message and the ACK, as documented (fw 96). Gate sessions A and B confirm the
knob block, preset select and the ACK; the block switches and LED colour stay ``observed``
(session A only), so they still need ``--experimental``. Bypass, loopback and the three persistent
kinds are ``observed`` since spec 004 gate session A (2026-11-18) sent them from openvave; they
need ``--experimental`` until gate session B confirms them (spec 004 R7)."""

_RANK = {"hypothesis": 0, "observed": 1, "confirmed": 2}


def message_for(
    kind: str, argument: int | None, messages: Sequence[WriteMessage] = WRITE_MESSAGES
) -> WriteMessage:
    """The row for a write. Select, bypass and stored slot have one row for every index.
    ``KeyError`` if none."""
    wanted = None if kind in INDEXED_KINDS else argument
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
