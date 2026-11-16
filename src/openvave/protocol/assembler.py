"""Reassemble ``ae42`` notification chunks into complete frames (data-model.md).

Multi-notification reassembly is ``observed`` (app code), not yet seen on hardware.
"""

from __future__ import annotations

from collections.abc import Callable

from openvave.protocol.frame import HEADER_LEN, MARKER, body_length


class FrameAssembler:
    """Feed notification chunks; get back complete frames in order.

    Bytes that cannot start a frame (no ``00 59`` marker) are passed to ``on_stray`` and dropped.
    """

    def __init__(self, on_stray: Callable[[bytes], None] | None = None) -> None:
        self._buf = bytearray()
        self._on_stray = on_stray

    @property
    def pending(self) -> int:
        """Number of buffered bytes of an incomplete frame."""
        return len(self._buf)

    def reset(self) -> None:
        """Discard any partial frame (new request or timeout)."""
        self._buf.clear()

    def feed(self, chunk: bytes) -> list[bytes]:
        self._buf.extend(chunk)
        frames: list[bytes] = []
        while self._buf:
            head = bytes(self._buf[: len(MARKER)])
            if head != MARKER[: len(head)]:
                self._stray()
                break
            if len(self._buf) < HEADER_LEN:
                break
            total = HEADER_LEN + body_length(self._buf) + 1
            if len(self._buf) < total:
                break
            frames.append(bytes(self._buf[:total]))
            del self._buf[:total]
        return frames

    def _stray(self) -> None:
        stray = bytes(self._buf)
        self._buf.clear()
        if self._on_stray is not None:
            self._on_stray(stray)
