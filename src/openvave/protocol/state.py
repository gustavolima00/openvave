"""Pedal state from the global block and the edit buffer (pure, spec 004 research R1).

| State | Rule |
|---|---|
| ``bypass`` | slot = ``ff`` and the buffer is 21 × ``00`` (bank 0–8) |
| ``tuner`` | mode = 2 |
| ``normal`` | mode = 1, slot 0–3, bank 0–8, buffer not all zero |
| ``edit`` | mode = 0, slot 0–3, bank 0–8, buffer not all zero |
| ``unrecognised`` | anything else |

One read cannot tell bypass from the one-cycle loading transient (same bytes); the session
confirms ``bypass`` with a second read (:meth:`openvave.TankG.state`). Mirrors "Pedal state" in
``specs/protocol/command-layer.md``.
"""

from __future__ import annotations

from openvave.models import PedalState, Region

EDIT, NORMAL, TUNER = 0, 1, 2
"""Global byte 3 (``mode``) values."""
LOADING_SLOT = 0xFF
"""Global byte 2 while a preset loads, and while the pedal is bypassed."""
BANKS = 9
SLOTS = 4


def classify(global_bytes: bytes, buffer: bytes) -> PedalState:
    """Classify one read of the global block (4 B) and the edit buffer (21 B).

    Raises :class:`ValueError` for data of the wrong length.
    """
    if len(global_bytes) != Region.GLOBAL.length:
        raise ValueError(f"global block must be 4 bytes, got {len(global_bytes)}")
    if len(buffer) != Region.CURRENT_PRESET.length:
        raise ValueError(f"edit buffer must be 21 bytes, got {len(buffer)}")
    bank, slot, mode = global_bytes[1], global_bytes[2], global_bytes[3]
    known_bank = bank if bank < BANKS else None
    empty = not any(buffer)
    if slot == LOADING_SLOT:
        if empty and known_bank is not None:
            return PedalState(kind="bypass", index=None, bank=known_bank)
        return PedalState(kind="unrecognised", index=None, bank=known_bank)
    index = bank * SLOTS + slot if known_bank is not None and slot < SLOTS else None
    if mode == TUNER:
        return PedalState(kind="tuner", index=index, bank=known_bank)
    if mode not in (EDIT, NORMAL) or index is None or empty:
        return PedalState(kind="unrecognised", index=None, bank=known_bank)
    return PedalState(kind="edit" if mode == EDIT else "normal", index=index, bank=known_bank)
