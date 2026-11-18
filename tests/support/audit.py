"""Command audit for every frame the test suite sends (SC-004 of 001, FR-013 of 003).

Allowed: ``0x11`` (query), ``0x23`` (read) and ``0x22`` (write) **only** to the spec 003 write
allowlist plus the two volatile kinds of spec 004 M1, written here independently of
``openvave.protocol.writes`` so a widened library allowlist fails the audit:

- type 4, ``0x10000004`` × 14 (knob block)
- type 4, ``0x10000000 + k`` × 1, k = 0–3 (block switch)
- type 4, ``0x10000012`` × 3 (LED colour)
- type 4, ``0xE0000000 + i`` × 1, i = 0–35, data ``01`` (preset select)
- type 4, ``0xE1000000 + i`` × 1, i = 0–35, data ``01`` (bypass, spec 004)
- type 4, ``0xD0000000`` × 1, data ``00`` or ``01`` (loopback, spec 004)

Never allowed: erase ``0x21``, the commit (``0xF0000000``), stored-area writes (addresses
``0``–``0x2F5``), or any other command byte.
"""

from __future__ import annotations

from collections.abc import Iterable

READ_ONLY_COMMANDS = frozenset({0x11, 0x23})
WRITE = 0x22
ALLOWED_COMMANDS = READ_ONLY_COMMANDS | {WRITE}
WRITE_SHAPES: frozenset[tuple[int, int, int]] = frozenset(
    {(4, 0x10000004, 14), (4, 0x10000012, 3)}
    | {(4, 0x10000000 + k, 1) for k in range(4)}
    | {(4, 0xE0000000 + i, 1) for i in range(36)}
    | {(4, 0xE1000000 + i, 1) for i in range(36)}
    | {(4, 0xD0000000, 1)}
)


def allowed_write(frame: bytes) -> bool:
    """True iff ``frame`` is a well-formed ``0x22`` frame to an allowlisted target."""
    body = frame[6:-1]
    if len(frame) < 15 or frame[2] != WRITE or int.from_bytes(frame[3:6], "little") != len(body):
        return False
    shape = (body[0], int.from_bytes(body[1:5], "little"), int.from_bytes(body[5:8], "little"))
    data = body[8:]
    if shape not in WRITE_SHAPES or len(data) != shape[2]:
        return False
    if 0xE0000000 <= shape[1] < 0xE0000000 + 36 or 0xE1000000 <= shape[1] < 0xE1000000 + 36:
        return data == b"\x01"
    if shape[1] == 0xD0000000:
        return data in (b"\x00", b"\x01")
    return True


def unsafe_frames(frames: Iterable[bytes]) -> list[bytes]:
    """Frames with a command byte other than ``0x11``/``0x23``, or a ``0x22`` off the allowlist."""
    unsafe = []
    for f in frames:
        if len(f) < 3 or f[2] not in ALLOWED_COMMANDS:
            unsafe.append(f)
        elif f[2] == WRITE and not allowed_write(f):
            unsafe.append(f)
    return unsafe
