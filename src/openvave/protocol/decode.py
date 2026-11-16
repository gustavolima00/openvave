"""Apply the byte map to region bytes (pure: no I/O, no logging; FR-013).

Bytes outside an encoding's range are flagged, never clamped (FR-015). Bytes from a firmware
other than :data:`MAP_FIRMWARE` are decoded with the same map and marked untested (FR-018).
"""

from __future__ import annotations

from collections.abc import Iterable

from openvave.models import (
    ByteChange,
    ByteMapEntry,
    DecodedField,
    DecodedRegion,
    Encoding,
    RegionRead,
)
from openvave.protocol.bytemap import BYTE_MAP, MAP_FIRMWARE


def _named(entries: Iterable[ByteMapEntry]) -> list[ByteMapEntry]:
    return [e for e in entries if e.name is not None]


def _sort_key(entry: ByteMapEntry) -> tuple[int, int]:
    return (entry.offset, entry.mask or 0)


def decode_field(entry: ByteMapEntry, raw: int) -> DecodedField:
    """Interpret one byte with one named map entry."""
    value = raw & entry.mask if entry.mask is not None else raw
    interpreted: int | bool = value
    out_of_range = False
    display = str(value)
    encoding = entry.encoding
    if encoding is Encoding.FLAG:
        interpreted = value != 0
        display = "on" if interpreted else "off"
    elif encoding is Encoding.SWITCH:
        if value == entry.on_value:
            interpreted, display = True, "on"
        elif value == entry.off_value:
            interpreted, display = False, "off"
        else:
            out_of_range = True
    elif encoding in (Encoding.CONTINUOUS, Encoding.SELECTOR, Encoding.INDEX):
        assert entry.min is not None and entry.max is not None
        out_of_range = not entry.min <= value <= entry.max
        if encoding is Encoding.SELECTOR and not out_of_range:
            display = entry.labels.get(value, f"#{value}")
    else:  # UNKNOWN entries are never decoded as fields
        raise ValueError(f"cannot decode an unknown entry: {entry}")
    return DecodedField(
        entry=entry,
        raw=raw,
        value=value,
        interpreted=interpreted,
        display=display,
        out_of_range=out_of_range,
    )


def decode_region(read: RegionRead, firmware: int) -> DecodedRegion:
    """Decode every named byte of ``read`` with :data:`BYTE_MAP`.

    ``firmware`` is the pedal's firmware version; when it is not :data:`MAP_FIRMWARE` the result
    is marked ``firmware_untested``. Device info has no entries: no fields, every offset unknown.
    """
    data = read.data
    entries = sorted(
        (e for e in _named(BYTE_MAP) if e.region is read.region and e.offset < len(data)),
        key=_sort_key,
    )
    named_offsets = {e.offset for e in entries}
    return DecodedRegion(
        read=read,
        fields=tuple(decode_field(e, data[e.offset]) for e in entries),
        unknown_offsets=tuple(i for i in range(len(data)) if i not in named_offsets),
        map_firmware=MAP_FIRMWARE,
        firmware_untested=firmware != MAP_FIRMWARE,
    )


def diff(before: RegionRead, after: RegionRead) -> tuple[ByteChange, ...]:
    """One :class:`ByteChange` per differing byte, in offset order.

    Raises ``ValueError`` if the two reads are of different regions or lengths.
    """
    if before.region is not after.region or len(before.data) != len(after.data):
        raise ValueError("diff needs two reads of the same region")
    named = _named(BYTE_MAP)
    changes: list[ByteChange] = []
    for offset, (old, new) in enumerate(zip(before.data, after.data, strict=True)):
        if old == new:
            continue
        on_byte = tuple(
            sorted(
                (e for e in named if e.region is before.region and e.offset == offset),
                key=_sort_key,
            )
        )
        whole = next((e for e in on_byte if e.mask is None), None)
        changes.append(ByteChange(before.region, offset, old, new, field=whole, fields=on_byte))
    return tuple(changes)
