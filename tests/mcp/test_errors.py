"""Library errors become tool errors with the CLI's hints (spec 006 FR-026, research R5)."""

from __future__ import annotations

import logging

import pytest

from openvave.devices import Target
from openvave.errors import (
    BluetoothUnavailableError,
    ConfigError,
    ConnectionLostError,
    HandshakeError,
    MultipleDevicesError,
    NoDeviceFoundError,
    OpenvaveError,
    RequestTimeoutError,
    TargetNotFoundError,
    WriteRefusedError,
)
from openvave.mcp_server.errors import error_message, kind_of
from openvave.models import DeviceInfo
from tests.mcp.conftest import CountingFactory, open_harness, options

OTHER = DeviceInfo("AA:BB:CC:DD:EE:02", "TANK-Gv2_BLE", -70)


@pytest.mark.parametrize(
    ("error", "kind"),
    [
        (NoDeviceFoundError("no TANK-Gv2_BLE found"), "no_device_found"),
        (
            TargetNotFoundError(Target("AA:BB:CC:DD:EE:01", "stage", "selected"), [OTHER]),
            "target_not_found",
        ),
        (MultipleDevicesError([OTHER, OTHER]), "multiple_devices"),
        (ConfigError("bad file", reason="invalid_file"), "config_error"),
        (BluetoothUnavailableError("off"), "bluetooth_unavailable"),
        (ConnectionLostError("gone"), "connection_lost"),
        (RequestTimeoutError("slow"), "timeout"),
        (HandshakeError("nope"), "handshake_failed"),
        (WriteRefusedError("experimental_required", "needs experimental"), "experimental_required"),
        (ValueError("bad"), "invalid_value"),
        (RuntimeError("boom"), "internal"),
    ],
)
def test_kinds(error: Exception, kind: str) -> None:
    assert kind_of(error) == kind
    assert error_message(error).startswith(f"{kind}: ")


def test_message_carries_cli_lines() -> None:
    err = TargetNotFoundError(Target("AA:BB:CC:DD:EE:01", "stage", "selected"), [OTHER])
    lines = error_message(err).splitlines()
    assert any(line.startswith("seen: ") for line in lines)
    assert any(line.startswith("hint: ") and "phone app" in line for line in lines)


def test_partial_is_appended() -> None:
    err = OpenvaveError("stopped")
    message = error_message(err, lambda e: {"applied": ["gain"]})
    assert message.splitlines()[-1] == 'partial: {"applied":["gain"]}'


async def test_error_is_is_error_and_server_keeps_serving(tmp_path) -> None:
    factory = CountingFactory(error=MultipleDevicesError([OTHER, OTHER]))
    async with open_harness(options(tmp_path), factory) as h:
        message = await h.error("pedal_info")
        assert message.startswith("multiple_devices: 2 pedals found")
        assert "openvave select ID" in message
        factory.error = None
        await h.ok("pedal_info")


async def test_unexpected_exception_is_internal_and_logged(
    tmp_path, caplog: pytest.LogCaptureFixture
) -> None:
    factory = CountingFactory(error=None)

    async def boom(target, scan_timeout):  # type: ignore[no-untyped-def]
        raise RuntimeError("boom")

    async with open_harness(options(tmp_path), factory) as h:
        h.holder.factory = boom
        with caplog.at_level(logging.ERROR, logger="openvave.mcp"):
            message = await h.error("pedal_info")
        assert message == "internal: unexpected RuntimeError: boom"
        assert any("unexpected error" in r.message for r in caplog.records)
        h.holder.factory = factory
        await h.ok("pedal_info")
