""" "Last seen" after a command (spec 005 T040, research R9, FR-023, FR-026).

A successful command on a known pedal updates its ``last_name``, ``last_firmware`` and
``last_seen_at``; an unknown pedal leaves the file untouched (not even created); ``--device`` and
``OPENVAVE_DEVICE`` never change the default; a file that cannot be written does not fail the
command.
"""

from __future__ import annotations

import json
import os
from typing import Any

import pytest

from tests.support import choice as ch
from tests.support.cli005 import config_path, file_bytes, seed
from tests.support.scanner import MAC_1, TANK, UUID_1, UUID_2


@pytest.fixture(autouse=True)
def _fast(monkeypatch: pytest.MonkeyPatch) -> None:
    ch.no_waits(monkeypatch)


def entry(identifier: str) -> dict[str, Any]:
    document = json.loads(config_path().read_text(encoding="utf-8"))
    return next(d for d in document["devices"] if d["identifier"] == identifier)


def default() -> str | None:
    return json.loads(config_path().read_text(encoding="utf-8"))["default"]


def test_known_pedal_is_recorded(capsys: pytest.CaptureFixture[str]) -> None:
    seed((UUID_1, "stage"))
    assert entry(UUID_1)["last_seen_at"] is None
    code, _, err = ch.run(capsys, ["info"], ch.Pedals([(UUID_1, TANK, -58)]))
    assert code == 0, err
    seen = entry(UUID_1)
    assert seen["last_name"] == TANK
    assert seen["last_firmware"] == 96
    assert seen["last_seen_at"] is not None


def test_unknown_pedal_creates_no_file(capsys: pytest.CaptureFixture[str]) -> None:
    code, _, err = ch.run(capsys, ["info"], ch.Pedals([(UUID_1, TANK, -58)]))
    assert code == 0, err
    assert file_bytes() is None


def test_unknown_pedal_leaves_the_file_untouched(capsys: pytest.CaptureFixture[str]) -> None:
    seed((UUID_2, "home"))
    before = file_bytes()
    code, _, err = ch.run(capsys, ["--device", MAC_1, "info"], ch.Pedals([(MAC_1, TANK, -58)]))
    assert code == 0, err
    assert file_bytes() == before


@pytest.mark.parametrize("how", ["option", "environment"])
def test_option_and_environment_keep_the_default(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, how: str
) -> None:
    seed((UUID_2, "home"), (UUID_1, "stage"))
    argv = ["info"]
    if how == "option":
        argv = ["--device", "home", "info"]
    else:
        monkeypatch.setenv("OPENVAVE_DEVICE", "home")
    pedals = ch.Pedals([(UUID_1, TANK, -58), (UUID_2, TANK, -61)])
    code, _, err = ch.run(capsys, argv, pedals)
    assert code == 0, err
    assert pedals.opened == [UUID_2]
    assert default() == UUID_1
    assert entry(UUID_2)["last_firmware"] == 96  # only the "last seen" fields change


@pytest.mark.skipif(os.name != "posix" or os.geteuid() == 0, reason="needs POSIX modes, not root")
def test_read_only_directory_does_not_fail_the_command(capsys: pytest.CaptureFixture[str]) -> None:
    seed((UUID_1, "stage"))
    before = file_bytes()
    directory = config_path().parent
    directory.chmod(0o500)
    try:
        code, out, err = ch.run(capsys, ["info"], ch.Pedals([(UUID_1, TANK, -58)]))
    finally:
        directory.chmod(0o700)
    assert code == 0, err
    assert "firmware 96" in out
    assert "error" not in err
    assert file_bytes() == before


def test_failed_command_records_nothing(capsys: pytest.CaptureFixture[str]) -> None:
    seed((UUID_1, "stage"))
    before = file_bytes()
    code, _, _ = ch.run(capsys, ["info"], ch.Pedals([(UUID_2, TANK, -61)]))
    assert code == 3
    assert file_bytes() == before
