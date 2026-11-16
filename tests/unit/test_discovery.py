"""Pure device selection after a scan (T026). No Bluetooth involved."""

from __future__ import annotations

import pytest

from openvave.errors import MultipleDevicesError, NoDeviceFoundError
from openvave.models import DeviceInfo
from openvave.transport.ble import BLE_NAME, select_device

PEDAL_A = DeviceInfo("AAAA-1111", "TANK-Gv2_BLE", -58)
PEDAL_B = DeviceInfo("BBBB-2222", "TANK-Gv2_BLE", -71)
CLASSIC = DeviceInfo("CCCC-3333", "TANK-Gv2", -60)
OTHER = DeviceInfo("DDDD-4444", "Some Speaker", None)


def test_ble_name() -> None:
    assert BLE_NAME == "TANK-Gv2_BLE"


def test_no_match() -> None:
    with pytest.raises(NoDeviceFoundError):
        select_device([OTHER], None)


def test_empty_scan() -> None:
    with pytest.raises(NoDeviceFoundError):
        select_device([], None)


def test_single_match() -> None:
    assert select_device([OTHER, PEDAL_A], None) is PEDAL_A


def test_multiple_matches_without_wanted() -> None:
    with pytest.raises(MultipleDevicesError) as exc:
        select_device([PEDAL_A, OTHER, PEDAL_B], None)
    assert set(exc.value.candidates) == {PEDAL_A, PEDAL_B}


def test_wanted_id_skips_name_filter() -> None:
    assert select_device([PEDAL_A, OTHER, PEDAL_B], "DDDD-4444") is OTHER


def test_wanted_id_case_insensitive() -> None:
    assert select_device([PEDAL_A, PEDAL_B], "bbbb-2222") is PEDAL_B


def test_wanted_id_not_found() -> None:
    with pytest.raises(NoDeviceFoundError):
        select_device([PEDAL_A], "EEEE-5555")


def test_classic_identity_never_matches() -> None:
    with pytest.raises(NoDeviceFoundError):
        select_device([CLASSIC], None)
    assert select_device([CLASSIC, PEDAL_A], None) is PEDAL_A
