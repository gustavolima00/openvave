"""The preset / global / status byte map (pure data, research R1).

Mirrored row for row from the table under "Preset / global byte map" in
``specs/protocol/command-layer.md``, which is authoritative. ``tests/unit/test_bytemap_doc.py``
fails on any difference, so change both in the same commit. Notes here are short; the doc holds
the findings in full.

Renaming a named entry is a breaking JSON change (research R8): it bumps ``schema_version`` and
goes in the CHANGELOG rename table. 0.2.0 renamed ``knob_unknown`` → ``gain`` and
``not_in_edit_mode`` → ``mode``.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from openvave.models import ByteMapEntry, Encoding, Region

MAP_FIRMWARE = 96
"""Firmware version the byte map was built from."""

_FW96 = "captures/fw96/"
_FW96_CONNECT = _FW96 + "20261116-probe-connect.jsonl"
_FW96_REVERB_APP = _FW96 + "20261117-reverb-sections-app.jsonl"


def _step(field: str) -> str:
    return f"{_FW96}20261116-step-{field}.jsonl"


def _unknown(region: Region, offset: int, notes: str) -> ByteMapEntry:
    return ByteMapEntry(
        region=region,
        offset=offset,
        encoding=Encoding.UNKNOWN,
        firmware=MAP_FIRMWARE,
        notes=notes,
    )


def _twice(field: str) -> tuple[str, str]:
    """The two independent sessions of a front-panel step: 18:25 (or 18:47) and 19:17."""
    return (_step(field), _step(f"{field}-1917"))


def _knob(offset: int, name: str, label: str, field: str, notes: str, *extra: str) -> ByteMapEntry:
    """A 7-bit front-panel knob of the current preset (0–127), seen in two sessions."""
    return ByteMapEntry(
        region=Region.CURRENT_PRESET,
        offset=offset,
        name=name,
        label=label,
        encoding=Encoding.CONTINUOUS,
        min=0,
        max=127,
        control=f"{label} knob",
        confidence="confirmed",
        firmware=MAP_FIRMWARE,
        evidence=(*extra, *_twice(field)),
        notes=notes,
    )


def _selector(offset: int, name: str, label: str) -> ByteMapEntry:
    """A 9-position stepped knob of the current preset (0–8), counted click by click."""
    return ByteMapEntry(
        region=Region.CURRENT_PRESET,
        offset=offset,
        name=name,
        label=label,
        encoding=Encoding.SELECTOR,
        min=0,
        max=8,
        control=f"{label} selector",
        confidence="confirmed",
        firmware=MAP_FIRMWARE,
        evidence=_twice(name),
        notes="9 positions, 0-8, one click at a time (2026-11-16 19:17)",
    )


def _block(offset: int, block: str) -> ByteMapEntry:
    """An effect block's on/off switch in the current preset."""
    return ByteMapEntry(
        region=Region.CURRENT_PRESET,
        offset=offset,
        name=f"{block}_on",
        label=f"{block} on",
        encoding=Encoding.SWITCH,
        on_value=1,
        off_value=0,
        control=f"{block} block switch",
        confidence="confirmed",
        firmware=MAP_FIRMWARE,
        evidence=_twice(f"{block}_on"),
        notes="1 = block on; toggled alone in labelled steps of two sessions (2026-11-16)",
    )


def _position(offset: int, name: str, label: str, top: int, notes: str) -> ByteMapEntry:
    """Where the pedal is in its 9 banks × 4 slots (0-based)."""
    return ByteMapEntry(
        region=Region.GLOBAL,
        offset=offset,
        name=name,
        label=label,
        encoding=Encoding.INDEX,
        min=0,
        max=top,
        control="preset selection",
        confidence="observed",
        firmware=MAP_FIRMWARE,
        evidence=(_step("preset_select-bank"), _step("preset_select-slots")),
        notes=notes,
    )


_PER_PRESET = "differs per preset (see Preset comparison); no control moved it"

BYTE_MAP: tuple[ByteMapEntry, ...] = (
    _position(0, "browse_bank", "browsed bank", 8, "0-based bank shown while browsing"),
    _position(1, "bank", "bank", 8, "0-based bank of the loaded preset"),
    _position(2, "slot", "slot", 3, "0-3 = A-D; 255 for one cycle while a preset loads"),
    ByteMapEntry(
        region=Region.GLOBAL,
        offset=3,
        name="mode",
        label="mode",
        encoding=Encoding.SELECTOR,
        min=0,
        max=2,
        labels={0: "edit", 1: "normal", 2: "tuner"},
        control="edit mode, tuner",
        confidence="confirmed",
        firmware=MAP_FIRMWARE,
        evidence=(_FW96_CONNECT, _step("mode-1843"), _step("mode-1847")),
        notes="0 edit, 1 normal, 2 tuner; named not_in_edit_mode until 0.1.x",
    ),
    _block(0, "amp"),
    _block(1, "mod"),
    _block(2, "delay"),
    _block(3, "reverb"),
    _knob(4, "noise_gate", "noise gate", "noise_gate", "0-127 swept"),
    _selector(5, "amp_type", "amp type"),
    _knob(6, "gain", "gain", "gain", "0-127 swept; named knob_unknown until 0.1.x"),
    _knob(7, "treble", "treble", "treble", "0-127 swept"),
    _knob(8, "middle", "middle", "middle", "0-127 swept"),
    _knob(9, "bass", "bass", "bass", "0-127 swept"),
    _knob(10, "volume", "volume", "volume", "0-127 swept"),
    _knob(11, "mod_fx", "mod fx", "mod_fx", "0-127 swept"),
    _knob(12, "mod_speed", "mod speed", "mod_speed", "0-127 swept"),
    _knob(13, "delay_mix", "delay mix", "delay_mix", "0-127 swept"),
    _knob(14, "delay_time", "delay time", "delay_time", "0-127 swept"),
    _knob(
        15,
        "reverb_decay",
        "reverb decay",
        "reverb_decay",
        "0-127 swept; the app splits it into 3 sections of 44 (see REVERB_SECTIONS)",
        _FW96_CONNECT,
        _FW96_REVERB_APP,
    ),
    _knob(16, "reverb_mix", "reverb mix", "reverb_mix", "0-127 swept"),
    _selector(17, "ir_cab", "IR cab"),
    _unknown(Region.CURRENT_PRESET, 18, _PER_PRESET),
    _unknown(Region.CURRENT_PRESET, 19, _PER_PRESET),
    _unknown(Region.CURRENT_PRESET, 20, _PER_PRESET),
    _unknown(Region.STATUS, 0, "0x01 in all seven sessions, every preset and mode"),
)
"""Every byte of ``GLOBAL`` (4), ``CURRENT_PRESET`` (21) and ``STATUS`` (1): 26 offsets."""


REVERB_SECTION_SIZE = 44
"""Raw values per section of ``reverb_decay`` (preset byte 15) as the phone app splits it."""
REVERB_SECTION_STEPS = 40
"""Numbered app positions per section (1–40); the rest of a section shows as ``X``."""
REVERB_SECTIONS: tuple[str, ...] = ("blue", "orange", "green")
"""Section names by the colour the phone app draws them in: how the app shows the knob, kept
for 0.3.0 compatibility. The pedal's own names are :data:`REVERB_TYPES` (manual); the split
itself is ``observed`` (2026-11-17, fw 96)."""


def reverb_decay_parts(raw: int) -> tuple[str, int | None]:
    """``reverb_decay`` as the phone app shows it: (section, position 1–40, or ``None`` for X).

    Mirrors "Reverb decay sections" in ``specs/protocol/command-layer.md``: section
    ``raw // 44``, position ``raw % 44 + 1`` up to 40. Green (88–127) has 40 values and no X.
    """
    if not 0 <= raw <= 127:
        raise ValueError(f"reverb_decay raw value must be 0-127, got {raw}")
    section, step = divmod(raw, REVERB_SECTION_SIZE)
    return REVERB_SECTIONS[section], (step + 1 if step < REVERB_SECTION_STEPS else None)


REVERB_TYPES: tuple[str, ...] = ("room", "spring", "cloud")
"""Reverb types along the decay knob, in knob order. The Tank-G manual says the RVB DECAY knob
runs through three processes, ROOM, SPRING and CLOUD, and that between two processes the reverb
is off. Each type is one measured section of :data:`REVERB_SECTIONS` (same order); between them
lie 4 raw values (40–43, 84–87) the app shows as ``X``."""

MOD_FX_TYPES: tuple[str, ...] = ("chorus", "phaser", "tremolo")
"""MOD FX processes in knob order (manual: chorus mix, phaser depth, tremolo mix)."""
DELAY_MIX_TYPES: tuple[str, ...] = ("analog", "tape", "dual")
"""DLY MIX processes in knob order (manual: analog, tape, dual delay)."""

TYPED_FIELDS: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {"mod_fx": MOD_FX_TYPES, "delay_mix": DELAY_MIX_TYPES, "reverb_decay": REVERB_TYPES}
)
"""Fields whose knob runs through named types and whose type split is at least ``observed``
(spec 004 R3): ``set`` takes ``--type`` for them. All three split the same way: 44 raw values per
type, positions 1–40, 4 off values between types (reverb decay readings, and the MOD FX / DLY MIX
readings of spec 004 T022). Mirrors the knob-type table under "Reverb decay sections" in
``specs/protocol/command-layer.md`` (checked by ``tests/unit/test_bytemap_doc.py``)."""


def _types(field: str) -> tuple[str, ...]:
    types = TYPED_FIELDS.get(field)
    if types is None:
        names = ", ".join(sorted(TYPED_FIELDS))
        raise ValueError(f"{field} has no knob types; fields with types: {names}")
    return types


def type_parts(field: str, raw: int) -> tuple[str | None, int | None]:
    """(type, position 1–40) of a typed field's raw value, or ``(None, None)`` between types.

    Type ``raw // 44``, position ``raw % 44 + 1`` while ``raw % 44 < 40``; the other values lie
    between two types, where the manual says the module is off. Raises :class:`ValueError` for a
    field without types or a raw value outside 0–127.
    """
    types = _types(field)
    if not 0 <= raw <= 127:
        raise ValueError(f"{field} raw value must be 0-127, got {raw}")
    index, step = divmod(raw, REVERB_SECTION_SIZE)
    if step >= REVERB_SECTION_STEPS:
        return None, None
    return types[index], step + 1


def type_raw(field: str, type_name: str, position: int) -> int:
    """Raw value of a type and position: ``44 · index(type) + position − 1``.

    ``type_name`` is case-insensitive (``room``, ``spring``, ``cloud`` for ``reverb_decay``);
    ``position`` is 1–40. Raises :class:`ValueError` otherwise.
    """
    types = _types(field)
    name = type_name.lower()
    if name not in types:
        raise ValueError(f"{field} type must be one of {', '.join(types)}, got {type_name!r}")
    if not 1 <= position <= REVERB_SECTION_STEPS:
        raise ValueError(f"position must be 1–{REVERB_SECTION_STEPS}, got {position}")
    return REVERB_SECTION_SIZE * types.index(name) + position - 1
