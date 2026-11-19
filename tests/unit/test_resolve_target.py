"""resolve_target: the data-model table (spec 005 T007, research R5)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from openvave.devices import KnownDevices, Target, resolve_target
from openvave.errors import ConfigError

A = "8F3A21C4-0000-4000-8000-000000000001"
B = "AA:BB:CC:DD:EE:02"
C = "AA:BB:CC:DD:EE:03"  # never known
NOW = datetime(2026, 11, 19, 10, 0, tzinfo=UTC)


@pytest.fixture
def known(tmp_path: Path) -> KnownDevices:
    """A "stage" is the default; B "home" is known."""
    empty = KnownDevices(path=tmp_path / "devices.json")
    return empty.select(B, "home", now=NOW).select(A, "stage", now=NOW)


@pytest.fixture
def no_default(known: KnownDevices) -> KnownDevices:
    return known.forget()


# --- the seven rows of the table ---------------------------------------------------------


def test_row1_option_identifier(known: KnownDevices) -> None:
    assert resolve_target(B, A, known) == Target(B, "home", "device_option")
    assert resolve_target(C, None, known) == Target(C, None, "device_option")


def test_row2_option_known_nickname(known: KnownDevices) -> None:
    assert resolve_target("HOME", "stage", known) == Target(B, "home", "device_option")


def test_row3_option_other_text(known: KnownDevices) -> None:
    with pytest.raises(ConfigError) as info:
        resolve_target("nobody", A, known)
    assert info.value.reason == "unknown_nickname"
    assert info.value.exit_code == 2
    assert "nobody" in str(info.value)
    assert "home" in str(info.value)
    assert "stage" in str(info.value)


def test_row4_environment(known: KnownDevices) -> None:
    assert resolve_target(None, C, known) == Target(C, None, "environment")
    assert resolve_target(None, "home", known) == Target(B, "home", "environment")
    assert resolve_target(None, B.lower(), known) == Target(B.lower(), "home", "environment")


def test_row5_environment_other_text(known: KnownDevices) -> None:
    with pytest.raises(ConfigError) as info:
        resolve_target(None, "nobody", known)
    assert info.value.reason == "unknown_nickname"


@pytest.mark.parametrize("environment", [None, ""])
def test_row6_default(known: KnownDevices, environment: str | None) -> None:
    assert resolve_target(None, environment, known) == Target(A, "stage", "selected")


@pytest.mark.parametrize("environment", [None, ""])
def test_row7_nothing(no_default: KnownDevices, environment: str | None) -> None:
    assert resolve_target(None, environment, no_default) is None


# --- extra rules -------------------------------------------------------------------------


def test_option_beats_environment_beats_default(known: KnownDevices) -> None:
    assert resolve_target(C, "home", known).chosen_by == "device_option"  # type: ignore[union-attr]
    assert resolve_target(None, "home", known).chosen_by == "environment"  # type: ignore[union-attr]
    assert resolve_target(None, None, known).chosen_by == "selected"  # type: ignore[union-attr]


def test_empty_option_is_unset(known: KnownDevices) -> None:
    assert resolve_target("", None, known) == Target(A, "stage", "selected")


def test_known_none_with_identifier() -> None:
    assert resolve_target(A, None, None) == Target(A, None, "device_option")
    assert resolve_target(None, B, None) == Target(B, None, "environment")
    assert resolve_target(None, None, None) is None


def test_known_none_with_nickname() -> None:
    with pytest.raises(ConfigError) as info:
        resolve_target("stage", None, None)
    assert info.value.reason == "unknown_nickname"


def test_unknown_nickname_without_any_nickname(tmp_path: Path) -> None:
    known = KnownDevices(path=tmp_path / "devices.json").select(A, now=NOW)
    with pytest.raises(ConfigError) as info:
        resolve_target("stage", None, known)
    assert "no known pedal has a nickname" in str(info.value)


def test_target_is_frozen() -> None:
    import dataclasses

    target = Target(A, None, "selected")
    with pytest.raises(dataclasses.FrozenInstanceError):
        target.identifier = B  # type: ignore[misc]
