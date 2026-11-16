"""``openvave info`` region output: JSON schema, fields, determinism, human dumps (T038)."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from openvave.cli import main
from openvave.models import DeviceInfo
from openvave.protocol import decode_frame
from openvave.transport import Transport
from openvave.transport.fake import FakeTransport
from tests.support.captures import (
    DEVICE_INFO,
    FW96_CONNECT,
    GLOBAL,
    PRESET,
    QUERY,
    REPO_ROOT,
    STATUS,
    load_capture,
)
from tests.support.mutations import with_payload

CAP = load_capture(FW96_CONNECT)
PEDAL = DeviceInfo("3F1A-UUID", "TANK-Gv2_BLE", -58)
SCHEMA_PATH = REPO_ROOT / "specs" / "001-readonly-ble-connection" / "contracts" / "info.schema.json"
DECODED_FIELD_SCHEMA_PATH = (
    REPO_ROOT / "specs" / "002-preset-byte-map" / "contracts" / "decoded-field.schema.json"
)
ECHO_LEN = 8
KEY_FOR = {
    "device_info": DEVICE_INFO,
    "global": GLOBAL,
    "current_preset": PRESET,
    "status": STATUS,
}

Factory = Callable[[str | None, float], Awaitable[tuple[Transport, DeviceInfo | None]]]


def factory_for(fake: FakeTransport, device: DeviceInfo | None = PEDAL) -> Factory:
    async def factory(
        device_id: str | None, scan_timeout: float
    ) -> tuple[Transport, DeviceInfo | None]:
        return fake, device

    return factory


def recorded(label: str) -> bytes:
    return decode_frame(CAP.rx(label)).body[ECHO_LEN:]


def run(
    capsys: pytest.CaptureFixture[str], argv: list[str], fake: FakeTransport | None = None
) -> tuple[int, str, str, FakeTransport]:
    fake = fake or FakeTransport.from_capture(FW96_CONNECT)
    code = main(argv, transport_factory=factory_for(fake))
    out, err = capsys.readouterr()
    return code, out, err, fake


def info_json(capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    code, out, err, _ = run(capsys, ["info", "--json"])
    assert code == 0, err
    doc: dict[str, Any] = json.loads(out)
    return doc


def dump_lines(data: bytes) -> list[str]:
    return [f"  {i:02x}: {data[i : i + 16].hex(' ')}" for i in range(0, len(data), 16)]


def test_json_validates_against_schema(capsys: pytest.CaptureFixture[str]) -> None:
    schema = json.loads(Path(SCHEMA_PATH).read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(info_json(capsys), schema, cls=jsonschema.Draft202012Validator)


def test_json_region_data_equals_capture(capsys: pytest.CaptureFixture[str]) -> None:
    regions = info_json(capsys)["regions"]
    assert set(regions) == set(KEY_FOR)
    for key, label in KEY_FOR.items():
        assert regions[key]["data"] == recorded(label).hex(" ")
        assert regions[key]["length"] == len(recorded(label))
    assert regions["global"]["address"] == "0x20000000"
    assert regions["device_info"]["address"] == "0xd0000000"
    assert regions["device_info"]["type"] == 5


def test_json_fields(capsys: pytest.CaptureFixture[str]) -> None:
    regions = info_json(capsys)["regions"]
    flag = [f for f in regions["global"]["fields"] if f["offset"] == 3]
    assert flag == [
        {
            "offset": 3,
            "size": 1,
            "name": "not_in_edit_mode",
            "value": recorded(GLOBAL)[3],
            "confidence": "confirmed",
            "raw": recorded(GLOBAL)[3],
            "mask": None,
            "encoding": "selector",
            "range": {"min": 0, "max": 2},
            "display": "normal",
            "interpreted": 1,
            "out_of_range": False,
        }
    ]
    knob = regions["current_preset"]["fields"]
    assert [(f["offset"], f["value"]) for f in knob] == [
        (offset, recorded(PRESET)[offset]) for offset in range(18)
    ]
    assert [f["name"] for f in regions["global"]["fields"]] == [
        "browse_bank",
        "bank",
        "slot",
        "not_in_edit_mode",
    ]
    assert regions["device_info"]["fields"] == []
    assert regions["status"]["fields"] == []
    for region in regions.values():
        assert region["map_firmware"] == 96
    assert regions["global"]["unknown_offsets"] == []
    assert regions["status"]["unknown_offsets"] == [0]
    assert regions["device_info"]["unknown_offsets"] == list(range(32))
    assert regions["current_preset"]["unknown_offsets"] == [18, 19, 20]


def test_json_fields_validate_decoded_field_schema(capsys: pytest.CaptureFixture[str]) -> None:
    schema = json.loads(DECODED_FIELD_SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    doc = info_json(capsys)
    assert doc["schema_version"] == 1
    items = [f for region in doc["regions"].values() for f in region["fields"]]
    assert len(items) == 4 + 18  # global 0-3, preset 0-17
    for item in items:
        jsonschema.validate(item, schema, cls=jsonschema.Draft202012Validator)


def test_json_sends_captured_frames_in_order(capsys: pytest.CaptureFixture[str]) -> None:
    code, _, _, fake = run(capsys, ["info", "--json"])
    assert code == 0
    assert fake.sent == CAP.ordered_tx


def test_two_runs_identical_except_read_at(capsys: pytest.CaptureFixture[str]) -> None:
    first = info_json(capsys)
    second = info_json(capsys)
    first.pop("read_at")
    second.pop("read_at")
    assert first == second


def test_human_region_blocks(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err, _ = run(capsys, ["info"])
    assert code == 0
    assert err == ""
    lines = out.splitlines()
    assert lines[0] == "Device     TANK-Gv2  (firmware 96)"
    assert "Device info   type 5 @ 0xD0000000, 32 bytes   [meaning: unknown]" in lines
    assert "Global        type 4 @ 0x20000000, 4 bytes    [meaning: unknown]" in lines
    assert "Status        type 4 @ 0xD0000000, 1 byte     [meaning: unknown]" in lines
    for label in (DEVICE_INFO, GLOBAL, STATUS):
        expected = dump_lines(recorded(label))
        start = lines.index(expected[0])
        assert lines[start : start + len(expected)] == expected
    assert "  00: 00 00 01 01" in lines
    assert "  10: " + recorded(DEVICE_INFO)[16:].hex(" ") in lines
    assert "      [0]  browsed bank                   0    0–8        observed" in lines
    assert "      [2]  slot                           1    0–3        observed" in lines
    assert "      [3]  mode                      normal    selector   confirmed" in lines
    assert "      unknown: 0" in lines  # status only: global is fully named
    assert "      unknown: 0" in lines
    device_block = lines[lines.index(dump_lines(recorded(DEVICE_INFO))[0]) :]
    assert not device_block[2].startswith("      ")  # device info stays undecoded


def test_human_untested_firmware_note(capsys: pytest.CaptureFixture[str]) -> None:
    reply = with_payload(CAP.rx(QUERY), b"TANK-Gv2_097".ljust(27, b"\x00"))
    fake = FakeTransport.from_capture(FW96_CONNECT, replies={QUERY: reply})
    code, out, _, _ = run(capsys, ["info"], fake)
    assert code == 0
    lines = out.splitlines()
    note = "  (decoded with the fw 96 map)"
    assert ("Global        type 4 @ 0x20000000, 4 bytes    [meaning: unknown]" + note) in lines
    assert ("Status        type 4 @ 0xD0000000, 1 byte     [meaning: unknown]" + note) in lines
    assert "Device info   type 5 @ 0xD0000000, 32 bytes   [meaning: unknown]" in lines


def test_human_omits_current_preset(capsys: pytest.CaptureFixture[str]) -> None:
    _, out, _, _ = run(capsys, ["info"])
    assert "0x10000000" not in out
    assert "knob" not in out


def test_human_block_order(capsys: pytest.CaptureFixture[str]) -> None:
    _, out, _, _ = run(capsys, ["info"])
    assert out.index("Device info") < out.index("Global") < out.index("Status")
    assert "\n\nDevice info" in out


@pytest.mark.parametrize("json_flag", [False, True])
def test_read_timeout_exit_6(capsys: pytest.CaptureFixture[str], json_flag: bool) -> None:
    fake = FakeTransport.from_capture(FW96_CONNECT, drop={GLOBAL: 1})
    argv = ["--timeout", "0.05", "info"] + (["--json"] if json_flag else [])
    code = main(argv, transport_factory=factory_for(fake))
    out, err = capsys.readouterr()
    assert code == 6
    assert "error:" in err
    assert "Traceback" not in err
    assert out == ""
    assert fake.sent.count(CAP.tx(GLOBAL)) == 1
    assert fake.closed
