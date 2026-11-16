"""In-memory transport that replays a capture: for tests and simulations.

Capture format: ``captures/README.md``. This module parses captures itself so library users need
nothing from the openvave test suite.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from openvave.errors import ConnectionLostError


def _label(text: str) -> str:
    return " ".join(text.split())


Replies = bytes | Sequence[bytes]
"""One reply frame, or several served in order (the last one then repeats)."""


def _reply_list(label: str, replies: Replies) -> list[bytes]:
    frames = (
        [bytes(replies)] if isinstance(replies, bytes | bytearray) else [bytes(r) for r in replies]
    )
    if not frames:
        raise ValueError(f"no reply for label {label!r}")
    return frames


class FakeTransport:
    """Answers each known request frame with its scripted reply.

    ``script`` maps a label to ``(request frame, reply)``. The reply is one frame, or a sequence
    of frames served in order to successive matching requests; once the sequence is exhausted
    its last frame repeats (ordered replay, used to simulate a pedal whose state changes while
    ``TankG.watch()`` polls it). Options (keyed by label):

    - ``split``: deliver every reply as this many notification chunks.
    - ``drop``: ``{label: k}`` — send no reply to the first ``k`` matching requests (a dropped
      request does not consume a reply).
    - ``disconnect_after``: after this many writes the link is lost; later writes raise
      :class:`ConnectionLostError`.
    - ``replies``: ``{label: reply}`` — reply with this frame (or sequence of frames) instead of
      the scripted one.

    Every frame written is recorded in :attr:`sent`. A request that is not in the script raises
    ``AssertionError`` (the test is wrong, not the pedal).
    """

    def __init__(
        self,
        script: Mapping[str, tuple[bytes, Replies]],
        *,
        split: int | None = None,
        drop: Mapping[str, int] | None = None,
        disconnect_after: int | None = None,
        replies: Mapping[str, Replies] | None = None,
    ) -> None:
        self._replies = {label: _reply_list(label, rx) for label, (_, rx) in script.items()}
        self._labels = {bytes(tx): label for label, (tx, _) in script.items()}
        for option in (drop or {}, replies or {}):
            for label in option:
                if label not in self._replies:
                    raise KeyError(f"unknown label {label!r}")
        for label, override in (replies or {}).items():
            self._replies[label] = _reply_list(label, override)
        self._served: dict[str, int] = {}
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
        replies: Mapping[str, Replies] | None = None,
    ) -> FakeTransport:
        """Build a fake from a capture file (labels are whitespace-normalised).

        Several ``rx`` lines with the same label (e.g. a ``watch`` session record) become an
        ordered reply sequence. Events other than ``tx``/``rx`` are ignored.
        """
        tx: dict[str, bytes] = {}
        rx: dict[str, list[bytes]] = {}
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                record = json.loads(line)
                event = record["event"]
                if event == "tx":
                    label = _label(record["label"])
                    frame = bytes.fromhex(record["hex"])
                    if tx.setdefault(label, frame) != frame:
                        raise ValueError(f"{path}: label {label!r} names two different requests")
                elif event == "rx":
                    label = _label(record["label"])
                    if label not in tx:
                        raise ValueError(f"{path}: rx {label!r} before its tx")
                    rx.setdefault(label, []).append(bytes.fromhex(record["hex"]))
        script: dict[str, tuple[bytes, Replies]] = {label: (tx[label], rx[label]) for label in rx}
        return cls(
            script, split=split, drop=drop, disconnect_after=disconnect_after, replies=replies
        )

    async def open(self) -> None:
        """Mark the fake as connected (nothing else to do)."""
        self.opened = True
        self.closed = False

    def on_notify(self, callback: Callable[[bytes], None]) -> None:
        """Register the callback that receives reply chunks."""
        self._callback = callback

    async def write(self, frame: bytes) -> None:
        """Record ``frame`` in :attr:`sent` and schedule its scripted reply (unless dropped)."""
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
        frames = self._replies[label]
        served = self._served.get(label, 0)
        self._served[label] = served + 1
        self._deliver(frames[min(served, len(frames) - 1)])

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
        """Mark the fake as closed. Idempotent."""
        self.closed = True
