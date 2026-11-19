"""Library errors as MCP tool errors (spec 006 research R5, contracts/tools.md §Errors).

A tool error's text is ``<kind>: <message>``, then the CLI's own lines for the same error
(``seen:`` pedals, candidates, ``hint:`` …), then ``partial: <JSON>`` when the error carries the
result of a batch or sequence stopped midway. The server keeps running after any of them.
"""

from __future__ import annotations

import contextlib
import json
import logging
from collections.abc import Callable, Iterator
from typing import Any

from mcp.server.mcpserver.exceptions import ToolError

from openvave.cli import error_text, report_lines
from openvave.errors import (
    BluetoothUnavailableError,
    ConfigError,
    ConnectionLostError,
    HandshakeError,
    MultipleDevicesError,
    NoDeviceFoundError,
    OpenvaveError,
    ProtocolError,
    RequestTimeoutError,
    TargetNotFoundError,
    WriteNakError,
    WriteNotAppliedError,
    WriteRefusedError,
)

logger = logging.getLogger("openvave.mcp")

_KINDS: tuple[tuple[type[OpenvaveError], str], ...] = (
    (TargetNotFoundError, "target_not_found"),
    (NoDeviceFoundError, "no_device_found"),
    (MultipleDevicesError, "multiple_devices"),
    (ConfigError, "config_error"),
    (BluetoothUnavailableError, "bluetooth_unavailable"),
    (ConnectionLostError, "connection_lost"),
    (RequestTimeoutError, "timeout"),
    (HandshakeError, "handshake_failed"),
    (WriteNakError, "write_nak"),
    (WriteNotAppliedError, "write_not_applied"),
    (ProtocolError, "protocol_error"),
)


class InvalidValue(ValueError):
    """A tool argument that cannot be used (``invalid_value``); nothing was sent."""

    kind = "invalid_value"


class UnknownField(ValueError):
    """A ``pedal_set`` field that is not writable (``unknown_field``); nothing was sent."""

    kind = "unknown_field"


class InvalidFile(ValueError):
    """A backup file name that cannot be used (``invalid_file``); nothing was read."""

    kind = "invalid_file"


class Declined(Exception):
    """The owner declined (or cancelled) the confirmation prompt (``declined_by_owner``)."""

    kind = "declined_by_owner"


def kind_of(err: BaseException) -> str:
    """The stable ``kind`` of an error (contracts/tools.md §Errors)."""
    if isinstance(err, WriteRefusedError):
        return err.reason
    if isinstance(err, InvalidValue | UnknownField | InvalidFile | Declined):
        return err.kind
    for cls, kind in _KINDS:
        if isinstance(err, cls):
            return kind
    if isinstance(err, OpenvaveError):
        return "refused"
    if isinstance(err, ValueError):
        return "invalid_value"
    return "internal"


Partial = Callable[[OpenvaveError], dict[str, Any] | None]
"""Builds the ``partial`` document of an error raised mid-batch / mid-sequence (or ``None``)."""


def error_message(err: BaseException, partial: Partial | None = None) -> str:
    """The full text of the tool error for ``err``."""
    kind = kind_of(err)
    if isinstance(err, OpenvaveError):
        lines = [f"{kind}: {error_text(err)}", *(line.strip() for line in report_lines(err))]
        document = partial(err) if partial is not None else None
        if document is not None:
            lines.append("partial: " + json.dumps(document, separators=(",", ":")))
    elif kind == "internal":
        lines = [f"internal: unexpected {type(err).__name__}: {err}"]
    else:
        lines = [f"{kind}: {err}"]
    return "\n".join(lines)


@contextlib.contextmanager
def tool_errors(on_error: Callable[[str], None], partial: Partial | None = None) -> Iterator[None]:
    """Turn any exception raised inside into a :class:`ToolError`; ``on_error`` gets the first
    line (the holder's ``last_error``). ``ToolError`` raised inside passes through."""
    try:
        yield
    except ToolError:
        raise
    except Exception as err:
        message = error_message(err, partial)
        if kind_of(err) == "internal":
            logger.exception("unexpected error in a tool call")
        on_error(message.splitlines()[0])
        raise ToolError(message) from err


__all__ = [
    "Declined",
    "InvalidFile",
    "InvalidValue",
    "UnknownField",
    "error_message",
    "kind_of",
    "tool_errors",
]
