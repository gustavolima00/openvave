"""``openvave bypass on | off <position>`` (spec 004 T028, contracts/cli.md, FR-007…FR-010)."""

from __future__ import annotations

import json
from typing import Any

import jsonschema
import pytest

from openvave.cli import main
from openvave.transport.fake import FakeTransport
from tests.contract.test_cli_set import factory_for
from tests.support import storage_fixture as sf
from tests.support.captures import REPO_ROOT
from tests.support.write_fixture import ACK, EDIT, NORMAL, TUNER, make_fake, nak, writes

SCHEMA = REPO_ROOT / "specs/004-remote-edit-save-restore/contracts/write-result.schema.json"
P = sf.PUBLIC_PRESET
EDITED = P[:6] + bytes([90]) + P[7:]
BYPASS_1B = "00 59 22 09 00 00 04 01 00 00 e1 01 00 00 01 17"
SELECT_1B = "00 59 22 09 00 00 04 01 00 00 e0 01 00 00 01 18"
BYPASSED = bytes([0, 0, 0xFF, NORMAL])
REPLY = "  reply  00 59 00 01 00 00 00 ff   ACK"


def bypassed_fake() -> FakeTransport:
    return make_fake(NORMAL, buffer=bytes(21), glob=BYPASSED)


def run(
    capsys: pytest.CaptureFixture[str], argv: list[str], fake: FakeTransport
) -> tuple[int, str, str]:
    code = main(["bypass", *argv], transport_factory=factory_for(fake))
    out, err = capsys.readouterr()
    return code, out, err


def validate(doc: dict[str, Any]) -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    jsonschema.validators.validator_for(schema)(schema).validate(doc)


# -- bypass on -----------------------------------------------------------------------------------


def test_on_human_output(capsys: pytest.CaptureFixture[str]) -> None:
    fake = make_fake(NORMAL)
    code, out, err = run(capsys, ["on", "--experimental"], fake)
    assert code == 0, err
    assert out.splitlines() == [
        "Bypass on   (was 1B, normal mode)",
        f"  write  {BYPASS_1B}",
        REPLY,
        "  now    bypass (slot ff, buffer all 00)   applied",
        "Leave bypass: openvave bypass off 1B",
    ]
    assert [f.hex(" ") for f in writes(fake)] == [BYPASS_1B]


def test_on_dry_run(capsys: pytest.CaptureFixture[str]) -> None:
    fake = make_fake(NORMAL)
    code, out, err = run(capsys, ["on", "--dry-run", "--experimental"], fake)
    assert code == 0, err
    assert out.splitlines() == [
        "Bypass on   (was 1B, normal mode)",
        f"  write  {BYPASS_1B}",
        "  dry run: nothing sent",
    ]
    assert writes(fake) == []


def test_on_dry_run_without_experimental_has_no_refusal(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # spec 004 T090: bypass is confirmed (gate sessions A and B), so no opt-in is needed
    fake = make_fake(NORMAL)
    code, out, err = run(capsys, ["on", "--dry-run"], fake)
    assert code == 0, err
    assert not any("refused" in line for line in out.splitlines())
    assert any(BYPASS_1B in line for line in out.splitlines())
    assert writes(fake) == []


def test_on_without_experimental_runs(capsys: pytest.CaptureFixture[str]) -> None:
    fake = make_fake(NORMAL)
    code, out, err = run(capsys, ["on"], fake)
    assert code == 0, err
    assert "applied" in out
    assert [f.hex(" ") for f in writes(fake)] == [BYPASS_1B]


def test_on_with_edits_needs_discard_edits(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err = run(capsys, ["on", "--experimental"], make_fake(NORMAL, buffer=EDITED))
    assert code == 1
    assert "edits_would_be_discarded" in err
    assert "--discard-edits" in err
    fake = make_fake(NORMAL, buffer=EDITED)
    code, out, err = run(capsys, ["on", "--experimental", "--discard-edits"], fake)
    assert code == 0, err
    assert [f.hex(" ") for f in writes(fake)] == [BYPASS_1B]


@pytest.mark.parametrize(("mode", "reason"), [(EDIT, "edit_mode"), (TUNER, "tuner_mode")])
def test_on_refused_by_state(capsys: pytest.CaptureFixture[str], mode: int, reason: str) -> None:
    fake = make_fake(mode)
    code, out, err = run(capsys, ["on", "--experimental", "--discard-edits"], fake)
    assert code == 1
    assert reason in err
    assert writes(fake) == []


def test_on_already_bypassed(capsys: pytest.CaptureFixture[str]) -> None:
    fake = bypassed_fake()
    code, out, err = run(capsys, ["on", "--experimental"], fake)
    assert code == 0, err
    assert out.strip() == "already bypassed; nothing sent"
    assert writes(fake) == []


def test_on_nak_exit_7(capsys: pytest.CaptureFixture[str]) -> None:
    fake = make_fake(NORMAL, script={"bypass": (bytes.fromhex(BYPASS_1B), nak(1))})
    code, out, err = run(capsys, ["on", "--experimental"], fake)
    assert code == 7
    assert "not acknowledged" in err


def test_on_not_applied_exit_8(capsys: pytest.CaptureFixture[str]) -> None:
    fake = make_fake(NORMAL, script={"bypass": (bytes.fromhex(BYPASS_1B), ACK)})
    code, out, err = run(capsys, ["on", "--experimental"], fake)
    assert code == 8
    assert "not applied (expected slot ff, buffer all 00)" in out
    assert "Leave bypass" not in out


def test_on_json(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err = run(capsys, ["on", "--experimental", "--json"], make_fake(NORMAL))
    assert code == 0, err
    doc = json.loads(out)
    validate(doc)
    assert doc["command"] == "bypass on"
    assert doc["plan"]["action"] == "bypass on 1B"
    assert doc["plan"]["target"] == {
        "kind": "bypass",
        "type": 4,
        "address": "0xe1000001",
        "length": 1,
        "argument": 1,
    }
    assert doc["plan"]["frame"] == BYPASS_1B
    assert doc["plan"]["confidence"] == "confirmed"
    assert doc["result"]["applied"] is True
    assert doc["result"]["return_index"] == 1
    assert doc["result"]["return_position"] == "1B"


@pytest.mark.parametrize("extra", [["--dry-run"], ["--dry-run", "--experimental"]])
def test_on_json_dry_run_validates(capsys: pytest.CaptureFixture[str], extra: list[str]) -> None:
    code, out, err = run(capsys, ["on", "--json", *extra], make_fake(NORMAL))
    assert code == 0, err
    doc = json.loads(out)
    validate(doc)
    assert doc["plan"]["dry_run"] is True
    assert "result" not in doc


# -- bypass off ----------------------------------------------------------------------------------


def test_off_human_output(capsys: pytest.CaptureFixture[str]) -> None:
    fake = bypassed_fake()
    code, out, err = run(capsys, ["off", "1B"], fake)
    assert code == 0, err
    assert out.splitlines() == [
        "Bypass off: select 1B (index 1)   from bypass (bank 1)",
        f"  write  {SELECT_1B}",
        REPLY,
        "  now    bank 1, slot B   buffer = stored 1B   applied",
    ]
    assert [f.hex(" ") for f in writes(fake)] == [SELECT_1B]


def test_off_accepts_an_index(capsys: pytest.CaptureFixture[str]) -> None:
    fake = bypassed_fake()
    code, out, err = run(capsys, ["off", "1", "--experimental"], fake)
    assert code == 0, err
    assert [f.hex(" ") for f in writes(fake)] == [SELECT_1B]


def test_off_dry_run(capsys: pytest.CaptureFixture[str]) -> None:
    fake = bypassed_fake()
    code, out, err = run(capsys, ["off", "1B", "--dry-run"], fake)
    assert code == 0, err
    assert out.splitlines() == [
        "Bypass off: select 1B (index 1)   from bypass (bank 1)",
        f"  write  {SELECT_1B}",
        "  dry run: nothing sent",
    ]
    assert writes(fake) == []


def test_off_without_position_exit_2_names_the_bank(capsys: pytest.CaptureFixture[str]) -> None:
    fake = make_fake(NORMAL, buffer=bytes(21), glob=bytes([2, 2, 0xFF, NORMAL]))
    code, out, err = run(capsys, ["off"], fake)
    assert code == 2
    assert "position" in err
    assert "does not report the loaded slot" in err
    assert "bank 3" in err
    assert "openvave bypass off 3A" in err
    assert out == ""
    assert writes(fake) == []


def test_off_without_position_when_not_bypassed_exit_2(capsys: pytest.CaptureFixture[str]) -> None:
    fake = make_fake(NORMAL)
    code, out, err = run(capsys, ["off"], fake)
    assert code == 2
    assert "not bypassed" in err
    assert writes(fake) == []


def test_off_bad_position_exit_2_before_connecting(capsys: pytest.CaptureFixture[str]) -> None:
    fake = bypassed_fake()
    code, out, err = run(capsys, ["off", "9E"], fake)
    assert code == 2
    assert fake.sent == []


def test_off_not_bypassed_exit_1(capsys: pytest.CaptureFixture[str]) -> None:
    fake = make_fake(NORMAL)
    code, out, err = run(capsys, ["off", "1B"], fake)
    assert code == 1
    assert "not_bypassed" in err
    assert "preset select" in err
    assert writes(fake) == []


def test_off_json(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err = run(capsys, ["off", "1B", "--json"], bypassed_fake())
    assert code == 0, err
    doc = json.loads(out)
    validate(doc)
    assert doc["command"] == "bypass off"
    assert doc["plan"]["action"] == "bypass off 1B"
    assert doc["plan"]["target"]["kind"] == "preset_select"
    assert doc["result"]["applied"] is True


# -- position names on the bypass placeholder (spec 007 US4, Codex round 3) ----------------------


def _amp_change(doc: dict[str, Any]) -> dict[str, Any]:
    return next(c for c in doc["result"]["changes"] if c["name"] == "amp_type")


def test_on_json_names_only_the_preset_side(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err = run(capsys, ["on", "--json"], make_fake(NORMAL))
    assert code == 0, err
    amp = _amp_change(json.loads(out))
    assert (amp["before"], amp["after"]) == (P[5], 0)
    assert amp["position_name_before"] is not None
    assert amp["position_name_after"] is None  # zeros of the bypass buffer, not amp 0


def test_off_json_names_only_the_preset_side(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err = run(capsys, ["off", "1B", "--json"], bypassed_fake())
    assert code == 0, err
    amp = _amp_change(json.loads(out))
    assert (amp["before"], amp["after"]) == (0, P[5])
    assert amp["position_name_before"] is None
    assert amp["position_name_after"] is not None


def test_bypassed_preset_dump_json_has_no_names(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["preset", "dump", "--json"], transport_factory=factory_for(bypassed_fake()))
    out, err = capsys.readouterr()
    assert code == 0, err
    fields = {f["name"]: f for f in json.loads(out)["preset"]["fields"]}
    assert fields["amp_type"]["value"] == 0
    assert fields["amp_type"]["position_name"] is None
    assert fields["ir_cab"]["position_name"] is None


def test_bypassed_set_preview_names_only_the_requested_position(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from openvave.protocol.names import position_name

    code = main(
        ["set", "amp_type", "4", "--dry-run"], transport_factory=factory_for(bypassed_fake())
    )
    out, err = capsys.readouterr()
    assert code == 0, err
    name = position_name("amp_type", 4)
    assert name is not None
    assert out.splitlines()[0].startswith(f"Set amp_type #0 → #4 ({name.text}")


def test_bypassed_save_preview_names_only_the_stored_side(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Codex round 4: the buffer saved from bypass is zeros; the stored slot keeps its name."""
    code = main(
        ["preset", "save", "--to", "1B", "--dry-run", "--unsafe"],
        transport_factory=factory_for(bypassed_fake()),
    )
    out, err = capsys.readouterr()
    amp = [line for line in out.splitlines() if "amp_type" in line]
    assert amp, (code, out, err)
    assert amp[0].rstrip().endswith("→ #0")
    assert "amp_type #4 (" in amp[0]
