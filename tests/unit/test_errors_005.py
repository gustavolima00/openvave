"""ConfigError and TargetNotFoundError (spec 005 T008, research R12)."""

from __future__ import annotations

from pathlib import Path

from openvave.devices import Target
from openvave.errors import ConfigError, NoDeviceFoundError, OpenvaveError, TargetNotFoundError
from openvave.models import DeviceInfo

UUID = "8F3A21C4-0000-4000-8000-000000000001"


def test_config_error() -> None:
    path = Path("/tmp/x/devices.json")
    err = ConfigError("not valid JSON", reason="invalid_file", path=path)
    assert isinstance(err, OpenvaveError)
    assert ConfigError.exit_code == 2
    assert err.reason == "invalid_file"
    assert err.path == path
    assert err.problem == "not valid JSON"
    assert str(err) == f"{path}: not valid JSON"  # the platform's separator


def test_config_error_without_path() -> None:
    err = ConfigError("unknown nickname 'x'", reason="unknown_nickname")
    assert err.path is None
    assert str(err) == "unknown nickname 'x'"


def test_target_not_found_with_nickname() -> None:
    target = Target(UUID, "stage", "selected")
    seen = (DeviceInfo("AA:BB:CC:DD:EE:02", "TANK-Gv2_BLE", -60),)
    err = TargetNotFoundError(target, seen)
    assert isinstance(err, NoDeviceFoundError)
    assert TargetNotFoundError.exit_code == 3
    assert err.target is target
    assert err.seen == seen
    assert str(err) == f"stage ({UUID}) not found"


def test_target_not_found_without_nickname() -> None:
    err = TargetNotFoundError(Target(UUID, None, "device_option"), [])
    assert err.seen == ()
    assert str(err) == f"device {UUID} not found"
