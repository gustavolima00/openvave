"""Where the known-pedals file lives (spec 005 T006, research R1)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from openvave.devices import default_config_path


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    for name in ("OPENVAVE_CONFIG", "XDG_CONFIG_HOME", "APPDATA"):
        monkeypatch.delenv(name, raising=False)
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    return home


def test_openvave_config_wins(monkeypatch: pytest.MonkeyPatch, clean_env: Path) -> None:
    monkeypatch.setenv("OPENVAVE_CONFIG", "/somewhere/else/pedals.json")
    monkeypatch.setenv("XDG_CONFIG_HOME", "/xdg")
    assert default_config_path() == Path("/somewhere/else/pedals.json")


def test_openvave_config_expands_user(monkeypatch: pytest.MonkeyPatch, clean_env: Path) -> None:
    monkeypatch.setenv("OPENVAVE_CONFIG", "~/pedals.json")
    assert default_config_path() == clean_env / "pedals.json"


def test_empty_openvave_config_is_unset(monkeypatch: pytest.MonkeyPatch, clean_env: Path) -> None:
    monkeypatch.setenv("OPENVAVE_CONFIG", "")
    monkeypatch.setattr(sys, "platform", "darwin")
    assert default_config_path() == clean_env / ".config" / "openvave" / "devices.json"


def test_xdg_config_home(monkeypatch: pytest.MonkeyPatch, clean_env: Path) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", "/xdg")
    monkeypatch.setattr(sys, "platform", "linux")
    assert default_config_path() == Path("/xdg/openvave/devices.json")


def test_empty_xdg_is_unset(monkeypatch: pytest.MonkeyPatch, clean_env: Path) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", "")
    monkeypatch.setattr(sys, "platform", "linux")
    assert default_config_path() == clean_env / ".config" / "openvave" / "devices.json"


def test_windows_appdata(monkeypatch: pytest.MonkeyPatch, clean_env: Path) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", "/appdata")
    assert default_config_path() == Path("/appdata") / "openvave" / "devices.json"


def test_windows_without_appdata_falls_back(
    monkeypatch: pytest.MonkeyPatch, clean_env: Path
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    assert default_config_path() == clean_env / ".config" / "openvave" / "devices.json"


@pytest.mark.parametrize("platform", ["darwin", "linux"])
def test_home_fallback(monkeypatch: pytest.MonkeyPatch, clean_env: Path, platform: str) -> None:
    monkeypatch.setattr(sys, "platform", platform)
    assert default_config_path() == clean_env / ".config" / "openvave" / "devices.json"
