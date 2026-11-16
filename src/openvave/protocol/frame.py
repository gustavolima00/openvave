"""Frame codec: ``00 59 | command | len (3, LE) | body | checksum``.

Only the read-only commands may be encoded (FR-010, research R10).
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
ALLOWED_COMMANDS: frozenset[int] = frozenset({QUERY, READ})
MAX_BODY = (1 << 24) - 1


@dataclass(frozen=True)
class Frame:
    command: int
    body: bytes


def checksum(body: bytes) -> int:
    """``(~sum(body)) & 0xFF``; the 6-byte header is not summed."""
    return (~sum(body)) & 0xFF


def encode_frame(command: int, body: bytes) -> bytes:
    """Encode a frame. Raises :class:`UnsafeCommandError` for any non read-only command."""
    if command not in ALLOWED_COMMANDS:
        raise UnsafeCommandError(f"command 0x{command:02x} is not allowed (read-only: 0x11, 0x23)")
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
