"""openvave: unofficial client for the M-VAVE Tank-G pedal.

Unofficial. Not affiliated with or endorsed by M-VAVE / Cuvave.

Public API (semver-governed; see ``specs/001-readonly-ble-connection/contracts/library-api.md``)::

    import openvave

    async with openvave.TankG.connect() as pedal:        # BLE
        print(pedal.identity)
        snap = await pedal.snapshot()
        backup = await pedal.backup()                    # all 36 stored presets, verified
        plan = await pedal.plan_set("gain", 90)          # reads only: the exact write frame
        result = await pedal.set_field("gain", 90, experimental=True)   # edit buffer, unsaved
        result = await pedal.set_fields({"gain": 95, "delay_on": True},  # several fields,
                                        experimental=True)                # one session
        result = await pedal.select_preset(6, experimental=True)        # load stored 2C
        result = await pedal.save_preset(unsafe=True, experimental=True,  # PERSISTENT: backup
                                         on_backup=store)                 # first, then save

    fake = openvave.FakeTransport.from_capture("captures/fw96/20261116-probe-connect.jsonl")
    async with openvave.TankG.over(fake) as pedal:        # any Transport
        ...

    async with openvave.TankG.connect() as pedal:        # the only polling API
        async for event in pedal.watch(interval=0.5):    # WatchStart, then WatchChange
            ...

Only ``0x11`` (query), ``0x23`` (read) and ``0x22`` (write) to a closed allowlist can ever be
sent: the volatile edit buffer, preset select, bypass and loopback writes, and three persistent
writes (stored slot, commit, stored image) that only ``save_preset`` / ``restore`` send, only with
``unsafe=True`` and after a verified backup. Erase, the global block and any other address cannot
be encoded. The pure codec and
the byte map decoder (``decode_region``, ``diff``, ``BYTE_MAP``, ``WRITE_MESSAGES``) live in
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
    WriteNakError,
    WriteNotAppliedError,
    WriteRefusedError,
)
from openvave.models import (
    Backup,
    ByteChange,
    ByteMapEntry,
    DecodedField,
    DecodedRegion,
    DeviceIdentity,
    DeviceInfo,
    DeviceSnapshot,
    EditPlan,
    EditResult,
    EditWrite,
    EditWriteOutcome,
    Encoding,
    FieldEdit,
    PedalState,
    Region,
    RegionRead,
    SequencePlan,
    SequenceResult,
    SequenceStep,
    StepOutcome,
    StoredPreset,
    WatchChange,
    WatchStart,
    WritePlan,
    WriteResult,
)
from openvave.protocol.identity import TESTED_FIRMWARE
from openvave.session import TankG
from openvave.transport import Transport
from openvave.transport.ble import discover
from openvave.transport.fake import FakeTransport

__version__ = "0.3.0"

__all__ = [
    "Backup",
    "BluetoothUnavailableError",
    "ByteChange",
    "ByteMapEntry",
    "ConnectionLostError",
    "DecodedField",
    "DecodedRegion",
    "DeviceIdentity",
    "DeviceInfo",
    "DeviceSnapshot",
    "EditPlan",
    "EditResult",
    "EditWrite",
    "EditWriteOutcome",
    "Encoding",
    "FakeTransport",
    "FieldEdit",
    "HandshakeError",
    "MultipleDevicesError",
    "NoDeviceFoundError",
    "OpenvaveError",
    "PedalState",
    "ProtocolError",
    "Region",
    "RegionRead",
    "RequestTimeoutError",
    "SequencePlan",
    "SequenceResult",
    "SequenceStep",
    "StepOutcome",
    "StoredPreset",
    "TESTED_FIRMWARE",
    "TankG",
    "Transport",
    "UnsafeCommandError",
    "WatchChange",
    "WatchStart",
    "WriteNakError",
    "WriteNotAppliedError",
    "WritePlan",
    "WriteRefusedError",
    "WriteResult",
    "discover",
]
