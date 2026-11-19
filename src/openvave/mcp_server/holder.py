"""The one pedal connection an MCP server holds (spec 006 research R7, data-model.md).

:class:`PedalHolder` keeps at most one :class:`~openvave.TankG` open for many tool calls:

- **lazy**: nothing is scanned or connected until a pedal tool runs;
- **one at a time**: an :class:`asyncio.Lock` serialises pedal operations on the single link;
- **one reopen**: when the held session was lost, the next :meth:`use` closes it and opens a
  new one, once; an error raised *during* an operation (with its partial result) propagates
  unchanged and nothing is resent;
- **released when idle**: ``idle_release`` seconds after the last pedal call, and on
  :meth:`disconnect` / :meth:`shutdown`, so the phone app can take the pedal.

The pedal is chosen with the CLI's rule (``openvave.cli.choice``): the pedal selected in this
server session, else ``--device``, else ``OPENVAVE_DEVICE``, else the default, else the only
Tank-G in range; never another one.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from openvave.cli import choice
from openvave.devices import Target
from openvave.errors import MultipleDevicesError
from openvave.models import DeviceInfo, Region, RegionRead
from openvave.session import DEFAULT_SCAN_TIMEOUT, DEFAULT_TIMEOUT, TankG
from openvave.transport import Transport

logger = logging.getLogger("openvave.mcp")

DEFAULT_IDLE_RELEASE = 300.0
"""Seconds without a pedal tool call before the connection is closed (clarification 2)."""

TransportFactory = choice.TransportFactory
Sleep = Callable[[float], Awaitable[None]]


@dataclass(frozen=True)
class ServerOptions:
    """Fixed for the life of one ``openvave mcp`` process (contracts/tools.md, Command)."""

    backup_dir: Path
    device: str | None = None
    read_only: bool = False
    idle_release: float = DEFAULT_IDLE_RELEASE
    scan_timeout: float = DEFAULT_SCAN_TIMEOUT
    timeout: float = DEFAULT_TIMEOUT
    trace: bool = False

    def as_json(self) -> dict[str, Any]:
        return {
            "read_only": self.read_only,
            "device": self.device,
            "backup_dir": str(self.backup_dir),
            "idle_release": self.idle_release,
            "scan_timeout": self.scan_timeout,
            "timeout": self.timeout,
        }


@dataclass
class PedalHolder:
    """At most one open session, shared by every tool call of one server."""

    options: ServerOptions
    factory: TransportFactory
    sleep: Sleep = asyncio.sleep
    """Waits out the idle release (injectable for tests)."""
    poll_sleep: Sleep = asyncio.sleep
    """Waits between ``pedal_changes`` polls (injectable for tests)."""
    scanner_factory: Any = None
    """Replaces ``BleakScanner`` for ``pedal_scan`` / ``pedal_select`` (tests); ``None``: real."""
    session_target: Target | None = None
    pedal: TankG | None = None
    device: DeviceInfo | None = None
    connected_since: datetime | None = None
    last_error: str | None = None
    baseline: dict[Region, RegionRead] | None = None
    bypass_return: int | None = None
    opens: int = 0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _idle_task: asyncio.Task[None] | None = None

    # -- state --------------------------------------------------------------------------------

    @property
    def connected(self) -> bool:
        return self.pedal is not None and self.pedal.is_connected

    def status(self) -> dict[str, Any]:
        """Holder fields only: never takes the lock and sends nothing (FR-015)."""
        pedal = self.pedal if self.connected else None
        identity = pedal.identity if pedal is not None else None
        return {
            "connected": pedal is not None,
            "since": self.connected_since.isoformat()
            if pedal is not None and self.connected_since is not None
            else None,
            "pedal": _device_json(self.device) if pedal is not None else None,
            "firmware": identity.firmware if identity is not None else None,
            "firmware_untested": identity.firmware_untested if identity is not None else None,
            "session_choice": _target_json(self.session_target),
            "last_error": self.last_error,
            "bypass_return": self.bypass_return,
            "options": self.options.as_json(),
        }

    # -- use ----------------------------------------------------------------------------------

    @contextlib.asynccontextmanager
    async def use(self) -> AsyncIterator[TankG]:
        """The open session for one tool call, under the lock; opens or reopens it once."""
        async with self.lock:
            self._cancel_idle()
            try:
                if not self.connected:
                    await self._open()
                assert self.pedal is not None
                yield self.pedal
            finally:
                self._arm_idle()

    @contextlib.asynccontextmanager
    async def exclusive(self) -> AsyncIterator[None]:
        """The lock without connecting (scan, disconnect, select)."""
        async with self.lock:
            yield

    async def _open(self) -> None:
        await self._close()
        target, known = choice.choose(self._namespace())
        try:
            transport, device = await self.factory(target, self.options.scan_timeout)
        except MultipleDevicesError as err:
            candidates = [
                _with_nickname(c, choice.nickname_of(c.identifier, known)) for c in err.candidates
            ]
            raise MultipleDevicesError(candidates) from err
        device = choice.annotate(device, target, known)

        async def source() -> tuple[Transport, DeviceInfo | None]:
            return transport, device

        pedal = TankG(source, timeout=self.options.timeout)
        await pedal.open()
        self.opens += 1
        if (
            device is not None
            and self.device is not None
            and (device.identifier.casefold() != self.device.identifier.casefold())
        ):
            self.baseline = None
            self.bypass_return = None
        self.pedal, self.device = pedal, device
        self.connected_since = datetime.now(UTC)
        if device is not None and known is not None:
            choice.record_seen(known, device, pedal.identity.firmware)
        logger.info("connected to %s", device.identifier if device is not None else "pedal")

    def _namespace(self) -> argparse.Namespace:
        device = self.session_target.identifier if self.session_target is not None else None
        return argparse.Namespace(device=device or self.options.device)

    # -- release ------------------------------------------------------------------------------

    async def _close(self) -> None:
        pedal, self.pedal = self.pedal, None
        self.connected_since = None
        if pedal is not None:
            await pedal.close()

    async def disconnect(self) -> bool:
        """Close the held connection (idempotent). Returns whether one was open."""
        async with self.lock:
            self._cancel_idle()
            was = self.connected
            await self._close()
            return was

    async def shutdown(self) -> None:
        """Close everything on server exit (does not wait for a pending call)."""
        self._cancel_idle()
        await self._close()

    async def choose(self, target: Target | None) -> None:
        """Make ``target`` the session's pedal; closes a held connection to another pedal.
        The caller holds :meth:`exclusive`."""
        self.session_target = target
        if (
            self.device is not None
            and target is not None
            and (self.device.identifier.casefold() != target.identifier.casefold())
        ):
            await self._close()
            self.device = None
            self.baseline = None
            self.bypass_return = None

    def _arm_idle(self) -> None:
        self._cancel_idle()
        if self.options.idle_release <= 0 or not self.connected:
            return
        self._idle_task = asyncio.get_running_loop().create_task(self._idle())

    def _cancel_idle(self) -> None:
        task, self._idle_task = self._idle_task, None
        if task is not None and not task.done() and task is not asyncio.current_task():
            task.cancel()

    async def _idle(self) -> None:
        await self.sleep(self.options.idle_release)
        async with self.lock:
            if self._idle_task is not asyncio.current_task():
                return  # re-armed or cancelled while waiting for the lock
            self._idle_task = None
            logger.info("idle for %.0f s: releasing the pedal", self.options.idle_release)
            await self._close()


def _with_nickname(device: DeviceInfo, nickname: str | None) -> DeviceInfo:
    from dataclasses import replace

    return replace(device, nickname=device.nickname or nickname)


def _device_json(device: DeviceInfo | None) -> dict[str, Any] | None:
    from openvave.cli.render import device_json

    return device_json(device)


def _target_json(target: Target | None) -> dict[str, Any] | None:
    if target is None:
        return None
    return {"identifier": target.identifier, "nickname": target.nickname}


__all__ = ["DEFAULT_IDLE_RELEASE", "PedalHolder", "ServerOptions", "TransportFactory"]
