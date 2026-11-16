"""The documented library snippet runs against FakeTransport (T045, US4).

The snippet is extracted from contracts/library-api.md at test time, so the documentation cannot
drift from the code without this test failing.
"""

from __future__ import annotations

import asyncio
import logging
import re
import textwrap
from pathlib import Path
from typing import Any

import pytest

import openvave

REPO = Path(__file__).resolve().parents[2]
CONTRACT = REPO / "specs" / "001-readonly-ble-connection" / "contracts" / "library-api.md"
FAKE_SECTION = "# Session over any transport"

QUERY_FRAME = bytes.fromhex("00 59 11 00 00 00 ff")
PRESET_READ_FRAME = bytes.fromhex("00 59 23 08 00 00 04 00 00 00 10 15 00 00 d6")


def fake_snippet(body: str | None = None) -> str:
    """The ``FakeTransport`` part of the first python block, optionally with ``...`` replaced."""
    text = CONTRACT.read_text(encoding="utf-8")
    block = re.search(r"```python\n(.*?)```", text, re.S)
    assert block is not None, "no python block in library-api.md"
    code = block.group(1)
    assert FAKE_SECTION in code
    code = code[code.index(FAKE_SECTION) :]
    if body is not None:
        assert "    ...\n" in code
        code = code.replace("    ...\n", textwrap.indent(body, "    ") + "\n", 1)
    return code


async def run_snippet(code: str, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Run ``code`` as the body of an async function with ``openvave`` imported."""
    monkeypatch.chdir(REPO)  # the snippet uses a repo-relative capture path
    namespace: dict[str, Any] = {"openvave": openvave}
    indented = textwrap.indent(code, "    ")
    source = f"async def __snippet__():\n{indented}\n    return locals()\n"
    exec(compile(source, str(CONTRACT), "exec"), namespace)
    result: dict[str, Any] = await namespace["__snippet__"]()
    return result


async def test_snippet_verbatim(monkeypatch: pytest.MonkeyPatch) -> None:
    scope = await run_snippet(fake_snippet(), monkeypatch)
    fake = scope["fake"]
    assert isinstance(fake, openvave.FakeTransport)
    assert fake.sent == [QUERY_FRAME]
    assert fake.closed


async def test_snippet_reads_preset(monkeypatch: pytest.MonkeyPatch) -> None:
    body = "identity = pedal.identity\nread = await pedal.read(openvave.Region.CURRENT_PRESET)"
    scope = await run_snippet(fake_snippet(body), monkeypatch)
    assert scope["identity"].name == "TANK-Gv2"
    assert scope["identity"].firmware == 96
    assert len(scope["read"].data) == openvave.Region.CURRENT_PRESET.length
    assert scope["fake"].sent == [QUERY_FRAME, PRESET_READ_FRAME]


async def test_trace_with_handler(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG, logger="openvave.trace")
    body = "await pedal.read(openvave.Region.CURRENT_PRESET)"
    scope = await run_snippet(fake_snippet(body), monkeypatch)
    lines = [r.getMessage() for r in caplog.records if r.name == "openvave.trace"]
    tx = [line for line in lines if line.startswith("TX ")]
    rx = [line for line in lines if line.startswith("RX ") and not line.startswith("RX chunk")]
    assert tx == [f"TX {f.hex(' ')}" for f in scope["fake"].sent]
    assert len(rx) == 2


async def test_trace_silent_without_handler(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    await run_snippet(fake_snippet("await pedal.snapshot()"), monkeypatch)
    out, err = capsys.readouterr()
    assert out == ""
    assert err == ""


async def test_no_tasks_survive(monkeypatch: pytest.MonkeyPatch) -> None:
    before = asyncio.all_tasks()
    await run_snippet(fake_snippet("await pedal.snapshot()"), monkeypatch)
    await asyncio.sleep(0)
    assert asyncio.all_tasks() - before == set()
