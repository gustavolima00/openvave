"""The choice matrix (spec 005 T035, SC-004, data-model "resolve_target" and "Scan outcome").

Every combination of ``--device`` × ``OPENVAVE_DEVICE`` × configuration × scan result, for a read
(``info``) and a write (``set gain=90``). The expected outcome is computed here from the
data-model tables, independently of ``openvave.devices``; the test asserts the connected
identifier or the exit code, and that no transport is ever built for another pedal.

Pedals: A (``UUID_1``, nickname ``stage``) and B (``UUID_2``, nickname ``home``, known only in the
"A+B" configuration).
"""

from __future__ import annotations

import itertools

import pytest

from tests.support import choice as ch
from tests.support.cli005 import config_path, file_bytes, seed
from tests.support.scanner import TANK, UUID_1, UUID_2

A, B = UUID_1, UUID_2
OPTIONS = {"none": None, "identifier": B, "known-nickname": "stage", "unknown-nickname": "nobody"}
ENVIRONMENTS = {"none": None, "identifier": A, "nickname": "home"}
CONFIGS = ("none", "default-A", "default-A+B", "invalid")
SCANS = {"A": [A], "B": [B], "A+B": [A, B], "none": []}
RSSI = {A: -58, B: -61}
NICKNAMES = {"none": {}, "default-A": {"stage": A}, "default-A+B": {"stage": A, "home": B}}


def is_identifier(value: str) -> bool:
    return value in (A, B)


def expected(option: str | None, environment: str | None, config: str, scan: list[str]) -> str:
    """``"connect <id>"`` or ``"exit <code>"`` from the data-model tables."""
    value = option or environment
    if config == "invalid" and (value is None or not is_identifier(value)):
        return "exit 2"  # the file is needed and cannot be read
    nicknames = NICKNAMES.get(config, {})
    if value is not None:
        if is_identifier(value):
            target: str | None = value
        elif value in nicknames:
            target = nicknames[value]
        else:
            return "exit 2"  # unknown nickname, before any scan
    else:
        target = A if config in ("default-A", "default-A+B") else None
    if target is not None:
        return f"connect {target}" if target in scan else "exit 3"
    if len(scan) == 1:
        return f"connect {scan[0]}"
    return "exit 3" if not scan else "exit 4"


def configure(config: str) -> None:
    if config == "default-A":
        seed((A, "stage"))
    elif config == "default-A+B":
        seed((B, "home"), (A, "stage"))
    elif config == "invalid":
        path = config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"format_version": 2}', encoding="utf-8")


MATRIX = list(itertools.product(OPTIONS, ENVIRONMENTS, CONFIGS, SCANS))


@pytest.fixture(autouse=True)
def _fast(monkeypatch: pytest.MonkeyPatch) -> None:
    ch.no_waits(monkeypatch)


@pytest.mark.parametrize("command", ["info", "set gain=90"])
@pytest.mark.parametrize(("option", "environment", "config", "scan"), MATRIX)
def test_choice(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    command: str,
    option: str,
    environment: str,
    config: str,
    scan: str,
) -> None:
    option_value, environment_value = OPTIONS[option], ENVIRONMENTS[environment]
    configure(config)
    if environment_value is not None:
        monkeypatch.setenv("OPENVAVE_DEVICE", environment_value)
    argv = command.split()
    if option_value is not None:
        argv = ["--device", option_value, *argv]
    fake_for = "info" if command == "info" else "set FIELD=VALUE"
    pedals = ch.Pedals([(i, TANK, RSSI[i]) for i in SCANS[scan]], fake_for)
    default_before = file_bytes()

    code, _, err = ch.run(capsys, argv, pedals)

    outcome = expected(option_value, environment_value, config, SCANS[scan])
    if outcome.startswith("connect"):
        wanted = outcome.split()[1]
        assert code == 0, err
        assert pedals.opened == [wanted]  # SC-004: nothing else, ever
        if command.startswith("set"):
            assert pedals.fakes[wanted].sent  # the write went to the chosen pedal
    else:
        assert code == int(outcome.split()[1]), err
        assert pedals.opened == []
    if config == "invalid":
        assert file_bytes() == default_before  # never rewritten


def test_matrix_size() -> None:
    assert len(MATRIX) == 4 * 3 * 4 * 4
