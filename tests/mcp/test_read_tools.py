"""Read tools: results equal the CLI's ``--json`` documents (spec 006 US1, SC-007)."""

from __future__ import annotations

import asyncio
import json

import pytest

from openvave.cli import main
from openvave.transport.fake import FakeTransport
from tests.mcp.conftest import PEDAL, CountingFactory, open_harness, options
from tests.support import choice as ch
from tests.support.captures import FW96_CONNECT, QUERY, load_capture
from tests.support.mutations import with_payload
from tests.support.write_fixture import NORMAL, TUNER, make_fake

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


# -- preset_read (T017) -------------------------------------------------------------------------

KNOB_KEYS = ("knob_type", "knob_position")


def normal_pedal() -> FakeTransport:
    return make_fake(NORMAL, status=bytes([0]))


def without_knob_keys(document: dict) -> dict:
    """The document with the MCP's additive typed-knob keys removed (CLI parity)."""
    copy = json.loads(json.dumps(document))
    for field in copy.get("preset", copy.get("region", {})).get("fields", []):
        for key in KNOB_KEYS:
            field.pop(key, None)
    return copy


@pytest.fixture
def _fast(monkeypatch: pytest.MonkeyPatch) -> None:
    ch.no_waits(monkeypatch)


async def test_preset_read_current_equals_preset_dump(
    tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    expected = await cli_json(capsys, ["preset", "dump"], normal_pedal())
    async with open_harness(options(tmp_path), CountingFactory(make=normal_pedal)) as h:
        result = await h.ok("preset_read")
        again = await h.ok("preset_read", {"region": "current"})
    assert strip(without_knob_keys(result)) == strip(expected)
    assert strip(again) == strip(result)
    assert result["pedal_state"] == expected["pedal_state"]
    assert result["summary"]


async def test_preset_read_typed_knobs_carry_type_and_position(tmp_path) -> None:
    async with open_harness(options(tmp_path), CountingFactory(make=normal_pedal)) as h:
        result = await h.ok("preset_read")
    fields = {f["name"]: f for f in result["preset"]["fields"]}
    assert fields["reverb_decay"]["knob_type"] == "room"
    assert fields["reverb_decay"]["knob_position"] == 6
    assert fields["mod_fx"]["knob_type"] == "chorus"
    assert fields["mod_fx"]["knob_position"] == 1
    assert "knob_type" not in fields["gain"]


async def test_preset_read_names_amp_type_and_ir_cab(tmp_path) -> None:
    """Spec 007 US4: the CLI's ``position_name`` key reaches the MCP result."""
    from openvave.protocol.names import position_name

    async with open_harness(options(tmp_path), CountingFactory(make=normal_pedal)) as h:
        result = await h.ok("preset_read")
    fields = {f["name"]: f for f in result["preset"]["fields"]}
    for name in ("amp_type", "ir_cab"):
        expected = position_name(name, fields[name]["value"])
        got = fields[name]["position_name"]
        assert (got and got["text"]) == (expected and expected.text)
    assert "position_name" not in fields["gain"]


@pytest.mark.parametrize("region", ["global", "status"])
async def test_preset_read_other_regions_equal_info_regions(
    tmp_path, capsys: pytest.CaptureFixture[str], region: str
) -> None:
    info = await cli_json(capsys, ["info"], FakeTransport.from_capture(FW96_CONNECT))
    async with open_harness(options(tmp_path), CountingFactory()) as h:
        result = await h.ok("preset_read", {"region": region})
    assert result["region"] == info["regions"][region]
    assert result["identity"] == info["identity"]
    assert result["pedal_state"] == info["pedal_state"]
    assert result["summary"]


@pytest.mark.usefixtures("_fast")
async def test_preset_read_bypassed_reports_the_state(tmp_path) -> None:
    def bypassed() -> FakeTransport:
        return make_fake(NORMAL, glob=bytes([0, 0, 0xFF, 1]), buffer=bytes(21), status=bytes([0]))

    async with open_harness(options(tmp_path), CountingFactory(make=bypassed)) as h:
        result = await h.ok("preset_read")
    assert result["pedal_state"].startswith("bypass")
    assert "bypass" in result["summary"]


async def test_preset_read_tuner_reports_the_state(tmp_path) -> None:
    def tuner() -> FakeTransport:
        return make_fake(TUNER, status=bytes([0]))

    async with open_harness(options(tmp_path), CountingFactory(make=tuner)) as h:
        result = await h.ok("preset_read")
    assert result["pedal_state"].startswith("tuner")
    assert "tuner" in result["summary"]


async def test_preset_read_unknown_region_is_invalid_value(tmp_path) -> None:
    factory = CountingFactory()
    async with open_harness(options(tmp_path), factory) as h:
        text = await h.error("preset_read", {"region": "device_info"})
    assert text.startswith("invalid_value: ")
    assert "current, global, status" in text
    assert factory.calls == 0
