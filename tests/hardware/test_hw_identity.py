"""Real-pedal identity check (T034). Runs only with ``--hardware`` and a fw-96 Tank-G nearby.

Close the M-VAVE phone app first: it holds the pedal's BLE connection.
"""

from __future__ import annotations

import asyncio

import pytest

from openvave.session import TankG

pytestmark = pytest.mark.hardware


async def test_identity_on_hardware() -> None:
    async with asyncio.timeout(10):
        async with TankG.connect() as pedal:
            assert pedal.identity.name == "TANK-Gv2"
            assert pedal.identity.firmware == 96
            assert pedal.identity.firmware_untested is False
            assert pedal.device is not None
            assert pedal.device.name == "TANK-Gv2_BLE"
