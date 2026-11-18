"""``openvave preset select``: output, refusals, JSON and exit codes (T030, contracts/cli.md)."""

from __future__ import annotations

import json

import pytest

from openvave import session
from tests.contract.test_cli_set import run, validate
from tests.support.write_fixture import ACK, EDIT, NORMAL, make_fake, nak, writes

SELECT_6 = "00 59 22 09 00 00 04 06 00 00 e0 01 00 00 01 13"


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    async def instant(_: float) -> None:
        return None

    monkeypatch.setattr(session, "SELECT_SLEEP", instant)


@pytest.mark.parametrize("position", ["2C", "2c", "6"])
def test_human_output(capsys: pytest.CaptureFixture[str], position: str) -> None:
    code, out, err, fake = run(
        capsys, ["preset", "select", position, "--experimental"], make_fake(NORMAL)
    )
    assert code == 0, err
    assert out.splitlines() == [
        "Select 2C (index 6)   from 1B",
        f"  write  {SELECT_6}",
        "  reply  00 59 00 01 00 00 00 ff   ACK",
        "  now    bank 2, slot C   buffer = stored 2C   applied",
    ]
    assert writes(fake) == [bytes.fromhex(SELECT_6)]


@pytest.mark.parametrize("position", ["10A", "1E", "0A", "36", "-1", "x"])
def test_invalid_position_exit_2(capsys: pytest.CaptureFixture[str], position: str) -> None:
    fake = make_fake(NORMAL)
    code, _, err, _ = run(capsys, ["preset", "select", position], fake)
    assert code == 2
    assert "1A" in err
    assert fake.sent == []


def test_edit_mode_needs_discard_edits(capsys: pytest.CaptureFixture[str]) -> None:
    code, _, err, fake = run(capsys, ["preset", "select", "2C", "--experimental"], make_fake(EDIT))
    assert code == 1
    assert "--discard-edits" in err
    assert writes(fake) == []
    code, _, err, fake = run(
        capsys,
        ["preset", "select", "2C", "--experimental", "--discard-edits"],
        make_fake(EDIT),
    )
    assert code == 0, err
    assert writes(fake) == [bytes.fromhex(SELECT_6)]


def test_dry_run(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err, fake = run(
        capsys, ["preset", "select", "2C", "--dry-run", "--discard-edits"], make_fake(EDIT)
    )
    assert code == 0, err
    lines = out.splitlines()
    assert lines[0] == "Select 2C (index 6)   from 1B"
    assert lines[1] == f"  write  {SELECT_6}"
    assert "refused" not in out  # preset select is confirmed on fw 96 (gate session B)
    assert lines[-1] == "  dry run: nothing sent"
    assert writes(fake) == []


def test_json(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err, _ = run(
        capsys, ["preset", "select", "2C", "--experimental", "--json"], make_fake(NORMAL)
    )
    assert code == 0, err
    doc = json.loads(out)
    validate(doc)
    assert doc["command"] == "preset select"
    assert doc["plan"]["action"] == "select 2C"
    assert doc["plan"]["target"]["address"] == "0xe0000006"
    assert doc["result"]["applied"] is True
    assert {c["region"] for c in doc["result"]["changes"]} == {"global", "preset"}


def test_nak_exit_7(capsys: pytest.CaptureFixture[str]) -> None:
    fake = make_fake(NORMAL, script={"s": (bytes.fromhex(SELECT_6), nak())})
    code, _, err, _ = run(capsys, ["preset", "select", "2C", "--experimental"], fake)
    assert code == 7
    assert nak().hex(" ") in err


def test_not_applied_exit_8(capsys: pytest.CaptureFixture[str]) -> None:
    fake = make_fake(NORMAL, apply_writes=False, script={"s": (bytes.fromhex(SELECT_6), ACK)})
    code, out, err, _ = run(capsys, ["preset", "select", "2C", "--experimental"], fake)
    assert code == 8
    assert "not applied" in out


def test_select_from_bypass_names_the_state(capsys: pytest.CaptureFixture[str]) -> None:
    # spec 004 gate: the pedal reports no slot while bypassed; say so instead of "?"
    fake = make_fake(NORMAL, buffer=bytes(21), glob=bytes([0, 0, 0xFF, NORMAL]))
    code, out, err, _ = run(capsys, ["preset", "select", "1A", "--experimental"], fake)
    assert code == 0, err
    assert out.splitlines()[0] == "Select 1A (index 0)   from bypass (bank 1)"
    assert out.splitlines()[-1].endswith("buffer = stored 1A   applied")
