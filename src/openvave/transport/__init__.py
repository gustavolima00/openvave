"""Transports carrying frames to and from the pedal (contracts/library-api.md)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, runtime_checkable


@runtime_checkable
class Transport(Protocol):
    """A byte pipe to one pedal: ``ae41`` for writes, ``ae42`` notifications for replies."""

    async def open(self) -> None:
        """Connect and enable notifications."""

    async def write(self, frame: bytes) -> None:
        """Write one frame (write-without-response to ``ae41``)."""

    def on_notify(self, callback: Callable[[bytes], None]) -> None:
        """Register the callback receiving each ``ae42`` notification chunk."""

    async def close(self) -> None:
        """Disconnect. Idempotent."""


__all__ = ["Transport"]
