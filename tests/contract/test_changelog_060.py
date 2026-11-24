"""CHANGELOG 0.6.0 and the package version describe the release of spec 006 (T059), with the
spec 007 work merged before it.

0.6.0 adds ``openvave mcp``, an MCP server for AI assistants, and spec 007's preset management.
Its section must open with a summary, name the command, the extra, the options and every tool,
the opt-ins and the owner's confirmation, keep ``schema_version`` 2, and say what was tested on
fw 96; the version printed by ``openvave --version`` must match it.
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

VERSION = "0.6.0"


def _section(version: str) -> str:
    text = CHANGELOG.read_text(encoding="utf-8")
    match = re.search(rf"^## \[{re.escape(version)}\].*?(?=^## \[|\Z)", text, re.S | re.M)
    assert match is not None, f"CHANGELOG.md has no [{version}] section"
    return match.group(0)


TOOLS = [
    "pedal_status",
    "pedal_disconnect",
    "pedal_scan",
    "pedal_select",
    "pedal_info",
    "preset_read",
    "pedal_changes",
    "preset_backup",
    "backups_list",
    "pedal_set",
    "preset_select",
    "preset_reload",
    "bypass_on",
    "bypass_off",
    "loopback",
    "preset_save",
    "preset_restore",
    "preset_copy",
    "preset_swap",
    "preset_import",
    "preset_export",
]


@pytest.mark.parametrize(
    "needle",
    [
        # the command, its extra and options
        "`openvave mcp",
        "`openvave[mcp]`",
        "--read-only",
        "--idle-release",
        "--backup-dir",
        # the opt-ins and the confirmation
        "`dry_run`",
        "`experimental`",
        "`discard_edits`",
        "`unsafe: true`",
        "elicitation",
        "`declined_by_owner`",
        # spec 007 on the command line
        "`openvave preset copy",
        "`preset swap",
        "`preset export",
        "`preset import",
        "`OPENVAVE_BACKUP_DIR`",
        # the guide
        "docs/mcp.md",
        *(f"`{tool}`" for tool in TOOLS),
    ],
)
def test_release_section_names(needle: str) -> None:
    section = _section(VERSION)
    assert needle.lower() in section.lower(), f"CHANGELOG [{VERSION}] does not mention {needle}"


def test_every_tool_the_server_lists_is_named() -> None:
    pytest.importorskip("mcp")
    from openvave.mcp_server import TOOLS as REGISTRY

    assert set(REGISTRY) == set(TOOLS)


def test_schema_version_unchanged() -> None:
    assert "`schema_version` stays 2" in _section(VERSION)


def test_summary_paragraph_before_first_subsection() -> None:
    section = _section(VERSION)
    summary = section.split("\n### ", 1)[0].split("\n", 1)[1].strip()
    assert len(summary) > 100, "the 0.6.0 section opens with a summary paragraph"
    assert "openvave mcp" in summary


def test_tested_on_fw96() -> None:
    match = re.search(r"^### Tested\n.*?(?=^### |\Z)", _section(VERSION), re.S | re.M)
    assert match is not None, f"CHANGELOG [{VERSION}] has no '### Tested'"
    assert "fw 96" in match.group(0)


def test_release_is_not_left_under_unreleased() -> None:
    text = CHANGELOG.read_text(encoding="utf-8")
    assert text.index("## [Unreleased]") < text.index(f"## [{VERSION}]")
    assert text.index(f"## [{VERSION}]") < text.index("## [0.5.0]")
    unreleased = re.search(r"^## \[Unreleased\]\n(.*?)(?=^## \[)", text, re.S | re.M)
    assert unreleased is not None
    assert "openvave mcp" not in unreleased.group(1), "0.6.0 left unreleased"


def test_versions_agree() -> None:
    assert openvave.__version__ == VERSION
    with PYPROJECT.open("rb") as fh:
        assert tomllib.load(fh)["project"]["version"] == VERSION


def test_cli_version(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--version"]) == 0
    assert VERSION in capsys.readouterr().out
