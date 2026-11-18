"""CHANGELOG 0.4.0 and the package version describe the release of spec 004 (T092, T093).

0.4.0 is the first release that can change stored presets. Its section must name the new
commands, `set` in normal mode, both opt-ins, the safety statement that replaces 0.3.0's "never
saves", the confidence of each new write message and the firmware it was tested on; the version
printed by ``openvave --version`` must match it.
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

VERSION = "0.4.0"


def _section(version: str) -> str:
    text = CHANGELOG.read_text(encoding="utf-8")
    match = re.search(rf"^## \[{re.escape(version)}\].*?(?=^## \[|\Z)", text, re.S | re.M)
    assert match is not None, f"CHANGELOG.md has no [{version}] section"
    return match.group(0)


def _subsection(version: str, title: str) -> str:
    match = re.search(rf"^### {title}\n.*?(?=^### |\Z)", _section(version), re.S | re.M)
    assert match is not None, f"CHANGELOG [{version}] has no '### {title}'"
    return match.group(0)


@pytest.mark.parametrize(
    "needle",
    [
        # new commands
        "`openvave preset reload",
        "`openvave bypass on",
        "`openvave bypass off",
        "`openvave loopback on|off`",
        "`openvave preset save",
        "`openvave preset restore",
        # both opt-ins
        "`--unsafe`",
        "`--experimental`",
        # the new write targets
        "`0xE1000000 + i`",
        "`0xD0000000`",
        "`2 + 21·i`",
        "`0xF0000000`",
        "758-byte image",
    ],
)
def test_release_section_names(needle: str) -> None:
    section = _section(VERSION)
    assert needle.lower() in section.lower(), f"CHANGELOG [{VERSION}] does not mention {needle}"


def test_set_in_normal_mode_is_a_change() -> None:
    assert "`openvave set` works in normal mode" in _subsection(VERSION, "Changed")


def test_replaced_safety_statement() -> None:
    changed = _subsection(VERSION, "Changed")
    assert "openvave can now change stored presets" in changed
    assert "never saves or" in changed  # names the 0.3.0 statement it replaces
    assert "automatic, verified backup" in changed


@pytest.mark.parametrize(
    ("message", "confidence"),
    [
        ("Bypass", "confirmed"),
        ("Save", "confirmed"),
        ("Restore", "confirmed"),
        ("Loopback", "observed"),
    ],
)
def test_confidence_of_each_new_message(message: str, confidence: str) -> None:
    added = _subsection(VERSION, "Added")
    entry = re.search(rf"^- \*\*{message}\*\*.*?(?=^- |\Z)", added, re.S | re.M)
    assert entry is not None, f"no '**{message}**' entry under Added"
    assert f"`{confidence}`" in entry.group(0), f"{message} entry does not say `{confidence}`"


def test_tested_on_fw96() -> None:
    tested = _subsection(VERSION, "Tested")
    assert "fw 96" in tested


def test_release_is_not_left_under_unreleased() -> None:
    text = CHANGELOG.read_text(encoding="utf-8")
    assert text.index(f"## [{VERSION}]") < text.index("## [0.3.0]")
    unreleased = re.search(r"^## \[Unreleased\]\n(.*?)(?=^## \[)", text, re.S | re.M)
    assert unreleased is not None
    assert "openvave preset save" not in unreleased.group(1), "0.4.0 left unreleased"


def test_versions_agree() -> None:
    assert openvave.__version__ == VERSION
    with PYPROJECT.open("rb") as fh:
        assert tomllib.load(fh)["project"]["version"] == VERSION


def test_cli_version(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--version"]) == 0
    assert VERSION in capsys.readouterr().out
