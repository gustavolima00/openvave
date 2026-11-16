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
from tests.support.captures import QUERY as QUERY_LABEL
from tests.support.mutations import with_payload

CAP = load_capture(FW96_CONNECT)
PEDAL = DeviceInfo("3F1A-UUID", "TANK-Gv2_BLE", -58)
SCHEMA_PATH = (
    REPO_ROOT / "specs" / "001-readonly-ble-connection" / "contracts" / "preset-dump.schema.json"
)
DECODED_FIELD_SCHEMA_PATH = (
    REPO_ROOT / "specs" / "002-preset-byte-map" / "contracts" / "decoded-field.schema.json"
)
ECHO_LEN = 8
FW97_IDENTITY = b"TANK-Gv2_097".ljust(27, b"\x00")
DECODED_LINES = [
    "      [0]  amp on                        on    on/off     confirmed",
    "      [1]  mod on                       off    on/off     confirmed",
    "      [2]  delay on                     off    on/off     confirmed",
    "      [3]  reverb on                     on    on/off     confirmed",
    "      [4]  noise gate                    15    0–127      confirmed",
    "      [5]  amp type                      #4    selector   confirmed",
    "      [6]  gain                          60    0–127      confirmed",
    "      [7]  treble                        60    0–127      confirmed",
    "      [8]  middle                        70    0–127      confirmed",
    "      [9]  bass                          50    0–127      confirmed",
    "      [10] volume                        50    0–127      confirmed",
    "      [11] mod fx                         0    0–127      confirmed",
    "      [12] mod speed                      0    0–127      confirmed",
    "      [13] delay mix                      0    0–127      confirmed",
    "      [14] delay time                     0    0–127      confirmed",
    "      [15] reverb decay                   5    0–127      confirmed",
    "      [16] reverb mix                     4    0–127      confirmed",
    "      [17] IR cab                        #7    selector   confirmed",
    "      unknown: 18 19 20",
]
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


def run(
    capsys: pytest.CaptureFixture[str], argv: list[str], fake: FakeTransport | None = None
) -> tuple[int, str, str, FakeTransport]:
    fake = fake or FakeTransport.from_capture(FW96_CONNECT)
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
    # the fw96 capture is stored preset 1B
    assert [(f["offset"], f["name"], f["value"], f["confidence"]) for f in preset["fields"]] == [
        (0, "amp_on", 1, "confirmed"),
        (1, "mod_on", 0, "confirmed"),
        (2, "delay_on", 0, "confirmed"),
        (3, "reverb_on", 1, "confirmed"),
        (4, "noise_gate", 15, "confirmed"),
        (5, "amp_type", 4, "confirmed"),
        (6, "knob_unknown", 60, "confirmed"),
        (7, "treble", 60, "confirmed"),
        (8, "middle", 70, "confirmed"),
        (9, "bass", 50, "confirmed"),
        (10, "volume", 50, "confirmed"),
        (11, "mod_fx", 0, "confirmed"),
        (12, "mod_speed", 0, "confirmed"),
        (13, "delay_mix", 0, "confirmed"),
        (14, "delay_time", 0, "confirmed"),
        (15, "reverb_decay", 5, "confirmed"),
        (16, "reverb_mix", 4, "confirmed"),
        (17, "ir_cab", 7, "confirmed"),
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
        *DECODED_LINES,
    ]


def fw97_fake() -> FakeTransport:
    reply = with_payload(CAP.rx(QUERY_LABEL), FW97_IDENTITY)
    return FakeTransport.from_capture(FW96_CONNECT, replies={QUERY_LABEL: reply})


def test_human_block_untested_firmware(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _, _ = run(capsys, ["preset", "dump"], fw97_fake())
    assert code == 0
    lines = out.splitlines()
    assert lines[0] == (
        "Current preset  (TANK-Gv2, firmware 97)   type 4 @ 0x10000000, 21 bytes"
        "  (decoded with the fw 96 map)"
    )
    assert lines[3:] == DECODED_LINES


def test_json_decoded_fields(capsys: pytest.CaptureFixture[str]) -> None:
    preset = preset_json(capsys)["preset"]
    assert preset["map_firmware"] == 96
    assert preset["unknown_offsets"] == [18, 19, 20]
    decay = next(f for f in preset["fields"] if f["name"] == "reverb_decay")
    assert decay == {
        "offset": 15,
        "size": 1,
        "name": "reverb_decay",
        "value": 5,
        "confidence": "confirmed",
        "raw": 5,
        "mask": None,
        "encoding": "continuous",
        "range": {"min": 0, "max": 127},
        "display": "5",
        "interpreted": 5,
        "out_of_range": False,
    }
    cab = next(f for f in preset["fields"] if f["name"] == "ir_cab")
    assert (cab["encoding"], cab["display"], cab["interpreted"]) == ("selector", "#7", 7)


def test_json_fields_validate_decoded_field_schema(capsys: pytest.CaptureFixture[str]) -> None:
    schema = json.loads(DECODED_FIELD_SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    fields = preset_json(capsys)["preset"]["fields"]
    assert fields
    for item in fields:
        jsonschema.validate(item, schema, cls=jsonschema.Draft202012Validator)


def test_json_untested_firmware(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err, _ = run(capsys, ["preset", "dump", "--json"], fw97_fake())
    assert code == 0, err
    doc = json.loads(out)
    assert doc["schema_version"] == 1
    assert doc["identity"]["firmware_untested"] is True
    assert doc["preset"]["map_firmware"] == 96
    assert [f["name"] for f in doc["preset"]["fields"]] == [
        name
        for _, name, _, _ in [
            (0, "amp_on", 1, "confirmed"),
            (1, "mod_on", 0, "confirmed"),
            (2, "delay_on", 0, "confirmed"),
            (3, "reverb_on", 1, "confirmed"),
            (4, "noise_gate", 15, "confirmed"),
            (5, "amp_type", 4, "confirmed"),
            (6, "knob_unknown", 60, "confirmed"),
            (7, "treble", 60, "confirmed"),
            (8, "middle", 70, "confirmed"),
            (9, "bass", 50, "confirmed"),
            (10, "volume", 50, "confirmed"),
            (11, "mod_fx", 0, "confirmed"),
            (12, "mod_speed", 0, "confirmed"),
            (13, "delay_mix", 0, "confirmed"),
            (14, "delay_time", 0, "confirmed"),
            (15, "reverb_decay", 5, "confirmed"),
            (16, "reverb_mix", 4, "confirmed"),
            (17, "ir_cab", 7, "confirmed"),
        ]
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
