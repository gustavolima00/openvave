"""Real-pedal snapshot check (T041). Runs only with ``--hardware`` and a fw-96 Tank-G nearby.

Close the M-VAVE phone app first: it holds the pedal's BLE connection.
"""

from __future__ import annotations

import asyncio

import pytest

from openvave.models import Region
from openvave.session import TankG

pytestmark = pytest.mark.hardware


async def test_snapshot_on_hardware() -> None:
    async with asyncio.timeout(15):
        async with TankG.connect() as pedal:
            snap = await pedal.snapshot()
    assert list(snap.regions) == [
        Region.DEVICE_INFO,
        Region.GLOBAL,
        Region.CURRENT_PRESET,
        Region.STATUS,
    ]
    for region, read in snap.regions.items():
        assert len(read.data) == region.length
    assert snap.regions[Region.DEVICE_INFO].data[:4] == bytes.fromhex("0a 30 39 36")
    assert len(snap.regions[Region.STATUS].data) == 1
