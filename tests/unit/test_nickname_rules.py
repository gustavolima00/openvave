"""Identifier shapes and nickname rules (spec 005 T003, research R3)."""

from __future__ import annotations

import pytest

from openvave.devices import check_nickname, is_identifier
from openvave.errors import ConfigError


@pytest.mark.parametrize(
    "value",
    [
        "AA:BB:CC:DD:EE:01",
        "aa:bb:cc:dd:ee:01",
        "AA-BB-CC-DD-EE-01",
        "8F3A21C4-0000-4000-8000-000000000001",
        "8f3a21c4-0000-4000-8000-000000000001",
    ],
)
def test_identifier_shapes(value: str) -> None:
    assert is_identifier(value)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "stage",
        "AA:BB:CC:DD:EE",  # five octets
        "AA:BB:CC:DD:EE:01:02",
        "AA:BB-CC:DD:EE:01",  # mixed separators
        "GG:BB:CC:DD:EE:01",
        "8F3A21C4-0000-4000-8000-00000000000",  # short last group
        "8F3A21C40000400080000000000000001",
        "8F3A21C4",
    ],
)
def test_not_identifier(value: str) -> None:
    assert not is_identifier(value)


@pytest.mark.parametrize("value", ["stage", "amp-2", "a1", "Home_Rig", "x" * 32, "abc", "cafe-1"])
def test_valid_nicknames(value: str) -> None:
    assert check_nickname(value) == value


@pytest.mark.parametrize(
    "value",
    [
        "",
        "x" * 33,
        "my pedal",
        "stage!",
        "pédale",
        "AA:BB:CC:DD:EE:01",
        "8F3A21C4-0000-4000-8000-000000000001",
        "abcd",
        "8F3A",
        "beef",
        "0123456789",
        "DEADBEEF",
    ],
)
def test_rejected_nicknames(value: str) -> None:
    with pytest.raises(ConfigError) as info:
        check_nickname(value)
    assert info.value.reason == "bad_nickname"
    assert info.value.exit_code == 2


def test_short_hex_is_a_nickname() -> None:
    # fewer than 4 hex characters cannot be an identifier prefix (R4)
    assert check_nickname("abc") == "abc"
    assert check_nickname("a1") == "a1"
