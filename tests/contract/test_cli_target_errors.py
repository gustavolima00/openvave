"""What a pedal command says when the chosen pedal is not there (spec 005 T039, FR-019).

Exit 3 names the target and lists the Tank-G pedals seen; exit 4 lists the candidates with the
nicknames of known pedals; an unknown nickname is exit 2 before any scan; an invalid
configuration file is exit 2 only when the file is needed. No transport is ever built for a
pedal other than the chosen one.
"""

from __future__ import annotations

from typing import Any

import pytest

from openvave.cli import main
from openvave.devices import Target
from tests.support import choice as ch
from tests.support.cli005 import config_path, file_bytes, seed
from tests.support.scanner import MAC_1, TANK, UUID_1, UUID_2, forbidden_scanner

HINT_ADVERTISING = (
    "hint: switch it on and close the M-VAVE phone app (a connected pedal stops advertising)."
)
HINT_CHOOSE = (
    "hint: use another pedal once with --device ID, or make it the default with: openvave select ID"
)


@pytest.fixture(autouse=True)
def _fast(monkeypatch: pytest.MonkeyPatch) -> None:
    ch.no_waits(monkeypatch)


@pytest.mark.parametrize("argv", [["info"], ["set", "gain", "90"]], ids=["read", "write"])
def test_default_not_seen_lists_the_pedals_seen(
    capsys: pytest.CaptureFixture[str], argv: list[str]
) -> None:
    seed((UUID_1, "stage"))
    pedals = ch.Pedals([(UUID_2, TANK, -61), ("9B7C0000-0000-4000-8000-0000000000AA", "S", -30)])
    code, out, err = ch.run(capsys, argv, pedals)
    assert code == 3
    assert out == ""
    assert err.splitlines() == [
        f"error: stage ({UUID_1}) not found",
        f"  seen: {UUID_2}  {TANK}  -61 dBm",
        HINT_ADVERTISING,
        HINT_CHOOSE,
    ]
    assert pedals.opened == []


def test_default_not_seen_and_nothing_seen(capsys: pytest.CaptureFixture[str]) -> None:
    seed((UUID_1, "stage"))
    code, _, err = ch.run(capsys, ["info"], ch.Pedals([]))
    assert code == 3
    assert err.splitlines() == [f"error: stage ({UUID_1}) not found", HINT_ADVERTISING, HINT_CHOOSE]


def test_identifier_unknown_to_the_configuration(capsys: pytest.CaptureFixture[str]) -> None:
    pedals = ch.Pedals([(UUID_1, TANK, -58)])
    code, _, err = ch.run(capsys, ["--device", MAC_1, "info"], pedals)
    assert code == 3
    assert err.splitlines()[:2] == [
        f"error: device {MAC_1} not found",
        f"  seen: {UUID_1}  {TANK}  -58 dBm",
    ]
    assert pedals.opened == []


def test_several_pedals_without_a_choice(capsys: pytest.CaptureFixture[str]) -> None:
    seed((UUID_2, "home"), default=None)
    pedals = ch.Pedals([(UUID_2, TANK, -61), (UUID_1, TANK, -58)])
    code, _, err = ch.run(capsys, ["info"], pedals)
    assert code == 4
    assert err.splitlines() == [
        "error: 2 pedals found",
        f"  {UUID_1}  {TANK}  -58 dBm",
        f"  {UUID_2}  {TANK}  -61 dBm  home",
        "hint: use one once with --device ID, or remember one with: openvave select ID",
    ]
    assert pedals.opened == []


def no_scan_factory() -> Any:
    async def factory(target: Target | None, scan_timeout: float) -> Any:
        raise AssertionError("must not scan or connect")

    return factory


@pytest.mark.parametrize("how", ["option", "environment"])
def test_unknown_nickname_exit_2_before_any_scan(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, how: str
) -> None:
    seed((UUID_1, "stage"), (UUID_2, "home"))
    before = file_bytes()
    argv = ["info"]
    if how == "option":
        argv = ["--device", "nobody", "info"]
    else:
        monkeypatch.setenv("OPENVAVE_DEVICE", "nobody")
    code = main(argv, transport_factory=no_scan_factory(), scanner_factory=forbidden_scanner)
    out, err = capsys.readouterr()
    assert code == 2
    assert out == ""
    assert err.splitlines() == [
        "error: unknown pedal nickname 'nobody'; known nicknames: stage, home"
    ]
    assert file_bytes() == before


def write_invalid() -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")


def test_invalid_file_is_exit_2_when_needed(capsys: pytest.CaptureFixture[str]) -> None:
    write_invalid()
    code = main(["info"], transport_factory=no_scan_factory(), scanner_factory=forbidden_scanner)
    _, err = capsys.readouterr()
    assert code == 2
    lines = err.splitlines()
    assert lines[0].startswith(f"error: {config_path()}: not valid JSON")
    assert lines[1] == "hint: fix the file or reset it with: openvave forget --all"


@pytest.mark.parametrize("how", ["option", "environment"])
def test_invalid_file_with_an_identifier_runs_with_a_warning(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, how: str
) -> None:
    write_invalid()
    argv = ["info"]
    if how == "option":
        argv = ["--device", UUID_1, "info"]
    else:
        monkeypatch.setenv("OPENVAVE_DEVICE", UUID_1)
    code, out, err = ch.run(capsys, argv, ch.Pedals([(UUID_1, TANK, -58)]))
    assert code == 0, err
    assert "firmware 96" in out
    lines = err.splitlines()
    assert lines[0].startswith(f"warning: {config_path()}: not valid JSON")
    assert lines[0].endswith("(nicknames unavailable)")
    reason = "(--device)" if how == "option" else "(OPENVAVE_DEVICE)"
    assert lines[1] == f"pedal: 8F3A21C4…  -58 dBm  {reason}"
    assert config_path().read_text(encoding="utf-8") == "{not json"


def test_no_choice_keeps_the_0_4_0_exit_3_hint(capsys: pytest.CaptureFixture[str]) -> None:
    code, _, err = ch.run(capsys, ["info"], ch.Pedals([]))
    assert code == 3
    assert err.splitlines() == [
        "error: no TANK-Gv2_BLE found",
        "hint: switch the pedal on and close the M-VAVE phone app (it holds the connection)",
    ]


def test_device_help_mentions_nicknames(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["info", "--help"]) == 0
    assert "nickname" in capsys.readouterr().out
