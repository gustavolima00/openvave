"""SC-004 audit: no frame sent during the test run may carry a non read-only command byte."""

from __future__ import annotations

from collections.abc import Iterable

READ_ONLY_COMMANDS = frozenset({0x11, 0x23})


def unsafe_frames(frames: Iterable[bytes]) -> list[bytes]:
    """Frames whose command byte (offset 2) is not ``0x11``/``0x23`` (or that are too short)."""
    return [f for f in frames if len(f) < 3 or f[2] not in READ_ONLY_COMMANDS]
