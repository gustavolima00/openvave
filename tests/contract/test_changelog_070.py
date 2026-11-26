"""CHANGELOG 0.7.0 and the package version describe the release of spec 008 (T006).

0.7.0 adds the simulated pedal, the front panel as data with the group enabled state, and the
strict preset position helpers. Its section must open with a summary, name every new public name,
say that GATE's rule is ``documented``, keep ``schema_version`` 2 and say that no pedal was
needed; the version printed by ``openvave --version`` must match it.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

import openvave
from openvave.cli import main

ROOT = Path(__file__).resolve().parents[2]
CHANGELOG = ROOT / "CHANGELOG.md"
PYPROJECT = ROOT / "pyproject.toml"

VERSION = "0.7.0"
NAMES = [
    "FakeTransport.simulated",
    "PANEL_CONTROLS",
    "PanelControl",
    "panel_control",
    "PANEL_GROUPS",
    "PanelGroup",
    "panel_group",
    "group_enabled",
    "preset_index",
    "preset_position",
]


def _text() -> str:
    return CHANGELOG.read_text(encoding="utf-8")


def _section(version: str) -> str:
    match = re.search(rf"^## \[{re.escape(version)}\].*?(?=^## \[|\Z)", _text(), re.S | re.M)
    assert match is not None, f"CHANGELOG.md has no [{version}] section"
    return match.group(0)


def test_section_sits_between_unreleased_and_060() -> None:
    text = _text()
    assert text.index("## [Unreleased]") < text.index(f"## [{VERSION}]")
    assert text.index(f"## [{VERSION}]") < text.index("## [0.6.0]")


def test_unreleased_is_empty() -> None:
    match = re.search(r"^## \[Unreleased\]\n(.*?)(?=^## \[)", _text(), re.S | re.M)
    assert match is not None
    assert match.group(1).strip() == ""


@pytest.mark.parametrize("name", NAMES)
def test_names_every_addition(name: str) -> None:
    assert f"`{name}" in _section(VERSION), f"CHANGELOG [{VERSION}] does not name {name}"


def test_summary_paragraph_before_first_subsection() -> None:
    summary = _section(VERSION).split("\n### ", 1)[0].split("\n", 1)[1].strip()
    assert len(summary) > 100, "the 0.7.0 section opens with a summary paragraph"


def test_gate_rule_is_documented() -> None:
    section = _section(VERSION)
    assert re.search(r"GATE[^\n]*`documented`|`documented`[^\n]*GATE", section), section


def test_schema_version_unchanged() -> None:
    assert "`schema_version` stays 2" in _section(VERSION)


def test_tested_without_a_pedal() -> None:
    match = re.search(r"^### Tested\n.*?(?=^### |\Z)", _section(VERSION), re.S | re.M)
    assert match is not None, f"CHANGELOG [{VERSION}] has no '### Tested'"
    assert "no pedal" in match.group(0).lower()


def test_spec007_names_stay_in_060() -> None:
    assert "Added (spec 007 US4)" not in _section(VERSION)
    assert "Added (spec 007 US4)" in _section("0.6.0")


def test_versions_agree() -> None:
    assert openvave.__version__ == VERSION
    with PYPROJECT.open("rb") as fh:
        assert tomllib.load(fh)["project"]["version"] == VERSION


def test_cli_version(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--version"]) == 0
    assert VERSION in capsys.readouterr().out
