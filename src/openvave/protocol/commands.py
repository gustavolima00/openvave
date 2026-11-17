"""Build the query/read/write requests and parse their replies."""

from __future__ import annotations

from typing import Protocol

from openvave.errors import ProtocolError, WriteNakError
from openvave.models import Region, RegionRead
from openvave.protocol.frame import QUERY, READ, WRITE, decode_frame, encode_frame
from openvave.protocol.storage import StorageRead
from openvave.protocol.writes import WriteTarget, check_write_data

ECHO_LEN = 8
ACK_LEN = 8
ACK_COMMAND = 0x00
ACK_STATUS = 0x00


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


def build_write(target: WriteTarget, data: bytes) -> bytes:
    """The ``0x22`` frame writing ``data`` to an allowlisted ``target``: the only way to encode one.

    Raises :class:`TypeError` if ``target`` is not a :class:`WriteTarget` and :class:`ValueError`
    if ``data`` has the wrong length (or is not ``01`` for a preset select).
    """
    if not isinstance(target, WriteTarget):
        raise TypeError(f"target must be a WriteTarget, not {type(target).__name__}")
    data = bytes(data)
    check_write_data(target, data)
    return encode_frame(WRITE, _read_prefix(target) + data)


def parse_write_reply(frame: bytes) -> None:
    """Accept the write ACK ``00 59 00 01 00 00 00 ff``; anything else raises (spec 003 R3).

    Frame errors (marker, length, checksum) raise :class:`ProtocolError` as for any reply. A
    well-formed reply that is not 8 bytes with command byte ``00`` and status ``00`` raises
    :class:`WriteNakError` carrying the raw bytes.
    """
    decoded = decode_frame(frame)
    if len(frame) != ACK_LEN or decoded.command != ACK_COMMAND or decoded.body[0] != ACK_STATUS:
        raise WriteNakError(bytes(frame))
