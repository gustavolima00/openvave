"""Tool results: the CLI's ``--json`` documents plus a short ``summary`` (research R6)."""

from __future__ import annotations

from typing import Any

from openvave.cli.render import type_reading
from openvave.models import ByteChange
from openvave.protocol import TYPED_FIELDS, type_parts
from openvave.protocol.decode import decode_field


def with_summary(document: dict[str, Any], human: str) -> dict[str, Any]:
    """``document`` with ``summary``: the first non-empty line of the CLI's human output."""
    summary = next((line.strip() for line in human.splitlines() if line.strip()), "")
    return {"summary": summary, **document}


def add_knob_types(region: dict[str, Any]) -> dict[str, Any]:
    """Add ``knob_type`` / ``knob_position`` to the typed knobs of a ``region_json`` document
    (in place; additive to the CLI's JSON, which keeps the raw value only). Between two types
    both are ``None`` (the module is off there)."""
    for field in region.get("fields", []):
        name, value = field.get("name"), field.get("value")
        if name in TYPED_FIELDS and isinstance(value, int) and not field.get("out_of_range"):
            field["knob_type"], field["knob_position"] = type_parts(name, value)
    return region


def change_json(change: ByteChange) -> dict[str, Any]:
    """One changed byte of ``pedal_changes``: name, raw before/after and their display form
    (``5 (room 6)`` for a typed knob, hex for an unknown or flag byte)."""
    entry = change.field
    if entry is not None:
        before, after = (decode_field(entry, raw) for raw in (change.old, change.new))
        display = tuple(
            f.display if type_reading(f) is None else f"{f.display} ({type_reading(f)})"
            for f in (before, after)
        )
        name: str | None = entry.name
    else:
        display = (f"0x{change.old:02x}", f"0x{change.new:02x}")
        name = None
    return {
        "region": change.region.name.lower(),
        "offset": change.offset,
        "name": name,
        "before": change.old,
        "after": change.new,
        "display_before": display[0],
        "display_after": display[1],
    }


def change_label(change: ByteChange) -> str:
    """The human name of a changed byte (``gain``, ``reverb decay``, ``unknown byte``)."""
    if change.field is not None:
        return change.field.label
    return " / ".join(e.label for e in change.fields) if change.fields else "unknown byte"


__all__ = ["add_knob_types", "change_json", "change_label", "with_summary"]
