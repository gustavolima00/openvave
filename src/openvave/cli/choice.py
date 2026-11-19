"""Choosing the pedal for every pedal command (spec 005 M2: research R5, R8, R9).

One way in for every command that talks to a pedal: :func:`pedal_session` resolves the target
(``--device`` → ``OPENVAVE_DEVICE`` → the default → the only Tank-G in range), asks the transport
factory for it, prints the ``pedal:`` line, opens the session and records "last seen". No command
builds its own transport source, so none can bypass the choice or fall back to another pedal.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import replace

from openvave.cli import render
from openvave.devices import KnownDevices, Target, is_identifier, resolve_target
from openvave.errors import ConfigError, MultipleDevicesError
from openvave.models import DeviceInfo
from openvave.session import TankG
from openvave.transport import Transport

logger = logging.getLogger("openvave")

TransportFactory = Callable[[Target | None, float], Awaitable[tuple[Transport, DeviceInfo | None]]]
"""``(target, scan_timeout) -> (transport not yet open, device)``; injectable for tests. ``None``
means no choice: the only Tank-G in range (0.4.0 rules)."""


def choose(args: argparse.Namespace) -> tuple[Target | None, KnownDevices | None]:
    """The target of this command and the known pedals (``None`` when the file is invalid and
    not needed). The file is needed unless ``--device`` / ``OPENVAVE_DEVICE`` is an identifier;
    when it is needed and invalid, :class:`ConfigError` (exit 2) is raised before any scan."""
    option = getattr(args, "device", None) or None
    environment = os.environ.get("OPENVAVE_DEVICE") or None
    value = option or environment
    known: KnownDevices | None
    try:
        known = KnownDevices.load()
    except ConfigError as err:
        if value is None or not is_identifier(value):
            raise
        print(f"warning: {err} (nicknames unavailable)", file=sys.stderr)
        known = None
    return resolve_target(option, environment, known), known


def _same(a: str, b: str) -> bool:
    return a.casefold() == b.casefold()


def nickname_of(identifier: str, known: KnownDevices | None) -> str | None:
    """The nickname of the known pedal with this identifier (not a nickname match)."""
    if known is None:
        return None
    entry = known.find(identifier)
    if entry is None or not _same(entry.identifier, identifier):
        return None
    return entry.nickname


def annotate(
    device: DeviceInfo | None, target: Target | None, known: KnownDevices | None
) -> DeviceInfo | None:
    """``device`` with its ``nickname`` and ``chosen_by`` filled in where the factory left them
    empty (a test factory, or a transport built by hand)."""
    if device is None:
        return None
    nickname = device.nickname
    if nickname is None and target is not None and _same(target.identifier, device.identifier):
        nickname = target.nickname
    if nickname is None:
        nickname = nickname_of(device.identifier, known)
    chosen_by = device.chosen_by or (target.chosen_by if target is not None else "only_one_found")
    return replace(device, nickname=nickname, chosen_by=chosen_by)


def record_seen(known: KnownDevices, device: DeviceInfo, firmware: int | None) -> None:
    """Best effort: update ``last_name``, ``last_firmware`` and ``last_seen_at`` of a known pedal
    (research R9). An unknown pedal leaves the file untouched; a write failure is ignored."""
    entry = known.find(device.identifier)
    if entry is None or not _same(entry.identifier, device.identifier):
        return
    try:
        known.record_seen(entry.identifier, device.name, firmware).save()
    except OSError as err:
        logger.debug("could not record last seen in %s: %s", known.path, err)


@asynccontextmanager
async def pedal_session(
    args: argparse.Namespace,
    factory: TransportFactory,
    *,
    on_transport: Callable[[Transport], None] | None = None,
) -> AsyncIterator[TankG]:
    """An open :class:`TankG` on the chosen pedal, closed on exit.

    The ``pedal:`` line goes to stderr in human mode once the pedal is chosen and before
    connecting. ``on_transport`` receives the transport before it is opened (``watch`` records
    its ATT MTU).
    """
    target, known = choose(args)
    try:
        transport, device = await factory(target, args.scan_timeout)
    except MultipleDevicesError as err:
        candidates = [
            replace(c, nickname=c.nickname or nickname_of(c.identifier, known))
            for c in err.candidates
        ]
        raise MultipleDevicesError(candidates) from err
    device = annotate(device, target, known)
    if device is not None and not args.json:
        print(render.pedal_line(device), file=sys.stderr, flush=True)
    if on_transport is not None:
        on_transport(transport)

    async def source() -> tuple[Transport, DeviceInfo | None]:
        return transport, device

    async with TankG(source, timeout=args.timeout) as pedal:
        if device is not None and known is not None:
            record_seen(known, device, pedal.identity.firmware)
        yield pedal


__all__ = ["TransportFactory", "annotate", "choose", "nickname_of", "pedal_session", "record_seen"]
