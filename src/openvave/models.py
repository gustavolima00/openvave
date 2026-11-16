"""Immutable value types (data-model.md)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Literal

Confidence = Literal["confirmed", "observed", "hypothesis"]


class Region(Enum):
    """The closed set of memory regions this library can read (FR-008, FR-011).

    Value is ``(type, address, length)``. The read operations are confirmed on fw 96; the
    meanings of the regions are hypotheses.
    """

    DEVICE_INFO = (5, 0xD0000000, 32)
    GLOBAL = (4, 0x20000000, 4)
    CURRENT_PRESET = (4, 0x10000000, 21)
    STATUS = (4, 0xD0000000, 1)

    @property
    def type(self) -> int:
        return self.value[0]

    @property
    def address(self) -> int:
        return self.value[1]

    @property
    def length(self) -> int:
        return self.value[2]


@dataclass(frozen=True)
class DeviceInfo:
    """A pedal found by discovery."""

    identifier: str
    """Platform identifier: MAC (Linux/Windows) or CoreBluetooth UUID (macOS)."""
    name: str
    rssi: int | None = None


@dataclass(frozen=True)
class DeviceIdentity:
    """Result of the name/version handshake (command ``0x11``)."""

    raw: bytes
    name: str
    firmware: int
    firmware_untested: bool


@dataclass(frozen=True)
class RegionRead:
    """Bytes read from one region."""

    region: Region
    data: bytes


@dataclass(frozen=True)
class DeviceSnapshot:
    """Everything one connection read (what ``openvave info`` shows)."""

    device: DeviceInfo | None
    identity: DeviceIdentity
    regions: Mapping[Region, RegionRead]
    read_at: datetime


@dataclass(frozen=True)
class FieldSpec:
    """A byte whose meaning is (partly) known, with its confidence level (FR-017)."""

    offset: int
    name: str
    label: str
    confidence: Confidence


KNOWN_FIELDS: Mapping[Region, tuple[FieldSpec, ...]] = {
    Region.DEVICE_INFO: (),
    Region.GLOBAL: (FieldSpec(3, "not_in_edit_mode", "not in edit mode", "observed"),),
    Region.CURRENT_PRESET: (
        FieldSpec(6, "knob_unknown", "knob (which one: unknown)", "observed"),
        FieldSpec(16, "reverb_mix", "reverb mix?", "hypothesis"),
        FieldSpec(17, "ir_cab", "IR cab?", "hypothesis"),
    ),
    Region.STATUS: (),
}
