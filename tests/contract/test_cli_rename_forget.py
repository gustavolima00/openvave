"""``openvave device rename`` and ``openvave forget`` (spec 005 T020, contracts/cli.md).

None of them uses Bluetooth: every run gets the scanner that fails the test if built.
"""

from __future__ import annotations

import json

import pytest

from openvave.devices import KnownDevices
from tests.support.cli005 import config_path, file_bytes, run, seed, validate
from tests.support.scanner import MAC_1, UUID_1, UUID_2

SHORT_1 = UUID_1[:8] + "…"


def saved() -> KnownDevices:
    return KnownDevices.load(config_path())


def test_rename_by_nickname(capsys: pytest.CaptureFixture[str]) -> None:
    seed((UUID_1, "stage"))
    code, out, _ = run(capsys, ["device", "rename", "stage", "live"])
    assert code == 0
    assert out == f"Renamed stage → live  {SHORT_1}\n"
    assert saved().find("live") is not None


def test_rename_by_identifier(capsys: pytest.CaptureFixture[str]) -> None:
    seed((MAC_1, None))
    code, out, _ = run(capsys, ["device", "rename", MAC_1.lower(), "live"])
    assert code == 0
    assert out == f"Renamed {MAC_1} → live  {MAC_1}\n"


@pytest.mark.parametrize(
    ("old", "new", "text"),
    [
        ("nobody", "live", "no known pedal"),
        ("stage", "8F3A", "bad nickname"),
        ("stage", "home", "already used"),
    ],
)
def test_rename_refusals(capsys: pytest.CaptureFixture[str], old: str, new: str, text: str) -> None:
    seed((UUID_2, "home"), (UUID_1, "stage"))
    before = file_bytes()
    code, out, err = run(capsys, ["device", "rename", old, new])
    assert code == 2
    assert out == ""
    assert text in err
    assert file_bytes() == before


def test_forget_clears_the_default_and_keeps_the_pedals(capsys: pytest.CaptureFixture[str]) -> None:
    seed((UUID_2, "home"), (UUID_1, "stage"))
    code, out, _ = run(capsys, ["forget"])
    assert code == 0
    assert out == (
        f"Forgot the default (stage {SHORT_1}). It is still a known pedal; remove it with: "
        "openvave forget stage\n"
    )
    known = saved()
    assert known.default is None and len(known.devices) == 2


def test_forget_without_default(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(capsys, ["forget"])
    assert code == 0
    assert out == "No default pedal.\n"
    assert file_bytes() is None


def test_forget_target_removes_it_and_the_default(capsys: pytest.CaptureFixture[str]) -> None:
    seed((UUID_2, "home"), (UUID_1, "stage"))
    code, out, _ = run(capsys, ["forget", "stage"])
    assert code == 0
    assert out == f"Forgot stage  {SHORT_1} (it was the default)\n"
    known = saved()
    assert known.default is None
    assert [d.identifier for d in known.devices] == [UUID_2]


def test_forget_other_target_keeps_the_default(capsys: pytest.CaptureFixture[str]) -> None:
    seed((UUID_2, "home"), (UUID_1, "stage"))
    code, out, _ = run(capsys, ["forget", UUID_2])
    assert code == 0
    assert out == f"Forgot home  {UUID_2[:8]}…\n"
    assert saved().default_identifier == UUID_1


def test_forget_unknown_target_exits_2(capsys: pytest.CaptureFixture[str]) -> None:
    seed((UUID_1, "stage"))
    before = file_bytes()
    code, _, err = run(capsys, ["forget", "nobody"])
    assert code == 2
    assert "no known pedal" in err
    assert file_bytes() == before


def test_forget_all(capsys: pytest.CaptureFixture[str]) -> None:
    seed((UUID_2, "home"), (UUID_1, "stage"))
    code, out, _ = run(capsys, ["forget", "--all"])
    assert code == 0
    assert out == "Forgot 2 known pedals.\n"
    assert saved().devices == ()


def test_forget_all_and_a_target_is_a_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    code, _, _ = run(capsys, ["forget", "stage", "--all"])
    assert code == 2


def test_forget_on_invalid_file_exits_2(capsys: pytest.CaptureFixture[str]) -> None:
    path = config_path()
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    code, _, err = run(capsys, ["forget"])
    assert code == 2
    assert err.startswith(f"error: {path}: not valid JSON")
    assert "hint: fix the file or reset it with: openvave forget --all" in err
    assert path.read_text(encoding="utf-8") == "{not json"


def test_forget_all_moves_an_invalid_file_aside(capsys: pytest.CaptureFixture[str]) -> None:
    path = config_path()
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    code, out, _ = run(capsys, ["forget", "--all"])
    assert code == 0
    (moved,) = path.parent.glob("devices.json.invalid-*")
    assert moved.read_text(encoding="utf-8") == "{not json"
    assert str(moved) in out
    assert saved().devices == ()  # a valid empty file
    validate(json.loads(path.read_text(encoding="utf-8")), "devices-file.schema.json")


@pytest.mark.parametrize(
    ("argv", "command"),
    [
        (["forget", "--json"], "forget"),
        (["forget", "home", "--json"], "forget"),
        (["forget", "--all", "--json"], "forget"),
        (["device", "rename", "stage", "live", "--json"], "device rename"),
    ],
)
def test_json_documents(capsys: pytest.CaptureFixture[str], argv: list[str], command: str) -> None:
    seed((UUID_2, "home"), (UUID_1, "stage"))
    code, out, _ = run(capsys, argv)
    assert code == 0
    document = json.loads(out)
    validate(document, "device.schema.json")
    assert document["command"] == command
    if argv[1] == "home":
        assert [d["nickname"] for d in document["removed"]] == ["home"]
    if argv[1] == "--all":
        assert len(document["removed"]) == 2 and document["devices"] == []
