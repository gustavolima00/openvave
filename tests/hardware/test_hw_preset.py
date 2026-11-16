"""Real-pedal current-preset read (T052). Runs only with ``--hardware`` and a fw-96 Tank-G nearby.

Close the M-VAVE phone app first: it holds the pedal's BLE connection.
"""

from __future__ import annotations

import asyncio

import pytest

from openvave.models import Region
from openvave.session import TankG

pytestmark = pytest.mark.hardware


async def test_preset_read_on_hardware() -> None:
    async with asyncio.timeout(10):
        async with TankG.connect() as pedal:
            assert pedal.identity.firmware == 96
            read = await pedal.read(Region.CURRENT_PRESET)
    assert read.region is Region.CURRENT_PRESET
    assert len(read.data) == 21
