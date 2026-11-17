"""Stored-preset image layout and the closed set of storage reads (pure data).

Layout (``specs/protocol/command-layer.md`` "Storage layout", confirmed read-only on fw 96,
2026-11-17): the image lives at type 4, address 0; two header bytes (``a5 5a`` on hardware, meaning
unknown) followed by 36 stored presets of 21 bytes each, preset ``i`` at address ``2 + 21·i``.
Preset ``i`` is bank ``i // 4 + 1``, slot ``A``–``D`` = ``i % 4`` (position ``1A``…``9D``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

STORAGE_TYPE = 4
"""Region type byte of every storage read."""
STORE_OFFSET = 2
"""Address of stored preset 0 (after the 2 header bytes)."""
PRESET_SIZE = 21
"""Bytes per stored preset (= ``Region.CURRENT_PRESET.length``)."""
PRESET_COUNT = 36
"""9 banks × 4 slots."""
IMAGE_SIZE = STORE_OFFSET + PRESET_SIZE * PRESET_COUNT
"""758 bytes: header + 36 presets."""
EXPECTED_HEADER = bytes.fromhex("a5 5a")
"""Header seen on hardware (2026-11-17); its meaning is unknown."""
SLOTS = "ABCD"

_POSITION = re.compile(r"^([1-9])([A-Da-d])$")
_INDEX = re.compile(r"^[0-9]{1,2}$")


def _check_index(index: int) -> None:
    if isinstance(index, bool) or not isinstance(index, int):
        raise TypeError(f"preset index must be an int, not {type(index).__name__}")
    if not 0 <= index < PRESET_COUNT:
        raise ValueError(f"preset index must be 0–{PRESET_COUNT - 1}, got {index}")


def position(index: int) -> str:
    """``0 → "1A"``, ``6 → "2C"``, ``35 → "9D"``."""
    _check_index(index)
    return f"{index // 4 + 1}{SLOTS[index % 4]}"


def parse_position(text: str) -> int:
    """``"2C"`` / ``"2c"`` / ``"6"`` → 6. Raises :class:`ValueError` for anything else."""
    match = _POSITION.match(text)
    if match:
        return (int(match.group(1)) - 1) * 4 + SLOTS.index(match.group(2).upper())
    if _INDEX.match(text):
        index = int(text)
        if index < PRESET_COUNT:
            return index
    raise ValueError(f"invalid preset position {text!r} (expected 1A–9D or 0–{PRESET_COUNT - 1})")


_KEY = object()


def _preset_shape(index: int | None) -> tuple[int, int, int, int | None] | None:
    if index is None:
        return None
    return (STORAGE_TYPE, STORE_OFFSET + PRESET_SIZE * index, PRESET_SIZE, index)


@dataclass(frozen=True)
class StorageRead:
    """One storage read target. Built only by :meth:`header`, :meth:`preset` and :meth:`image`.

    There is no constructor taking an address: like :class:`~openvave.models.Region`, the set of
    readable targets is closed.
    """

    type: int
    """Region type byte of the read request (always 4)."""
    address: int
    """Start address within the stored image."""
    length: int
    """Number of data bytes the read returns."""
    index: int | None
    """Stored preset index for :meth:`preset` targets, else ``None``."""
    _key: object = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        # The key stops direct construction; the shape check stops dataclasses.replace().
        if self._key is not _KEY or (self.type, self.address, self.length, self.index) not in (
            (STORAGE_TYPE, 0, STORE_OFFSET, None),
            (STORAGE_TYPE, 0, IMAGE_SIZE, None),
            _preset_shape(self.index),
        ):
            raise TypeError("StorageRead is built only by header(), preset(i) or image()")

    @classmethod
    def header(cls) -> StorageRead:
        """The 2 header bytes (type 4, address 0, length 2)."""
        return cls(STORAGE_TYPE, 0, STORE_OFFSET, None, _KEY)

    @classmethod
    def preset(cls, index: int) -> StorageRead:
        """Stored preset ``index`` (0–35): type 4, address ``2 + 21·index``, length 21."""
        _check_index(index)
        return cls(STORAGE_TYPE, STORE_OFFSET + PRESET_SIZE * index, PRESET_SIZE, index, _KEY)

    @classmethod
    def image(cls) -> StorageRead:
        """The whole image (type 4, address 0, length 758)."""
        return cls(STORAGE_TYPE, 0, IMAGE_SIZE, None, _KEY)
