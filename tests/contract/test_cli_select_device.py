"""``openvave select [TARGET] [--name NICKNAME] [--offline]`` (spec 005 T018, research R4)."""

from __future__ import annotations

import json

import pytest

from openvave.devices import KnownDevices
from tests.support.cli005 import config_path, file_bytes, run, seed, validate
from tests.support.scanner import MAC_1, MAC_2, TANK, UUID_1, UUID_2, fake_scanner

FAST = ["--scan-timeout", "0.1"]
ONE = fake_scanner([(UUID_1, TANK, -58)])
TWO = fake_scanner([(UUID_1, TANK, -58), (UUID_2, TANK, -61)])


def saved() -> KnownDevices:
    return KnownDevices.load(config_path())


def test_full_identifier_in_range_with_a_nickname(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err = run(capsys, ["select", UUID_1, "--name", "stage", *FAST], scanner=TWO)
    assert code == 0, err
    assert out == (f"Default pedal: stage  {UUID_1}  ({TANK}, -58 dBm)\nSaved in {config_path()}\n")
    known = saved()
    assert known.default is not None
    assert known.default.identifier == UUID_1 and known.default.nickname == "stage"
    assert known.default.last_name == TANK


def test_full_identifier_not_seen_saves_nothing(capsys: pytest.CaptureFixture[str]) -> None:
    code, _, err = run(capsys, ["select", UUID_2, *FAST], scanner=ONE)
    assert code == 3
    assert f"device {UUID_2} not found" in err
    assert file_bytes() is None


def test_identifier_is_case_insensitive_and_stored_as_reported(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, _, _ = run(capsys, ["select", UUID_1.lower(), *FAST], scanner=ONE)
    assert code == 0
    assert saved().default_identifier == UUID_1


def test_prefix_matching_one(capsys: pytest.CaptureFixture[str]) -> None:
    scanner = fake_scanner([(UUID_1, TANK, -58), (MAC_1, TANK, -70)])
    code, out, _ = run(capsys, ["select", "8f3a", *FAST], scanner=scanner)
    assert code == 0
    assert out.startswith(f"Default pedal: {UUID_1}  ({TANK}, -58 dBm)\n")


def test_prefix_ignores_separators(capsys: pytest.CaptureFixture[str]) -> None:
    scanner = fake_scanner([(UUID_1, TANK, -58), (MAC_1, TANK, -70)])
    code, _, _ = run(capsys, ["select", "AABBCC", *FAST], scanner=scanner)
    assert code == 0
    assert saved().default_identifier == MAC_1


def test_prefix_matching_two_exits_4(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err = run(capsys, ["select", "8F3A", *FAST], scanner=TWO)
    assert code == 4
    assert out == ""
    assert UUID_1 in err and UUID_2 in err
    assert file_bytes() is None


def test_prefix_matching_none_exits_3(capsys: pytest.CaptureFixture[str]) -> None:
    code, _, err = run(capsys, ["select", "DEAD", *FAST], scanner=TWO)
    assert code == 3
    assert "DEAD" in err
    assert file_bytes() is None


def test_no_argument_one_pedal(capsys: pytest.CaptureFixture[str]) -> None:
    code, _, _ = run(capsys, ["select", *FAST], scanner=ONE)
    assert code == 0
    assert saved().default_identifier == UUID_1


def test_no_argument_two_pedals_exits_4(capsys: pytest.CaptureFixture[str]) -> None:
    code, _, err = run(capsys, ["select", *FAST], scanner=TWO)
    assert code == 4
    assert "2 pedals found" in err
    assert file_bytes() is None


def test_no_argument_no_pedal_exits_3(capsys: pytest.CaptureFixture[str]) -> None:
    code, _, _ = run(capsys, ["select", *FAST], scanner=fake_scanner([]))
    assert code == 3
    assert file_bytes() is None


def test_known_nickname_needs_no_scan(capsys: pytest.CaptureFixture[str]) -> None:
    seed((UUID_1, "stage"), (UUID_2, "home"))
    code, out, _ = run(capsys, ["select", "STAGE"])  # forbidden scanner
    assert code == 0
    assert out == (
        f"Default pedal: stage  {UUID_1}  ({TANK})\nWas: home  {UUID_2}\nSaved in {config_path()}\n"
    )
    known = saved()
    assert known.default_identifier == UUID_1
    assert known.find("home") is not None  # the previous default stays known


def test_selecting_the_default_again_has_no_was_line(capsys: pytest.CaptureFixture[str]) -> None:
    seed((UUID_1, "stage"))
    code, out, _ = run(capsys, ["select", "stage"])
    assert code == 0
    assert "Was:" not in out


def test_name_on_a_known_pedal_renames_it(capsys: pytest.CaptureFixture[str]) -> None:
    seed((UUID_1, "stage"))
    code, _, _ = run(capsys, ["select", "stage", "--name", "live"])
    assert code == 0
    assert saved().find("live") is not None and saved().find("stage") is None


def test_offline_full_identifier(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(capsys, ["select", MAC_1, "--name", "stage", "--offline"])
    assert code == 0
    assert out == f"Default pedal: stage  {MAC_1}\nSaved in {config_path()}\n"
    assert saved().default_identifier == MAC_1


def test_offline_with_a_prefix_exits_2(capsys: pytest.CaptureFixture[str]) -> None:
    code, _, err = run(capsys, ["select", "AABB", "--offline"])
    assert code == 2
    assert "--offline" in err
    assert file_bytes() is None


def test_offline_without_target_exits_2(capsys: pytest.CaptureFixture[str]) -> None:
    code, _, _ = run(capsys, ["select", "--offline"])
    assert code == 2


def test_unknown_text_exits_2_before_scanning(capsys: pytest.CaptureFixture[str]) -> None:
    seed((UUID_1, "stage"))
    code, _, err = run(capsys, ["select", "nobody"])
    assert code == 2
    assert "nobody" in err and "stage" in err


@pytest.mark.parametrize("bad", ["8F3A", "two words", "x" * 33, MAC_2])
def test_bad_nickname_exits_2_and_saves_nothing(
    capsys: pytest.CaptureFixture[str], bad: str
) -> None:
    seed((UUID_2, "home"))
    before = file_bytes()
    code, out, err = run(capsys, ["select", MAC_1, "--name", bad, "--offline"])
    assert code == 2
    assert out == ""
    assert "bad nickname" in err
    assert file_bytes() == before


def test_nickname_in_use_exits_2_and_saves_nothing(capsys: pytest.CaptureFixture[str]) -> None:
    seed((UUID_2, "home"))
    before = file_bytes()
    code, _, err = run(capsys, ["select", UUID_1, "--name", "HOME", *FAST], scanner=ONE)
    assert code == 2
    assert "already used" in err
    assert file_bytes() == before


def test_json_document(capsys: pytest.CaptureFixture[str]) -> None:
    seed((UUID_2, "home"))
    code, out, err = run(
        capsys, ["select", UUID_1, "--name", "stage", "--json", *FAST], scanner=ONE
    )
    assert code == 0
    assert err == ""
    document = json.loads(out)
    validate(document, "device.schema.json")
    assert document["command"] == "select"
    assert document["config_path"] == str(config_path())
    assert document["default"]["identifier"] == UUID_1
    assert document["default"]["nickname"] == "stage"
    assert document["previous_default"]["nickname"] == "home"
    assert document["rssi"] == -58
    assert [d["identifier"] for d in document["devices"]] == [UUID_2, UUID_1]
