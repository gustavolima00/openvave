"""Exception hierarchy. Each class maps 1:1 to a CLI exit code (contracts/cli.md)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from openvave.models import DeviceInfo


class OpenvaveError(Exception):
    """Base class for every error raised by openvave."""

    exit_code: ClassVar[int] = 1


class NoDeviceFoundError(OpenvaveError):
    """No Tank-G was found within the scan timeout."""

    exit_code = 3


class MultipleDevicesError(OpenvaveError):
    """More than one Tank-G was found and none was selected."""

    exit_code = 4

    def __init__(self, candidates: Sequence[DeviceInfo]) -> None:
        self.candidates: tuple[DeviceInfo, ...] = tuple(candidates)
        super().__init__(f"{len(self.candidates)} pedals found; select one with --device")


class BluetoothUnavailableError(OpenvaveError):
    """The Bluetooth adapter is off, missing, or access was denied."""

    exit_code = 5


class ConnectionLostError(OpenvaveError):
    """The pedal disconnected during the session."""

    exit_code = 6


class RequestTimeoutError(OpenvaveError):
    """The pedal did not reply to a request in time."""

    exit_code = 6


class ProtocolError(OpenvaveError):
    """A frame or reply was malformed or did not match its request.

    ``reason`` is a stable code (``bad_marker``, ``length_mismatch``, ``bad_checksum``,
    ``wrong_command``, ``echo_mismatch``, ``short_data``, ``bad_identity``); ``detail`` narrows it
    where useful (e.g. which echo field mismatched).
    """

    exit_code = 7

    def __init__(self, reason: str, detail: str | None = None, message: str | None = None) -> None:
        self.reason = reason
        self.detail = detail
        text = message or (f"{reason} ({detail})" if detail else reason)
        super().__init__(text)


class HandshakeError(OpenvaveError):
    """The name/version handshake failed after all attempts."""

    exit_code = 7


class UnsafeCommandError(OpenvaveError):
    """Attempt to encode a command byte outside the read-only allowlist (programming error)."""

    exit_code = 1
