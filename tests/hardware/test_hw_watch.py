"""Real-pedal watch (T029). Runs only with ``--hardware`` and a fw-96 Tank-G nearby.

Close the M-VAVE phone app first: it holds the pedal's BLE connection. Run from your own
terminal (macOS asks that app, not an agent, for Bluetooth permission).
"""

from __future__ import annotations

import asyncio

import pytest

from openvave.models import Region, WatchStart
from openvave.session import TankG
from openvave.trace import trace_hook

pytestmark = pytest.mark.hardware


async def test_watch_on_hardware() -> None:
    sent: list[bytes] = []

    def on_frame(kind: str, data: bytes) -> None:
        if kind == "tx":
            sent.append(data)

    with trace_hook(on_frame):
        async with asyncio.timeout(15):
            async with TankG.connect() as pedal:
                events = [e async for e in pedal.watch(cycles=3)]
    start = events[0]
    assert isinstance(start, WatchStart)
    assert list(start.regions) == [Region.GLOBAL, Region.CURRENT_PRESET, Region.STATUS]
    assert len(start.regions[Region.CURRENT_PRESET].read.data) == 21
    queries = [f for f in sent if f[2] == 0x11]
    reads = [f for f in sent if f[2] == 0x23]
    assert queries and sent[: len(queries)] == queries  # handshake (retries allowed) first
    assert len(reads) == 3 * 3 == len(sent) - len(queries)
