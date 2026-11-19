"""Every listed tool's annotations equal the contract's tool table (spec 006 SC-004), and
``--read-only`` hides exactly the write tools (FR-010)."""

from __future__ import annotations

import re
from dataclasses import dataclass

import pytest

from tests.mcp.conftest import CountingFactory, open_harness, options
from tests.support.captures import REPO_ROOT

CONTRACT = REPO_ROOT / "specs/006-mcp-server/contracts/tools.md"
ROW = re.compile(r"^\|\s*`(?P<name>[a-z_]+)`\s*\|")


@dataclass(frozen=True)
class Row:
    read_only: bool
    destructive: bool
    idempotent: bool
    hidden: bool


def contract_rows() -> dict[str, Row]:
    text = CONTRACT.read_text(encoding="utf-8")
    section = text.split("## Tools", 1)[1].split("### Values", 1)[0]
    rows: dict[str, Row] = {}
    for line in section.splitlines():
        match = ROW.match(line)
        if match is None:
            continue
        cells = [c.strip() for c in line.replace(r"\|", "/").strip().strip("|").split("|")]
        ro, d, i, listing = cells[4], cells[5], cells[6], cells[7]
        rows[match["name"]] = Row(
            read_only=ro.startswith("✓"),
            destructive=d.startswith("✓"),
            idempotent=i.startswith("✓"),
            hidden=listing == "hidden",
        )
    return rows


ROWS = contract_rows()
WRITES = {name for name, row in ROWS.items() if row.hidden}


def test_the_contract_table_is_parsed() -> None:
    assert len(ROWS) == 21  # spec 007 adds export, copy, swap, import
    assert WRITES == {
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
    }


MILESTONE_TOOLS = set(ROWS)
"""Tools that exist so far: every tool of the contract (milestone 3)."""


async def test_annotations_equal_the_contract(tmp_path) -> None:
    async with open_harness(options(tmp_path), CountingFactory()) as h:
        listed = {t.name: t for t in (await h.client.list_tools()).tools}
    assert MILESTONE_TOOLS <= set(listed) <= set(ROWS)
    for name, tool in listed.items():
        row = ROWS[name]
        hints = tool.annotations
        assert hints is not None, name
        assert hints.read_only_hint is row.read_only, name
        assert hints.destructive_hint is row.destructive, name
        assert hints.idempotent_hint is row.idempotent, name
        assert hints.open_world_hint is False, name


async def test_read_only_hides_the_write_tools(tmp_path) -> None:
    async with open_harness(options(tmp_path, read_only=True), CountingFactory()) as h:
        listed = {t.name for t in (await h.client.list_tools()).tools}
    assert listed == MILESTONE_TOOLS - WRITES
    assert not listed & WRITES


@pytest.mark.parametrize("name", sorted(MILESTONE_TOOLS & WRITES))
async def test_read_only_write_tool_cannot_be_called(tmp_path, name) -> None:
    factory = CountingFactory()
    async with open_harness(options(tmp_path, read_only=True), factory) as h:
        result = await h.call(name, {})
    assert result.is_error
    assert factory.calls == 0


async def test_status_reports_read_only(tmp_path) -> None:
    async with open_harness(options(tmp_path, read_only=True), CountingFactory()) as h:
        status = await h.ok("pedal_status")
    assert status["options"]["read_only"] is True
