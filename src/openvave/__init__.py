"""openvave: unofficial read-only client for the M-VAVE Tank-G pedal.

Unofficial. Not affiliated with or endorsed by M-VAVE / Cuvave.

Public API (semver-governed; see ``specs/001-readonly-ble-connection/contracts/library-api.md``)::

    import openvave

    async with openvave.TankG.connect() as pedal:        # BLE
        print(pedal.identity)
        snap = await pedal.snapshot()

    fake = openvave.FakeTransport.from_capture("captures/fw96/20261116-probe-connect.jsonl")
    async with openvave.TankG.over(fake) as pedal:        # any Transport
        ...

Only the read-only commands ``0x11`` (query) and ``0x23`` (read) can ever be sent. The pure
codec and the byte map decoder (``decode_region``, ``diff``, ``BYTE_MAP``) live in
:mod:`openvave.protocol`. Everything not exported here is internal.
"""

from openvave import protocol as protocol  # submodule: the pure codec
from openvave.errors import (
    BluetoothUnavailableError,
    ConnectionLostError,
    HandshakeError,
    MultipleDevicesError,
    NoDeviceFoundError,
    OpenvaveError,
    ProtocolError,
    RequestTimeoutError,
    UnsafeCommandError,
)
from openvave.models import (
    ByteChange,
    ByteMapEntry,
    DecodedField,
    DecodedRegion,
    DeviceIdentity,
    DeviceInfo,
    DeviceSnapshot,
    Encoding,
    Region,
    RegionRead,
)
from openvave.protocol.identity import TESTED_FIRMWARE
from openvave.session import TankG
from openvave.transport import Transport
from openvave.transport.ble import discover
from openvave.transport.fake import FakeTransport

__version__ = "0.1.0"

__all__ = [
    "BluetoothUnavailableError",
    "ByteChange",
    "ByteMapEntry",
    "ConnectionLostError",
    "DecodedField",
    "DecodedRegion",
    "DeviceIdentity",
    "DeviceInfo",
    "DeviceSnapshot",
    "Encoding",
    "FakeTransport",
    "HandshakeError",
    "MultipleDevicesError",
    "NoDeviceFoundError",
    "OpenvaveError",
    "ProtocolError",
    "Region",
    "RegionRead",
    "RequestTimeoutError",
    "TESTED_FIRMWARE",
    "TankG",
    "Transport",
    "UnsafeCommandError",
    "discover",
]
