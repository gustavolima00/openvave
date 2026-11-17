"""``openvave set``: output, dry run, JSON and exit codes (T029, contracts/cli.md)."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

import jsonschema
import pytest

from openvave.cli import main
from openvave.models import DeviceInfo
from openvave.transport import Transport
from openvave.transport.fake import FakeTransport
from tests.support import storage_fixture as sf
from tests.support.captures import REPO_ROOT
from tests.support.write_fixture import ACK, EDIT, NORMAL, make_fake, nak, write_frame, writes

PEDAL = DeviceInfo("3F1A-UUID", "TANK-Gv2_BLE", -58)
SCHEMA = REPO_ROOT / "specs/003-preset-backup-edit-writes/contracts/write-result.schema.json"
GAIN_90 = "00 59 22 16 00 00 04 04 00 00 10 0e 00 00 0f 04 5a 3c 46 32 32 00 00 00 00 05 04 07 76"
NOT_SAVED = "Not saved: leave edit mode on the pedal without saving to restore the stored preset."

Factory = Callable[[str | None, float], Awaitable[tuple[Transport, DeviceInfo | None]]]


def factory_for(fake: FakeTransport) -> Factory:
    async def factory(
        device_id: str | None, scan_timeout: float
    ) -> tuple[Transport, DeviceInfo | None]:
        return fake, PEDAL

    return factory


def run(
    capsys: pytest.CaptureFixture[str], argv: list[str], fake: FakeTransport | None = None
) -> tuple[int, str, str, FakeTransport]:
    fake = fake or make_fake()
    code = main(argv, transport_factory=factory_for(fake))
    out, err = capsys.readouterr()
    return code, out, err, fake


def validate(doc: dict[str, Any]) -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    jsonschema.validators.validator_for(schema)(schema).validate(doc)


def test_human_output(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err, fake = run(capsys, ["set", "gain", "90", "--experimental"])
    assert code == 0, err
    assert out.splitlines() == [
        "Set gain 60 → 90   (current preset 1B, edit mode)",
        f"  write  {GAIN_90}",
        "  reply  00 59 00 01 00 00 00 ff   ACK",
        "  after  [6] gain 90   applied",
        NOT_SAVED,
    ]
    assert writes(fake) == [bytes.fromhex(GAIN_90)]


def test_switch_and_colour_values(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err, fake = run(capsys, ["set", "mod_on", "on", "--experimental"])
    assert code == 0, err
    assert out.splitlines()[0].startswith("Set mod_on off → on")
    assert writes(fake) == [write_frame(0x10000001, b"\x01")]
    for value in ("#ff0000", "255,0,0"):
        code, out, err, fake = run(capsys, ["set", "led_colour", value, "--experimental"])
        assert code == 0, err
        assert writes(fake) == [write_frame(0x10000012, bytes.fromhex("ff 00 00"))]
        assert out.splitlines()[0].startswith("Set led_colour #431643 → #ff0000")


def test_dry_run_sends_no_write(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err, fake = run(capsys, ["set", "gain", "90", "--dry-run", "--experimental"])
    assert code == 0, err
    assert out.splitlines() == [
        "Set gain 60 → 90   (current preset 1B, edit mode)",
        f"  write  {GAIN_90}",
        "  dry run: nothing sent",
    ]
    assert writes(fake) == []


def test_dry_run_shows_the_refusal(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err, fake = run(capsys, ["set", "gain", "90", "--dry-run"], make_fake(NORMAL))
    assert code == 0, err
    assert "refused: not_edit_mode" in out
    assert "dry run: nothing sent" in out
    assert writes(fake) == []
    code, out, err, fake = run(capsys, ["set", "gain", "90", "--dry-run"])
    assert code == 0
    assert "refused: experimental_required" in out
    assert "--experimental" in out


def test_no_change(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err, fake = run(capsys, ["set", "gain", "60", "--experimental"])
    assert code == 0, err
    assert out.strip() == "gain is already 60; nothing sent"
    assert writes(fake) == []


def test_json_result(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err, _ = run(capsys, ["set", "gain", "90", "--experimental", "--json"])
    assert code == 0, err
    doc = json.loads(out)
    validate(doc)
    assert doc["schema_version"] == 2
    assert doc["command"] == "set"
    plan = doc["plan"]
    assert plan["action"] == "set gain"
    assert plan["target"] == {
        "kind": "knob_block",
        "type": 4,
        "address": "0x10000004",
        "length": 14,
        "argument": None,
    }
    assert plan["frame"] == GAIN_90
    assert plan["dry_run"] is False
    assert plan["confidence"] == "hypothesis"
    assert plan["before"] == sf.PUBLIC_PRESET.hex(" ")
    assert plan["global_before"] == "00 00 01 00"
    result = doc["result"]
    assert result["ack"] is True
    assert result["reply"] == ACK.hex(" ")
    assert result["applied"] is True
    assert result["changes"] == [
        {"region": "preset", "offset": 6, "before": 60, "after": 90, "name": "gain"}
    ]


def test_json_dry_run_has_no_result(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _, _ = run(capsys, ["set", "gain", "90", "--dry-run", "--json"])
    assert code == 0
    doc = json.loads(out)
    validate(doc)
    assert doc["plan"]["dry_run"] is True
    assert doc["plan"]["refusal"] == "experimental_required"
    assert "result" not in doc


def test_refused_exit_1(capsys: pytest.CaptureFixture[str]) -> None:
    code, _, err, fake = run(capsys, ["set", "gain", "90", "--experimental"], make_fake(NORMAL))
    assert code == 1
    assert "edit mode" in err
    assert writes(fake) == []


def test_experimental_required_message(capsys: pytest.CaptureFixture[str]) -> None:
    code, _, err, fake = run(capsys, ["set", "gain", "90"])
    assert code == 1
    assert "--experimental" in err
    assert "hypothesis" in err
    assert writes(fake) == []


def test_out_of_range_exit_1(capsys: pytest.CaptureFixture[str]) -> None:
    code, _, err, fake = run(capsys, ["set", "gain", "128", "--experimental"])
    assert code == 1
    assert "out_of_range" in err or "range" in err
    assert writes(fake) == []


@pytest.mark.parametrize(
    ("argv", "needle"),
    [
        (["set", "knob_unknown", "1"], "gain"),
        (["set", "gain", "loud"], "gain"),
        (["set", "mod_on", "maybe"], "on"),
        (["set", "led_colour", "red"], "#rrggbb"),
        (["set", "led_colour", "1,2"], "#rrggbb"),
    ],
)
def test_usage_errors_exit_2_without_connecting(
    capsys: pytest.CaptureFixture[str], argv: list[str], needle: str
) -> None:
    fake = make_fake()
    code, _, err, _ = run(capsys, argv, fake)
    assert code == 2
    assert needle in err
    assert fake.sent == []


def test_nak_exit_7(capsys: pytest.CaptureFixture[str]) -> None:
    fake = make_fake(script={"w": (bytes.fromhex(GAIN_90), nak())})
    code, _, err, _ = run(capsys, ["set", "gain", "90", "--experimental"], fake)
    assert code == 7
    assert nak().hex(" ") in err


def test_not_applied_exit_8(capsys: pytest.CaptureFixture[str]) -> None:
    fake = make_fake(EDIT, apply_writes=False, script={"w": (bytes.fromhex(GAIN_90), ACK)})
    code, out, err, _ = run(capsys, ["set", "gain", "90", "--experimental"], fake)
    assert code == 8
    assert "not applied" in out
    assert "not applied" in err


def test_not_applied_json_keeps_stdout_empty(capsys: pytest.CaptureFixture[str]) -> None:
    fake = make_fake(EDIT, apply_writes=False, script={"w": (bytes.fromhex(GAIN_90), ACK)})
    code, out, err, _ = run(capsys, ["set", "gain", "90", "--experimental", "--json"], fake)
    assert code == 8
    assert out == ""
    assert "not applied" in err
