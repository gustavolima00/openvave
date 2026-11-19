"""KnownDevices operations: the data-model "Operations" table (spec 005 T004)."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from openvave.devices import KnownDevice, KnownDevices
from openvave.errors import ConfigError

A = "8F3A21C4-0000-4000-8000-000000000001"
B = "AA:BB:CC:DD:EE:02"
T0 = datetime(2026, 11, 19, 10, 0, tzinfo=UTC)
T1 = T0 + timedelta(minutes=5)
T2 = T0 + timedelta(minutes=10)


@pytest.fixture
def empty(tmp_path: Path) -> KnownDevices:
    return KnownDevices(path=tmp_path / "devices.json")


@pytest.fixture
def two(empty: KnownDevices) -> KnownDevices:
    """A known as "home", then B selected as "stage" (the default)."""
    return empty.select(A, "home", now=T0).select(B, "stage", name="TANK-Gv2_BLE", now=T1)


def test_empty(empty: KnownDevices) -> None:
    assert empty.devices == ()
    assert empty.default is None
    assert empty.nicknames == ()


def test_select_new(empty: KnownDevices) -> None:
    known = empty.select(A, now=T0)
    assert known is not empty
    assert empty.devices == ()  # the original is unchanged
    (device,) = known.devices
    assert device == KnownDevice(identifier=A, nickname=None, added_at=T0, selected_at=T0)
    assert known.default == device
    assert known.path == empty.path


def test_select_with_nickname_and_name(empty: KnownDevices) -> None:
    known = empty.select(A, "stage", name="TANK-Gv2_BLE", now=T0)
    assert known.default is not None
    assert known.default.nickname == "stage"
    assert known.default.last_name == "TANK-Gv2_BLE"


def test_select_known_keeps_added_at_and_previous_default(two: KnownDevices) -> None:
    known = two.select(A.lower(), now=T2)
    assert [d.identifier for d in known.devices] == [A, B]  # stored as first reported, order kept
    assert known.default is not None
    assert known.default.identifier == A
    assert known.default.added_at == T0
    assert known.default.selected_at == T2
    assert known.default.nickname == "home"  # no nickname given: kept
    assert known.find(B) is not None  # previous default stays known


def test_select_known_renames(two: KnownDevices) -> None:
    known = two.select(A, "live", now=T2)
    assert known.find("live") is not None
    assert known.find("home") is None


def test_select_same_nickname_on_same_device(two: KnownDevices) -> None:
    known = two.select(A, "HOME", now=T2)
    assert known.default is not None
    assert known.default.nickname == "HOME"


def test_select_nickname_in_use(two: KnownDevices) -> None:
    with pytest.raises(ConfigError) as info:
        two.select(A, "Stage", now=T2)
    assert info.value.reason == "nickname_in_use"


def test_select_bad_nickname(empty: KnownDevices) -> None:
    with pytest.raises(ConfigError) as info:
        empty.select(A, "my pedal", now=T0)
    assert info.value.reason == "bad_nickname"


def test_rename(two: KnownDevices) -> None:
    known = two.rename("stage", "live")
    found = known.find("live")
    assert found is not None
    assert found.identifier == B
    assert known.default == found  # the default follows the device
    assert two.find("stage") is not None  # the original is unchanged


def test_rename_by_identifier(two: KnownDevices) -> None:
    known = two.rename(A.lower(), "rig")
    found = known.find("rig")
    assert found is not None
    assert found.identifier == A


def test_rename_unknown(two: KnownDevices) -> None:
    with pytest.raises(ConfigError) as info:
        two.rename("nobody", "live")
    assert info.value.reason == "unknown_device"


def test_rename_bad(two: KnownDevices) -> None:
    with pytest.raises(ConfigError) as info:
        two.rename("stage", "beef")
    assert info.value.reason == "bad_nickname"


def test_rename_in_use(two: KnownDevices) -> None:
    with pytest.raises(ConfigError) as info:
        two.rename("stage", "HOME")
    assert info.value.reason == "nickname_in_use"


def test_forget_default_keeps_devices(two: KnownDevices) -> None:
    known = two.forget()
    assert known.default is None
    assert known.devices == two.devices


def test_forget_without_default(empty: KnownDevices) -> None:
    assert empty.forget() == empty


def test_forget_target_default(two: KnownDevices) -> None:
    known = two.forget("STAGE")
    assert [d.identifier for d in known.devices] == [A]
    assert known.default is None


def test_forget_target_other(two: KnownDevices) -> None:
    known = two.forget(A)
    assert [d.identifier for d in known.devices] == [B]
    assert known.default is not None
    assert known.default.identifier == B


def test_forget_unknown(two: KnownDevices) -> None:
    with pytest.raises(ConfigError) as info:
        two.forget("nobody")
    assert info.value.reason == "unknown_device"


def test_forget_all(two: KnownDevices) -> None:
    known = two.forget_all()
    assert known.devices == ()
    assert known.default is None
    assert known.path == two.path


@pytest.mark.parametrize("value", ["home", "HOME", A, A.lower()])
def test_find_a(two: KnownDevices, value: str) -> None:
    found = two.find(value)
    assert found is not None
    assert found.identifier == A


def test_find_mac_case_insensitive(two: KnownDevices) -> None:
    found = two.find(B.lower())
    assert found is not None
    assert found.nickname == "stage"


def test_find_missing(two: KnownDevices) -> None:
    assert two.find("nobody") is None
    assert two.find("AA:BB:CC:DD:EE:09") is None


def test_record_seen_known(two: KnownDevices) -> None:
    known = two.record_seen(A.lower(), "TANK-Gv2_BLE", 96, now=T2)
    found = known.find(A)
    assert found is not None
    assert (found.last_name, found.last_firmware, found.last_seen_at) == ("TANK-Gv2_BLE", 96, T2)
    assert found.selected_at == T0  # nothing else changes
    assert known.default == two.default


def test_record_seen_unknown(two: KnownDevices) -> None:
    assert two.record_seen("AA:BB:CC:DD:EE:09", "TANK-Gv2_BLE", 96, now=T2) == two


def test_nicknames(two: KnownDevices) -> None:
    assert two.nicknames == ("home", "stage")


def test_values_are_frozen(two: KnownDevices) -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        two.path = Path("/elsewhere")  # type: ignore[misc]
    device = two.devices[0]
    with pytest.raises(dataclasses.FrozenInstanceError):
        device.nickname = "x"  # type: ignore[misc]


def test_default_time_is_utc_now(empty: KnownDevices) -> None:
    before = datetime.now(UTC)
    known = empty.select(A)
    assert known.default is not None
    assert before <= known.default.added_at <= datetime.now(UTC)
    assert known.default.added_at.tzinfo is not None
