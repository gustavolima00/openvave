"""Early-stopping BLE scan (spec 004 M0 gate, SC-001): no Bluetooth involved.

A scan used to wait its whole timeout (5 s) even after the pedal had been seen. It now stops
``SCAN_GRACE`` seconds after the first pedal advertising ``TANK-Gv2_BLE`` (so a second pedal in
that window still gives "more than one pedal"), and at once when the ``--device`` identifier is
seen. ``discover()`` still scans for the whole timeout (it lists every pedal).
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from types import SimpleNamespace, TracebackType
from typing import Any

import pytest

from openvave.errors import MultipleDevicesError
from openvave.transport import ble
from openvave.transport.ble import BLE_NAME, select_device

PEDAL_A = ("AAAA-1111", BLE_NAME, -58)
PEDAL_B = ("BBBB-2222", BLE_NAME, -71)
SPEAKER = ("DDDD-4444", "Some Speaker", -40)


def fake_scanner(schedule: list[tuple[float, tuple[str, str, int]]]) -> Callable[..., Any]:
    """A BleakScanner stand-in that reports each advertisement at its time (seconds)."""

    class FakeScanner:
        def __init__(self, detection_callback: Callable[[Any, Any], None]) -> None:
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


async def scan(
    schedule: list[tuple[float, tuple[str, str, int]]],
    *,
    timeout: float = 2.0,
    grace: float = 0.1,
    wanted: str | None = None,
    stop_early: bool = True,
) -> tuple[list[str], float]:
    started = time.monotonic()
    devices = await ble._scan(
        timeout,
        wanted_id=wanted,
        stop_early=stop_early,
        grace=grace,
        scanner_factory=fake_scanner(schedule),
    )
    return sorted(devices), time.monotonic() - started


async def test_one_pedal_stops_after_the_grace_period() -> None:
    found, elapsed = await scan([(0.02, SPEAKER), (0.05, PEDAL_A)])
    assert found == [PEDAL_A[0], SPEAKER[0]]
    assert 0.1 <= elapsed < 0.5  # first match at 0.05 s + 0.1 s grace, far below the 2 s timeout


async def test_second_pedal_within_grace_is_still_reported() -> None:
    found, _ = await scan([(0.05, PEDAL_A), (0.1, PEDAL_B)])
    assert found == [PEDAL_A[0], PEDAL_B[0]]
    with pytest.raises(MultipleDevicesError):
        select_device([ble.DeviceInfo(a, BLE_NAME, r) for a, _, r in (PEDAL_A, PEDAL_B)], None)


async def test_pedal_after_the_grace_period_is_not_waited_for() -> None:
    found, elapsed = await scan([(0.05, PEDAL_A), (1.5, PEDAL_B)])
    assert found == [PEDAL_A[0]]
    assert elapsed < 0.5


async def test_wanted_device_stops_at_once() -> None:
    found, elapsed = await scan([(0.05, SPEAKER), (0.3, PEDAL_A)], wanted="dddd-4444", grace=1.0)
    assert SPEAKER[0] in found
    assert elapsed < 0.25  # no grace period with --device


async def test_no_pedal_scans_the_whole_timeout() -> None:
    found, elapsed = await scan([(0.05, SPEAKER)], timeout=0.4)
    assert found == [SPEAKER[0]]
    assert elapsed >= 0.4


async def test_without_stop_early_the_whole_timeout_is_used() -> None:
    found, elapsed = await scan([(0.05, PEDAL_A)], timeout=0.4, stop_early=False)
    assert found == [PEDAL_A[0]]
    assert elapsed >= 0.4


async def test_open_ble_uses_the_early_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    async def fake_scan(timeout: float, **options: Any) -> dict[str, Any]:
        calls.append({"timeout": timeout, **options})
        device = SimpleNamespace(address=PEDAL_A[0], name=BLE_NAME)
        return {PEDAL_A[0]: (device, ble.DeviceInfo(PEDAL_A[0], BLE_NAME, -58))}

    monkeypatch.setattr(ble, "_scan", fake_scan)
    _, chosen = await ble.open_ble(None, 5.0)
    assert chosen.identifier == PEDAL_A[0]
    assert calls == [{"timeout": 5.0, "wanted_id": None, "stop_early": True}]


def test_default_grace_is_one_second() -> None:
    assert ble.SCAN_GRACE == 1.0
