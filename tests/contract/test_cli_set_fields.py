"""``openvave set FIELD=VALUE ...``: several fields over one connection (contracts/cli.md).

The ``set FIELD VALUE`` form is unchanged (``test_cli_set.py``).
"""

from __future__ import annotations

import json
from typing import Any

import jsonschema
import pytest

from openvave.protocol.bytemap import type_raw
from tests.contract.test_cli_set import NOT_SAVED_NORMAL, run
from tests.support import storage_fixture as sf
from tests.support.captures import REPO_ROOT
from tests.support.write_fixture import ACK, NORMAL, TUNER, make_fake, write_frame, writes

SCHEMA = REPO_ROOT / "specs/004-remote-edit-save-restore/contracts/set-fields-result.schema.json"
P = sf.PUBLIC_PRESET
ROOM_18 = type_raw("reverb_decay", "room", 18)
KNOB = write_frame(0x10000004, P[4:6] + bytes([95, 58]) + P[8:15] + bytes([ROOM_18]) + P[16:18])
DELAY_ON = write_frame(0x10000002, b"\x01")
LED = write_frame(0x10000012, bytes.fromhex("2040ff"))
OWNER = [
    "set",
    "gain=95",
    "treble=58",
    "reverb_decay=room:18",
    "delay_on=on",
    "led_colour=#2040ff",
    "--experimental",
]
ACK_HEX = ACK.hex(" ")


def validate(doc: dict[str, Any]) -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    jsonschema.validators.validator_for(schema)(schema).validate(doc)


def test_human_output(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err, fake = run(capsys, OWNER, make_fake(NORMAL))
    assert code == 0, err
    assert out.splitlines() == [
        "Set 5 fields   (current preset 1B, normal mode)",
        "  gain          60 → 95",
        "  treble        60 → 58",
        "  reverb_decay  5 (room 6) → 17 (room 18)",
        "  delay_on      off → on",
        "  led_colour    #431643 → #2040ff",
        f"  write  {KNOB.hex(' ')}   knob_block: gain, treble, reverb_decay",
        f"  reply  {ACK_HEX}   ACK   applied",
        f"  write  {DELAY_ON.hex(' ')}   block_switch 2: delay_on",
        f"  reply  {ACK_HEX}   ACK   applied",
        f"  write  {LED.hex(' ')}   led_colour: led_colour",
        f"  reply  {ACK_HEX}   ACK   applied",
        "  after  [2] delay_on on",
        "         [6] gain 95",
        "         [7] treble 58",
        "         [15] reverb_decay 17 (room 18)",
        "         [18] 32",
        "         [19] 64",
        "         [20] 255",
        NOT_SAVED_NORMAL,
    ]
    assert writes(fake) == [KNOB, DELAY_ON, LED]
    # one connection: one handshake for the whole batch
    assert sum(1 for f in fake.sent if f[2] == 0x11) == 1


def test_dry_run_prints_every_frame_and_sends_nothing(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err, fake = run(capsys, [*OWNER, "--dry-run"], make_fake(NORMAL))
    assert code == 0, err
    lines = out.splitlines()
    assert f"  write  {KNOB.hex(' ')}   knob_block: gain, treble, reverb_decay" in lines
    assert f"  write  {DELAY_ON.hex(' ')}   block_switch 2: delay_on" in lines
    assert f"  write  {LED.hex(' ')}   led_colour: led_colour" in lines
    assert lines[-1] == "  dry run: nothing sent"
    assert writes(fake) == []


def test_dry_run_shows_the_refusal(capsys: pytest.CaptureFixture[str]) -> None:
    argv = ["set", "gain=95", "delay_on=on", "--dry-run"]
    code, out, err, fake = run(capsys, argv, make_fake(NORMAL))
    assert code == 0, err
    assert (
        "  refused: experimental_required "
        "(delay_on: block_switch is 'observed'; needs --experimental)"
    ) in out.splitlines()
    assert writes(fake) == []


def test_unchanged_fields_are_listed(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err, fake = run(capsys, ["set", "gain=60", "treble=58"], make_fake(NORMAL))
    assert code == 0, err
    assert out.splitlines()[1:3] == ["  gain    60 (unchanged)", "  treble  60 → 58"]
    assert len(writes(fake)) == 1


def test_all_unchanged_sends_nothing(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err, fake = run(capsys, ["set", "gain=60", "amp_on=on"], make_fake(NORMAL))
    assert code == 0, err
    assert out.strip() == "gain, amp_on already set; nothing sent"
    assert writes(fake) == []


def test_single_assignment_uses_the_batch_form(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err, fake = run(capsys, ["set", "gain=95"], make_fake(NORMAL))
    assert code == 0, err
    assert out.splitlines()[0] == "Set 1 field   (current preset 1B, normal mode)"
    assert len(writes(fake)) == 1


def test_typed_values(capsys: pytest.CaptureFixture[str]) -> None:
    argv = ["set", "reverb_decay=18", "mod_fx=phaser:2", "delay_mix=raw:50", "--dry-run"]
    code, out, err, _ = run(capsys, argv, make_fake(NORMAL))
    assert code == 0, err
    assert "  reverb_decay  5 (room 6) → 17 (room 18)" in out
    assert "  mod_fx        0 (chorus 1) → 45 (phaser 2)" in out
    assert "  delay_mix     0 (analog 1) → 50 (tape 7)" in out


def test_json_result(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err, _ = run(capsys, [*OWNER, "--json"], make_fake(NORMAL))
    assert code == 0, err
    doc = json.loads(out)
    validate(doc)
    assert doc["command"] == "set"
    plan = doc["plan"]
    assert plan["dry_run"] is False
    assert plan["refusal"] is None
    assert [w["frame"] for w in plan["writes"]] == [KNOB.hex(" "), DELAY_ON.hex(" "), LED.hex(" ")]
    assert plan["writes"][0]["fields"] == ["gain", "treble", "reverb_decay"]
    assert plan["writes"][1]["target"] == {
        "kind": "block_switch",
        "type": 4,
        "address": "0x10000002",
        "length": 1,
        "argument": 2,
    }
    assert [f["field"] for f in plan["fields"]] == [
        "gain",
        "treble",
        "reverb_decay",
        "delay_on",
        "led_colour",
    ]
    result = doc["result"]
    assert result["applied"] is True
    assert [w["status"] for w in result["writes"]] == ["acked"] * 3
    assert result["fields"] == {
        "gain": "applied",
        "treble": "applied",
        "reverb_decay": "applied",
        "delay_on": "applied",
        "led_colour": "applied",
    }


def test_json_dry_run_has_no_result(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _, _ = run(capsys, ["set", "gain=95", "delay_on=on", "--dry-run", "--json"])
    assert code == 0
    doc = json.loads(out)
    validate(doc)
    assert doc["plan"]["dry_run"] is True
    assert doc["plan"]["refusal"] == "experimental_required"
    assert doc["plan"]["refused_field"] == "delay_on"
    assert "result" not in doc


def test_refused_exit_1(capsys: pytest.CaptureFixture[str]) -> None:
    code, _, err, fake = run(capsys, OWNER, make_fake(TUNER))
    assert code == 1
    assert "tuner_mode" in err
    assert writes(fake) == []
    code, _, err, fake = run(capsys, ["set", "gain=95", "treble=200"], make_fake(NORMAL))
    assert code == 1
    assert "out_of_range" in err and "treble" in err
    assert writes(fake) == []


def test_nak_mid_batch_reports_applied_fields(capsys: pytest.CaptureFixture[str]) -> None:
    fake = make_fake(NORMAL, faults={"block_switch": "nak"})
    code, out, err, _ = run(capsys, OWNER, fake)
    assert code == 7
    assert out == ""
    lines = err.splitlines()
    assert lines[0].startswith("error: write not acknowledged")
    assert lines[1:7] == [
        "  gain          applied",
        "  treble        applied",
        "  reverb_decay  applied",
        "  delay_on      unknown (nak)",
        "  led_colour    not sent",
        "Nothing was retried. Applied fields are in the edit buffer, not saved. "
        "Discard: openvave preset reload",
    ]


def test_nak_mid_batch_json(capsys: pytest.CaptureFixture[str]) -> None:
    fake = make_fake(NORMAL, faults={"block_switch": "nak"})
    code, out, err, _ = run(capsys, [*OWNER, "--json"], fake)
    assert code == 7
    doc = json.loads(out)
    validate(doc)
    assert doc["result"]["applied"] is False
    assert [w["status"] for w in doc["result"]["writes"]] == ["acked", "nak", "not_sent"]
    assert doc["result"]["fields"]["gain"] == "applied"
    assert doc["result"]["fields"]["delay_on"] == "unknown"
    assert doc["result"]["fields"]["led_colour"] == "not_sent"
    assert "delay_on      unknown (nak)" in err


def test_not_applied_exit_8(capsys: pytest.CaptureFixture[str]) -> None:
    fake = make_fake(NORMAL, faults={"knob_block": "ignore"})
    code, _, err, _ = run(capsys, ["set", "gain=95", "delay_on=on", "--experimental"], fake)
    assert code == 8
    assert "  gain      not applied" in err
    assert "  delay_on  not sent" in err


@pytest.mark.parametrize(
    ("argv", "needle"),
    [
        (["set", "gain=95", "treble", "58"], "FIELD=VALUE"),
        (["set", "gain", "95", "treble=58"], "FIELD=VALUE"),
        (["set", "gain=95", "gain=96"], "twice"),
        (["set", "gain=95", "fuzz=3"], "unknown field 'fuzz'"),
        (["set", "gain=95", "delay_on=maybe"], "on or off"),
        (["set", "gain=loud"], "gain"),
        (["set", "reverb_decay=lake:3"], "room"),
        (["set", "reverb_decay=room:41"], "1–40"),
        (["set", "gain=95", "--type", "room"], "TYPE:POSITION"),
        (["set", "gain=95", "--raw"], "raw:"),
        (["set", "=95"], "FIELD=VALUE"),
        (["set", "gain"], "FIELD VALUE"),
    ],
)
def test_usage_errors_exit_2_without_connecting(
    capsys: pytest.CaptureFixture[str], argv: list[str], needle: str
) -> None:
    fake = make_fake()
    code, _, err, _ = run(capsys, argv, fake)
    assert code == 2, err
    assert needle in err
    assert fake.sent == []
