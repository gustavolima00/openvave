"""``TankG.connect`` forms and ``TankG.connect_selected`` (spec 005 T050, US5, research R10).

The scan is replaced by a stand-in for ``openvave.transport.ble.open_ble`` that records the target
it receives and annotates the device the way :func:`~openvave.transport.ble.locate` does.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

import openvave
from openvave.devices import KnownDevice, KnownDevices, Target
from openvave.errors import ConfigError
from openvave.models import DeviceInfo
from openvave.session import TankG
from openvave.transport.fake import FakeTransport
from tests.support.write_fixture import make_fake

A = "AA:BB:CC:DD:EE:01"
B = "AA:BB:CC:DD:EE:02"
NOW = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)


class ScanStandIn:
    """Records every target ``open_ble`` is called with and hands out a fresh fake pedal."""

    def __init__(self) -> None:
        self.targets: list[Target | str | None] = []
        self.fakes: list[FakeTransport] = []

    async def __call__(
        self, target: Target | str | None, scan_timeout: float, **_: object
    ) -> tuple[FakeTransport, DeviceInfo]:
        self.targets.append(target)
        fake = make_fake()
        self.fakes.append(fake)
        if isinstance(target, str):
            target = Target(target, None, "device_option")
        if target is None:
            info = DeviceInfo(A, "TANK-Gv2_BLE", -50, None, "only_one_found")
        else:
            info = DeviceInfo(target.identifier, "TANK-Gv2_BLE", -50)
            info = replace(info, nickname=target.nickname, chosen_by=target.chosen_by)
        return fake, info


@pytest.fixture
def scan(monkeypatch: pytest.MonkeyPatch) -> ScanStandIn:
    stand_in = ScanStandIn()
    monkeypatch.setattr("openvave.transport.ble.open_ble", stand_in)
    return stand_in


@pytest.fixture
def no_config_read(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_: object, **__: object) -> KnownDevices:
        raise AssertionError("the configuration was read")

    monkeypatch.setattr(KnownDevices, "load", classmethod(refuse))


def _known(tmp_path: Path, *, default: str | None = A) -> Path:
    known = KnownDevices.load(tmp_path / "devices.json")
    known = known.select(B, nickname="home", now=NOW)
    if default is not None:
        known = known.select(default, nickname="stage", now=NOW)
    else:
        known = known.forget()
    known.save()
    return tmp_path / "devices.json"


@pytest.mark.usefixtures("no_config_read")
async def test_connect_without_argument_passes_none_and_reads_no_configuration(
    scan: ScanStandIn,
) -> None:
    async with TankG.connect() as pedal:
        assert pedal.device is not None
        assert pedal.device.chosen_by == "only_one_found"
        assert pedal.device.nickname is None
    assert scan.targets == [None]


@pytest.mark.usefixtures("no_config_read")
async def test_connect_with_an_identifier(scan: ScanStandIn) -> None:
    async with TankG.connect(A) as pedal:
        assert pedal.device is not None
        assert pedal.device.identifier == A
        assert pedal.device.chosen_by == "device_option"
    assert scan.targets == [A]


@pytest.mark.usefixtures("no_config_read")
async def test_connect_with_a_known_device(scan: ScanStandIn) -> None:
    known = KnownDevice(identifier=B, nickname="home", added_at=NOW)
    async with TankG.connect(known) as pedal:
        assert pedal.device is not None
        assert pedal.device.identifier == B
        assert pedal.device.nickname == "home"
        assert pedal.device.chosen_by == "device_option"
    assert scan.targets == [Target(B, "home", "device_option")]


@pytest.mark.usefixtures("no_config_read")
async def test_connect_with_a_target(scan: ScanStandIn) -> None:
    target = Target(A, "stage", "environment")
    async with TankG.connect(target) as pedal:
        assert pedal.device is not None
        assert pedal.device.nickname == "stage"
        assert pedal.device.chosen_by == "environment"
    assert scan.targets == [target]


async def test_connect_selected_uses_the_default_of_the_file(
    scan: ScanStandIn, tmp_path: Path
) -> None:
    path = _known(tmp_path)
    async with TankG.connect_selected(config_path=path) as pedal:
        assert pedal.device is not None
        assert pedal.device.identifier == A
        assert pedal.device.nickname == "stage"
        assert pedal.device.chosen_by == "selected"
    assert scan.targets == [Target(A, "stage", "selected")]


async def test_connect_selected_default_path_honours_openvave_config(
    scan: ScanStandIn, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _known(tmp_path)
    monkeypatch.setenv("OPENVAVE_CONFIG", str(path))
    async with TankG.connect_selected() as pedal:
        assert pedal.device is not None
        assert pedal.device.identifier == A
    assert scan.targets == [Target(A, "stage", "selected")]


async def test_connect_selected_without_a_default_raises(scan: ScanStandIn, tmp_path: Path) -> None:
    path = _known(tmp_path, default=None)
    with pytest.raises(ConfigError) as err:
        TankG.connect_selected(config_path=path)
    assert err.value.reason == "unknown_device"
    assert err.value.path == path
    with pytest.raises(ConfigError):
        TankG.connect_selected(config_path=tmp_path / "missing.json")
    assert scan.targets == []


async def test_connect_selected_on_an_invalid_file_raises(tmp_path: Path) -> None:
    path = tmp_path / "devices.json"
    path.write_text("not json", encoding="utf-8")
    with pytest.raises(ConfigError) as err:
        TankG.connect_selected(config_path=path)
    assert err.value.reason == "invalid_file"


async def test_connect_selected_reopens_the_same_pedal(scan: ScanStandIn, tmp_path: Path) -> None:
    path = _known(tmp_path)
    pedal = TankG.connect_selected(config_path=path)
    await pedal.open()
    await pedal.close()
    await pedal.open()
    await pedal.close()
    assert scan.targets == [Target(A, "stage", "selected")] * 2


def test_connect_selected_is_public() -> None:
    assert openvave.TankG is TankG
    assert callable(openvave.TankG.connect_selected)
