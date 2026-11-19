"""Exception hierarchy. Each class maps to one CLI exit code (``exit_code``, contracts/cli.md)."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from openvave.devices import Target
    from openvave.models import DeviceInfo, EditResult, SequenceResult, WriteResult


class OpenvaveError(Exception):
    """Base class for every error raised by openvave.

    ``sequence`` is set on an error raised in the middle of ``save_preset`` / ``restore``: the
    partial :class:`~openvave.models.SequenceResult` (which steps were acknowledged, not sent or
    unanswered, and whether stored presets may have changed). ``None`` otherwise.

    ``edit`` is set on an error raised in the middle of ``set_fields`` (a batch edit): the
    partial :class:`~openvave.models.EditResult` saying which fields were applied, which are
    unknown and which were not sent. ``None`` otherwise.
    """

    exit_code: ClassVar[int] = 1
    sequence: SequenceResult | None = None
    edit: EditResult | None = None


class NoDeviceFoundError(OpenvaveError):
    """No Tank-G was found within the scan timeout."""

    exit_code = 3


class TargetNotFoundError(NoDeviceFoundError):
    """The chosen pedal (``--device``, ``OPENVAVE_DEVICE`` or the default) was not seen in the
    scan (spec 005 FR-019). Nothing else is connected to instead.

    ``target`` is the :class:`~openvave.devices.Target` that was looked for; ``seen`` the Tank-G
    pedals the scan did see, strongest first (may be empty).
    """

    def __init__(self, target: Target, seen: Sequence[DeviceInfo] = ()) -> None:
        self.target = target
        self.seen: tuple[DeviceInfo, ...] = tuple(seen)
        if target.nickname:
            message = f"{target.nickname} ({target.identifier}) not found"
        else:
            message = f"device {target.identifier} not found"
        super().__init__(message)


class MultipleDevicesError(OpenvaveError):
    """More than one Tank-G was found and none was selected."""

    exit_code = 4

    def __init__(self, candidates: Sequence[DeviceInfo]) -> None:
        self.candidates: tuple[DeviceInfo, ...] = tuple(candidates)
        super().__init__(f"{len(self.candidates)} pedals found; select one with --device")


class ConfigError(OpenvaveError):
    """A problem with the known pedals or their file (spec 005, exit code 2).

    ``reason`` is a stable code: ``invalid_file`` (the file cannot be read or does not follow
    ``devices-file.schema.json``), ``unknown_nickname`` (a nickname given to ``--device`` /
    ``OPENVAVE_DEVICE`` that no known pedal has), ``bad_nickname`` (not ``[A-Za-z0-9_-]{1,32}``,
    or shaped like an identifier), ``nickname_in_use`` (another pedal has it) and
    ``unknown_device`` (no known pedal with that nickname or identifier). ``path`` is the file
    concerned, when there is one; ``problem`` the message without the path. ``str(error)`` is
    ``"<path>: <problem>"`` when ``path`` is set.
    """

    exit_code = 2

    def __init__(self, problem: str, *, reason: str, path: Path | None = None) -> None:
        self.problem = problem
        self.reason = reason
        self.path = path
        super().__init__(f"{path}: {problem}" if path is not None else problem)


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
    ``wrong_command``, ``echo_mismatch``, ``short_data``, ``bad_identity``, ``backup_mismatch``
    (a backup whose whole-image read differs from its single reads), and ``nak`` for
    :class:`WriteNakError`); ``detail`` narrows it where useful (e.g. which echo field
    mismatched).
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
    """Attempt to encode a frame outside the command allowlist (programming error).

    Allowed: ``0x11``, ``0x23``, and ``0x22`` only to an allowlisted write target (spec 003 R2).
    """

    exit_code = 1


class WriteRefusedError(UnsafeCommandError):
    """A write was refused before anything was sent (spec 003 FR-009/010/014/015/017).

    ``reason`` is one of ``out_of_range``, ``untested_firmware``, ``experimental_required``,
    ``edits_would_be_discarded``, ``unknown_field``, and since spec 004 ``tuner_mode``,
    ``bypassed``, ``unrecognised_state``, ``type_required`` (a typed knob given a position
    without a type while it sits between two types), ``edit_mode`` (bypass on / off, save or
    restore in edit mode), ``not_bypassed`` (bypass off on a pedal that is not bypassed),
    ``unsafe_required`` (save or restore without ``unsafe=True``) and ``firmware_mismatch`` (a
    backup file from another firmware, without ``experimental=True``). ``not_edit_mode`` (0.3.0)
    is no longer raised.
    """

    exit_code = 1

    def __init__(self, reason: str, message: str | None = None) -> None:
        self.reason = reason
        super().__init__(message or reason)


class WriteNakError(ProtocolError):
    """The pedal answered a write with something other than the ACK (FR-011).

    ``reply`` holds the raw reply frame; it is never retried.
    """

    def __init__(self, reply: bytes) -> None:
        self.reply = bytes(reply)
        super().__init__(
            "nak", self.reply.hex(" "), f"write not acknowledged: reply {self.reply.hex(' ')}"
        )


class WriteNotAppliedError(OpenvaveError):
    """The write was acknowledged but the re-read does not show it (FR-012, exit code 8).

    ``result`` is the :class:`~openvave.models.WriteResult` with ``applied`` false; ``None`` when
    a save/restore read-back failed, whose details are in ``sequence`` instead, or a batch edit
    stopped, whose details are in ``edit``.
    """

    exit_code = 8

    def __init__(
        self,
        result: WriteResult | None,
        message: str | None = None,
        *,
        sequence: SequenceResult | None = None,
    ) -> None:
        self.result = result
        self.sequence = sequence
        if message is None:
            action = result.plan.action if result is not None else "write"
            message = f"{action}: acknowledged but not applied (re-read differs)"
        super().__init__(message)
