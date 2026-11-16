"""``openvave preset dump`` output: JSON schema, frames sent, human block (T049)."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

import jsonschema
import pytest

from openvave.cli import main
from openvave.models import DeviceInfo
from openvave.protocol import decode_frame
from openvave.transport import Transport
from openvave.transport.fake import FakeTransport
from tests.support.captures import FW96_CONNECT, PRESET, REPO_ROOT, load_capture

CAP = load_capture(FW96_CONNECT)
PEDAL = DeviceInfo("3F1A-UUID", "TANK-Gv2_BLE", -58)
SCHEMA_PATH = (
    REPO_ROOT / "specs" / "001-readonly-ble-connection" / "contracts" / "preset-dump.schema.json"
)
ECHO_LEN = 8
QUERY = bytes.fromhex("00 59 11 00 00 00 ff")
PRESET_READ = bytes.fromhex("00 59 23 08 00 00 04 00 00 00 10 15 00 00 d6")
EXPECTED_DATA = "01 00 00 01 0f 04 3c 3c 46 32 32 00 00 00 00 05 04 07 43 16 43"

Factory = Callable[[str | None, float], Awaitable[tuple[Transport, DeviceInfo | None]]]


def factory_for(fake: FakeTransport, device: DeviceInfo | None = PEDAL) -> Factory:
    async def factory(
        device_id: str | None, scan_timeout: float
    ) -> tuple[Transport, DeviceInfo | None]:
        return fake, device

    return factory


def run(capsys: pytest.CaptureFixture[str], argv: list[str]) -> tuple[int, str, str, FakeTransport]:
    fake = FakeTransport.from_capture(FW96_CONNECT)
    code = main(argv, transport_factory=factory_for(fake))
    out, err = capsys.readouterr()
    return code, out, err, fake


def preset_json(capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    code, out, err, _ = run(capsys, ["preset", "dump", "--json"])
    assert code == 0, err
    doc: dict[str, Any] = json.loads(out)
    return doc


def recorded_preset() -> bytes:
    return decode_frame(CAP.rx(PRESET)).body[ECHO_LEN:]


def test_json_validates_against_schema(capsys: pytest.CaptureFixture[str]) -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(preset_json(capsys), schema, cls=jsonschema.Draft202012Validator)


def test_json_content(capsys: pytest.CaptureFixture[str]) -> None:
    doc = preset_json(capsys)
    assert doc["schema_version"] == 1
    assert doc["command"] == "preset dump"
    assert doc["device"] == {"identifier": "3F1A-UUID", "name": "TANK-Gv2_BLE", "rssi": -58}
    assert doc["identity"]["name"] == "TANK-Gv2"
    assert doc["identity"]["firmware"] == 96
    assert "regions" not in doc
    preset = doc["preset"]
    assert preset["data"] == EXPECTED_DATA == recorded_preset().hex(" ")
    assert (preset["type"], preset["address"], preset["length"]) == (4, "0x10000000", 21)
    assert [(f["offset"], f["name"], f["value"], f["confidence"]) for f in preset["fields"]] == [
        (6, "knob_unknown", 60, "observed"),
        (16, "reverb_mix", 4, "hypothesis"),
        (17, "ir_cab", 7, "hypothesis"),
    ]


@pytest.mark.parametrize("json_flag", [False, True])
def test_sends_only_query_and_preset_read(
    capsys: pytest.CaptureFixture[str], json_flag: bool
) -> None:
    argv = ["preset", "dump"] + (["--json"] if json_flag else [])
    code, _, err, fake = run(capsys, argv)
    assert code == 0, err
    assert fake.sent == [QUERY, PRESET_READ]
    assert fake.closed


def test_human_block(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err, _ = run(capsys, ["preset", "dump"])
    assert code == 0
    assert err == ""
    assert out.splitlines() == [
        "Current preset  (TANK-Gv2, firmware 96)   type 4 @ 0x10000000, 21 bytes",
        "  00: 01 00 00 01 0f 04 3c 3c 46 32 32 00 00 00 00 05",
        "  10: 04 07 43 16 43",
        "      [6] knob (which one: unknown) = 60   (observed)",
        "      [16] reverb mix? = 4   (hypothesis)",
        "      [17] IR cab? = 7   (hypothesis)",
    ]


def test_global_options_after_subcommand(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _, _ = run(capsys, ["--json", "preset", "dump"])
    assert code == 0
    assert json.loads(out)["command"] == "preset dump"


def test_preset_without_action_is_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _, fake = run(capsys, ["preset"])
    assert code == 2
    assert out == ""
    assert fake.sent == []


@pytest.mark.parametrize("json_flag", [False, True])
def test_read_timeout_exit_6(capsys: pytest.CaptureFixture[str], json_flag: bool) -> None:
    fake = FakeTransport.from_capture(FW96_CONNECT, drop={PRESET: 1})
    argv = ["--timeout", "0.05", "preset", "dump"] + (["--json"] if json_flag else [])
    code = main(argv, transport_factory=factory_for(fake))
    out, err = capsys.readouterr()
    assert code == 6
    assert err.startswith("error:")
    assert "Traceback" not in err
    assert out == ""
    assert fake.closed
