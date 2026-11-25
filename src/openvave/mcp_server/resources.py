"""Reference resources for the assistant, built from the library's tables (spec 006 FR-027).

Nothing here talks to a pedal: the documents are derived from ``WRITABLE_FIELDS``,
``WRITE_MESSAGES``, the knob-type tables and ``BYTE_MAP``, so they cannot drift from what the
library accepts.
"""

from __future__ import annotations

from typing import Any

from openvave._jsonform import position_name_json
from openvave.models import Region
from openvave.protocol import (
    BYTE_MAP,
    MAP_FIRMWARE,
    REVERB_SECTION_SIZE,
    REVERB_SECTION_STEPS,
    TYPED_FIELDS,
)
from openvave.protocol.names import NAME_STATUS, NAMED_FIELDS, POSITION_NAMES
from openvave.protocol.writes import WRITABLE_FIELDS, WritableField, sendable_by_default

POSITIONS = {"min": 1, "max": REVERB_SECTION_STEPS}


def _field(spec: WritableField) -> dict[str, Any]:
    argument = spec.offset if spec.kind == "block_switch" else None
    experimental = not sendable_by_default(spec.kind, argument, MAP_FIRMWARE)
    row: dict[str, Any] = {"name": spec.name}
    entry = spec.entry
    if spec.kind == "led_colour":
        row.update(
            kind="LED",
            label="preset LED colour",
            syntax="#rrggbb or r,g,b",
            range={"min": 0, "max": 255},
        )
    elif spec.kind == "block_switch":
        assert entry is not None
        row.update(kind="block switch", label=entry.label, syntax="on | off", range=None)
    elif spec.name in TYPED_FIELDS:
        assert entry is not None
        row.update(
            kind="typed knob",
            label=entry.label,
            syntax="TYPE:POSITION (e.g. room:18), POSITION (keeps the current type) or raw:N",
            range={"min": entry.min, "max": entry.max},
            types=list(TYPED_FIELDS[spec.name]),
            positions=POSITIONS,
        )
    else:
        assert entry is not None
        kind = "selector" if entry.encoding.value == "selector" else "knob"
        row.update(
            kind=kind,
            label=entry.label,
            syntax=f"integer {entry.min}–{entry.max}",
            range={"min": entry.min, "max": entry.max},
        )
    row["experimental"] = experimental
    row["offset"] = spec.offset
    return row


def fields_document() -> dict[str, Any]:
    """``openvave://fields``: every field ``pedal_set`` accepts."""
    return {
        "firmware": MAP_FIRMWARE,
        "fields": [_field(spec) for spec in WRITABLE_FIELDS.values()],
        "notes": (
            "pedal_set takes {field: value} with these value texts (JSON numbers and booleans "
            "are accepted too). Fields with experimental: true use a write message not yet "
            "confirmed on hardware and need experimental: true in the call (none on firmware 96 "
            "since spec 007); untested firmware needs it for every write. Edits change the "
            "current sound only (not saved; preset_reload discards them)."
        ),
    }


def effect_types_document() -> dict[str, Any]:
    """``openvave://effect-types``: the typed knobs' types and the raw values of each."""
    fields: dict[str, Any] = {}
    for name, types in TYPED_FIELDS.items():
        fields[name] = {
            "types": list(types),
            "raw_ranges": [
                {
                    "type": type_name,
                    "min": REVERB_SECTION_SIZE * i,
                    "max": REVERB_SECTION_SIZE * i + REVERB_SECTION_STEPS - 1,
                    "positions": POSITIONS,
                }
                for i, type_name in enumerate(types)
            ],
        }
    return {
        "fields": fields,
        "notes": (
            f"Each type spans {REVERB_SECTION_SIZE} raw values: positions 1–"
            f"{REVERB_SECTION_STEPS}, then {REVERB_SECTION_SIZE - REVERB_SECTION_STEPS} values "
            "between two types where the module is off. Raw = 44 × type index + position − 1."
        ),
    }


def byte_map_document() -> dict[str, Any]:
    """``openvave://byte-map``: what every byte of the global, preset and status regions means."""
    regions: dict[str, list[dict[str, Any]]] = {}
    for entry in BYTE_MAP:
        ranged = entry.min is not None and entry.max is not None
        row: dict[str, Any] = {
            "offset": entry.offset,
            "name": entry.name,
            "label": entry.label,
            "encoding": entry.encoding.value,
            "range": {"min": entry.min, "max": entry.max} if ranged else None,
            "confidence": entry.confidence,
        }
        if entry.mask is not None:
            row["mask"] = entry.mask
        if entry.labels:
            row["labels"] = {str(k): v for k, v in entry.labels.items()}
        if entry.name in NAMED_FIELDS:  # spec 007 US4: model names, with their status
            row["position_names"] = {
                str(raw): position_name_json(name)
                for raw, name in POSITION_NAMES[entry.name].items()
            }
            row["names_status"] = NAME_STATUS
        regions.setdefault(_region_key(entry.region), []).append(row)
    return {"map_firmware": MAP_FIRMWARE, "regions": regions}


def _region_key(region: Region) -> str:
    return region.name.lower()


SAFETY = """\
# openvave safety rules (MCP server)

openvave is unofficial: not affiliated with or endorsed by M-VAVE / Cuvave.

## Volatile and persistent

- **Volatile** (lost at the next preset change or power cycle): `pedal_set`, `preset_select`,
  `preset_reload`, `bypass_on` / `bypass_off`, `loopback`. They change the current sound or
  state only; nothing is saved unless `preset_save` is called.
- **Persistent** (overwrites stored presets): `preset_save`, `preset_restore`, `preset_copy`,
  `preset_swap` and `preset_import`. All need `unsafe: true` and always write a full verified
  backup to the backup folder first; if that backup fails, nothing is written. The owner may be
  asked to confirm. `preset_export` only reads the pedal (it writes a preset file into the
  backup folder for `preset_import`).

## Opt-ins (arguments of each call, never remembered)

- `dry_run: true`: plan only; the result shows the exact frames, nothing is sent.
- `experimental: true`: allows write messages not yet *confirmed* on hardware (none on firmware
  96 since spec 007: block switches, LED colour and loopback are confirmed) and any write on a
  firmware other than 96.
- `discard_edits: true`: allows losing unsaved edits of the current sound.
- `unsafe: true`: allows overwriting stored presets (save, restore, copy, swap, import).

Ask the owner before passing `unsafe` or `discard_edits`.

## Never sent

Only three commands can ever be sent: query, read, and write to a closed list of addresses.
Erase, writes to the global block and any other address cannot be encoded; openvave has no
firmware update or factory reset. A lost link is never retried inside a call: the call fails
and nothing is resent.

## One connection

The pedal accepts one Bluetooth connection. While the server holds it, the phone app cannot
connect; `pedal_disconnect` frees it (the server also releases it after a few idle minutes).
"""


__all__ = [
    "SAFETY",
    "byte_map_document",
    "effect_types_document",
    "fields_document",
]
