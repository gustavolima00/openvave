"""Immutable value types (data-model.md)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Literal

from openvave.errors import ProtocolError

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


class Encoding(Enum):
    """How a mapped byte is interpreted (closed set; research R2, data-model.md)."""

    CONTINUOUS = "continuous"
    """Integer ``min..max`` (a knob)."""
    SWITCH = "switch"
    """On/off; ``on_value`` and ``off_value`` give the raw values."""
    SELECTOR = "selector"
    """Position ``min..max`` of a stepped control, with optional labels."""
    FLAG = "flag"
    """One bit (``mask``) of a byte that packs several switches."""
    INDEX = "index"
    """A position (base stated in the notes), e.g. a preset number."""
    UNKNOWN = "unknown"
    """No known meaning; the raw value only."""


@dataclass(frozen=True)
class ByteMapEntry:
    """One row of the byte map, mirrored from ``specs/protocol/command-layer.md``."""

    region: Region
    """``GLOBAL``, ``CURRENT_PRESET`` or ``STATUS`` (device info is not mapped)."""
    offset: int
    """Data offset within the region (``0 <= offset < region.length``)."""
    encoding: Encoding
    """How the byte is interpreted."""
    firmware: int
    """Firmware the evidence came from."""
    name: str | None = None
    """Stable snake_case machine name; ``None`` iff the encoding is ``UNKNOWN``."""
    label: str = ""
    """Human label in our own words."""
    mask: int | None = None
    """``None`` for a whole byte; a non-zero 8-bit mask for ``FLAG`` entries."""
    min: int | None = None
    """Lowest valid value (``CONTINUOUS``, ``SELECTOR``, ``INDEX``)."""
    max: int | None = None
    """Highest valid value (``CONTINUOUS``, ``SELECTOR``, ``INDEX``)."""
    on_value: int | None = None
    """Raw value meaning "on" (``SWITCH``)."""
    off_value: int | None = None
    """Raw value meaning "off" (``SWITCH``)."""
    labels: Mapping[int, str] = field(default_factory=dict, hash=False)
    """Optional position labels (``SELECTOR`` only), in our own words."""
    control: str | None = None
    """The physical control this byte follows, if linked."""
    confidence: Confidence | None = None
    """Evidence level; ``None`` iff the encoding is ``UNKNOWN``."""
    evidence: tuple[str, ...] = ()
    """Committed capture paths supporting the row."""
    notes: str = ""
    """Values seen, controls tried, refuted claims."""


@dataclass(frozen=True)
class DecodedField:
    """A named :class:`ByteMapEntry` applied to the bytes of one read."""

    entry: ByteMapEntry
    """The map row."""
    raw: int
    """The whole byte."""
    value: int
    """``raw``, or ``raw & mask`` for flags (same meaning as 001's JSON ``value``)."""
    interpreted: int | bool
    """Value per encoding (bool for switches and flags)."""
    display: str
    """Human form; the raw value when :attr:`out_of_range`."""
    out_of_range: bool
    """True when the byte breaks the encoding's range rule (never clamped, FR-015)."""


@dataclass(frozen=True)
class DecodedRegion:
    """A region read decoded with the byte map."""

    read: RegionRead
    """The raw read, unchanged."""
    fields: tuple[DecodedField, ...]
    """Named fields in offset (then mask) order."""
    unknown_offsets: tuple[int, ...]
    """Offsets with no named entry."""
    map_firmware: int
    """Firmware the map was built from."""
    firmware_untested: bool
    """True when decoding bytes from a firmware other than :attr:`map_firmware` (FR-018)."""


@dataclass(frozen=True)
class ByteChange:
    """One byte that differs between two reads of the same region."""

    region: Region
    """The region."""
    offset: int
    """Data offset."""
    old: int
    """Value before."""
    new: int
    """Value after (``!= old``)."""
    field: ByteMapEntry | None = None
    """The whole-byte entry, or ``None`` if the byte is unknown or holds flags."""
    fields: tuple[ByteMapEntry, ...] = ()
    """Every named entry on this byte (one whole-byte entry or several flags)."""


@dataclass(frozen=True)
class WatchStart:
    """First event of :meth:`TankG.watch`: every watched region read once (the baseline)."""

    t: float
    """Seconds since the watch started (monotonic clock)."""
    identity: DeviceIdentity
    """Handshake result of the session."""
    regions: Mapping[Region, DecodedRegion]
    """Each watched region, decoded, in poll order."""


@dataclass(frozen=True)
class WatchChange:
    """A poll cycle whose bytes differ from the previous cycle (all changes of one cycle)."""

    t: float
    """Seconds since the watch started (monotonic clock)."""
    cycle: int
    """Poll cycle number; the baseline cycle of :class:`WatchStart` is 1."""
    changes: tuple[ByteChange, ...]
    """Every changed byte of the cycle (at least one), in poll order then offset order."""
    regions: Mapping[Region, DecodedRegion]
    """Each watched region after the change, decoded, in poll order."""


WatchEvent = WatchStart | WatchChange
"""What :meth:`TankG.watch` yields."""


@dataclass(frozen=True)
class StoredPreset:
    """One of the 36 stored presets read by :meth:`TankG.backup`."""

    index: int
    """0–35 (``bank·4 + slot``)."""
    position: str
    """``"1A"`` … ``"9D"``."""
    data: bytes
    """The 21 stored bytes."""
    decoded: DecodedRegion
    """``data`` decoded with the current-preset byte map."""


@dataclass(frozen=True)
class Backup:
    """A verified copy of the stored-preset image (spec 003, US1).

    Construction checks the invariant ``image == header + presets[0].data + … + presets[35].data``
    and raises :class:`~openvave.errors.ProtocolError` (``backup_mismatch``, detail naming the
    differing positions) when it does not hold.
    """

    identity: DeviceIdentity
    """Handshake result of the session that read it."""
    created_at: datetime
    """Timezone-aware UTC time taken after the last read."""
    header: bytes
    """The 2 header bytes (``a5 5a`` expected)."""
    image: bytes
    """The 758-byte whole-image read, exactly as received."""
    presets: tuple[StoredPreset, ...]
    """The 36 single preset reads, in index order."""
    warnings: tuple[str, ...] = ()
    """``unexpected_header`` and/or ``untested_firmware``."""

    def __post_init__(self) -> None:
        from openvave.protocol.storage import (
            IMAGE_SIZE,
            PRESET_COUNT,
            PRESET_SIZE,
            STORE_OFFSET,
            position,
        )

        if len(self.header) != STORE_OFFSET or len(self.image) != IMAGE_SIZE:
            raise ValueError(f"header must be {STORE_OFFSET} and image {IMAGE_SIZE} bytes")
        if [p.index for p in self.presets] != list(range(PRESET_COUNT)):
            raise ValueError(f"presets must be the {PRESET_COUNT} stored presets in index order")
        differing = [] if self.image[:STORE_OFFSET] == self.header else ["header"]
        for preset in self.presets:
            start = STORE_OFFSET + PRESET_SIZE * preset.index
            if preset.position != position(preset.index):
                raise ValueError(f"preset {preset.index} has position {preset.position!r}")
            if self.image[start : start + PRESET_SIZE] != preset.data:
                differing.append(preset.position)
        if differing:
            raise ProtocolError(
                "backup_mismatch",
                ", ".join(differing),
                "whole-image read differs from the single reads at " + ", ".join(differing),
            )

    def to_document(self) -> dict[str, Any]:
        """The backup file document (``specs/003-preset-backup-edit-writes/contracts/``)."""
        from openvave import __version__
        from openvave.backup import to_document

        return to_document(self, __version__)

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> Backup:
        """Rebuild a backup from its document; checks kind, format version and invariants."""
        from openvave.backup import from_document

        return from_document(document)


@dataclass(frozen=True)
class FieldSpec:
    """Deprecated (001): a known byte. Use :class:`ByteMapEntry` / ``BYTE_MAP`` instead."""

    offset: int
    name: str
    label: str
    confidence: Confidence


def _known_fields() -> Mapping[Region, tuple[FieldSpec, ...]]:
    from openvave.protocol.bytemap import BYTE_MAP

    return {
        region: tuple(
            FieldSpec(
                e.offset,
                e.name,
                e.label + ("?" if e.confidence == "hypothesis" else ""),
                e.confidence,
            )
            for e in BYTE_MAP
            if e.region is region and e.name is not None and e.confidence is not None
        )
        for region in Region
    }


def __getattr__(name: str) -> object:
    # Deprecated 001 alias, derived from BYTE_MAP lazily (protocol.bytemap imports this module).
    if name == "KNOWN_FIELDS":
        return _known_fields()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
