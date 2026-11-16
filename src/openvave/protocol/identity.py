"""Parse the name/version handshake reply (command ``0x11``).

The 27-byte payload is ASCII ``<name>_<version>`` padded with NULs, e.g. ``TANK-Gv2_096``
(confirmed on fw 96, ``captures/fw96/20261116-probe-connect.jsonl``).
"""

from __future__ import annotations

from openvave.errors import ProtocolError
from openvave.models import DeviceIdentity

TESTED_FIRMWARE: frozenset[int] = frozenset({96})
"""Firmware versions this library has been verified against on hardware."""

IDENTITY_LEN = 27


def parse_identity(payload: bytes) -> DeviceIdentity:
    """Turn the handshake payload into a :class:`DeviceIdentity`.

    Raises :class:`ProtocolError` with reason ``bad_identity`` if the payload is not 27 bytes,
    is not ASCII before the first NUL, has no ``_``, or has a non-numeric version.
    """
    payload = bytes(payload)
    if len(payload) != IDENTITY_LEN:
        raise ProtocolError("bad_identity", f"length {len(payload)}, expected {IDENTITY_LEN}")
    text_bytes = payload.split(b"\x00", 1)[0]
    try:
        text = text_bytes.decode("ascii")
    except UnicodeDecodeError:
        raise ProtocolError("bad_identity", "not ASCII") from None
    name, sep, version = text.rpartition("_")
    if not sep or not name:
        raise ProtocolError("bad_identity", "no '_' separator")
    if not version.isdigit() or not version.isascii():
        raise ProtocolError("bad_identity", f"non-numeric version {version!r}")
    firmware = int(version)
    return DeviceIdentity(
        raw=payload,
        name=name,
        firmware=firmware,
        firmware_untested=firmware not in TESTED_FIRMWARE,
    )
