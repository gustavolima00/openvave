"""CHANGELOG 0.3.0 and the package version describe the first release with writes (003 T065).

The 0.3.0 section is how a user finds out that openvave can now write to the pedal: it must name
the new commands, the new exit code and the write allowlist, and the version printed by
``openvave --version`` must match it.
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

VERSION = "0.3.0"


def _section(version: str) -> str:
    text = CHANGELOG.read_text(encoding="utf-8")
    match = re.search(rf"^## \[{re.escape(version)}\].*?(?=^## \[|\Z)", text, re.S | re.M)
    assert match is not None, f"CHANGELOG.md has no [{version}] section"
    return match.group(0)


@pytest.mark.parametrize(
    "needle",
    [
        "`openvave preset backup",
        "`openvave set",
        "`openvave preset select",
        "`--dry-run`",
        "`--experimental`",
        "exit code 8",
        "`0x22`",
        # the four allowlisted write targets (command-layer.md "Write messages")
        "`0x10000004`",
        "`0x10000000 + k`",
        "`0x10000012`",
        "`0xE0000000 + i`",
    ],
)
def test_release_section_names(needle: str) -> None:
    section = _section(VERSION)
    assert needle.lower() in section.lower(), f"CHANGELOG [{VERSION}] does not mention {needle}"


def test_release_section_says_what_is_never_sent() -> None:
    section = _section(VERSION)
    for never in ("`0x21`", "`0xF0000000`"):
        assert never in section, f"CHANGELOG [{VERSION}] must say {never} is never sent"


def test_release_is_not_left_under_unreleased() -> None:
    text = CHANGELOG.read_text(encoding="utf-8")
    assert text.index(f"## [{VERSION}]") < text.index("## [0.2.0]")
    unreleased = re.search(r"^## \[Unreleased\]\n(.*?)(?=^## \[)", text, re.S | re.M)
    assert unreleased is not None
    # Later changes may be listed under [Unreleased]; the 0.3.0 entries must not be.
    assert "openvave preset backup [--output" not in unreleased.group(1), "0.3.0 left unreleased"


def test_versions_agree() -> None:
    assert openvave.__version__ == VERSION
    with PYPROJECT.open("rb") as fh:
        assert tomllib.load(fh)["project"]["version"] == VERSION


def test_cli_version(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--version"]) == 0
    assert VERSION in capsys.readouterr().out
