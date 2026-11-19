"""``openvave device [--check]`` (spec 005 T019, contracts/cli.md)."""

from __future__ import annotations

import json
from datetime import timedelta

import pytest

from tests.support.cli005 import WHEN, config_path, file_bytes, run, seed, validate
from tests.support.scanner import TANK, UUID_1, UUID_2, fake_scanner

FAST = ["--scan-timeout", "0.1"]
CHOICE = (
    "openvave connects for the length of one command; this is a choice, not an open connection."
)


def local(moment: object) -> str:
    return moment.astimezone().strftime("%Y-%m-%d %H:%M")  # type: ignore[attr-defined]


def test_no_file(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(capsys, ["device"])  # forbidden scanner
    assert code == 0
    assert out == (
        "No default pedal. Commands use the only Tank-G in range.\n"
        "Choose one: openvave scan, then openvave select ID\n"
        f"Configuration: {config_path()}\n"
    )
    assert file_bytes() is None


def test_known_pedals_without_default(capsys: pytest.CaptureFixture[str]) -> None:
    seed((UUID_1, "stage"), default=None)
    code, out, _ = run(capsys, ["device"])
    assert code == 0
    assert out.splitlines()[:4] == [
        "No default pedal. Commands use the only Tank-G in range.",
        "Choose one: openvave scan, then openvave select ID",
        "Known pedals:",
        f"  stage  {UUID_1}",
    ]


def test_default_and_two_known_pedals(capsys: pytest.CaptureFixture[str]) -> None:
    known = seed((UUID_2, "home"), (UUID_1, "stage"))
    seen = WHEN + timedelta(minutes=3)
    known.record_seen(UUID_1, TANK, 96, now=seen).save()
    code, out, _ = run(capsys, ["device"])
    assert code == 0
    assert out == (
        f"Default pedal: stage  {UUID_1}\n"
        f"  selected {local(WHEN)}, last seen {local(seen)} ({TANK}, firmware 96)\n"
        "Known pedals:\n"
        f"  home   {UUID_2}\n"
        f"* stage  {UUID_1}\n"
        f"Configuration: {config_path()}\n"
        f"{CHOICE}\n"
    )


def test_default_never_seen(capsys: pytest.CaptureFixture[str]) -> None:
    seed((UUID_1, None))
    code, out, _ = run(capsys, ["device"])
    assert code == 0
    assert out.splitlines()[:4] == [
        f"Default pedal: {UUID_1}",
        f"  selected {local(WHEN)}",
        "Known pedals:",
        f"* {UUID_1}",
    ]


def test_environment_override_line(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    seed((UUID_1, "stage"))
    monkeypatch.setenv("OPENVAVE_DEVICE", "home")
    code, out, _ = run(capsys, ["device"])
    assert code == 0
    assert "OPENVAVE_DEVICE=home overrides the default in this shell.\n" in out


def test_check_in_range(capsys: pytest.CaptureFixture[str]) -> None:
    seed((UUID_1, "stage"))
    calls: list[str] = []
    scanner = fake_scanner([(UUID_2, TANK, -61), (UUID_1, TANK, -58)], calls=calls)
    code, out, _ = run(capsys, ["device", "--check", "--scan-timeout", "5"], scanner=scanner)
    assert code == 0
    assert out.splitlines()[-1] == "In range: yes (-58 dBm)"
    assert calls == ["scan"]


def test_check_stops_when_the_default_is_seen(capsys: pytest.CaptureFixture[str]) -> None:
    import time

    seed((UUID_1, "stage"))
    started = time.monotonic()
    code, _, _ = run(
        capsys,
        ["device", "--check", "--scan-timeout", "5"],
        scanner=fake_scanner([(UUID_1, TANK, -58)]),
    )
    assert code == 0
    assert time.monotonic() - started < 2


def test_check_not_in_range(capsys: pytest.CaptureFixture[str]) -> None:
    seed((UUID_1, "stage"))
    code, out, _ = run(
        capsys, ["device", "--check", *FAST], scanner=fake_scanner([(UUID_2, TANK, -61)])
    )
    assert code == 3
    assert out.splitlines()[-1] == "In range: no"


def test_check_without_default_exits_2(capsys: pytest.CaptureFixture[str]) -> None:
    code, _, err = run(capsys, ["device", "--check"])
    assert code == 2
    assert "no default pedal" in err.lower()


def test_json_document(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    seed((UUID_2, "home"), (UUID_1, "stage"))
    monkeypatch.setenv("OPENVAVE_DEVICE", "home")
    code, out, _ = run(capsys, ["device", "--json"])
    assert code == 0
    document = json.loads(out)
    validate(document, "device.schema.json")
    assert document["command"] == "device"
    assert document["default"]["nickname"] == "stage"
    assert document["environment_override"] == "home"
    assert len(document["devices"]) == 2
    assert "in_range" not in document


def test_json_check(capsys: pytest.CaptureFixture[str]) -> None:
    seed((UUID_1, "stage"))
    code, out, _ = run(
        capsys, ["device", "--check", "--json", *FAST], scanner=fake_scanner([(UUID_1, TANK, -58)])
    )
    assert code == 0
    document = json.loads(out)
    validate(document, "device.schema.json")
    assert document["in_range"] is True
    assert document["rssi"] == -58


def test_json_without_file(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(capsys, ["device", "--json"])
    assert code == 0
    document = json.loads(out)
    validate(document, "device.schema.json")
    assert document["default"] is None and document["devices"] == []
