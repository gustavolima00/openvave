"""Hex trace of every frame on logger ``openvave.trace`` at DEBUG (FR-018), plus frame hooks.

Silent unless a handler is attached and the logger is enabled for DEBUG (the CLI's ``--trace``).
Format: ``TX <hex>``, ``RX chunk <hex>`` per notification, ``RX <hex>`` per reassembled frame.

:func:`trace_hook` registers a callback that sees the same frames (``"tx"``, ``"rx-chunk"``,
``"rx"``, ``"rx-stray"``); ``openvave watch`` uses it to write its session record. Hooks only
observe: they never change what is sent.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager

logger = logging.getLogger("openvave.trace")

TraceHook = Callable[[str, bytes], None]
"""``(kind, data)`` with kind ``"tx"``, ``"rx-chunk"``, ``"rx"`` or ``"rx-stray"``."""

_hooks: list[TraceHook] = []


@contextmanager
def trace_hook(hook: TraceHook) -> Iterator[None]:
    """Call ``hook`` for every traced frame while the ``with`` block runs."""
    _hooks.append(hook)
    try:
        yield
    finally:
        _hooks.remove(hook)


def _emit(kind: str, data: bytes) -> None:
    for hook in tuple(_hooks):
        hook(kind, data)


def _hex(data: bytes) -> str:
    return data.hex(" ")


def trace_tx(frame: bytes) -> None:
    _emit("tx", frame)
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("TX %s", _hex(frame))


def trace_rx_chunk(chunk: bytes) -> None:
    _emit("rx-chunk", chunk)
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("RX chunk %s", _hex(chunk))


def trace_rx(frame: bytes) -> None:
    _emit("rx", frame)
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("RX %s", _hex(frame))


def trace_rx_stray(chunk: bytes) -> None:
    """Bytes that could not start a frame (ignored by the session)."""
    _emit("rx-stray", chunk)
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("RX stray %s", _hex(chunk))
