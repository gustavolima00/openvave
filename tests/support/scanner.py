"""Stand-ins for ``BleakScanner`` (spec 005): no Bluetooth involved.

``fake_scanner(schedule)`` reports each advertisement at its time; ``forbidden_scanner`` fails the
test if a command that must not use Bluetooth constructs a scanner. Identifiers are made up
(Constitution VI).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from types import SimpleNamespace, TracebackType
from typing import Any

from openvave.errors import OpenvaveError

TANK = "TANK-Gv2_BLE"
UUID_1 = "8F3A21C4-0000-4000-8000-000000000001"
UUID_2 = "8F3A21C4-0000-4000-8000-000000000002"
UUID_3 = "8F3A21C4-0000-4000-8000-000000000003"
MAC_1 = "AA:BB:CC:DD:EE:01"
MAC_2 = "AA:BB:CC:DD:EE:02"
SPEAKER = "9B7C0000-0000-4000-8000-0000000000AA"

Advert = tuple[str, str, int | None]
"""``(identifier, advertised name, rssi)``."""


def fake_scanner(
    adverts: Sequence[Advert] | Sequence[tuple[float, Advert]],
    *,
    calls: list[str] | None = None,
) -> Callable[..., Any]:
    """A ``BleakScanner`` stand-in. ``adverts`` are reported at 0.01 s each, or at the time given
    as ``(seconds, advert)``. ``calls`` records ``"scan"`` once per scanner built."""
    schedule: list[tuple[float, Advert]] = []
    for item in adverts:
        if isinstance(item[0], float | int) and isinstance(item[1], tuple):
            schedule.append((float(item[0]), item[1]))  # type: ignore[arg-type]
        else:
            schedule.append((0.01, item))  # type: ignore[arg-type]

    class FakeScanner:
        def __init__(self, detection_callback: Callable[[Any, Any], None]) -> None:
            if calls is not None:
                calls.append("scan")
            self._callback = detection_callback
            self._handles: list[asyncio.TimerHandle] = []

        async def __aenter__(self) -> FakeScanner:
            loop = asyncio.get_running_loop()
            for at, (address, name, rssi) in schedule:
                device = SimpleNamespace(address=address, name=name)
                adv = SimpleNamespace(local_name=name, rssi=rssi)
                self._handles.append(loop.call_later(at, self._callback, device, adv))
            return self

        async def __aexit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            tb: TracebackType | None,
        ) -> None:
            for handle in self._handles:
                handle.cancel()

    return FakeScanner


def forbidden_scanner(*_args: Any, **_kwargs: Any) -> Any:
    """Fails the test: the command was not allowed to use Bluetooth."""
    raise AssertionError("this command must not scan")


def raising_scanner(error: OpenvaveError) -> Callable[..., Any]:
    """A scanner whose construction raises ``error`` (e.g. Bluetooth unavailable)."""

    def build(*_args: Any, **_kwargs: Any) -> Any:
        raise error

    return build
