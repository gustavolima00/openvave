"""Fixtures for the MCP server tests (spec 006): an in-process client over ``FakeTransport``.

The server runs in the test's event loop through the SDK's in-memory ``Client``; no Bluetooth
backend is loaded and no test waits for the real idle timeout (:class:`ManualSleep`).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from mcp import Client
from mcp.server.mcpserver import MCPServer

from openvave.devices import Target
from openvave.errors import OpenvaveError
from openvave.mcp_server import PedalHolder, ServerOptions, create
from openvave.models import DeviceInfo
from openvave.transport import Transport
from openvave.transport.fake import FakeTransport
from tests.support.captures import FW96_CONNECT

PEDAL = DeviceInfo("AA:BB:CC:DD:EE:01", "TANK-Gv2_BLE", -58)


class ManualSleep:
    """An injectable ``sleep`` that waits until the test calls :meth:`fire`."""

    def __init__(self) -> None:
        self.calls: list[float] = []
        self._events: list[asyncio.Event] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)
        event = asyncio.Event()
        self._events.append(event)
        await event.wait()

    async def fire(self) -> None:
        events, self._events = self._events, []
        for event in events:
            event.set()
        await settle()


async def settle(rounds: int = 10) -> None:
    for _ in range(rounds):
        await asyncio.sleep(0)


@dataclass
class CountingFactory:
    """A transport factory handing out a fresh fake per connection, and counting them."""

    make: Callable[[], FakeTransport] = lambda: FakeTransport.from_capture(FW96_CONNECT)
    device: DeviceInfo | None = PEDAL
    error: OpenvaveError | None = None
    fakes: list[FakeTransport] = field(default_factory=list)
    targets: list[Target | None] = field(default_factory=list)

    async def __call__(
        self, target: Target | None, scan_timeout: float
    ) -> tuple[Transport, DeviceInfo | None]:
        self.targets.append(target)
        if self.error is not None:
            raise self.error
        fake = self.make()
        self.fakes.append(fake)
        return fake, self.device

    @property
    def calls(self) -> int:
        return len(self.targets)

    @property
    def fake(self) -> FakeTransport:
        return self.fakes[-1]


def options(tmp_path: Path, **overrides: Any) -> ServerOptions:
    values: dict[str, Any] = {"backup_dir": tmp_path / "backups", "timeout": 0.5}
    values.update(overrides)
    return ServerOptions(**values)


@dataclass
class Harness:
    server: MCPServer
    holder: PedalHolder
    factory: Any
    sleep: ManualSleep
    client: Client

    async def call(self, name: str, args: dict[str, Any] | None = None) -> Result:
        result = await self.client.call_tool(name, args or {})
        text = "".join(getattr(c, "text", "") for c in result.content)
        return Result(bool(result.is_error), result.structured_content, text)

    async def ok(self, name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        result = await self.call(name, args)
        assert not result.is_error, result.text
        assert result.data is not None
        return result.data

    async def error(self, name: str, args: dict[str, Any] | None = None) -> str:
        """The tool error's own text (the SDK's ``Error executing tool …:`` prefix removed)."""
        result = await self.call(name, args)
        assert result.is_error, result.text
        prefix = f"Error executing tool {name}: "
        return result.text[len(prefix) :] if result.text.startswith(prefix) else result.text

    async def resource(self, uri: str) -> tuple[str | None, str]:
        """``(mime type, text)`` of a resource."""
        result = await self.client.read_resource(uri)
        content = result.contents[0]
        return content.mime_type, getattr(content, "text", "")


@dataclass
class Result:
    is_error: bool
    data: dict[str, Any] | None
    text: str

    def json(self) -> Any:
        return json.loads(self.text)


@pytest.fixture
def factory() -> CountingFactory:
    return CountingFactory()


@pytest.fixture
def manual_sleep() -> ManualSleep:
    return ManualSleep()


@pytest.fixture
def server_options(tmp_path: Path) -> ServerOptions:
    return options(tmp_path)


class open_harness:  # noqa: N801 - used like a function
    """``async with open_harness(options, factory, sleep) as h``: server, holder and client."""

    def __init__(
        self,
        server_options: ServerOptions,
        factory: Any,
        sleep: ManualSleep | None = None,
        *,
        mode: str = "legacy",
        scanner_factory: Any = None,
        poll_sleep: Any = None,
        **client_kwargs: Any,
    ) -> None:
        self.sleep = sleep or ManualSleep()
        extra: dict[str, Any] = {"scanner_factory": scanner_factory}
        if poll_sleep is not None:
            extra["poll_sleep"] = poll_sleep
        self.server, self.holder = create(server_options, factory, sleep=self.sleep, **extra)
        self.factory = factory
        self.client = Client(self.server, mode=mode, **client_kwargs)

    async def __aenter__(self) -> Harness:
        await self.client.__aenter__()
        return Harness(self.server, self.holder, self.factory, self.sleep, self.client)

    async def __aexit__(self, *exc: object) -> None:
        try:
            await self.client.__aexit__(*exc)
        finally:
            await self.holder.shutdown()
