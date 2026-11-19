"""The documented library snippet runs against FakeTransport (T045, US4).

The snippet is extracted from contracts/library-api.md at test time, so the documentation cannot
drift from the code without this test failing.
"""

from __future__ import annotations

import asyncio
import logging
import os
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


# -- spec 005 library examples (T051) ---------------------------------------------------------

CONTRACT_005 = REPO / "specs" / "005-device-selection" / "contracts" / "library-api.md"
A = "AA:BB:CC:DD:EE:01"
B = "AA:BB:CC:DD:EE:02"


def contract_005_block(heading: str) -> str:
    """The first python block under ``## <heading>`` of the 005 library contract."""
    text = CONTRACT_005.read_text(encoding="utf-8")
    section = text[text.index(f"## {heading}\n") :]
    block = re.search(r"```python\n(.*?)```", section, re.S)
    assert block is not None, f"no python block under {heading!r}"
    return block.group(1)


async def test_005_known_pedals_example(tmp_path: Path) -> None:
    # "Known pedals": the same calls, with made-up identifiers instead of the "…" placeholders
    path = tmp_path / "devices.json"
    known = openvave.KnownDevices.load(path)
    assert known.devices == ()
    known = known.select(A, nickname="stage")
    known = known.rename("stage", "live")
    known = known.select(B, nickname="home")
    known = known.forget()
    assert known.default is None
    known = known.forget("live")
    known.save()
    again = openvave.KnownDevices.load(path)
    assert again == known
    assert again.find("home") is not None
    assert again.find("live") is None
    assert openvave.default_config_path() == Path(os.environ["OPENVAVE_CONFIG"])


async def test_005_choosing_and_connecting_example(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # "Choosing and connecting": every connect form against fake pedals
    targets: list[object] = []

    async def open_ble(target: object, scan_timeout: float, **_: object) -> Any:
        from dataclasses import replace

        from tests.support.write_fixture import make_fake

        targets.append(target)
        if isinstance(target, str):
            target = openvave.Target(target, None, "device_option")
        if target is None:
            info = openvave.DeviceInfo(A, "TANK-Gv2_BLE", -50, None, "only_one_found")
        else:
            assert isinstance(target, openvave.Target)
            info = replace(
                openvave.DeviceInfo(target.identifier, "TANK-Gv2_BLE", -50),
                nickname=target.nickname,
                chosen_by=target.chosen_by,
            )
        return make_fake(), info

    monkeypatch.setattr("openvave.transport.ble.open_ble", open_ble)
    known = openvave.KnownDevices.load(tmp_path / "devices.json")
    known = known.select(B, nickname="home").select(A, nickname="stage")
    known.save()
    monkeypatch.setenv("OPENVAVE_CONFIG", str(known.path))

    target = openvave.resolve_target(option=None, environment=None, known=known)
    assert target == openvave.Target(A, "stage", "selected")
    seen: list[tuple[str | None, str | None]] = []
    for pedal in (
        openvave.TankG.connect(),
        openvave.TankG.connect(B),
        openvave.TankG.connect(known.find("home")),
        openvave.TankG.connect(target),
        openvave.TankG.connect_selected(),
    ):
        async with pedal:
            assert pedal.device is not None
            seen.append((pedal.device.nickname, pedal.device.chosen_by))
    assert seen == [
        (None, "only_one_found"),
        (None, "device_option"),
        ("home", "device_option"),
        ("stage", "selected"),
        ("stage", "selected"),
    ]
    assert targets[0] is None


async def test_005_long_lived_connection_example() -> None:
    # "Long-lived connection": the contract's code verbatim, over a fake instead of BLE
    from tests.support.write_fixture import make_fake, writes

    code = contract_005_block("Long-lived connection")
    assert "openvave.TankG.connect_selected()" in code
    assert "while running:" in code
    code = code.replace("openvave.TankG.connect_selected()", "openvave.TankG.over(fake)")
    code = code.replace("while running:", "for value in values:")
    code = code.replace('set_field("gain", value)', 'set_field("gain", value, experimental=True)')
    fake = make_fake()
    namespace: dict[str, Any] = {"openvave": openvave, "fake": fake, "values": [70, 80, 90]}
    source = "async def __example__():\n" + textwrap.indent(code, "    ") + "\n    return pedal\n"
    exec(compile(source, str(CONTRACT_005), "exec"), namespace)
    pedal = await namespace["__example__"]()
    assert pedal.is_connected is False
    assert fake.closed
    assert sum(1 for f in fake.sent if f == QUERY_FRAME) == 1  # one connection, one handshake
    assert len(writes(fake)) == 3
