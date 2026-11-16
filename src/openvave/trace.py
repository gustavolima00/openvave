"""Hex trace of every frame on logger ``openvave.trace`` at DEBUG (FR-018).

Silent unless a handler is attached and the logger is enabled for DEBUG (the CLI's ``--trace``).
Format: ``TX <hex>``, ``RX chunk <hex>`` per notification, ``RX <hex>`` per reassembled frame.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("openvave.trace")


def _hex(data: bytes) -> str:
    return data.hex(" ")


def trace_tx(frame: bytes) -> None:
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("TX %s", _hex(frame))


def trace_rx_chunk(chunk: bytes) -> None:
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("RX chunk %s", _hex(chunk))


def trace_rx(frame: bytes) -> None:
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("RX %s", _hex(frame))


def trace_rx_stray(chunk: bytes) -> None:
    """Bytes that could not start a frame (ignored by the session)."""
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("RX stray %s", _hex(chunk))
