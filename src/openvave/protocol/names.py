"""Amp type and IR cab position names (spec 007 US4, pure data).

Every name comes from the evidence record ``specs/007-mapping-gaps/evidence-amp-cab-names.md``
(FR-011), which transcribes two M-VAVE lists that disagree:

- ``manual-2024``: the Tank-G user manual, figures 5 (amp) and 6 (IR cab);
- ``preset-card-2026``: M-VAVE's "TANK-G NEW PRESET" card (V04, 2026-02-08).

:data:`NAME_CHOICE` says which list names each raw position, and with which confidence. Until the
owner matches the positions on a fw 96 pedal (spec 007 T031) every position takes the manual's
name as a ``hypothesis``. Switching to the card, or mixing the two, changes only
:data:`NAME_CHOICE`. ``specs/protocol/command-layer.md`` ("Amp type and IR cab names") mirrors
the chosen names and ``tests/unit/test_names_doc.py`` fails on any difference.

The brand and model names are trademarks of their owners, used only to describe the sound
character, as the vendor's manual does; the IR cab names describe the **factory** IRs, which a
user can replace.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

NAMED_FIELDS: tuple[str, ...] = ("amp_type", "ir_cab")
"""Byte-map fields whose positions carry a model name."""

EVIDENCE = "specs/007-mapping-gaps/evidence-amp-cab-names.md"

NAMES_FIRMWARE = 96
"""Firmware the names are kept for; JSON carries it next to every name, so a result from an
untested firmware (decoded with the fw 96 map) shows its scope."""


@dataclass(frozen=True, slots=True)
class NameSource:
    """Where a list of names comes from."""

    key: str
    title: str
    publisher: str
    date: str


@dataclass(frozen=True, slots=True)
class PositionName:
    """The model one raw position of ``amp_type`` or ``ir_cab`` is named after."""

    field: str
    raw: int
    name: str
    """The model as printed, without the "Based on" prefix (``Plexi 100``)."""
    detail: str
    """Amp: ``clean``, ``overdrive`` or ``distortion``; cab: the speaker layout (``4x12``)."""
    factory: bool
    """True for IR cab positions: the name describes the factory IR, which a user can replace."""
    source: str
    """A key of :data:`NAME_SOURCES`."""
    confidence: str
    """``hypothesis`` until matched on the pedal, then ``observed`` (by ear) or ``confirmed``."""

    @property
    def text(self) -> str:
        """``Plexi 100`` or, for a cab, ``Mesa Boogie 4x12``."""
        return f"{self.name} {self.detail}" if self.factory else self.name


NAME_SOURCES: Mapping[str, NameSource] = MappingProxyType(
    {
        "manual-2024": NameSource(
            "manual-2024",
            "M-VAVE TANK-G Multi Guitar Pedal User Manual, figures 5 and 6",
            "M-VAVE (Manuals+ copy, posted 2024-02-13)",
            "2024-02",
        ),
        "preset-card-2026": NameSource(
            "preset-card-2026",
            "TANK-G NEW PRESET card, V04",
            "M-VAVE",
            "2026-02-08",
        ),
    }
)

# Printed lists, in raw order (amp: printed slot k = raw k - 1; cab: printed slot k = raw k).
# Each item: (name, detail). ``None`` = no model (IR cab 0 turns the cab off).
_LISTS: Mapping[str, Mapping[str, tuple[tuple[str, str] | None, ...]]] = MappingProxyType(
    {
        "manual-2024": {
            "amp_type": (
                ("VOX AC30HW Normal", "clean"),
                ("Fender 65 Twin Reverb", "clean"),
                ("Bogner Shiva", "overdrive"),
                ("Marshall JTM45 OD", "overdrive"),
                ("Plexi 100", "overdrive"),
                ("Marshall JCM800", "distortion"),
                ("EVH 5150 LEAD", "distortion"),
                ("ENGL Powerball E645/2", "distortion"),
                ("Mesa Boogie Dual Rectifier", "distortion"),
            ),
            "ir_cab": (
                None,
                ("VHT Deliverance", "4x12"),
                ("Sperimental", "4x12"),
                ("Electrovoice", "2x10"),
                ("Mesa Boogie", "4x12"),
                ("Fender Champ", "1x8"),
                ("Fender Pr Junior", "1x10"),
                ("Marshall 1960V30", "4x12"),
                ("Diezel V30", "4x12"),
            ),
        },
        "preset-card-2026": {
            "amp_type": (
                ("J120_CL (Roland JC-120 Jazz Chorus)", "clean"),
                ("J900_CL (Marshall JCM900)", "clean"),
                ("VAVE_TS (M-VAVE ODRIVE-TS)", "overdrive"),
                ("RAT_OD (Pro Co RAT)", "overdrive"),
                ("VAVE_HTS (M-VAVE ODRIVE-TS)", "distortion"),
                ("VAVE_DS (M-VAVE MT1)", "distortion"),
                ("MS_GV2 (Marshall GV-2 Guv'nor Plus)", "distortion"),
                ("J900_HV (Marshall JCM900)", "distortion"),
                ("MS_HIGAIN (Marshall BB-2 Blues breaker)", "distortion"),
            ),
            "ir_cab": (
                None,
                ("AC-SeVin", "2x10"),
                ("JVM_1960_57", "4x12"),
                ("MESA_412", "4x12"),
                ("WANGS112", "1x12"),
                ("VOX_AC30", "2x12"),
                ("HIFI_YAMAHA", "2x10"),
                ("EGNL_412", "4x12"),
                ("V30_MD421", "1x12"),
            ),
        },
    }
)

_MANUAL = ("manual-2024", "hypothesis")

NAME_CHOICE: Mapping[str, tuple[tuple[str, str] | None, ...]] = MappingProxyType(
    {
        "amp_type": (_MANUAL,) * 9,
        "ir_cab": (None,) + (_MANUAL,) * 8,
    }
)
"""Per field, per raw position 0–8: ``(source, confidence)`` or ``None`` (no name). Spec 007
T031 (the owner's match on a fw 96 pedal) decides this; until then: the manual, unmatched."""

NAME_STATUS = "manual, not yet matched on fw 96"
"""How far the chosen names are verified, in words (docs, MCP resources)."""


def _build() -> Mapping[str, Mapping[int, PositionName]]:
    table: dict[str, Mapping[int, PositionName]] = {}
    for field in NAMED_FIELDS:
        positions: dict[int, PositionName] = {}
        for raw, choice in enumerate(NAME_CHOICE[field]):
            if choice is None:
                continue
            source, confidence = choice
            item = _LISTS[source][field][raw]
            if item is None:
                raise ValueError(f"{source} has no {field} name for raw {raw}")
            name, detail = item
            positions[raw] = PositionName(
                field, raw, name, detail, field == "ir_cab", source, confidence
            )
        table[field] = MappingProxyType(positions)
    return MappingProxyType(table)


POSITION_NAMES: Mapping[str, Mapping[int, PositionName]] = _build()
"""The names openvave shows: field → raw position → :class:`PositionName`."""


def source_list(source: str, field: str) -> tuple[tuple[str, str] | None, ...]:
    """One printed list in raw order, ``(name, detail)`` or ``None`` (for tests and docs)."""
    return _LISTS[source][field]


def position_name(field: str | None, raw: int) -> PositionName | None:
    """The name of position ``raw`` of ``field``, or ``None`` (no name, other field, out of
    range)."""
    if field is None:
        return None
    return POSITION_NAMES.get(field, {}).get(raw)


__all__ = [
    "EVIDENCE",
    "NAMED_FIELDS",
    "NAMES_FIRMWARE",
    "NAME_CHOICE",
    "NAME_SOURCES",
    "NAME_STATUS",
    "POSITION_NAMES",
    "NameSource",
    "PositionName",
    "position_name",
    "source_list",
]
