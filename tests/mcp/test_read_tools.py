"""Read tools: results equal the CLI's ``--json`` documents (spec 006 US1, SC-007)."""

from __future__ import annotations

import asyncio
import json

import pytest

from openvave.cli import main
from openvave.transport.fake import FakeTransport
from tests.mcp.conftest import PEDAL, CountingFactory, open_harness, options
from tests.support.captures import FW96_CONNECT, QUERY, load_capture
from tests.support.mutations import with_payload

VOLATILE = ("read_at",)


def cli_json_sync(capsys: pytest.CaptureFixture[str], argv: list[str], fake: FakeTransport) -> dict:
    async def factory(target, scan_timeout):  # type: ignore[no-untyped-def]
        return fake, PEDAL

    assert main([*argv, "--json"], transport_factory=factory) == 0
    return json.loads(capsys.readouterr().out)


async def cli_json(
    capsys: pytest.CaptureFixture[str], argv: list[str], fake: FakeTransport
) -> dict:
    """The CLI's document (it runs its own event loop, so in a thread)."""
    return await asyncio.to_thread(cli_json_sync, capsys, argv, fake)


def strip(document: dict) -> dict:
    return {k: v for k, v in document.items() if k not in (*VOLATILE, "summary")}


async def test_info_equals_cli_json(tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    expected = await cli_json(capsys, ["info"], FakeTransport.from_capture(FW96_CONNECT))
    async with open_harness(options(tmp_path), CountingFactory()) as h:
        result = await h.ok("pedal_info")
    assert strip(result) == strip(expected)
    assert result["summary"].startswith("TANK-Gv2, firmware 96, ")


async def test_info_untested_firmware(tmp_path) -> None:
    cap = load_capture(FW96_CONNECT)
    reply = with_payload(cap.rx(QUERY), b"TANK-Gv2_097".ljust(27, b"\x00"))

    def make() -> FakeTransport:
        return FakeTransport.from_capture(FW96_CONNECT, replies={QUERY: reply})

    async with open_harness(options(tmp_path), CountingFactory(make=make)) as h:
        result = await h.ok("pedal_info")
    assert result["identity"]["firmware_untested"] is True
    assert "untested firmware" in result["summary"]
