"""``openvave preset reload`` (spec 004 T010, contracts/cli.md, research R4)."""

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
from tests.support.write_fixture import EDIT, NORMAL, TUNER, make_fake, write_frame, writes

SCHEMA = REPO_ROOT / "specs/004-remote-edit-save-restore/contracts/write-result.schema.json"
P = sf.PUBLIC_PRESET
EDITED = P[:6] + bytes([90]) + P[7:]
SELECT_1B = write_frame(0xE0000001, b"\x01").hex(" ")


def run(
    capsys: pytest.CaptureFixture[str], argv: list[str], fake: FakeTransport
) -> tuple[int, str, str]:
    code = main(["preset", "reload", *argv], transport_factory=factory_for(fake))
    out, err = capsys.readouterr()
    return code, out, err


def validate(doc: dict[str, Any]) -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    jsonschema.validators.validator_for(schema)(schema).validate(doc)


def test_human_output(capsys: pytest.CaptureFixture[str]) -> None:
    fake = make_fake(NORMAL, buffer=EDITED)
    code, out, err = run(capsys, [], fake)
    assert code == 0, err
    assert out.splitlines() == [
        "Reload 1B (index 1)   discards unsaved edits",
        f"  write  {SELECT_1B}",
        "  reply  00 59 00 01 00 00 00 ff   ACK",
        "  now    bank 1, slot B   buffer = stored 1B   applied",
    ]
    assert [f.hex(" ") for f in writes(fake)] == [SELECT_1B]


def test_nothing_to_discard(capsys: pytest.CaptureFixture[str]) -> None:
    fake = make_fake(NORMAL)
    code, out, err = run(capsys, [], fake)
    assert code == 0, err
    assert out.strip() == "Reload 1B: nothing to discard; nothing sent"
    assert writes(fake) == []


def test_dry_run(capsys: pytest.CaptureFixture[str]) -> None:
    fake = make_fake(NORMAL, buffer=EDITED)
    code, out, err = run(capsys, ["--dry-run"], fake)
    assert code == 0, err
    assert out.splitlines() == [
        "Reload 1B (index 1)   discards unsaved edits",
        f"  write  {SELECT_1B}",
        "  dry run: nothing sent",
    ]
    assert writes(fake) == []


def test_edit_mode_needs_discard_edits(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err = run(capsys, [], make_fake(EDIT, buffer=EDITED))
    assert code == 1
    assert "edits_would_be_discarded" in err
    assert "--discard-edits" in err
    fake = make_fake(EDIT, buffer=EDITED)
    code, out, err = run(capsys, ["--discard-edits"], fake)
    assert code == 0, err
    assert "applied" in out
    assert [f.hex(" ") for f in writes(fake)] == [SELECT_1B]


def test_dry_run_prints_the_refusal(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err = run(capsys, ["--dry-run"], make_fake(TUNER, buffer=EDITED))
    assert code == 0, err
    assert "refused: tuner_mode" in out


@pytest.mark.parametrize(
    ("glob", "buffer", "needle"),
    [
        (bytes([0, 0, 0xFF, NORMAL]), bytes(21), "preset select"),
        (bytes([0, 0, 1, 6]), P, "unrecognised_state"),
    ],
)
def test_no_loaded_slot_exit_1(
    capsys: pytest.CaptureFixture[str], glob: bytes, buffer: bytes, needle: str
) -> None:
    fake = make_fake(NORMAL, buffer=buffer, glob=glob)
    code, out, err = run(capsys, [], fake)
    assert code == 1
    assert needle in err
    assert writes(fake) == []


def test_json(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err = run(capsys, ["--json"], make_fake(NORMAL, buffer=EDITED))
    assert code == 0, err
    doc = json.loads(out)
    validate(doc)
    assert doc["command"] == "preset reload"
    assert doc["plan"]["action"] == "reload 1B"
    assert doc["plan"]["target"]["kind"] == "preset_select"
    assert doc["plan"]["frame"] == SELECT_1B
    assert doc["result"]["applied"] is True


@pytest.mark.parametrize("extra", [[], ["--dry-run"]])
def test_json_no_change_and_dry_run_validate(
    capsys: pytest.CaptureFixture[str], extra: list[str]
) -> None:
    code, out, err = run(capsys, ["--json", *extra], make_fake(NORMAL))
    assert code == 0, err
    doc = json.loads(out)
    validate(doc)
    assert doc["plan"]["no_change"] is True
    assert "result" not in doc
