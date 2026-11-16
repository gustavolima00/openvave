"""Named mutations of real frames for negative tests (FR-022).

Never hand-type a reply frame in a test: start from a captured one and apply one of these.
Implemented independently of ``openvave`` so tests do not trust the code under test.
"""

from __future__ import annotations

READ = 0x23


def _checksum(body: bytes) -> int:
    return (~sum(body)) & 0xFF


def _rebuild(frame: bytes, body: bytes) -> bytes:
    return frame[:3] + len(body).to_bytes(3, "little") + body + bytes([_checksum(body)])


def _body(frame: bytes) -> bytes:
    return frame[6:-1]


def flip_checksum(frame: bytes) -> bytes:
    """Invert the checksum byte; everything else unchanged."""
    return frame[:-1] + bytes([frame[-1] ^ 0xFF])


def set_command(frame: bytes, command: int) -> bytes:
    """Replace the command byte (offset 2). The checksum stays valid (header is not summed)."""
    return frame[:2] + bytes([command]) + frame[3:]


def set_echo(
    frame: bytes,
    *,
    type: int | None = None,  # noqa: A002 - mirrors the protocol field name
    address: int | None = None,
    length: int | None = None,
) -> bytes:
    """Rewrite fields of a read reply's 8-byte echo prefix; checksum recomputed."""
    body = bytearray(_body(frame))
    if type is not None:
        body[0] = type
    if address is not None:
        body[1:5] = address.to_bytes(4, "little")
    if length is not None:
        body[5:8] = length.to_bytes(3, "little")
    return _rebuild(frame, bytes(body))


def with_payload(frame: bytes, payload: bytes) -> bytes:
    """Replace the payload; length field and checksum recomputed.

    For a read (``0x23``) frame the payload is the data after the 8-byte echo prefix (the prefix
    is kept); for any other command it is the whole body.
    """
    if frame[2] == READ:
        body = _body(frame)[:8] + payload
    else:
        body = payload
    return _rebuild(frame, body)


def truncate(frame: bytes, n: int) -> bytes:
    """Keep only the first ``n`` bytes."""
    return frame[:n]


def split(frame: bytes, n: int) -> list[bytes]:
    """Split into ``n`` non-empty chunks (sizes differ by at most one) that concatenate back."""
    if not 1 <= n <= len(frame):
        raise ValueError(f"n must be in 1..{len(frame)}, got {n}")
    size, extra = divmod(len(frame), n)
    chunks: list[bytes] = []
    pos = 0
    for i in range(n):
        step = size + (1 if i < extra else 0)
        chunks.append(frame[pos : pos + step])
        pos += step
    return chunks
