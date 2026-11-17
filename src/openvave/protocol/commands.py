"""Build the query/read requests and parse read replies."""

from __future__ import annotations

from typing import Protocol

from openvave.errors import ProtocolError
from openvave.models import Region, RegionRead
from openvave.protocol.frame import QUERY, READ, decode_frame, encode_frame
from openvave.protocol.storage import StorageRead

ECHO_LEN = 8


class ReadTarget(Protocol):
    """What a read request needs: satisfied by :class:`Region` and :class:`StorageRead`."""

    @property
    def type(self) -> int: ...

    @property
    def address(self) -> int: ...

    @property
    def length(self) -> int: ...


def _read_prefix(target: ReadTarget) -> bytes:
    return (
        bytes([target.type])
        + target.address.to_bytes(4, "little")
        + target.length.to_bytes(3, "little")
    )


def _read_data(target: ReadTarget, frame: bytes) -> bytes:
    decoded = decode_frame(frame)
    if decoded.command != READ:
        raise ProtocolError("wrong_command", f"0x{decoded.command:02x}")
    body = decoded.body
    if len(body) < ECHO_LEN:
        raise ProtocolError("short_data")
    expected = _read_prefix(target)
    for name, start, stop in (("type", 0, 1), ("address", 1, 5), ("length", 5, 8)):
        if body[start:stop] != expected[start:stop]:
            raise ProtocolError("echo_mismatch", name)
    data = body[ECHO_LEN:]
    if len(data) != target.length:
        raise ProtocolError("short_data")
    return data


def build_query() -> bytes:
    """The name/version handshake request: ``00 59 11 00 00 00 ff``."""
    return encode_frame(QUERY, b"")


def build_read(region: Region) -> bytes:
    """Read request for one of the four known regions. There is no address-based variant."""
    if not isinstance(region, Region):
        raise TypeError(f"region must be a Region member, not {type(region).__name__}")
    return encode_frame(READ, _read_prefix(region))


def parse_read_reply(region: Region, frame: bytes) -> RegionRead:
    """Validate a read reply against the request for ``region`` and return its data."""
    return RegionRead(region=region, data=_read_data(region, frame))


def build_storage_read(target: StorageRead) -> bytes:
    """Read request for a stored-image target (header, stored preset ``i`` or whole image)."""
    if not isinstance(target, StorageRead):
        raise TypeError(f"target must be a StorageRead, not {type(target).__name__}")
    return encode_frame(READ, _read_prefix(target))


def parse_storage_reply(target: StorageRead, frame: bytes) -> bytes:
    """Validate a storage read reply against ``target`` and return its data bytes.

    Same checks and error codes as :func:`parse_read_reply` (``wrong_command``,
    ``echo_mismatch``, ``short_data``, plus the frame errors of ``decode_frame``).
    """
    if not isinstance(target, StorageRead):
        raise TypeError(f"target must be a StorageRead, not {type(target).__name__}")
    return _read_data(target, frame)
