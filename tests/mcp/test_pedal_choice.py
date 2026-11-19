"""Choosing the pedal from the server: ``pedal_scan``, ``pedal_select`` and the choice rule
(spec 006 US4, FR-016–FR-018, research R12).

Pedals A (``UUID_1``) and B (``UUID_2``) are fake advertisers; the transport factory goes through
the library's real ``locate`` with a fake scanner (``tests.support.choice.Pedals``), so the
choice, ``TargetNotFoundError`` and the 0.4.0 rules are the real ones. ``opened`` records every
pedal a transport was built for: never one other than the chosen pedal. Identifiers are made up
(Constitution VI).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from openvave.devices import KnownDevices
from tests.mcp.conftest import open_harness, options
from tests.support import choice as ch
from tests.support.cli005 import config_path, file_bytes, seed
from tests.support.scanner import TANK, UUID_1, UUID_2, fake_scanner

A, B = UUID_1, UUID_2
RSSI = {A: -58, B: -61}


def pedals(*identifiers: str) -> ch.Pedals:
    return ch.Pedals([(i, TANK, RSSI[i]) for i in identifiers])


def harness(tmp_path: Path, p: ch.Pedals, **overrides: object) -> open_harness:
    return open_harness(
        options(tmp_path, scan_timeout=0.05, **overrides), p.factory, scanner_factory=p.scanner()
    )


@pytest.fixture(autouse=True)
def _fast(monkeypatch: pytest.MonkeyPatch) -> None:
    ch.no_waits(monkeypatch)


# -- the choice rule ------------------------------------------------------------------------------


async def test_only_pedal_in_range(tmp_path: Path) -> None:
    p = pedals(A)
    async with harness(tmp_path, p) as h:
        await h.ok("pedal_info")
        status = await h.ok("pedal_status")
    assert p.opened == [A]
    assert status["pedal"]["chosen_by"] == "only_one_found"


async def test_two_pedals_and_no_choice_lists_them(tmp_path: Path) -> None:
    p = pedals(A, B)
    async with harness(tmp_path, p) as h:
        text = await h.error("pedal_info")
        assert h.holder.last_error is not None
    assert text.startswith("multiple_devices: ")
    assert A in text and B in text
    assert p.opened == []


async def test_default_pedal_wins_over_the_only_one_rule(tmp_path: Path) -> None:
    seed((A, "stage"))
    p = pedals(A, B)
    async with harness(tmp_path, p) as h:
        await h.ok("pedal_info")
        status = await h.ok("pedal_status")
    assert p.opened == [A]
    assert status["pedal"]["nickname"] == "stage"
    assert status["pedal"]["chosen_by"] == "selected"


async def test_environment_wins_over_the_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed((A, "stage"))
    monkeypatch.setenv("OPENVAVE_DEVICE", B)
    p = pedals(A, B)
    async with harness(tmp_path, p) as h:
        await h.ok("pedal_info")
    assert p.opened == [B]


async def test_device_option_wins_over_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENVAVE_DEVICE", B)
    p = pedals(A, B)
    async with harness(tmp_path, p, device=A) as h:
        await h.ok("pedal_info")
    assert p.opened == [A]


async def test_session_choice_wins_over_device_option(tmp_path: Path) -> None:
    seed((B, "home"), (A, "stage"))
    before = file_bytes()
    p = pedals(A, B)
    async with harness(tmp_path, p, device=A) as h:
        result = await h.ok("pedal_select", {"target": "home"})
        assert file_bytes() == before  # selecting alone writes nothing
        await h.ok("pedal_info")
        await h.ok("pedal_info")
        status = await h.ok("pedal_status")
    assert p.opened == [B]
    assert result["remembered"] is False
    assert result["session_choice"]["identifier"] == B
    assert result["session_choice"]["nickname"] == "home"
    assert status["session_choice"]["identifier"] == B
    known = KnownDevices.load(config_path())
    assert known.default is not None
    assert known.default.identifier == A  # not remembered: the default is unchanged


async def test_chosen_pedal_absent_is_target_not_found(tmp_path: Path) -> None:
    p = pedals(A)
    async with harness(tmp_path, p, device=B) as h:
        text = await h.error("pedal_info")
        again = await h.ok("pedal_status")
    assert text.startswith("target_not_found: ")
    assert A in text  # the pedals seen are listed
    assert p.opened == []  # never another pedal
    assert again["connected"] is False


async def test_selecting_another_pedal_closes_the_held_connection(tmp_path: Path) -> None:
    p = pedals(A, B)
    async with harness(tmp_path, p, device=A) as h:
        await h.ok("pedal_info")
        assert h.holder.connected
        await h.ok("pedal_select", {"target": B})
        assert not h.holder.connected
        await h.ok("pedal_info")
    assert p.opened == [A, B]


async def test_selecting_the_held_pedal_keeps_the_connection(tmp_path: Path) -> None:
    p = pedals(A, B)
    async with harness(tmp_path, p, device=A) as h:
        await h.ok("pedal_info")
        await h.ok("pedal_select", {"target": A})
        assert h.holder.connected
        await h.ok("pedal_info")
    assert p.opened == [A]


# -- pedal_select targets -------------------------------------------------------------------------


async def test_select_unique_prefix(tmp_path: Path) -> None:
    p = pedals(A, B)
    async with harness(tmp_path, p) as h:
        result = await h.ok("pedal_select", {"target": B.replace("-", "")})
        await h.ok("pedal_info")
    assert result["session_choice"]["identifier"] == B
    assert result["session_choice"]["rssi"] == RSSI[B]
    assert p.opened == [B]


async def test_select_ambiguous_prefix(tmp_path: Path) -> None:
    p = pedals(A, B)
    async with harness(tmp_path, p) as h:
        text = await h.error("pedal_select", {"target": "8f3a"})
        status = await h.ok("pedal_status")
    assert text.startswith("multiple_devices: ")
    assert status["session_choice"] is None


@pytest.mark.parametrize("target", ["nobody", "8f3"])
async def test_select_unknown_nickname_or_short_prefix(tmp_path: Path, target: str) -> None:
    seed((A, "stage"))
    p = pedals(A, B)
    async with harness(tmp_path, p) as h:
        text = await h.error("pedal_select", {"target": target})
    assert text.startswith("config_error: ")
    assert "stage" in text  # the known nicknames are named


async def test_select_identifier_not_in_range(tmp_path: Path) -> None:
    p = pedals(A)
    async with harness(tmp_path, p) as h:
        text = await h.error("pedal_select", {"target": B})
    assert text.startswith("no_device_found: ")


async def test_select_with_invalid_config_file_still_takes_an_identifier(tmp_path: Path) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"format_version": 2}', encoding="utf-8")
    before = file_bytes()
    p = pedals(A, B)
    async with harness(tmp_path, p) as h:
        await h.ok("pedal_select", {"target": A})
        await h.ok("pedal_info")
        text = await h.error("pedal_select", {"target": B, "remember": True})
    assert p.opened == [A]
    assert text.startswith("config_error: ")
    assert file_bytes() == before


async def test_select_remember_saves_the_default_and_nickname(tmp_path: Path) -> None:
    seed((A, "stage"))
    p = pedals(A, B)
    async with harness(tmp_path, p) as h:
        result = await h.ok("pedal_select", {"target": B, "remember": True, "nickname": "home"})
        await h.ok("pedal_info")
    known = KnownDevices.load(config_path())
    assert known.default is not None
    assert known.default.identifier == B
    assert known.default.nickname == "home"
    assert result["command"] == "select"
    assert result["default"]["identifier"] == B
    assert result["previous_default"]["identifier"] == A
    assert "home" in result["summary"]
    assert p.opened == [B]


async def test_select_nickname_without_remember_is_invalid(tmp_path: Path) -> None:
    p = pedals(A)
    async with harness(tmp_path, p) as h:
        text = await h.error("pedal_select", {"target": A, "nickname": "home"})
    assert text.startswith("invalid_value: ")
    assert "remember" in text


async def test_select_bad_nickname(tmp_path: Path) -> None:
    p = pedals(A)
    async with harness(tmp_path, p) as h:
        text = await h.error("pedal_select", {"target": A, "remember": True, "nickname": "a b"})
    assert text.startswith("config_error: ")
    assert file_bytes() is None


# -- pedal_scan -----------------------------------------------------------------------------------


async def test_scan_lists_pedals_without_connecting(tmp_path: Path) -> None:
    seed((A, "stage"))
    p = pedals(A, B)
    async with harness(tmp_path, p) as h:
        result = await h.ok("pedal_scan")
        status = await h.ok("pedal_status")
    assert p.opened == []
    assert status["connected"] is False
    rows = {row["identifier"]: row for row in result["devices"]}
    assert set(rows) == {A, B}
    assert rows[A]["nickname"] == "stage"
    assert rows[A]["selected"] is True
    assert rows[B]["selected"] is False
    assert all(row["connected"] is False for row in rows.values())
    assert result["command"] == "scan"
    assert result["summary"].startswith("2 pedals found")


async def test_scan_lists_the_held_pedal_as_connected(tmp_path: Path) -> None:
    p = pedals(A)
    # the held pedal does not advertise: the scan sees only B
    scanner = fake_scanner([(B, TANK, RSSI[B])])
    opts = options(tmp_path, scan_timeout=0.05)
    async with open_harness(opts, p.factory, scanner_factory=scanner) as h:
        await h.ok("pedal_info")
        result = await h.ok("pedal_scan")
        assert h.holder.connected  # scanning does not drop the connection
    rows = {row["identifier"]: row for row in result["devices"]}
    assert rows[B]["connected"] is False
    assert rows[A]["connected"] is True
    assert rows[A]["tank_g"] is True


async def test_scan_with_nothing_in_range(tmp_path: Path) -> None:
    p = pedals()
    async with harness(tmp_path, p) as h:
        result = await h.ok("pedal_scan")
    assert result["devices"] == []
    assert result["summary"].startswith("no Tank-G found")
