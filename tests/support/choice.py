"""Helpers for the spec 005 Milestone 2 tests: every pedal command, run through the real choice.

``choosing_factory`` goes through :func:`openvave.transport.ble.locate` with a fake scanner, so the
target resolution, the early stop, ``TargetNotFoundError`` and the 0.4.0 rules are the real ones;
only the transport is a :class:`FakeTransport` per identifier. ``opened`` records every
identifier a transport was built for (SC-004: never one other than the chosen pedal).
Identifiers are made up (Constitution VI).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import pytest

from openvave.cli import main
from openvave.devices import Target
from openvave.models import DeviceInfo
from openvave.transport import Transport, ble
from openvave.transport.fake import FakeTransport
from tests.support import restore_fixture as rf
from tests.support.captures import FW96_CONNECT
from tests.support.scanner import Advert, fake_scanner
from tests.support.watch import FakeClock, ScriptedStdin
from tests.support.write_fixture import NORMAL, make_fake

FAST = ["--scan-timeout", "0.05"]
"""Every fake advertisement comes at 0.01 s; a target that is absent costs 0.05 s."""


def pedal(command: str = "info") -> FakeTransport:
    """A fake pedal for ``command`` (an id of :data:`COMMAND_IDS`). ``info`` reads the identity
    regions of the fw96 capture; every other command gets a pedal in normal mode on 1B with a
    stored image, the status byte and writes applied (some commands refuse, which is fine: the
    choice happens before)."""
    if command == "info":
        return FakeTransport.from_capture(FW96_CONNECT)
    return make_fake(NORMAL, status=bytes([0]))


class Pedals:
    """Fake pedals in range, the transports built, and the factory for ``main``."""

    def __init__(self, adverts: Sequence[Advert], command: str = "info") -> None:
        self.adverts = list(adverts)
        self.command = command
        self.opened: list[str] = []
        self.fakes: dict[str, FakeTransport] = {}

    async def factory(self, target: Target | None, scan_timeout: float) -> tuple[Transport, Any]:
        _, device = await ble.locate(target, scan_timeout, scanner_factory=self.scanner())
        self.opened.append(device.identifier)
        fake = self.fakes.setdefault(device.identifier, pedal(self.command))
        return fake, device

    def scanner(self) -> Callable[..., Any]:
        return fake_scanner(self.adverts)


def run(
    capsys: pytest.CaptureFixture[str],
    argv: Sequence[str],
    pedals: Pedals,
) -> tuple[int, str, str]:
    code = main(
        [*argv, *FAST],
        transport_factory=pedals.factory,
        scanner_factory=pedals.scanner(),
        stdin=ScriptedStdin(()),
        clock=FakeClock(),
    )
    out, err = capsys.readouterr()
    return code, out, err


def command_argvs(tmp_path: Path) -> dict[str, list[str]]:
    """Every pedal command (``COMMANDS`` and ``watch``), by a readable id."""
    restore = tmp_path / "restore-from.json"
    restore.write_text(json.dumps(rf.document()), encoding="utf-8")
    backup_dir = tmp_path / "auto"
    backup_dir.mkdir(exist_ok=True)
    unsafe = ["--unsafe", "--dry-run", "--backup-dir", str(backup_dir)]
    return {
        "info": ["info"],
        "preset dump": ["preset", "dump"],
        "preset backup": ["preset", "backup", "--output", str(tmp_path / "b.json"), "--force"],
        "preset select": ["preset", "select", "1C"],
        "preset reload": ["preset", "reload"],
        "preset save --dry-run": ["preset", "save", "--to", "1C", *unsafe],
        "preset restore --dry-run": ["preset", "restore", str(restore), "--all", *unsafe],
        "set": ["set", "gain", "90"],
        "set FIELD=VALUE": ["set", "gain=90", "treble=58"],
        "bypass on": ["bypass", "on"],
        "bypass off": ["bypass", "off", "1B"],
        "loopback on": ["loopback", "on", "--experimental"],
        "loopback off": ["loopback", "off", "--experimental"],
        "watch": ["watch", "--duration", "1", "--no-record"],
    }


COMMAND_IDS = (
    "info",
    "preset dump",
    "preset backup",
    "preset select",
    "preset reload",
    "preset save --dry-run",
    "preset restore --dry-run",
    "set",
    "set FIELD=VALUE",
    "bypass on",
    "bypass off",
    "loopback on",
    "loopback off",
    "watch",
)
"""The ids of :func:`command_argvs`, for parametrisation."""

COVERED_TOP_LEVEL = {"info", "preset", "set", "bypass", "loopback", "watch"}
"""Top-level commands :func:`command_argvs` covers; a test fails if ``COMMANDS`` grows."""


def device_of(pedals: Pedals, identifier: str) -> DeviceInfo:
    for address, name, rssi in pedals.adverts:
        if address == identifier:
            return DeviceInfo(address, name, rssi)
    raise KeyError(identifier)


def no_waits(monkeypatch: pytest.MonkeyPatch) -> None:
    """No settle or confirmation sleeps: hundreds of fake sessions run in seconds."""

    async def no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr("openvave.session.SETTLE_DELAY", 0)
    for name in ("SEQUENCE_SLEEP", "SELECT_SLEEP", "STATE_SLEEP"):
        monkeypatch.setattr(f"openvave.session.{name}", no_sleep)
