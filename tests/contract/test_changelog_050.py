"""CHANGELOG 0.5.0 and the package version describe the release of spec 005 (T065, T066).

0.5.0 finds, chooses and keeps a connection to Tank-G pedals. Its section must name the new
commands, the two environment variables, the new library names, the "no fallback" rule and the
unchanged JSON ``schema_version``. The package version moved on with 0.6.0
(``test_changelog_060.py``).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CHANGELOG = ROOT / "CHANGELOG.md"

VERSION = "0.5.0"


def _section(version: str) -> str:
    text = CHANGELOG.read_text(encoding="utf-8")
    match = re.search(rf"^## \[{re.escape(version)}\].*?(?=^## \[|\Z)", text, re.S | re.M)
    assert match is not None, f"CHANGELOG.md has no [{version}] section"
    return match.group(0)


@pytest.mark.parametrize(
    "needle",
    [
        # new commands
        "`openvave scan",
        "`openvave select",
        "`openvave device",
        "`openvave device rename",
        "`openvave forget",
        "--identify",
        "--device",
        # environment variables
        "`OPENVAVE_DEVICE`",
        "`OPENVAVE_CONFIG`",
        # library names
        "`openvave.KnownDevices`",
        "`openvave.resolve_target",
        "`openvave.scan(",
        "`openvave.identify(",
        "`TankG.connect_selected(",
        "`TankG.open()`",
        "`TankG.close()`",
        "`TankG.is_connected`",
        "`openvave.ConfigError`",
        "`openvave.TargetNotFoundError`",
        # the stderr line and the JSON fields
        "`pedal:`",
        "`chosen_by`",
        "`nickname`",
    ],
)
def test_release_section_names(needle: str) -> None:
    section = _section(VERSION)
    assert needle.lower() in section.lower(), f"CHANGELOG [{VERSION}] does not mention {needle}"


def test_no_fallback_rule() -> None:
    section = _section(VERSION)
    assert "**No fallback**" in section
    assert "nothing else" in section


def test_schema_version_unchanged() -> None:
    assert "`schema_version` stays 2" in _section(VERSION)


def test_summary_paragraph_before_first_subsection() -> None:
    section = _section(VERSION)
    summary = section.split("\n### ", 1)[0].split("\n", 1)[1].strip()
    assert len(summary) > 100, "the 0.5.0 section opens with a summary paragraph"


def test_tested_on_fw96() -> None:
    match = re.search(r"^### Tested\n.*?(?=^### |\Z)", _section(VERSION), re.S | re.M)
    assert match is not None, f"CHANGELOG [{VERSION}] has no '### Tested'"
    assert "fw 96" in match.group(0)


def test_release_is_not_left_under_unreleased() -> None:
    text = CHANGELOG.read_text(encoding="utf-8")
    assert text.index(f"## [{VERSION}]") < text.index("## [0.4.0]")
    unreleased = re.search(r"^## \[Unreleased\]\n(.*?)(?=^## \[)", text, re.S | re.M)
    assert unreleased is not None
    assert "openvave scan" not in unreleased.group(1), "0.5.0 left unreleased"
