"""``openvave mcp`` (spec 006 FR-001, FR-002, FR-004, contracts/tools.md §Command)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from mcp import Client, StdioServerParameters

from openvave.cli import main
from openvave.cli import mcp as mcp_command
from tests.mcp.conftest import CountingFactory, open_harness, options


def test_help_lists_the_options(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["mcp", "--help"]) == 0
    out = capsys.readouterr().out
    for option in ("--read-only", "--backup-dir", "--idle-release", "--device", "--trace"):
        assert option in out


def test_negative_idle_release_is_a_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["mcp", "--idle-release", "-1"]) == 2
    assert "must be 0 or more" in capsys.readouterr().err


def test_missing_extra_exits_2_with_the_hint(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in [m for m in sys.modules if m == "mcp" or m.startswith(("mcp.", "openvave.mcp_"))]:
        monkeypatch.delitem(sys.modules, name)
    monkeypatch.setitem(sys.modules, "mcp", None)  # import mcp → ImportError
    assert main(["mcp"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.strip() == mcp_command.INSTALL_HINT


def test_options_reach_the_server(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    seen: list[object] = []

    async def fake_serve(options, factory, scanner_factory=None):  # type: ignore[no-untyped-def]
        seen.append(options)
        return 0

    import openvave.mcp_server as mcp_server

    monkeypatch.setattr(mcp_server, "serve", fake_serve)
    argv = [
        "mcp",
        "--read-only",
        "--backup-dir",
        str(tmp_path),
        "--idle-release",
        "30",
        "--device",
        "stage",
        "--scan-timeout",
        "7",
    ]
    assert main(argv) == 0
    (options,) = seen
    assert options.read_only is True  # type: ignore[attr-defined]
    assert options.backup_dir == tmp_path  # type: ignore[attr-defined]
    assert options.idle_release == 30.0  # type: ignore[attr-defined]
    assert options.device == "stage"  # type: ignore[attr-defined]
    assert options.scan_timeout == 7.0  # type: ignore[attr-defined]


def test_default_backup_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    assert mcp_command.default_backup_dir() == tmp_path / "data" / "openvave" / "backups"
    monkeypatch.delenv("XDG_DATA_HOME")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    if sys.platform != "win32":
        expected = tmp_path / "home" / ".local" / "share" / "openvave" / "backups"
        assert mcp_command.default_backup_dir() == expected


async def test_tool_calls_print_nothing_on_stdout(
    tmp_path: Path, factory: CountingFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    async with open_harness(options(tmp_path), factory) as harness:
        await harness.ok("pedal_info")
        await harness.ok("pedal_status")
        await harness.call("nope")
    assert capsys.readouterr().out == ""


async def test_stdio_smoke(tmp_path: Path) -> None:
    """The real command over stdio lists its tools and resources, answers pedal_status and
    backups_list, and reads a resource (no pedal)."""
    env = {**os.environ, "OPENVAVE_CONFIG": str(tmp_path / "devices.json")}
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "openvave", "mcp", "--backup-dir", str(tmp_path)],
        env=env,
    )
    async with Client(params) as client:
        tools = {t.name for t in (await client.list_tools()).tools}
        assert {
            "pedal_status",
            "pedal_disconnect",
            "pedal_scan",
            "pedal_select",
            "pedal_info",
            "preset_read",
            "pedal_changes",
            "preset_backup",
            "backups_list",
        } <= tools
        result = await client.call_tool("pedal_status", {})
        assert not result.is_error
        assert result.structured_content["connected"] is False
        listed = await client.call_tool("backups_list", {})
        assert not listed.is_error
        assert listed.structured_content["backups"] == []
        uris = {str(r.uri) for r in (await client.list_resources()).resources}
        assert uris == {
            "openvave://fields",
            "openvave://effect-types",
            "openvave://byte-map",
            "openvave://safety",
        }
        fields = await client.read_resource("openvave://fields")
        assert "reverb_decay" in getattr(fields.contents[0], "text", "")
