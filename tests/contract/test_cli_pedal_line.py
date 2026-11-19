"""The ``pedal:`` line of every pedal command (spec 005 T036, research R8, SC-003).

For each command in ``COMMANDS`` (and ``watch``) and each of the four ways a pedal is chosen,
stderr carries exactly one ``pedal:`` line in human mode and none with ``--json``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from openvave.cli import COMMANDS
from tests.support import choice as ch
from tests.support.cli005 import seed
from tests.support.scanner import MAC_1, TANK, UUID_1, UUID_2

COMMAND_IDS = list(ch.COMMAND_IDS)

CASES = {
    "selected": (
        [],
        None,
        [(UUID_1, "stage")],
        [(UUID_1, TANK, -58)],
        "pedal: stage  8F3A21C4…  -58 dBm  (selected)",
    ),
    "device_option": (
        ["--device", MAC_1],
        None,
        [],
        [(MAC_1, TANK, -70)],
        f"pedal: {MAC_1}  -70 dBm  (--device)",
    ),
    "environment": (
        [],
        "home",
        [(UUID_2, "home"), (UUID_1, "stage")],
        [(UUID_1, TANK, -58), (UUID_2, TANK, -61)],
        "pedal: home  8F3A21C4…  -61 dBm  (OPENVAVE_DEVICE)",
    ),
    "only_one_found": (
        [],
        None,
        [],
        [(UUID_2, TANK, -61)],
        "pedal: 8F3A21C4…  -61 dBm  (only one found)",
    ),
}


@pytest.fixture(autouse=True)
def _fast(monkeypatch: pytest.MonkeyPatch) -> None:
    ch.no_waits(monkeypatch)


def test_every_command_is_covered(tmp_path: Path) -> None:
    assert set(COMMANDS) | {"watch"} == ch.COVERED_TOP_LEVEL
    assert tuple(ch.command_argvs(tmp_path)) == ch.COMMAND_IDS


def setup(
    monkeypatch: pytest.MonkeyPatch, case: str, command: str
) -> tuple[list[str], ch.Pedals, str]:
    option, environment, known, adverts, line = CASES[case]
    if environment is not None:
        monkeypatch.setenv("OPENVAVE_DEVICE", environment)
    if known:
        seed(*known)
    return option, ch.Pedals(adverts, command), line


@pytest.mark.parametrize("case", list(CASES))
@pytest.mark.parametrize("command", COMMAND_IDS)
def test_one_pedal_line_on_stderr(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    command: str,
    case: str,
) -> None:
    option, pedals, expected = setup(monkeypatch, case, command)
    argv = ch.command_argvs(tmp_path)[command]
    _, _, err = ch.run(capsys, [*option, *argv], pedals)
    assert [line for line in err.splitlines() if line.startswith("pedal:")] == [expected]
    assert err.startswith(expected + "\n"), err  # before anything else (it is printed first)
    assert len(set(pedals.opened)) == 1


@pytest.mark.parametrize("case", list(CASES))
@pytest.mark.parametrize("command", [c for c in COMMAND_IDS if c != "watch"])
def test_no_pedal_line_with_json(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    command: str,
    case: str,
) -> None:
    option, pedals, _ = setup(monkeypatch, case, command)
    argv = ch.command_argvs(tmp_path)[command]
    _, _, err = ch.run(capsys, [*option, *argv, "--json"], pedals)
    assert "pedal:" not in err


def test_non_tank_name_is_flagged(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    pedals = ch.Pedals([(MAC_1, "SOMETHING-ELSE", -70)])
    seed((MAC_1, "home"), default=None)
    code, _, err = ch.run(capsys, ["--device", "home", "info"], pedals)
    assert code == 0, err
    assert err.splitlines()[0] == (
        f"pedal: home  {MAC_1}  -70 dBm  (--device)   name: SOMETHING-ELSE (not a Tank-G name)"
    )


def test_unknown_signal_strength(capsys: pytest.CaptureFixture[str]) -> None:
    pedals = ch.Pedals([(UUID_1, TANK, None)])
    _, _, err = ch.run(capsys, ["info"], pedals)
    assert err.splitlines()[0] == "pedal: 8F3A21C4…  ? dBm  (only one found)"
