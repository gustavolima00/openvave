"""Build the query/read requests and parse read replies."""

from __future__ import annotations

from openvave.errors import ProtocolError
from openvave.models import Region, RegionRead
from openvave.protocol.frame import QUERY, READ, decode_frame, encode_frame

ECHO_LEN = 8


def _read_prefix(region: Region) -> bytes:
    return (
        bytes([region.type])
        + region.address.to_bytes(4, "little")
        + region.length.to_bytes(3, "little")
    )


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
    decoded = decode_frame(frame)
    if decoded.command != READ:
        raise ProtocolError("wrong_command", f"0x{decoded.command:02x}")
    body = decoded.body
    if len(body) < ECHO_LEN:
        raise ProtocolError("short_data")
    expected = _read_prefix(region)
    for name, start, stop in (("type", 0, 1), ("address", 1, 5), ("length", 5, 8)):
        if body[start:stop] != expected[start:stop]:
            raise ProtocolError("echo_mismatch", name)
    data = body[ECHO_LEN:]
    if len(data) != region.length:
        raise ProtocolError("short_data")
    return RegionRead(region=region, data=data)
