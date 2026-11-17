"""CHANGELOG 0.2.0 lists every field name of 0.1.0 that the byte map no longer has (002 T058).

Renaming a JSON field is a breaking change (research R8): scripts that read ``knob_unknown`` must
find, in the CHANGELOG, what it is called now.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from openvave.protocol import BYTE_MAP

ROOT = Path(__file__).resolve().parents[2]
CHANGELOG = ROOT / "CHANGELOG.md"

KNOWN_FIELDS_0_1_0 = ("not_in_edit_mode", "knob_unknown", "reverb_decay", "reverb_mix", "ir_cab")
"""Every name of ``KNOWN_FIELDS`` as released in 0.1.0 (frozen: 0.1.0 will not change)."""

ROW = re.compile(
    r"^[ \t]*\|\s*`(?P<old>[a-z0-9_]+)`\s*\|\s*`(?P<new>[a-z0-9_]+)`\s*\|", re.MULTILINE
)
"""A rename table row, ``| `old` | `new` | why |`` (indented under a bullet or not)."""


def _release_section(version: str) -> str:
    text = CHANGELOG.read_text(encoding="utf-8")
    match = re.search(rf"^## \[{re.escape(version)}\].*?(?=^## \[|\Z)", text, re.S | re.M)
    assert match is not None, f"CHANGELOG.md has no [{version}] section"
    return match.group(0)


def _renames() -> dict[str, str]:
    return {m["old"]: m["new"] for m in ROW.finditer(_release_section("0.2.0"))}


def _current_names() -> set[str]:
    return {e.name for e in BYTE_MAP if e.name is not None}


@pytest.mark.parametrize(
    "old", [n for n in KNOWN_FIELDS_0_1_0 if n not in {e.name for e in BYTE_MAP}]
)
def test_every_dropped_name_is_in_the_rename_table(old: str) -> None:
    renames = _renames()
    assert old in renames, f"`{old}` left the byte map but is not in the CHANGELOG 0.2.0 renames"
    assert renames[old] in _current_names(), f"`{old}` → `{renames[old]}`: no such field"


def test_rename_table_has_only_real_renames() -> None:
    renames = _renames()
    assert renames, "CHANGELOG 0.2.0 has no rename table"
    assert set(renames) <= set(KNOWN_FIELDS_0_1_0)
    assert not set(renames) & _current_names()


def test_release_section_is_kept() -> None:
    # The current version is pinned in test_changelog_030.py; 0.2.0's section stays as released.
    assert "## [0.2.0]" in CHANGELOG.read_text(encoding="utf-8")
