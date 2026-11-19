"""``openvave scan [--all] [--identify]`` (spec 005 T017, contracts/cli.md, scan.schema.json)."""

from __future__ import annotations

import json

import pytest

from openvave.devices import Target
from openvave.errors import BluetoothUnavailableError
from openvave.models import DeviceInfo
from openvave.transport import Transport
from openvave.transport.fake import FakeTransport
from tests.support.captures import FW96_CONNECT, QUERY, load_capture
from tests.support.cli005 import Factory, file_bytes, run, seed, validate
from tests.support.scanner import (
    SPEAKER,
    TANK,
    UUID_1,
    UUID_2,
    fake_scanner,
    raising_scanner,
)

CAP = load_capture(FW96_CONNECT)
FAST = ["--scan-timeout", "0.1"]
TWO = fake_scanner([(UUID_2, TANK, -61), (UUID_1, TANK, -58)])
FOOTER = "Select one: openvave select ID [--name NICKNAME]"
NONE_HINT = (
    "hint: switch the pedal on and close the M-VAVE phone app; a pedal that is connected to the "
    "app\n      or to another program stops advertising.\n"
)


def forbidden_factory() -> Factory:
    async def factory(device_id: str | None, scan_timeout: float) -> tuple[Transport, None]:
        raise AssertionError("scan must not connect without --identify")

    return factory


def test_two_pedals_no_configuration(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err = run(capsys, ["scan", *FAST], scanner=TWO, factory=forbidden_factory())
    assert code == 0
    assert out == (
        f"  {UUID_1}  {TANK}  -58 dBm\n  {UUID_2}  {TANK}  -61 dBm\n2 pedals found. {FOOTER}\n"
    )
    assert err == "Scanning for 0.1 s…\n"
    assert file_bytes() is None  # nothing written


def test_default_is_marked_with_its_nickname(capsys: pytest.CaptureFixture[str]) -> None:
    seed((UUID_1, "stage"))
    code, out, _ = run(capsys, ["scan", *FAST], scanner=TWO)
    assert code == 0
    assert out == (
        f"* stage  {UUID_1}  {TANK}  -58 dBm\n"
        f"         {UUID_2}  {TANK}  -61 dBm\n"
        f"2 pedals found. * = default. {FOOTER}\n"
    )


def test_one_pedal(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(capsys, ["scan", *FAST], scanner=fake_scanner([(UUID_1, TANK, None)]))
    assert code == 0
    assert out == f"  {UUID_1}  {TANK}  ? dBm\n1 pedal found. {FOOTER}\n"


def test_default_not_seen(capsys: pytest.CaptureFixture[str]) -> None:
    seed((UUID_2, "stage"))
    code, out, _ = run(capsys, ["scan", *FAST], scanner=fake_scanner([(UUID_1, TANK, -58)]))
    assert code == 0
    assert out == (
        f"  {UUID_1}  {TANK}  -58 dBm\n1 pedal found. {FOOTER}\nstage ({UUID_2}) not seen\n"
    )


def test_none_found(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err = run(capsys, ["scan", *FAST], scanner=fake_scanner([(SPEAKER, "S", -30)]))
    assert code == 3
    assert out == "No Tank-G found.\n"
    assert err == "Scanning for 0.1 s…\n" + NONE_HINT


def test_all_lists_other_advertisers(capsys: pytest.CaptureFixture[str]) -> None:
    scanner = fake_scanner(
        [(SPEAKER, "Some Speaker", -30), (UUID_1, TANK, -58), ("AA:BB:CC:DD:EE:99", "", None)]
    )
    code, out, _ = run(capsys, ["scan", "--all", *FAST], scanner=scanner)
    assert code == 0
    lines = out.splitlines()
    # columns line up: the name column starts at the same offset on every row
    assert lines[0].index(TANK) == lines[1].index("Some Speaker") == lines[2].index("-  ")
    assert lines[0].startswith(f"  {UUID_1}") and lines[0].endswith("-58 dBm")
    assert lines[1].startswith(f"  {SPEAKER}") and lines[1].endswith("(not a Tank-G)")
    assert "Some Speaker" in lines[1]
    assert lines[2].split()[:2] == ["AA:BB:CC:DD:EE:99", "-"]
    assert lines[2].endswith("? dBm  (not a Tank-G)")
    assert lines[3] == f"1 pedal found. {FOOTER}"


def test_all_without_tank_g_exits_3(capsys: pytest.CaptureFixture[str]) -> None:
    scanner = fake_scanner([(SPEAKER, "Some Speaker", -30)])
    code, out, _ = run(capsys, ["scan", "--all", *FAST], scanner=scanner)
    assert code == 3
    assert out.splitlines()[-1] == "No Tank-G found."
    assert "(not a Tank-G)" in out


def test_identify_adds_firmware(capsys: pytest.CaptureFixture[str]) -> None:
    fakes = {u: FakeTransport.from_capture(FW96_CONNECT) for u in (UUID_1, UUID_2)}
    calls: list[str | None] = []

    async def factory(target: Target | None, scan_timeout: float) -> tuple[Transport, DeviceInfo]:
        assert target is not None and target.chosen_by == "device_option"
        device_id = target.identifier
        calls.append(device_id)
        if device_id == UUID_2:
            raise BluetoothUnavailableError("Bluetooth unavailable: off")
        assert device_id is not None
        return fakes[device_id], DeviceInfo(device_id, TANK, -58)

    code, out, _ = run(capsys, ["scan", "--identify", *FAST], scanner=TWO, factory=factory)
    assert code == 0
    assert calls == [UUID_1, UUID_2]
    assert out.splitlines()[:2] == [
        f"  {UUID_1}  {TANK}  -58 dBm  fw 96",
        f"  {UUID_2}  {TANK}  -61 dBm  fw ? (Bluetooth unavailable: off)",
    ]
    assert fakes[UUID_1].sent == [CAP.tx(QUERY)]
    assert fakes[UUID_2].sent == []


def test_identify_updates_last_firmware_of_known_pedals(
    capsys: pytest.CaptureFixture[str],
) -> None:
    seed((UUID_1, "stage"))

    async def factory(device_id: str | None, scan_timeout: float) -> tuple[Transport, None]:
        return FakeTransport.from_capture(FW96_CONNECT), None

    code, _, _ = run(capsys, ["scan", "--identify", *FAST], scanner=TWO, factory=factory)
    assert code == 0
    stored = json.loads(file_bytes() or b"{}")
    (device,) = stored["devices"]
    assert device["last_firmware"] == 96
    assert device["last_seen_at"] is not None


def test_json_document(capsys: pytest.CaptureFixture[str]) -> None:
    seed((UUID_1, "stage"))
    code, out, err = run(capsys, ["scan", "--json", *FAST], scanner=TWO)
    assert code == 0
    assert err == ""
    document = json.loads(out)
    validate(document, "scan.schema.json")
    assert document["command"] == "scan"
    assert document["scan_seconds"] == 0.1
    assert document["default_seen"] is True
    first, second = document["devices"]
    assert first == {
        "identifier": UUID_1,
        "name": TANK,
        "rssi": -58,
        "tank_g": True,
        "nickname": "stage",
        "known": True,
        "selected": True,
    }
    assert second["identifier"] == UUID_2 and second["known"] is False


def test_json_empty_list_exits_3(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(capsys, ["scan", "--json", *FAST], scanner=fake_scanner([]))
    assert code == 3
    document = json.loads(out)
    validate(document, "scan.schema.json")
    assert document["devices"] == []
    assert document["default_seen"] is None


def test_json_identify_fields(capsys: pytest.CaptureFixture[str]) -> None:
    async def factory(device_id: str | None, scan_timeout: float) -> tuple[Transport, None]:
        return FakeTransport.from_capture(FW96_CONNECT), None

    code, out, _ = run(
        capsys,
        ["scan", "--json", "--identify", *FAST],
        scanner=fake_scanner([(UUID_1, TANK, -58)]),
        factory=factory,
    )
    assert code == 0
    document = json.loads(out)
    validate(document, "scan.schema.json")
    assert document["devices"][0]["firmware"] == 96
    assert document["devices"][0]["identify_error"] is None


def test_bluetooth_unavailable_exits_5(capsys: pytest.CaptureFixture[str]) -> None:
    error = BluetoothUnavailableError("Bluetooth unavailable: powered off")
    code, out, err = run(capsys, ["scan", *FAST], scanner=raising_scanner(error))
    assert code == 5
    assert out == ""
    assert "error: Bluetooth unavailable: powered off" in err
