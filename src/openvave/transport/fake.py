"""In-memory transport that replays a capture: for tests and simulations.

Capture format: ``captures/README.md``. This module parses captures itself so library users need
nothing from the openvave test suite.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Mapping
from pathlib import Path

from openvave.errors import ConnectionLostError


def _label(text: str) -> str:
    return " ".join(text.split())


class FakeTransport:
    """Answers each known request frame with its scripted reply.

    ``script`` maps a label to ``(request frame, reply frame)``. Options (keyed by label):

    - ``split``: deliver every reply as this many notification chunks.
    - ``drop``: ``{label: k}`` — send no reply to the first ``k`` matching requests.
    - ``disconnect_after``: after this many writes the link is lost; later writes raise
      :class:`ConnectionLostError`.
    - ``replies``: ``{label: frame}`` — reply with this frame instead of the scripted one.

    Every frame written is recorded in :attr:`sent`. A request that is not in the script raises
    ``AssertionError`` (the test is wrong, not the pedal).
    """

    def __init__(
        self,
        script: Mapping[str, tuple[bytes, bytes]],
        *,
        split: int | None = None,
        drop: Mapping[str, int] | None = None,
        disconnect_after: int | None = None,
        replies: Mapping[str, bytes] | None = None,
    ) -> None:
        self._replies = {label: rx for label, (_, rx) in script.items()}
        self._labels = {tx: label for label, (tx, _) in script.items()}
        for option in (drop or {}, replies or {}):
            for label in option:
                if label not in self._replies:
                    raise KeyError(f"unknown label {label!r}")
        self._replies.update(replies or {})
        self._drop = dict(drop or {})
        self._split = split
        self._disconnect_after = disconnect_after
        self._callback: Callable[[bytes], None] | None = None
        self.sent: list[bytes] = []
        """Every frame written, in order."""
        self.opened = False
        self.closed = False

    @classmethod
    def from_capture(
        cls,
        path: str | Path,
        *,
        split: int | None = None,
        drop: Mapping[str, int] | None = None,
        disconnect_after: int | None = None,
        replies: Mapping[str, bytes] | None = None,
    ) -> FakeTransport:
        """Build a fake from a capture file (labels are whitespace-normalised)."""
        script: dict[str, tuple[bytes, bytes]] = {}
        tx: dict[str, bytes] = {}
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                record = json.loads(line)
                event = record["event"]
                if event == "tx":
                    tx[_label(record["label"])] = bytes.fromhex(record["hex"])
                elif event == "rx":
                    label = _label(record["label"])
                    script[label] = (tx[label], bytes.fromhex(record["hex"]))
        return cls(
            script, split=split, drop=drop, disconnect_after=disconnect_after, replies=replies
        )

    async def open(self) -> None:
        self.opened = True
        self.closed = False

    def on_notify(self, callback: Callable[[bytes], None]) -> None:
        self._callback = callback

    async def write(self, frame: bytes) -> None:
        frame = bytes(frame)
        if not self.opened:
            raise AssertionError("FakeTransport.write() before open()")
        if self.closed:
            raise ConnectionLostError("transport closed")
        if self._disconnect_after is not None and len(self.sent) >= self._disconnect_after:
            self.closed = True
            raise ConnectionLostError("simulated disconnect")
        self.sent.append(frame)
        label = self._labels.get(frame)
        if label is None:
            raise AssertionError(f"FakeTransport: unexpected request {frame.hex(' ')}")
        if self._drop.get(label, 0) > 0:
            self._drop[label] -= 1
            return
        self._deliver(self._replies[label])

    def _deliver(self, reply: bytes) -> None:
        callback = self._callback
        if callback is None:
            return
        n = self._split or 1
        size, extra = divmod(len(reply), n)
        loop = asyncio.get_running_loop()
        pos = 0
        for i in range(n):
            step = size + (1 if i < extra else 0)
            loop.call_soon(callback, reply[pos : pos + step])
            pos += step

    async def close(self) -> None:
        self.closed = True
