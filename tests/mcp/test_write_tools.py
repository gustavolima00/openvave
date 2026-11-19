"""Volatile write tools: same frames as the CLI, same refusals, dry run, partial results
(spec 006 US2, contracts/tools.md)."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any

import pytest

from openvave import session
from openvave.cli import main
from openvave.transport.fake import FakeTransport
from tests.mcp.conftest import PEDAL, CountingFactory, open_harness, options
from tests.support import storage_fixture as sf
from tests.support.write_fixture import EDIT, NORMAL, TUNER, make_fake, writes

BYPASSED = bytes([0, 0, 0xFF, NORMAL])
P = sf.PUBLIC_PRESET
EDITED = P[:6] + bytes([90]) + P[7:]
VOLATILE = ("read_at", "summary", "reminder")


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    async def instant(_: float) -> None:
        return None

    monkeypatch.setattr(session, "SELECT_SLEEP", instant)


def cli_run_sync(
    capsys: pytest.CaptureFixture[str], argv: list[str], fake: FakeTransport
) -> tuple[int, Any]:
    async def factory(target, scan_timeout):  # type: ignore[no-untyped-def]
        return fake, PEDAL

    code = main([*argv, "--json"], transport_factory=factory)
    out = capsys.readouterr().out
    return code, json.loads(out) if out.strip() else None


async def cli_run(
    capsys: pytest.CaptureFixture[str], argv: list[str], fake: FakeTransport
) -> tuple[int, Any]:
    """The CLI's exit code and ``--json`` document (it runs its own loop, so in a thread)."""
    return await asyncio.to_thread(cli_run_sync, capsys, argv, fake)


def strip(document: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in document.items() if k not in VOLATILE}


def factory_of(make: Callable[[], FakeTransport]) -> CountingFactory:
    return CountingFactory(make=make)


PARITY = [
    # (tool, arguments, CLI argv, fake)
    (
        "pedal_set",
        {"changes": {"gain": 95, "treble": "58", "reverb_decay": "room:18"}},
        ["set", "gain=95", "treble=58", "reverb_decay=room:18"],
        lambda: make_fake(NORMAL),
    ),
    (
        "pedal_set",
        {"changes": {"delay_on": True, "led_colour": "#2040ff"}, "experimental": True},
        ["set", "delay_on=on", "led_colour=#2040ff", "--experimental"],
        lambda: make_fake(NORMAL),
    ),
    (
        "preset_select",
        {"position": "2C"},
        ["preset", "select", "2C"],
        lambda: make_fake(NORMAL),
    ),
    ("preset_select", {"position": 6}, ["preset", "select", "6"], lambda: make_fake(NORMAL)),
    (
        "preset_select",
        {"position": "2C", "discard_edits": True},
        ["preset", "select", "2C", "--discard-edits"],
        lambda: make_fake(EDIT),
    ),
    (
        "preset_reload",
        {"discard_edits": True},
        ["preset", "reload", "--discard-edits"],
        lambda: make_fake(EDIT, buffer=EDITED),
    ),
    ("preset_reload", {}, ["preset", "reload"], lambda: make_fake(NORMAL, buffer=EDITED)),
    ("bypass_on", {}, ["bypass", "on"], lambda: make_fake(NORMAL)),
    (
        "bypass_off",
        {"position": "1B"},
        ["bypass", "off", "1B"],
        lambda: make_fake(NORMAL, buffer=bytes(21), glob=BYPASSED),
    ),
    (
        "loopback",
        {"on": False, "experimental": True},
        ["loopback", "off", "--experimental"],
        lambda: make_fake(NORMAL, status=b"\x01"),
    ),
]


@pytest.mark.parametrize(("tool", "args", "argv", "make"), PARITY)
async def test_frames_and_document_equal_the_cli(
    tmp_path, capsys: pytest.CaptureFixture[str], tool, args, argv, make
) -> None:
    cli_fake = make()
    code, expected = await cli_run(capsys, argv, cli_fake)
    assert code == 0
    async with open_harness(options(tmp_path), factory_of(make)) as h:
        result = await h.ok(tool, args)
        fake = h.factory.fake
    assert writes(fake) == writes(cli_fake)
    assert strip(result) == strip(expected)
    assert result["summary"]
    assert result["reminder"]


@pytest.mark.parametrize(("tool", "args", "argv", "make"), PARITY)
async def test_dry_run_sends_nothing(
    tmp_path, capsys: pytest.CaptureFixture[str], tool, args, argv, make
) -> None:
    cli_fake = make()
    code, expected = await cli_run(capsys, [*argv, "--dry-run"], cli_fake)
    assert code == 0
    async with open_harness(options(tmp_path), factory_of(make)) as h:
        result = await h.ok(tool, {**args, "dry_run": True})
        fake = h.factory.fake
    assert writes(fake) == [] == writes(cli_fake)
    assert strip(result) == strip(expected)
    assert result["plan"]["dry_run"] is True
    assert "result" not in result
    assert "dry run" in result["summary"]


async def test_set_observed_field_needs_experimental(tmp_path) -> None:
    async with open_harness(options(tmp_path), factory_of(lambda: make_fake(NORMAL))) as h:
        text = await h.error("pedal_set", {"changes": {"delay_on": "on"}})
        assert text.startswith("experimental_required: ")
        assert writes(h.factory.fake) == []
        result = await h.ok("pedal_set", {"changes": {"delay_on": "on"}, "experimental": True})
    assert result["result"]["applied"] is True


@pytest.mark.parametrize(
    ("changes", "kind"),
    [
        ({"volume_knob": 3}, "unknown_field"),
        ({"gain": "loud"}, "invalid_value"),
        ({"gain": 1.5}, "invalid_value"),
        ({"amp_on": "maybe"}, "invalid_value"),
        ({"led_colour": "red"}, "invalid_value"),
        ({}, "invalid_value"),
    ],
)
async def test_set_bad_input_is_refused_before_any_frame(tmp_path, changes, kind) -> None:
    factory = factory_of(lambda: make_fake(NORMAL))
    async with open_harness(options(tmp_path), factory) as h:
        text = await h.error("pedal_set", {"changes": changes})
    assert text.startswith(f"{kind}: ")
    assert factory.calls == 0  # refused before connecting


async def test_set_unknown_field_names_the_writable_fields(tmp_path) -> None:
    async with open_harness(options(tmp_path), factory_of(lambda: make_fake(NORMAL))) as h:
        text = await h.error("pedal_set", {"changes": {"volume_knob": 3}})
    assert "gain" in text and "openvave://fields" in text


@pytest.mark.parametrize(
    ("make", "kind"),
    [
        (lambda: make_fake(TUNER), "tuner_mode"),
        (lambda: make_fake(NORMAL, buffer=bytes(21), glob=BYPASSED), "bypassed"),
    ],
)
async def test_set_refused_by_state(tmp_path, make, kind) -> None:
    async with open_harness(options(tmp_path), factory_of(make)) as h:
        text = await h.error("pedal_set", {"changes": {"gain": 90}})
        assert text.startswith(f"{kind}: ")
        assert writes(h.factory.fake) == []


async def test_set_numbers_and_booleans_become_cli_text(tmp_path) -> None:
    async with open_harness(options(tmp_path), factory_of(lambda: make_fake(NORMAL))) as h:
        result = await h.ok(
            "pedal_set",
            {"changes": {"gain": 90.0, "amp_on": False}, "experimental": True, "dry_run": True},
        )
    fields = {f["field"]: f for f in result["plan"]["fields"]}
    assert fields["gain"]["requested"] == "5a"
    assert fields["amp_on"]["requested"] == "00"


async def test_set_mid_batch_nak_carries_the_partial_document(
    tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    def make() -> FakeTransport:
        return make_fake(NORMAL, faults={"block_switch": "nak"})

    argv = ["set", "gain=95", "delay_on=on", "led_colour=#2040ff", "--experimental"]
    code, expected = await cli_run(capsys, argv, make())
    assert code != 0
    async with open_harness(options(tmp_path), factory_of(make)) as h:
        text = await h.error(
            "pedal_set",
            {
                "changes": {"gain": 95, "delay_on": "on", "led_colour": "#2040ff"},
                "experimental": True,
            },
        )
    assert text.startswith("write_nak: ")
    partial = next(line for line in text.splitlines() if line.startswith("partial: "))
    document = json.loads(partial.removeprefix("partial: "))
    assert strip(document) == strip(expected)
    assert [w["status"] for w in document["result"]["writes"]] == ["acked", "nak", "not_sent"]


async def test_set_reminder_in_normal_and_edit_mode(tmp_path) -> None:
    async with open_harness(options(tmp_path), factory_of(lambda: make_fake(NORMAL))) as h:
        normal = await h.ok("pedal_set", {"changes": {"gain": 90}})
    async with open_harness(options(tmp_path), factory_of(lambda: make_fake(EDIT))) as h:
        edit = await h.ok("pedal_set", {"changes": {"gain": 90}})
    assert normal["reminder"] == "not saved; discard with preset_reload"
    assert edit["reminder"] == "not saved; discard with preset_reload and discard_edits: true"


async def test_select_unsaved_edits_need_discard_edits(tmp_path) -> None:
    async with open_harness(options(tmp_path), factory_of(lambda: make_fake(EDIT))) as h:
        text = await h.error("preset_select", {"position": "2C"})
        assert text.startswith("edits_would_be_discarded: ")
        assert writes(h.factory.fake) == []


@pytest.mark.parametrize("position", ["10A", "1E", "36", "-1", "x", 36, -1])
async def test_select_invalid_position(tmp_path, position) -> None:
    factory = factory_of(lambda: make_fake(NORMAL))
    async with open_harness(options(tmp_path), factory) as h:
        text = await h.error("preset_select", {"position": position})
    assert text.startswith("invalid_value: ")
    assert factory.calls == 0


async def test_reload_refused_when_bypassed(tmp_path) -> None:
    make = lambda: make_fake(NORMAL, buffer=bytes(21), glob=BYPASSED)  # noqa: E731
    async with open_harness(options(tmp_path), factory_of(make)) as h:
        text = await h.error("preset_reload", {})
        assert text.startswith("bypassed: ")
        assert writes(h.factory.fake) == []


async def test_bypass_off_returns_to_the_position_bypass_on_reported(tmp_path) -> None:
    async with open_harness(options(tmp_path), factory_of(lambda: make_fake(NORMAL))) as h:
        on = await h.ok("bypass_on", {})
        assert on["result"]["return_position"] == "1B"
        assert "1B" in on["reminder"]
        assert h.holder.bypass_return == 1
        status = await h.ok("pedal_status")
        assert status["bypass_return"] == 1
        off = await h.ok("bypass_off", {})
        frames = writes(h.factory.fake)
    assert off["plan"]["target"]["argument"] == 1
    assert frames[-1] == bytes.fromhex("00 59 22 09 00 00 04 01 00 00 e0 01 00 00 01 18")
    assert h.holder.bypass_return is None


async def test_bypass_off_dry_run_keeps_the_return_position(tmp_path) -> None:
    async with open_harness(options(tmp_path), factory_of(lambda: make_fake(NORMAL))) as h:
        await h.ok("bypass_on", {})
        await h.ok("bypass_off", {"dry_run": True})
        assert h.holder.bypass_return == 1


async def test_bypass_on_dry_run_stores_nothing(tmp_path) -> None:
    async with open_harness(options(tmp_path), factory_of(lambda: make_fake(NORMAL))) as h:
        await h.ok("bypass_on", {"dry_run": True})
        assert h.holder.bypass_return is None


async def test_bypass_off_without_position_names_the_bank(tmp_path) -> None:
    make = lambda: make_fake(NORMAL, buffer=bytes(21), glob=bytes([2, 2, 0xFF, NORMAL]))  # noqa: E731
    async with open_harness(options(tmp_path), factory_of(make)) as h:
        text = await h.error("bypass_off", {})
        assert writes(h.factory.fake) == []
    assert text.startswith("invalid_value: ")
    assert "bank 3" in text and "3A" in text


async def test_bypass_off_without_position_when_not_bypassed(tmp_path) -> None:
    async with open_harness(options(tmp_path), factory_of(lambda: make_fake(NORMAL))) as h:
        text = await h.error("bypass_off", {})
    assert text.startswith("invalid_value: ")
    assert "not bypassed" in text and "preset_select" in text


async def test_bypass_off_refused_when_not_bypassed(tmp_path) -> None:
    async with open_harness(options(tmp_path), factory_of(lambda: make_fake(NORMAL))) as h:
        text = await h.error("bypass_off", {"position": "1B"})
        assert text.startswith("not_bypassed: ")
        assert writes(h.factory.fake) == []


async def test_loopback_needs_experimental(tmp_path) -> None:
    make = lambda: make_fake(NORMAL, status=b"\x00")  # noqa: E731
    async with open_harness(options(tmp_path), factory_of(make)) as h:
        text = await h.error("loopback", {"on": True})
        assert text.startswith("experimental_required: ")
        assert writes(h.factory.fake) == []
        result = await h.ok("loopback", {"on": True, "experimental": True})
    assert result["command"] == "loopback on"
    assert result["result"]["applied"] is True


async def test_loopback_already_set_sends_nothing(tmp_path) -> None:
    make = lambda: make_fake(NORMAL, status=b"\x01")  # noqa: E731
    async with open_harness(options(tmp_path), factory_of(make)) as h:
        result = await h.ok("loopback", {"on": True, "experimental": True})
        assert writes(h.factory.fake) == []
    assert result["plan"]["no_change"] is True
    assert "already" in result["summary"]


async def test_writes_share_the_held_connection(tmp_path) -> None:
    factory = factory_of(lambda: make_fake(NORMAL))
    async with open_harness(options(tmp_path), factory) as h:
        await h.ok("pedal_set", {"changes": {"gain": 90}})
        await h.ok("preset_reload", {})
        await h.ok("preset_read")
    assert factory.calls == 1
