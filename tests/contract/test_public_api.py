"""Public library surface matches contracts/library-api.md (T044, US4)."""

from __future__ import annotations

import dataclasses
import inspect

import pytest

import openvave
from tests.support.captures import FW96_CONNECT

ERRORS = {
    "OpenvaveError",
    "NoDeviceFoundError",
    "MultipleDevicesError",
    "BluetoothUnavailableError",
    "ConnectionLostError",
    "RequestTimeoutError",
    "ProtocolError",
    "HandshakeError",
    "UnsafeCommandError",
}
CONTRACT_EXPORTS = {
    "discover",
    "TankG",
    "Region",
    "DeviceInfo",
    "DeviceIdentity",
    "RegionRead",
    "DeviceSnapshot",
    "Transport",
    "FakeTransport",
    "TESTED_FIRMWARE",
    "Encoding",
    "ByteMapEntry",
    "DecodedField",
    "DecodedRegion",
    "ByteChange",
    "WatchStart",
    "WatchChange",
} | ERRORS
PROTOCOL_EXPORTS = {
    "encode_frame",
    "decode_frame",
    "FrameAssembler",
    "build_query",
    "build_read",
    "parse_read_reply",
    "parse_identity",
    "decode_region",
    "diff",
}
DATACLASSES = (
    "DeviceInfo",
    "DeviceIdentity",
    "RegionRead",
    "DeviceSnapshot",
    "ByteMapEntry",
    "DecodedField",
    "DecodedRegion",
    "ByteChange",
    "WatchStart",
    "WatchChange",
)
FORBIDDEN = ("write", "erase", "address")


def test_all_matches_contract() -> None:
    assert set(openvave.__all__) == CONTRACT_EXPORTS
    assert len(openvave.__all__) == len(CONTRACT_EXPORTS)
    for name in openvave.__all__:
        assert getattr(openvave, name) is not None


def test_every_public_name_documented() -> None:
    for name in openvave.__all__:
        obj = getattr(openvave, name)
        if isinstance(obj, frozenset):
            continue
        assert inspect.getdoc(obj), f"openvave.{name} has no docstring"
        if inspect.isclass(obj) and not issubclass(obj, BaseException):
            for attr, value in vars(obj).items():
                if attr.startswith("_") or not callable(getattr(obj, attr)):
                    continue
                assert inspect.getdoc(value), f"openvave.{name}.{attr} has no docstring"


def test_errors_derive_from_base() -> None:
    for name in ERRORS:
        assert issubclass(getattr(openvave, name), openvave.OpenvaveError)


def test_tested_firmware() -> None:
    assert isinstance(openvave.TESTED_FIRMWARE, frozenset)
    assert 96 in openvave.TESTED_FIRMWARE


def test_region_closed_enum() -> None:
    assert [r.name for r in openvave.Region] == [
        "DEVICE_INFO",
        "GLOBAL",
        "CURRENT_PRESET",
        "STATUS",
    ]


def test_protocol_module_exposes_codec() -> None:
    for name in PROTOCOL_EXPORTS:
        assert callable(getattr(openvave.protocol, name)), name
        assert name in openvave.protocol.__all__


def test_protocol_module_exposes_byte_map() -> None:
    assert openvave.protocol.MAP_FIRMWARE == 96
    assert isinstance(openvave.protocol.BYTE_MAP, tuple)
    assert all(isinstance(e, openvave.ByteMapEntry) for e in openvave.protocol.BYTE_MAP)
    assert {"BYTE_MAP", "MAP_FIRMWARE"} <= set(openvave.protocol.__all__)


def test_encoding_closed_enum() -> None:
    assert [e.value for e in openvave.Encoding] == [
        "continuous",
        "switch",
        "selector",
        "flag",
        "index",
        "unknown",
    ]


def test_deprecated_known_fields_alias() -> None:
    from openvave.models import KNOWN_FIELDS, FieldSpec

    assert [
        (s.offset, s.name, s.label, s.confidence)
        for s in KNOWN_FIELDS[openvave.Region.CURRENT_PRESET]
    ] == [
        (6, "knob_unknown", "knob (which one: unknown)", "observed"),
        (15, "reverb_decay", "reverb decay", "observed"),
        (16, "reverb_mix", "reverb mix?", "hypothesis"),
        (17, "ir_cab", "IR cab?", "hypothesis"),
    ]
    assert KNOWN_FIELDS[openvave.Region.GLOBAL] == (
        FieldSpec(3, "not_in_edit_mode", "not in edit mode", "observed"),
    )
    assert KNOWN_FIELDS[openvave.Region.DEVICE_INFO] == ()
    assert KNOWN_FIELDS[openvave.Region.STATUS] == ()


def test_tankg_has_no_write_erase_or_address_api() -> None:
    names = [n.lower() for n in dir(openvave.TankG)]
    for word in FORBIDDEN:
        assert not [n for n in names if word in n], word


async def test_tankg_instance_has_no_write_erase_or_address_api() -> None:
    fake = openvave.FakeTransport.from_capture(FW96_CONNECT)
    async with openvave.TankG.over(fake) as pedal:
        names = [n.lower() for n in dir(pedal)]
        for word in FORBIDDEN:
            assert not [n for n in names if word in n], word


async def test_read_by_address_is_type_error() -> None:
    fake = openvave.FakeTransport.from_capture(FW96_CONNECT)
    async with openvave.TankG.over(fake) as pedal:
        with pytest.raises(TypeError):
            await pedal.read(0x10000000)  # type: ignore[arg-type]
    assert len(fake.sent) == 1  # only the handshake; nothing was written for the bad read


@pytest.mark.parametrize("name", DATACLASSES)
def test_public_dataclasses_frozen(name: str) -> None:
    cls = getattr(openvave, name)
    assert dataclasses.is_dataclass(cls)
    assert cls.__dataclass_params__.frozen  # type: ignore[attr-defined]


def test_fake_transport_satisfies_protocol() -> None:
    fake = openvave.FakeTransport.from_capture(FW96_CONNECT)
    assert isinstance(fake, openvave.Transport)


def test_watch_event_union() -> None:
    from openvave.models import WatchEvent

    assert set(WatchEvent.__args__) == {openvave.WatchStart, openvave.WatchChange}
