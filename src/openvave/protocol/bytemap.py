"""The preset / global / status byte map (pure data, research R1).

Mirrored row for row from the table under "Preset / global byte map" in
``specs/protocol/command-layer.md``, which is authoritative. ``tests/unit/test_bytemap_doc.py``
fails on any difference, so change both in the same commit. Notes here are short; the doc holds
the findings in full.

JSON names stay stable until the 0.2.0 release (research R8): ``knob_unknown`` (gain) and
``not_in_edit_mode`` (the mode byte) keep their 0.1.0 names until then; their labels already say
what they are.
"""

from __future__ import annotations

from openvave.models import ByteMapEntry, Confidence, Encoding, Region

MAP_FIRMWARE = 96
"""Firmware version the byte map was built from."""

_FW96 = "captures/fw96/"
_FW96_CONNECT = _FW96 + "20261116-probe-connect.jsonl"


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


def _knob(
    offset: int,
    name: str,
    label: str,
    *evidence: str,
    confidence: Confidence = "observed",
    notes: str = "",
) -> ByteMapEntry:
    """A 7-bit front-panel knob of the current preset (0–127)."""
    return ByteMapEntry(
        region=Region.CURRENT_PRESET,
        offset=offset,
        name=name,
        label=label,
        encoding=Encoding.CONTINUOUS,
        min=0,
        max=127,
        control=f"{label} knob",
        confidence=confidence,
        firmware=MAP_FIRMWARE,
        evidence=evidence,
        notes=notes,
    )


def _selector(offset: int, name: str, label: str, evidence: str, notes: str) -> ByteMapEntry:
    """A stepped knob of the current preset; positions not counted yet (7-bit placeholder)."""
    return ByteMapEntry(
        region=Region.CURRENT_PRESET,
        offset=offset,
        name=name,
        label=label,
        encoding=Encoding.SELECTOR,
        min=0,
        max=127,
        control=f"{label} selector",
        confidence="observed",
        firmware=MAP_FIRMWARE,
        evidence=(evidence,),
        notes=notes,
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
        confidence="observed",
        firmware=MAP_FIRMWARE,
        evidence=(_step(f"{block}_on"),),
        notes="1 = block on; toggled alone in a labelled step (2026-11-16)",
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
        name="not_in_edit_mode",
        label="mode",
        encoding=Encoding.SELECTOR,
        min=0,
        max=2,
        labels={0: "edit", 1: "normal", 2: "tuner"},
        control="edit mode, tuner",
        confidence="confirmed",
        firmware=MAP_FIRMWARE,
        evidence=(_FW96_CONNECT, _step("mode-1843"), _step("mode-1847")),
        notes="0 edit, 1 normal, 2 tuner; JSON name kept until the 0.2.0 rename",
    ),
    _block(0, "amp"),
    _block(1, "mod"),
    _block(2, "delay"),
    _block(3, "reverb"),
    _knob(4, "noise_gate", "noise gate", _step("noise_gate"), notes="ends not yet swept"),
    _selector(5, "amp_type", "amp type", _step("amp_type"), "positions seen 0-8"),
    _knob(6, "knob_unknown", "gain", _step("gain"), notes="JSON name kept until 0.2.0"),
    _knob(7, "treble", "treble", _step("treble"), notes="reached 0; top not yet swept"),
    _knob(8, "middle", "middle", _step("middle"), notes="ends not yet swept"),
    _knob(9, "bass", "bass", _step("bass"), notes="ends not yet swept"),
    _knob(10, "volume", "volume", _step("volume"), notes="ends not yet swept; 127 on a preset"),
    _knob(11, "mod_fx", "mod fx", _step("mod_fx"), notes="0-127 swept"),
    _knob(12, "mod_speed", "mod speed", _step("mod_speed"), notes="0-127 swept"),
    _knob(13, "delay_mix", "delay mix", _step("delay_mix"), notes="0-127 swept"),
    _knob(14, "delay_time", "delay time", _step("delay_time"), notes="0-127 swept"),
    _knob(
        15,
        "reverb_decay",
        "reverb decay",
        _FW96_CONNECT,
        _step("reverb_decay"),
        confidence="confirmed",
        notes="only byte to move with this knob; 0..127 swept in a second session (2026-11-16)",
    ),
    _knob(16, "reverb_mix", "reverb mix", _step("reverb_mix"), notes="0-127 swept alone"),
    _selector(17, "ir_cab", "IR cab", _step("ir_cab"), "positions seen 0-8"),
    _unknown(Region.CURRENT_PRESET, 18, _PER_PRESET),
    _unknown(Region.CURRENT_PRESET, 19, _PER_PRESET),
    _unknown(Region.CURRENT_PRESET, 20, _PER_PRESET),
    _unknown(Region.STATUS, 0, "0x01 in all six sessions, every preset and mode"),
)
"""Every byte of ``GLOBAL`` (4), ``CURRENT_PRESET`` (21) and ``STATUS`` (1): 26 offsets."""
