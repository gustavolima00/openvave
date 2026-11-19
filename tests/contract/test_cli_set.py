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
from tests.support.write_fixture import (
    ACK,
    EDIT,
    NORMAL,
    TUNER,
    demote,
    make_fake,
    nak,
    write_frame,
    writes,
)

PEDAL = DeviceInfo("3F1A-UUID", "TANK-Gv2_BLE", -58)
SCHEMA = REPO_ROOT / "specs/004-remote-edit-save-restore/contracts/write-result.schema.json"
GAIN_90 = "00 59 22 16 00 00 04 04 00 00 10 0e 00 00 0f 04 5a 3c 46 32 32 00 00 00 00 05 04 07 76"
NOT_SAVED = (
    "Not saved. Discard: openvave preset reload --discard-edits "
    "(or leave edit mode on the pedal without saving)"
)
NOT_SAVED_NORMAL = (
    "Not saved. Discard: openvave preset reload   Keep: openvave preset save --unsafe"
)

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


def test_dry_run_shows_the_refusal(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    demote(monkeypatch, "block_switch")  # every fw 96 row is confirmed since spec 007
    code, out, err, fake = run(capsys, ["set", "gain", "90", "--dry-run"], make_fake(TUNER))
    assert code == 0, err
    assert "refused: tuner_mode" in out
    assert "dry run: nothing sent" in out
    assert writes(fake) == []
    code, out, err, fake = run(capsys, ["set", "mod_on", "on", "--dry-run"])
    assert code == 0
    assert "refused: experimental_required" in out
    assert "--experimental" in out
    code, out, err, fake = run(capsys, ["set", "gain", "90", "--dry-run"])
    assert code == 0
    assert "refused" not in out  # the knob block is confirmed on fw 96


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
    assert plan["confidence"] == "confirmed"
    assert plan["before"] == sf.PUBLIC_PRESET.hex(" ")
    assert plan["global_before"] == "00 00 01 00"
    result = doc["result"]
    assert result["ack"] is True
    assert result["reply"] == ACK.hex(" ")
    assert result["applied"] is True
    assert result["changes"] == [
        {"region": "preset", "offset": 6, "before": 60, "after": 90, "name": "gain"}
    ]


def test_json_dry_run_has_no_result(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    demote(monkeypatch, "led_colour")  # every fw 96 row is confirmed since spec 007
    code, out, _, _ = run(capsys, ["set", "led_colour", "#ff0000", "--dry-run", "--json"])
    assert code == 0
    doc = json.loads(out)
    validate(doc)
    assert doc["plan"]["dry_run"] is True
    assert doc["plan"]["refusal"] == "experimental_required"
    assert "result" not in doc


def test_refused_exit_1(capsys: pytest.CaptureFixture[str]) -> None:
    code, _, err, fake = run(capsys, ["set", "gain", "90", "--experimental"], make_fake(TUNER))
    assert code == 1
    assert "tuner_mode" in err
    assert "tuner" in err
    assert writes(fake) == []


BYPASS = bytes([0, 0, 0xFF, NORMAL])


def test_refused_in_bypass_exit_1(capsys: pytest.CaptureFixture[str]) -> None:
    fake = make_fake(NORMAL, buffer=bytes(21), glob=BYPASS)
    code, _, err, fake = run(capsys, ["set", "gain", "90"], fake)
    assert code == 1
    assert "bypassed" in err
    assert writes(fake) == []
    assert all(f[2] in (0x11, 0x23) for f in fake.sent)


# -- spec 004: normal mode and section input (contracts/cli.md "openvave set") ---------------


def test_normal_mode_output(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err, fake = run(capsys, ["set", "gain", "90"], make_fake(NORMAL))
    assert code == 0, err
    assert out.splitlines() == [
        "Set gain 60 → 90   (current preset 1B, normal mode)",
        f"  write  {GAIN_90}",
        "  reply  00 59 00 01 00 00 00 ff   ACK",
        "  after  [6] gain 90   applied",
        NOT_SAVED_NORMAL,
    ]
    assert writes(fake) == [bytes.fromhex(GAIN_90)]


DECAY_53 = write_frame(
    0x10000004, sf.PUBLIC_PRESET[4:15] + bytes([53]) + sf.PUBLIC_PRESET[16:18]
).hex(" ")


@pytest.mark.parametrize(
    "argv", [["10", "--type", "spring"], ["--type", "SPRING", "10"], ["--raw", "53"]]
)
def test_type_input_output(capsys: pytest.CaptureFixture[str], argv: list[str]) -> None:
    code, out, err, fake = run(capsys, ["set", "reverb_decay", *argv], make_fake(NORMAL))
    assert code == 0, err
    assert out.splitlines() == [
        "Set reverb_decay 5 (room 6) → 53 (spring 10)   (current preset 1B, normal mode)",
        f"  write  {DECAY_53}",
        "  reply  00 59 00 01 00 00 00 ff   ACK",
        "  after  [15] reverb_decay 53 (spring 10)   applied",
        NOT_SAVED_NORMAL,
    ]
    assert [f.hex(" ") for f in writes(fake)] == [DECAY_53]


def test_bare_position_keeps_the_current_type(capsys: pytest.CaptureFixture[str]) -> None:
    # 1B's decay is raw 5 = room 6; "20" means room 20 = raw 19, not raw 20
    code, out, err, fake = run(capsys, ["set", "reverb_decay", "20"], make_fake(NORMAL))
    assert code == 0, err
    assert out.splitlines()[0] == (
        "Set reverb_decay 5 (room 6) → 19 (room 20)   (current preset 1B, normal mode)"
    )
    expected = write_frame(
        0x10000004, sf.PUBLIC_PRESET[4:15] + bytes([19]) + sf.PUBLIC_PRESET[16:18]
    )
    assert writes(fake) == [expected]


def test_bare_position_with_reverb_off_needs_a_type(capsys: pytest.CaptureFixture[str]) -> None:
    off = sf.PUBLIC_PRESET[:15] + bytes([41]) + sf.PUBLIC_PRESET[16:]  # between room and spring
    code, out, err, fake = run(
        capsys, ["set", "reverb_decay", "20", "--dry-run"], make_fake(NORMAL, buffer=off)
    )
    assert code == 0, err
    assert "refused: type_required" in out
    code, _, err, fake = run(capsys, ["set", "reverb_decay", "20"], make_fake(NORMAL, buffer=off))
    assert code == 1
    assert "type_required" in err
    assert "--type" in err
    assert writes(fake) == []


@pytest.mark.parametrize(
    ("argv", "needle"),
    [
        (["set", "gain", "10", "--type", "room"], "reverb_decay"),
        (["set", "gain", "10", "--raw"], "reverb_decay"),
        (["set", "reverb_decay", "3", "--type", "hall"], "room, spring, cloud"),
        (["set", "reverb_decay", "3", "--type", "orange"], "room, spring, cloud"),
        (["set", "reverb_decay", "41", "--type", "room"], "1–40"),
        (["set", "reverb_decay", "0"], "1–40"),
        (["set", "reverb_decay", "ten", "--type", "room"], "1–40"),
        (["set", "reverb_decay", "53", "--raw", "--type", "room"], "--raw"),
        (["set", "reverb_decay", "loud", "--raw"], "0–127"),
    ],
)
def test_bad_type_input_exit_2(
    capsys: pytest.CaptureFixture[str], argv: list[str], needle: str
) -> None:
    fake = make_fake(NORMAL)
    code, _, err, _ = run(capsys, argv, fake)
    assert code == 2
    assert needle in err
    assert fake.sent == []


def test_json_in_normal_mode_has_no_refusal(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err, _ = run(capsys, ["set", "gain", "90", "--json"], make_fake(NORMAL))
    assert code == 0, err
    doc = json.loads(out)
    validate(doc)
    assert doc["plan"]["refusal"] is None
    assert doc["plan"]["global_before"] == "00 00 01 01"
    assert doc["result"]["applied"] is True


@pytest.mark.parametrize(
    ("glob", "buffer", "reason"),
    [
        (bytes([0, 0, 1, TUNER]), sf.PUBLIC_PRESET, "tuner_mode"),
        (BYPASS, bytes(21), "bypassed"),
        (bytes([0, 0, 1, 5]), sf.PUBLIC_PRESET, "unrecognised_state"),
        (
            bytes([0, 0, 1, NORMAL]),
            sf.PUBLIC_PRESET[:15] + b"\x55" + sf.PUBLIC_PRESET[16:],
            "type_required",
        ),
    ],
)
def test_json_dry_run_refusals_validate(
    capsys: pytest.CaptureFixture[str], glob: bytes, buffer: bytes, reason: str
) -> None:
    fake = make_fake(NORMAL, buffer=buffer, glob=glob)
    argv = ["set", "reverb_decay", "20", "--dry-run", "--json"]
    code, out, err, _ = run(capsys, argv, fake)
    assert code == 0, err
    doc = json.loads(out)
    validate(doc)
    assert doc["plan"]["refusal"] == reason


def test_experimental_required_message(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    demote(monkeypatch, "block_switch")  # every fw 96 row is confirmed since spec 007
    code, _, err, fake = run(capsys, ["set", "mod_on", "on"])
    assert code == 1
    assert "--experimental" in err
    assert "observed" in err
    assert writes(fake) == []


def test_confirmed_write_needs_no_opt_in(capsys: pytest.CaptureFixture[str]) -> None:
    # spec 003 M3: knob block confirmed by gate sessions A and B on fw 96 (SC-005)
    code, out, err, fake = run(capsys, ["set", "gain", "90"])
    assert code == 0, err
    assert f"  write  {GAIN_90}" in out
    assert "applied" in out
    assert [f.hex(" ") for f in writes(fake)] == [GAIN_90]


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


def test_keep_hint_names_the_save_opt_ins_while_unconfirmed() -> None:
    # the hint must stay runnable: --experimental while stored_slot / commit are not confirmed
    from openvave.protocol.writes import sendable_by_default

    needs = not all(sendable_by_default(k, None, 96) for k in ("stored_slot", "commit"))
    assert ("--experimental" in NOT_SAVED_NORMAL) is needs
    assert "Keep: openvave preset save --unsafe" in NOT_SAVED_NORMAL
