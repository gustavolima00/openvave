"""Frame codec: ``00 59 | command | len (3, LE) | body | checksum``.

Only the query and read commands, and writes to the spec 003 allowlist, may be encoded (001
FR-010, 003 FR-013 / research R2). Erase (``0x21``) and every other command byte are refused.
"""

from __future__ import annotations

from dataclasses import dataclass

from openvave.errors import ProtocolError, UnsafeCommandError

MARKER = b"\x00\x59"
HEADER_LEN = 6
QUERY = 0x11
"""Query device name and firmware version."""
READ = 0x23
"""Read ``length`` bytes of a memory region."""
WRITE = 0x22
"""Write ``length`` bytes. Only to an allowlisted target: build these with
:func:`openvave.protocol.commands.build_write`; :func:`encode_frame` refuses any other body."""
ALLOWED_COMMANDS: frozenset[int] = frozenset({QUERY, READ, WRITE})
MAX_BODY = (1 << 24) - 1


@dataclass(frozen=True)
class Frame:
    command: int
    body: bytes


def checksum(body: bytes) -> int:
    """``(~sum(body)) & 0xFF``; the 6-byte header is not summed."""
    return (~sum(body)) & 0xFF


def encode_frame(command: int, body: bytes) -> bytes:
    """Encode a frame.

    Raises :class:`UnsafeCommandError` for a command byte outside :data:`ALLOWED_COMMANDS`, and
    for a ``0x22`` body that is not a write to the allowlist of
    :mod:`openvave.protocol.writes` (knob block, block switch, LED colour, preset select).
    """
    if command not in ALLOWED_COMMANDS:
        raise UnsafeCommandError(
            f"command 0x{command:02x} is not allowed (allowed: 0x11, 0x23, allowlisted 0x22)"
        )
    if command == WRITE:
        from openvave.protocol.writes import allowed_write_body

        if not allowed_write_body(body):
            raise UnsafeCommandError(f"write body {body.hex(' ')!r} is not an allowlisted target")
    if len(body) > MAX_BODY:
        raise ValueError("body too long")
    return (
        MARKER + bytes([command]) + len(body).to_bytes(3, "little") + body + bytes([checksum(body)])
    )


def body_length(header: bytes | bytearray) -> int:
    """Body length from a frame header (at least 6 bytes)."""
    return int.from_bytes(header[3:6], "little")


def decode_frame(data: bytes | bytearray) -> Frame:
    """Decode one complete frame. Any command byte is accepted here."""
    if data[:2] != MARKER:
        raise ProtocolError("bad_marker")
    if len(data) < HEADER_LEN + 1 or len(data) != HEADER_LEN + body_length(data) + 1:
        raise ProtocolError("length_mismatch")
    body = bytes(data[HEADER_LEN:-1])
    if data[-1] != checksum(body):
        raise ProtocolError("bad_checksum")
    return Frame(command=data[2], body=body)
