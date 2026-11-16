"""The preset / global / status byte map (pure data, research R1).

Mirrored row for row from the table under "Preset / global byte map" in
``specs/protocol/command-layer.md``, which is authoritative. ``tests/unit/test_bytemap_doc.py``
fails on any difference, so change both in the same commit. Notes here are short; the doc holds
the findings in full.
"""

from __future__ import annotations

from openvave.models import ByteMapEntry, Encoding, Region

MAP_FIRMWARE = 96
"""Firmware version the byte map was built from."""

_FW96_CONNECT = "captures/fw96/20261116-probe-connect.jsonl"
_STEP_REVERB_DECAY = "captures/fw96/20261116-step-reverb_decay.jsonl"


def _unknown(region: Region, offset: int, notes: str) -> ByteMapEntry:
    return ByteMapEntry(
        region=region,
        offset=offset,
        encoding=Encoding.UNKNOWN,
        firmware=MAP_FIRMWARE,
        notes=notes,
    )


BYTE_MAP: tuple[ByteMapEntry, ...] = (
    _unknown(Region.GLOBAL, 0, "fw96: 0x00"),
    _unknown(Region.GLOBAL, 1, "fw96: 0x00"),
    _unknown(Region.GLOBAL, 2, "fw96: 0x01"),
    ByteMapEntry(
        region=Region.GLOBAL,
        offset=3,
        name="not_in_edit_mode",
        label="not in edit mode",
        encoding=Encoding.SWITCH,
        on_value=1,
        off_value=0,
        control="edit mode",
        confidence="observed",
        firmware=MAP_FIRMWARE,
        evidence=(_FW96_CONNECT,),
        notes="1 normally, 0 in edit mode (2026-11-16)",
    ),
    _unknown(Region.CURRENT_PRESET, 0, "fw96: 0x01"),
    _unknown(Region.CURRENT_PRESET, 1, "fw96: 0x00"),
    _unknown(Region.CURRENT_PRESET, 2, "fw96: 0x00"),
    _unknown(Region.CURRENT_PRESET, 3, "fw96: 0x01"),
    _unknown(Region.CURRENT_PRESET, 4, "fw96: 0x0f"),
    _unknown(Region.CURRENT_PRESET, 5, "fw96: 0x04"),
    ByteMapEntry(
        region=Region.CURRENT_PRESET,
        offset=6,
        name="knob_unknown",
        label="knob (which one: unknown)",
        encoding=Encoding.CONTINUOUS,
        min=0,
        max=127,
        control=None,
        confidence="observed",
        firmware=MAP_FIRMWARE,
        evidence=(_FW96_CONNECT,),
        notes="one front-panel knob, not yet identified (2026-11-16)",
    ),
    _unknown(Region.CURRENT_PRESET, 7, "fw96: 0x3c"),
    _unknown(Region.CURRENT_PRESET, 8, "fw96: 0x46"),
    _unknown(Region.CURRENT_PRESET, 9, "fw96: 0x32"),
    _unknown(Region.CURRENT_PRESET, 10, "fw96: 0x32"),
    _unknown(Region.CURRENT_PRESET, 11, "fw96: 0x00"),
    _unknown(Region.CURRENT_PRESET, 12, "fw96: 0x00"),
    _unknown(Region.CURRENT_PRESET, 13, "fw96: 0x00"),
    _unknown(Region.CURRENT_PRESET, 14, "fw96: 0x00"),
    ByteMapEntry(
        region=Region.CURRENT_PRESET,
        offset=15,
        name="reverb_decay",
        label="reverb decay",
        encoding=Encoding.CONTINUOUS,
        min=0,
        max=127,
        control="reverb decay knob",
        confidence="confirmed",
        firmware=MAP_FIRMWARE,
        evidence=(_FW96_CONNECT, _STEP_REVERB_DECAY),
        notes="only byte to move with this knob; 0..127 swept in a second session (2026-11-16)",
    ),
    ByteMapEntry(
        region=Region.CURRENT_PRESET,
        offset=16,
        name="reverb_mix",
        label="reverb mix",
        encoding=Encoding.CONTINUOUS,
        min=0,
        max=127,
        control="reverb mix knob",
        confidence="hypothesis",
        firmware=MAP_FIRMWARE,
        evidence=(_FW96_CONNECT,),
        notes="04 -> 7f, moved together with IR cab (2026-11-16)",
    ),
    ByteMapEntry(
        region=Region.CURRENT_PRESET,
        offset=17,
        name="ir_cab",
        label="IR cab",
        encoding=Encoding.SELECTOR,
        min=0,
        max=127,
        control="IR cab selector",
        confidence="hypothesis",
        firmware=MAP_FIRMWARE,
        evidence=(_FW96_CONNECT,),
        notes="07 -> 08, moved with reverb mix; range is a placeholder",
    ),
    _unknown(Region.CURRENT_PRESET, 18, "fw96: 0x43"),
    _unknown(Region.CURRENT_PRESET, 19, "fw96: 0x16"),
    _unknown(Region.CURRENT_PRESET, 20, "fw96: 0x43"),
    _unknown(Region.STATUS, 0, "fw96: 0x01"),
)
"""Every byte of ``GLOBAL`` (4), ``CURRENT_PRESET`` (21) and ``STATUS`` (1): 26 offsets."""
