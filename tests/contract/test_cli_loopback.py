"""``openvave loopback on | off`` (spec 004 T029, contracts/cli.md, FR-026)."""

from __future__ import annotations

import json
from typing import Any

import jsonschema
import pytest

from openvave.cli import main
from openvave.transport.fake import FakeTransport
from tests.contract.test_cli_set import factory_for
from tests.support.captures import REPO_ROOT
from tests.support.write_fixture import ACK, NORMAL, make_fake, nak, writes

SCHEMA = REPO_ROOT / "specs/004-remote-edit-save-restore/contracts/write-result.schema.json"
LOOPBACK_OFF = "00 59 22 09 00 00 04 00 00 00 d0 01 00 00 00 2a"
LOOPBACK_ON = "00 59 22 09 00 00 04 00 00 00 d0 01 00 00 01 29"


def run(
    capsys: pytest.CaptureFixture[str], argv: list[str], fake: FakeTransport
) -> tuple[int, str, str]:
    code = main(["loopback", *argv], transport_factory=factory_for(fake))
    out, err = capsys.readouterr()
    return code, out, err


def validate(doc: dict[str, Any]) -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    jsonschema.validators.validator_for(schema)(schema).validate(doc)


def test_off_human_output(capsys: pytest.CaptureFixture[str]) -> None:
    fake = make_fake(NORMAL, status=b"\x01")
    code, out, err = run(capsys, ["off", "--experimental"], fake)
    assert code == 0, err
    assert out.splitlines() == [
        "Loopback on → off   (status byte 0xD0000000: Bluetooth audio in the USB recording)",
        f"  write  {LOOPBACK_OFF}",
        "  reply  00 59 00 01 00 00 00 ff   ACK",
        "  after  status 00 (loopback off)   applied",
    ]
    assert [f.hex(" ") for f in writes(fake)] == [LOOPBACK_OFF]


def test_on_human_output(capsys: pytest.CaptureFixture[str]) -> None:
    fake = make_fake(NORMAL, status=b"\x00")
    code, out, err = run(capsys, ["on", "--experimental"], fake)
    assert code == 0, err
    assert out.splitlines()[0].startswith("Loopback off → on")
    assert out.splitlines()[-1] == "  after  status 01 (loopback on)   applied"
    assert [f.hex(" ") for f in writes(fake)] == [LOOPBACK_ON]


def test_dry_run(capsys: pytest.CaptureFixture[str]) -> None:
    fake = make_fake(NORMAL, status=b"\x01")
    code, out, err = run(capsys, ["off", "--dry-run", "--experimental"], fake)
    assert code == 0, err
    assert out.splitlines() == [
        "Loopback on → off   (status byte 0xD0000000: Bluetooth audio in the USB recording)",
        f"  write  {LOOPBACK_OFF}",
        "  dry run: nothing sent",
    ]
    assert writes(fake) == []


def test_dry_run_without_experimental_prints_the_refusal(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = run(capsys, ["off", "--dry-run"], make_fake(NORMAL, status=b"\x01"))
    assert code == 0, err
    assert "  refused: experimental_required (loopback is 'observed'; needs --experimental)" in (
        out.splitlines()
    )


@pytest.mark.parametrize(("argv", "status"), [(["off"], b"\x00"), (["on"], b"\x01")])
def test_no_change(capsys: pytest.CaptureFixture[str], argv: list[str], status: bytes) -> None:
    fake = make_fake(NORMAL, status=status)
    code, out, err = run(capsys, [*argv, "--experimental"], fake)
    assert code == 0, err
    assert out.strip() == f"loopback is already {argv[0]}; nothing sent"
    assert writes(fake) == []


def test_refused_without_experimental(capsys: pytest.CaptureFixture[str]) -> None:
    fake = make_fake(NORMAL, status=b"\x01")
    code, out, err = run(capsys, ["off"], fake)
    assert code == 1
    assert "experimental_required" in err
    assert "observed" in err
    assert "--experimental" in err
    assert writes(fake) == []


def test_nak_exit_7(capsys: pytest.CaptureFixture[str]) -> None:
    fake = make_fake(
        NORMAL, status=b"\x01", script={"loopback": (bytes.fromhex(LOOPBACK_OFF), nak(1))}
    )
    code, out, err = run(capsys, ["off", "--experimental"], fake)
    assert code == 7


def test_not_applied_exit_8(capsys: pytest.CaptureFixture[str]) -> None:
    fake = make_fake(
        NORMAL, status=b"\x01", script={"loopback": (bytes.fromhex(LOOPBACK_OFF), ACK)}
    )
    code, out, err = run(capsys, ["off", "--experimental"], fake)
    assert code == 8
    assert "  after  status 01 (loopback on)   not applied" in out


def test_missing_or_bad_argument_exit_2(capsys: pytest.CaptureFixture[str]) -> None:
    for argv in ([], ["maybe"]):
        fake = make_fake(NORMAL, status=b"\x01")
        code, out, err = run(capsys, argv, fake)
        assert code == 2
        assert fake.sent == []


def test_json(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err = run(
        capsys, ["off", "--experimental", "--json"], make_fake(NORMAL, status=b"\x01")
    )
    assert code == 0, err
    doc = json.loads(out)
    validate(doc)
    assert doc["command"] == "loopback off"
    assert doc["plan"]["target"]["kind"] == "loopback"
    assert doc["plan"]["before"] == "01"
    assert doc["result"]["after"] == "00"
    assert doc["result"]["changes"] == [
        {"region": "status", "offset": 0, "before": 1, "after": 0, "name": None}
    ]


@pytest.mark.parametrize("extra", [["--dry-run"], ["--experimental"]])
def test_json_dry_run_and_no_change_validate(
    capsys: pytest.CaptureFixture[str], extra: list[str]
) -> None:
    code, out, err = run(capsys, ["off", "--json", *extra], make_fake(NORMAL, status=b"\x00"))
    assert code == 0, err
    validate(json.loads(out))
