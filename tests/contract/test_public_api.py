"""Public library surface matches contracts/library-api.md (T044, US4)."""

from __future__ import annotations

import dataclasses
import inspect
from pathlib import Path

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
    "WriteRefusedError",
    "WriteNakError",
    "WriteNotAppliedError",
    "ConfigError",  # spec 005
    "TargetNotFoundError",
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
    "Backup",
    "StoredPreset",
    "WritePlan",
    "WriteResult",
    "PedalState",  # spec 004
    "SequencePlan",  # spec 004 M2
    "SequenceStep",
    "SequenceResult",
    "StepOutcome",
    "FieldEdit",  # batch set
    "EditWrite",
    "EditPlan",
    "EditWriteOutcome",
    "EditResult",
    "KnownDevice",  # spec 005 M0
    "KnownDevices",
    "Target",
    "resolve_target",
    "default_config_path",
    "scan",  # spec 005 M1
    "identify",
    "ScanEntry",
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
    "build_storage_read",
    "parse_storage_reply",
    "build_write",
    "parse_write_reply",
    "classify",  # spec 004
    "type_raw",  # spec 004
    "type_parts",  # spec 004
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
    "Backup",
    "StoredPreset",
    "WritePlan",
    "WriteResult",
    "PedalState",
    "SequencePlan",
    "SequenceStep",
    "SequenceResult",
    "StepOutcome",
    "FieldEdit",
    "EditWrite",
    "EditPlan",
    "EditWriteOutcome",
    "EditResult",
    "KnownDevice",  # spec 005
    "KnownDevices",
    "Target",
    "ScanEntry",
)
FORBIDDEN = ("write", "erase", "address", "commit", "raw")
"""No TankG name may contain these: writes exist only as the named actions below (003 FR-007)."""
WRITE_ACTIONS = {
    "plan_set",
    "set_field",
    "plan_select",
    "select_preset",
    "plan_reload",  # spec 004
    "reload_preset",  # spec 004
    "plan_bypass_on",  # spec 004 M1
    "bypass_on",
    "plan_bypass_off",
    "bypass_off",
    "plan_loopback",
    "set_loopback",
    "plan_save",  # spec 004 M2: persistent, unsafe=True required
    "save_preset",
    "plan_restore",
    "restore",
    "plan_set_fields",  # batch set: several fields over one session
    "set_fields",
}


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


def test_device_info_04_constructors_still_work() -> None:
    plain = openvave.DeviceInfo("id", "name")
    with_rssi = openvave.DeviceInfo("id", "name", -50)
    for info in (plain, with_rssi):
        assert info.nickname is None
        assert info.chosen_by is None
    assert with_rssi.rssi == -50
    assert [f.name for f in dataclasses.fields(openvave.DeviceInfo)][-2:] == [
        "nickname",
        "chosen_by",
    ]


def test_spec005_errors() -> None:
    assert openvave.ConfigError.exit_code == 2
    assert issubclass(openvave.TargetNotFoundError, openvave.NoDeviceFoundError)
    assert openvave.TargetNotFoundError.exit_code == 3


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


def test_protocol_module_exposes_storage_read() -> None:
    assert "StorageRead" in openvave.protocol.__all__
    target = openvave.protocol.StorageRead.preset(6)
    assert (target.type, target.address, target.length) == (4, 128, 21)


async def test_backup_sends_reads_only() -> None:
    from tests.support import storage_fixture as sf

    fake = openvave.FakeTransport.from_capture(sf.SYNTHETIC_CAPTURE)
    async with openvave.TankG.over(fake) as pedal:
        backup = await pedal.backup()
    assert isinstance(backup, openvave.Backup)
    assert {frame[2] for frame in fake.sent} == {0x11, 0x23}


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

    preset = KNOWN_FIELDS[openvave.Region.CURRENT_PRESET]
    assert [s.offset for s in preset] == list(range(21))
    by_offset = {s.offset: (s.name, s.label, s.confidence) for s in preset}
    assert by_offset[6] == ("gain", "gain", "confirmed")  # renamed from knob_unknown in 0.2.0
    assert by_offset[15] == ("reverb_decay", "reverb decay", "confirmed")
    assert by_offset[17] == ("ir_cab", "IR cab", "confirmed")
    assert [s.name for s in KNOWN_FIELDS[openvave.Region.GLOBAL]] == [
        "browse_bank",
        "bank",
        "slot",
        "mode",
    ]
    assert all(isinstance(s, FieldSpec) for s in preset)
    assert KNOWN_FIELDS[openvave.Region.DEVICE_INFO] == ()
    assert [s.name for s in KNOWN_FIELDS[openvave.Region.STATUS]] == ["loopback"]


def test_tankg_write_actions_are_named() -> None:
    public = {n for n in dir(openvave.TankG) if not n.startswith("_")}
    assert WRITE_ACTIONS <= public
    assert public - WRITE_ACTIONS == {
        "backup",
        "close",  # spec 005
        "connect",
        "connect_selected",  # spec 005
        "device",
        "identity",
        "is_connected",  # spec 005
        "open",  # spec 005
        "over",
        "read",
        "snapshot",
        "state",  # spec 004
        "watch",
    }


SESSION_LIFECYCLE = ("open", "close", "is_connected", "connect_selected")
"""Spec 005 additions to ``TankG`` (``contracts/library-api.md`` "Long-lived connection")."""


def test_spec005_session_lifecycle_is_public_and_documented() -> None:
    contract = (
        Path(__file__).resolve().parents[2]
        / "specs"
        / "005-device-selection"
        / "contracts"
        / "library-api.md"
    ).read_text(encoding="utf-8")
    for name in SESSION_LIFECYCLE:
        member = inspect.getattr_static(openvave.TankG, name)
        assert inspect.getdoc(getattr(openvave.TankG, name)) or inspect.getdoc(member), name
        assert f"pedal.{name}" in contract or f"TankG.{name}" in contract, name
    assert isinstance(inspect.getattr_static(openvave.TankG, "is_connected"), property)
    assert inspect.iscoroutinefunction(openvave.TankG.open)
    assert inspect.iscoroutinefunction(openvave.TankG.close)
    parameters = inspect.signature(openvave.TankG.connect_selected).parameters
    assert set(parameters) == {"config_path", "scan_timeout", "timeout"}
    assert all(p.kind is inspect.Parameter.KEYWORD_ONLY for p in parameters.values())


def test_protocol_module_exposes_write_allowlist() -> None:
    assert {"WriteTarget", "WRITE_MESSAGES", "WriteMessage"} <= set(openvave.protocol.__all__)
    target = openvave.protocol.WriteTarget.preset_select(6)
    assert (target.type, target.address, target.length) == (4, 0xE0000006, 1)
    assert isinstance(openvave.protocol.WRITE_MESSAGES, tuple)


def test_spec004_m1_targets_are_volatile_constructors() -> None:
    target_cls = openvave.protocol.WriteTarget
    bypass, loopback = target_cls.bypass(1), target_cls.loopback()
    assert (bypass.kind, bypass.address, bypass.persistent) == ("bypass", 0xE1000001, False)
    assert (loopback.kind, loopback.address, loopback.persistent) == ("loopback", 0xD0000000, False)
    assert "return_index" in {f.name for f in dataclasses.fields(openvave.WriteResult)}


def test_write_errors_exit_codes() -> None:
    assert issubclass(openvave.WriteRefusedError, openvave.UnsafeCommandError)
    assert issubclass(openvave.WriteNakError, openvave.ProtocolError)
    assert openvave.WriteRefusedError.exit_code == 1
    assert openvave.WriteNakError.exit_code == 7
    assert openvave.WriteNotAppliedError.exit_code == 8


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
