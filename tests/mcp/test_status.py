"""``pedal_status`` (spec 006 FR-005, FR-015)."""

from __future__ import annotations

from pathlib import Path

from tests.mcp.conftest import CountingFactory, open_harness, options


async def test_status_before_connecting(tmp_path: Path, factory: CountingFactory) -> None:
    async with open_harness(options(tmp_path), factory) as harness:
        status = await harness.ok("pedal_status")
        assert status["connected"] is False
        assert status["pedal"] is None
        assert status["firmware"] is None
        assert status["summary"].startswith("not connected")
        opts = status["options"]
        assert opts["read_only"] is False
        assert opts["idle_release"] == 300.0
        assert opts["backup_dir"].endswith("backups")


async def test_status_after_connecting(tmp_path: Path, factory: CountingFactory) -> None:
    async with open_harness(options(tmp_path), factory) as harness:
        await harness.ok("pedal_info")
        status = await harness.ok("pedal_status")
        assert status["connected"] is True
        assert status["pedal"]["identifier"] == "AA:BB:CC:DD:EE:01"
        assert status["pedal"]["chosen_by"] == "only_one_found"
        assert status["firmware"] == 96
        assert status["firmware_untested"] is False
        assert status["since"] is not None
        assert status["last_error"] is None
        assert "firmware 96" in status["summary"]
