"""``openvave scan``, ``select``, ``device`` and ``forget`` (spec 005 contracts/cli.md).

Finding pedals and managing the known pedals in ``devices.json``. ``device``, ``device rename``,
``forget`` and ``select`` with a known nickname or ``--offline`` never use Bluetooth. Every
command returns ``(stdout text, exit code)``; errors are raised as :class:`OpenvaveError` and
reported by ``openvave.cli.main``.
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from openvave.cli import render
from openvave.devices import (
    KnownDevice,
    KnownDevices,
    Target,
    check_nickname,
    default_config_path,
    is_identifier,
)
from openvave.errors import ConfigError, MultipleDevicesError, NoDeviceFoundError
from openvave.models import DeviceInfo, ScanEntry
from openvave.transport import Transport

logger = logging.getLogger("openvave")

Command = Callable[..., Awaitable[tuple[str, int]]]
TransportFactory = Callable[[Target | None, float], Awaitable[tuple[Transport, DeviceInfo | None]]]
ScannerFactory = Callable[..., Any] | None

_PREFIX = re.compile(r"^[0-9A-Fa-f:-]+$")
MIN_PREFIX_HEX = 4
"""An identifier prefix has at least this many hex digits (research R4)."""


class UsageError(Exception):
    """A combination of arguments that cannot be used (exit 2, nothing done)."""


def add_parsers(sub: Any, common: argparse.ArgumentParser) -> None:
    """The ``scan``, ``select``, ``device`` and ``forget`` subcommands."""
    scan = sub.add_parser(
        "scan",
        parents=[common],
        help="list the Tank-G pedals in range (connects to nothing)",
        description="Scans for the whole --scan-timeout and lists every Tank-G, strongest "
        "signal first; * marks the default pedal. Sends nothing unless --identify.",
    )
    scan.add_argument("--all", action="store_true", help="also list other Bluetooth advertisers")
    scan.add_argument(
        "--identify",
        action="store_true",
        help="connect to each pedal in turn and show its firmware (the handshake only)",
    )
    select = sub.add_parser(
        "select",
        parents=[common],
        help="choose the pedal commands use by default (see also: preset select)",
        description="TARGET is a known nickname, a full identifier, or an identifier prefix of "
        "at least 4 hex digits matching one pedal in range; without TARGET, the only pedal in "
        "range. Saved in the configuration file (openvave device shows where). Never prompts.",
    )
    select.add_argument("target", nargs="?", default=None, metavar="TARGET")
    select.add_argument(
        "--name", metavar="NICKNAME", default=None, help="give the pedal this nickname"
    )
    select.add_argument(
        "--offline",
        action="store_true",
        help="save a full identifier without checking that the pedal is in range",
    )
    device = sub.add_parser(
        "device",
        parents=[common],
        help="show the default pedal and the known pedals (no Bluetooth)",
        description="Shows the configuration. openvave connects for the length of one command; "
        "the default pedal is a choice, not an open connection.",
    )
    device.add_argument(
        "--check", action="store_true", help="scan for the default pedal and say if it is in range"
    )
    device_sub = device.add_subparsers(dest="action", metavar="ACTION")
    rename = device_sub.add_parser(
        "rename", parents=[common], help="change a known pedal's nickname"
    )
    rename.add_argument("old", metavar="OLD", help="its nickname or identifier")
    rename.add_argument("new", metavar="NEW", help="the new nickname")
    forget = sub.add_parser(
        "forget",
        parents=[common],
        help="clear the default pedal, or forget known pedals (no Bluetooth)",
        description="Without TARGET: clear the default (the pedal stays known). With TARGET "
        "(nickname or identifier): remove that pedal. --all: remove every known pedal; an "
        "invalid configuration file is moved aside.",
    )
    which = forget.add_mutually_exclusive_group()
    which.add_argument("target", nargs="?", default=None, metavar="TARGET")
    which.add_argument(
        "--all", dest="forget_all", action="store_true", help="forget every known pedal"
    )


def _load() -> KnownDevices:
    return KnownDevices.load(default_config_path())


async def scan(
    args: argparse.Namespace,
    scanner_factory: ScannerFactory,
    transport_factory: TransportFactory | None,
) -> tuple[str, int]:
    """``openvave scan``: exit 0 when a Tank-G is listed, 3 when none."""
    from openvave.transport import ble

    try:
        known: KnownDevices | None = _load()
    except ConfigError as err:
        print(f"warning: {err} (nicknames unavailable)", file=sys.stderr)
        known = None
    if not args.json:
        print(f"Scanning for {args.scan_timeout:g} s…", file=sys.stderr, flush=True)
    scanned_at = datetime.now(UTC)
    entries = await ble.scan(
        args.scan_timeout,
        include_all=args.all,
        known=known,
        scanner_factory=scanner_factory,
    )
    if args.identify:
        entries = await ble.identify(
            entries, timeout=args.timeout, transport_factory=_identify_factory(transport_factory)
        )
        _record_firmware(known, entries)
    found = any(e.tank_g for e in entries)
    if args.json:
        document = render.scan_json(
            entries,
            known,
            scanned_at=scanned_at,
            scan_seconds=args.scan_timeout,
            identified=args.identify,
        )
        return render.dumps(document), 0 if found else 3
    if not found:
        text = render.human_scan(entries, known, identified=args.identify)
        print(text)
        print(render.NO_TANK_G_HINT, file=sys.stderr)
        return "", 3
    return render.human_scan(entries, known, identified=args.identify), 0


def _identify_factory(
    factory: TransportFactory | None,
) -> Callable[[DeviceInfo], Awaitable[Transport]] | None:
    """The CLI's injected transport factory, adapted to :func:`identify`; ``None`` keeps the
    library's BLE default."""
    if factory is None:
        return None

    async def make(device: DeviceInfo) -> Transport:
        target = Target(device.identifier, device.nickname, "device_option")
        transport, _ = await factory(target, 0.0)
        return transport

    return make


def _record_firmware(known: KnownDevices | None, entries: list[ScanEntry]) -> None:
    """Best effort: ``last_firmware`` of known pedals that identify reached (research R7, R9)."""
    if known is None:
        return
    updated = known
    for entry in entries:
        if entry.known and entry.firmware is not None:
            updated = updated.record_seen(
                entry.device.identifier, entry.device.name, entry.firmware
            )
    if updated is known:
        return
    try:
        updated.save()
    except OSError as err:
        logger.debug("could not record last seen in %s: %s", known.path, err)


def _hex_digits(text: str) -> str:
    return re.sub(r"[:-]", "", text).casefold()


async def resolve_selection(
    target: str | None,
    known: KnownDevices | None,
    scan_timeout: float,
    scanner_factory: ScannerFactory,
    *,
    offline: bool = False,
) -> tuple[str, str | None, int | None]:
    """``(identifier, advertised name, rssi)`` of the pedal ``target`` names (research R4):
    a known nickname (no scan), a full identifier (checked by a scan unless ``offline``), an
    identifier prefix of at least :data:`MIN_PREFIX_HEX` hex digits matching one pedal in range,
    or ``None`` for the only pedal in range. Shared by ``openvave select`` and the MCP server's
    ``pedal_select``; ``known`` may be ``None`` (invalid file) when ``target`` is an identifier."""
    from openvave.transport import ble

    chosen = (
        _nickname_match(known, target)
        if known is not None and target is not None and not is_identifier(target)
        else None
    )
    if chosen is not None:
        return chosen.identifier, chosen.last_name, None
    if target is not None and is_identifier(target):
        if offline:
            return target, None, None
        seen = await ble.seek(target, scan_timeout, scanner_factory=scanner_factory)
        device = next((d for d in seen if d.identifier.casefold() == target.casefold()), None)
        if device is None:
            raise NoDeviceFoundError(f"device {target} not found")
        return device.identifier, device.name, device.rssi
    if target is not None:
        if not _PREFIX.match(target) or len(_hex_digits(target)) < MIN_PREFIX_HEX:
            nicknames = ", ".join(known.nicknames) if known is not None else ""
            raise ConfigError(
                f"{target!r} is not a known nickname, an identifier or a prefix of at least "
                f"{MIN_PREFIX_HEX} hex digits; known nicknames: {nicknames or 'none'}",
                reason="unknown_nickname",
            )
        entries = await ble.scan(scan_timeout, known=known, scanner_factory=scanner_factory)
        prefix = _hex_digits(target)
        matches = [e.device for e in entries if _hex_digits(e.device.identifier).startswith(prefix)]
        if not matches:
            raise NoDeviceFoundError(f"no Tank-G whose identifier starts with {target}")
        if len(matches) > 1:
            raise MultipleDevicesError(matches)
        return matches[0].identifier, matches[0].name, matches[0].rssi
    seen = await ble.seek(None, scan_timeout, scanner_factory=scanner_factory)
    device = ble.select_device(ble.strongest_first(seen), None)
    return device.identifier, device.name, device.rssi


async def select(args: argparse.Namespace, scanner_factory: ScannerFactory) -> tuple[str, int]:
    """``openvave select [TARGET] [--name NICKNAME] [--offline]`` (research R4)."""
    target, offline = args.target, args.offline
    if args.name is not None:
        check_nickname(args.name)
    if offline and (target is None or not is_identifier(target)):
        raise UsageError(
            "--offline takes a full identifier (MAC or UUID), not a nickname or prefix"
        )
    known = _load()
    identifier, name, rssi = await resolve_selection(
        target, known, args.scan_timeout, scanner_factory, offline=offline
    )
    previous = known.default
    updated = known.select(identifier, args.name, name=name)
    updated.save()
    chosen_device = updated.default
    assert chosen_device is not None
    if args.json:
        document = render.device_document("select", updated, rssi=rssi, previous_default=previous)
        return render.dumps(document), 0
    text = render.human_select_device(
        chosen_device, name=name, rssi=rssi, previous=previous, path=updated.path
    )
    return text, 0


def _nickname_match(known: KnownDevices, value: str) -> KnownDevice | None:
    return next(
        (d for d in known.devices if d.nickname and d.nickname.casefold() == value.casefold()),
        None,
    )


async def device(args: argparse.Namespace, scanner_factory: ScannerFactory) -> tuple[str, int]:
    """``openvave device [--check]`` and ``openvave device rename OLD NEW``."""
    if args.action == "rename":
        return rename(args)
    from openvave.transport import ble

    known = _load()
    environment = os.environ.get("OPENVAVE_DEVICE") or None
    in_range: tuple[bool, int | None] | None = None
    if args.check:
        default = known.default
        if default is None:
            raise ConfigError(
                "no default pedal to check; choose one with: openvave select ID",
                reason="unknown_device",
            )
        seen = await ble.seek(
            default.identifier, args.scan_timeout, scanner_factory=scanner_factory
        )
        found = next(
            (d for d in seen if d.identifier.casefold() == default.identifier.casefold()), None
        )
        in_range = (found is not None, found.rssi if found is not None else None)
    code = 3 if in_range is not None and not in_range[0] else 0
    if args.json:
        extra: dict[str, Any] = {"environment_override": environment}
        if in_range is not None:
            extra.update(in_range=in_range[0], rssi=in_range[1])
        return render.dumps(render.device_document("device", known, **extra)), code
    return render.human_device(known, environment=environment, in_range=in_range), code


def rename(args: argparse.Namespace) -> tuple[str, int]:
    """``openvave device rename OLD NEW`` (no Bluetooth)."""
    known = _load()
    before = known.find(args.old)
    updated = known.rename(args.old, args.new)
    updated.save()
    assert before is not None
    after = updated.find(before.identifier)
    assert after is not None
    if args.json:
        return render.dumps(render.device_document("device rename", updated)), 0
    return render.human_rename(before.nickname or before.identifier, after), 0


def forget(args: argparse.Namespace) -> tuple[str, int]:
    """``openvave forget [TARGET | --all]`` (no Bluetooth)."""
    path = default_config_path()
    if args.forget_all:
        return _forget_all(args, path)
    known = KnownDevices.load(path)
    if args.target is None:
        default = known.default
        updated = known.forget()
        if default is not None:
            updated.save()
        if args.json:
            removed: list[KnownDevice] = []
            return render.dumps(render.device_document("forget", updated, removed=removed)), 0
        return render.human_forget_default(default), 0
    device = known.find(args.target)
    updated = known.forget(args.target)
    assert device is not None
    was_default = known.default_identifier == device.identifier
    updated.save()
    if args.json:
        return render.dumps(render.device_document("forget", updated, removed=[device])), 0
    return render.human_forget_one(device, was_default=was_default), 0


def _forget_all(args: argparse.Namespace, path: Path) -> tuple[str, int]:
    moved: Path | None = None
    try:
        known = KnownDevices.load(path)
    except ConfigError as err:
        if err.reason != "invalid_file":
            raise
        moved = path.with_name(f"{path.name}.invalid-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
        os.replace(path, moved)
        known = KnownDevices(path=path)
    removed = list(known.devices)
    updated = known.forget_all()
    updated.save()
    if args.json:
        extra: dict[str, Any] = {"removed": removed}
        if moved is not None:
            extra["moved_to"] = str(moved)
        return render.dumps(render.device_document("forget", updated, **extra)), 0
    return render.human_forget_all(len(removed), moved), 0


__all__ = [
    "UsageError",
    "add_parsers",
    "device",
    "forget",
    "rename",
    "resolve_selection",
    "scan",
    "select",
]
