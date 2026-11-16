"""``openvave info`` identity output, errors and exit codes (T028, contracts/cli.md)."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from datetime import datetime

import pytest

import openvave
from openvave.cli import main
from openvave.errors import (
    BluetoothUnavailableError,
    HandshakeError,
    MultipleDevicesError,
    NoDeviceFoundError,
    OpenvaveError,
    RequestTimeoutError,
)
from openvave.models import DeviceInfo
from openvave.protocol import decode_frame
from openvave.transport import Transport
from openvave.transport.fake import FakeTransport
from tests.support.captures import FW96_CONNECT, QUERY, load_capture
from tests.support.mutations import with_payload

CAP = load_capture(FW96_CONNECT)
PEDAL = DeviceInfo("3F1A-UUID", "TANK-Gv2_BLE", -58)

Factory = Callable[[str | None, float], Awaitable[tuple[Transport, DeviceInfo | None]]]


def factory_for(
    fake: FakeTransport, device: DeviceInfo | None = PEDAL, calls: list[object] | None = None
) -> Factory:
    async def factory(
        device_id: str | None, scan_timeout: float
    ) -> tuple[Transport, DeviceInfo | None]:
        if calls is not None:
            calls.append((device_id, scan_timeout))
        return fake, device

    return factory


def raising(error: OpenvaveError) -> Factory:
    async def factory(
        device_id: str | None, scan_timeout: float
    ) -> tuple[Transport, DeviceInfo | None]:
        raise error

    return factory


def run(
    capsys: pytest.CaptureFixture[str], argv: list[str], factory: Factory
) -> tuple[int, str, str]:
    code = main(argv, transport_factory=factory)
    out, err = capsys.readouterr()
    return code, out, err


def test_human_output(capsys: pytest.CaptureFixture[str]) -> None:
    fake = FakeTransport.from_capture(FW96_CONNECT)
    code, out, err = run(capsys, ["info"], factory_for(fake))
    assert code == 0
    assert "TANK-Gv2" in out
    assert "firmware 96" in out
    assert "3F1A-UUID" in out
    assert err == ""
    assert fake.sent[0] == CAP.tx(QUERY)
    assert fake.closed


def test_human_output_without_device(capsys: pytest.CaptureFixture[str]) -> None:
    fake = FakeTransport.from_capture(FW96_CONNECT)
    code, out, _ = run(capsys, ["info"], factory_for(fake, device=None))
    assert code == 0
    assert "firmware 96" in out
    assert "Address" not in out


@pytest.mark.parametrize("argv", [["--json", "info"], ["info", "--json"]])
def test_json_output(capsys: pytest.CaptureFixture[str], argv: list[str]) -> None:
    fake = FakeTransport.from_capture(FW96_CONNECT)
    code, out, err = run(capsys, argv, factory_for(fake))
    assert code == 0
    assert err == ""
    doc = json.loads(out)
    assert doc["schema_version"] == 1
    assert doc["command"] == "info"
    read_at = datetime.fromisoformat(doc["read_at"])
    assert read_at.utcoffset() is not None and read_at.utcoffset().total_seconds() == 0
    assert doc["device"] == {"identifier": "3F1A-UUID", "name": "TANK-Gv2_BLE", "rssi": -58}
    identity = doc["identity"]
    assert identity["name"] == "TANK-Gv2"
    assert identity["firmware"] == 96
    assert identity["firmware_untested"] is False
    assert identity["raw"] == decode_frame(CAP.rx(QUERY)).body.hex(" ")


def test_json_device_null(capsys: pytest.CaptureFixture[str]) -> None:
    fake = FakeTransport.from_capture(FW96_CONNECT)
    code, out, _ = run(capsys, ["info", "--json"], factory_for(fake, device=None))
    assert code == 0
    assert json.loads(out)["device"] is None


def test_options_reach_factory(capsys: pytest.CaptureFixture[str]) -> None:
    calls: list[object] = []
    fake = FakeTransport.from_capture(FW96_CONNECT)
    code, _, _ = run(
        capsys,
        ["--device", "ABC", "info", "--scan-timeout", "3"],
        factory_for(fake, calls=calls),
    )
    assert code == 0
    assert calls == [("ABC", 3.0)]


@pytest.mark.parametrize(
    ("error", "exit_code"),
    [
        (NoDeviceFoundError("no Tank-G found"), 3),
        (MultipleDevicesError([PEDAL, DeviceInfo("OTHER-ID", "TANK-Gv2_BLE", -70)]), 4),
        (BluetoothUnavailableError("Bluetooth is off"), 5),
        (RequestTimeoutError("no reply within 2 s"), 6),
        (HandshakeError("handshake failed after 3 attempts"), 7),
    ],
)
@pytest.mark.parametrize("json_flag", [False, True])
def test_injected_errors(
    capsys: pytest.CaptureFixture[str], error: OpenvaveError, exit_code: int, json_flag: bool
) -> None:
    argv = ["info", "--json"] if json_flag else ["info"]
    code, out, err = run(capsys, argv, raising(error))
    assert code == exit_code
    assert "error:" in err
    assert "Traceback" not in err
    if json_flag:
        assert out == ""


def test_multiple_devices_lists_candidates(capsys: pytest.CaptureFixture[str]) -> None:
    other = DeviceInfo("OTHER-ID", "TANK-Gv2_BLE", None)
    code, _, err = run(capsys, ["info"], raising(MultipleDevicesError([PEDAL, other])))
    assert code == 4
    assert "3F1A-UUID" in err and "-58 dBm" in err
    assert "OTHER-ID" in err
    assert "hint:" in err and "--device" in err


def test_bluetooth_unavailable_hint(capsys: pytest.CaptureFixture[str]) -> None:
    code, _, err = run(capsys, ["info"], raising(BluetoothUnavailableError("denied")))
    assert code == 5
    assert "hint:" in err


@pytest.mark.parametrize("json_flag", [False, True])
def test_timeout_exit_6(capsys: pytest.CaptureFixture[str], json_flag: bool) -> None:
    # A lost link → exit 6 (read timeouts are covered in test_cli_info_regions.py).
    fake = FakeTransport.from_capture(FW96_CONNECT, disconnect_after=0)
    argv = ["info", "--json"] if json_flag else ["info"]
    code, out, err = run(capsys, argv, factory_for(fake))
    assert code == 6
    assert "error:" in err
    if json_flag:
        assert out == ""


@pytest.mark.parametrize("json_flag", [False, True])
def test_handshake_error_exit_7(capsys: pytest.CaptureFixture[str], json_flag: bool) -> None:
    fake = FakeTransport.from_capture(FW96_CONNECT, drop={QUERY: 3})
    argv = ["--timeout", "0.05", "info"] + (["--json"] if json_flag else [])
    code, out, err = run(capsys, argv, factory_for(fake))
    assert code == 7
    assert "error:" in err
    assert "Traceback" not in err
    if json_flag:
        assert out == ""
    assert fake.closed


def test_untested_firmware_warning(capsys: pytest.CaptureFixture[str]) -> None:
    original = decode_frame(CAP.rx(QUERY)).body
    fw97 = with_payload(CAP.rx(QUERY), b"TANK-Gv2_097" + original[12:])
    fake = FakeTransport.from_capture(FW96_CONNECT, replies={QUERY: fw97})
    code, out, err = run(capsys, ["info", "--json"], factory_for(fake))
    assert code == 0
    assert err.startswith("warning:")
    assert "97" in err and "96" in err
    doc = json.loads(out)
    assert doc["identity"]["firmware_untested"] is True


def test_trace_flag(capsys: pytest.CaptureFixture[str]) -> None:
    fake = FakeTransport.from_capture(FW96_CONNECT)
    code, out, err = run(capsys, ["--trace", "info"], factory_for(fake))
    assert code == 0
    assert "TX 00 59 11 00 00 00 ff" in err
    assert "TX" not in out


def test_no_trace_by_default(capsys: pytest.CaptureFixture[str]) -> None:
    fake = FakeTransport.from_capture(FW96_CONNECT)
    _, _, err = run(capsys, ["info"], factory_for(fake))
    assert "TX" not in err


def test_unexpected_error_exit_1(capsys: pytest.CaptureFixture[str]) -> None:
    async def factory(
        device_id: str | None, scan_timeout: float
    ) -> tuple[Transport, DeviceInfo | None]:
        raise RuntimeError("bug")

    code, out, err = run(capsys, ["info"], factory)
    assert code == 1
    assert "error:" in err
    assert "Traceback" not in err


def test_debug_env_shows_traceback(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENVAVE_DEBUG", "1")
    code, _, err = run(capsys, ["info"], raising(NoDeviceFoundError("none")))
    assert code == 3
    assert "Traceback" in err


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["--version"])
    out, _ = capsys.readouterr()
    assert code == 0
    assert openvave.__version__ in out


def test_usage_error_exit_2(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["bogus"]) == 2
    assert main([]) == 2
    capsys.readouterr()
