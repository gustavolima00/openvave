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
        """Region type byte of the read request."""
        return self.value[0]

    @property
    def address(self) -> int:
        """32-bit region address of the read request."""
        return self.value[1]

    @property
    def length(self) -> int:
        """Number of data bytes the read returns."""
        return self.value[2]


@dataclass(frozen=True)
class DeviceInfo:
    """A pedal found by discovery."""

    identifier: str
    """Platform identifier: MAC (Linux/Windows) or CoreBluetooth UUID (macOS)."""
    name: str
    """Advertised local name (``TANK-Gv2_BLE``)."""
    rssi: int | None = None
    """Signal strength at discovery, in dBm, when known."""


@dataclass(frozen=True)
class DeviceIdentity:
    """Result of the name/version handshake (command ``0x11``)."""

    raw: bytes
    """The handshake payload as received."""
    name: str
    """Device name, e.g. ``TANK-Gv2``."""
    firmware: int
    """Firmware version, e.g. ``96``."""
    firmware_untested: bool
    """True when :attr:`firmware` is not in ``TESTED_FIRMWARE``; byte layouts may differ."""


@dataclass(frozen=True)
class RegionRead:
    """Bytes read from one region."""

    region: Region
    """The region that was read."""
    data: bytes
    """Raw data bytes (``region.length`` of them), echo header stripped."""


@dataclass(frozen=True)
class DeviceSnapshot:
    """Everything one connection read (what ``openvave info`` shows)."""

    device: DeviceInfo | None
    """The discovered device, or ``None`` when the transport was supplied directly."""
    identity: DeviceIdentity
    """Handshake result."""
    regions: Mapping[Region, RegionRead]
    """All four regions, in read order."""
    read_at: datetime
    """Timezone-aware UTC time taken after the last read."""


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
        FieldSpec(15, "reverb_decay", "reverb decay", "observed"),
        FieldSpec(16, "reverb_mix", "reverb mix?", "hypothesis"),
        FieldSpec(17, "ir_cab", "IR cab?", "hypothesis"),
    ),
    Region.STATUS: (),
}
