"""In-memory transport that replays a capture: for tests and simulations.

Capture format: ``captures/README.md``. This module parses captures itself so library users need
nothing from the openvave test suite.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from openvave.errors import ConnectionLostError, ProtocolError
from openvave.protocol.frame import READ, decode_frame, encode_frame

ECHO_LEN = 8
MEMORY_TYPE = 4


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
    - ``memory``: ``{address: bytes}`` — type-4 memory blocks. A read (``0x23``) of type 4 that
      lies entirely inside one block and is not in the script is answered with a correct read
      reply built from the block (e.g. the stored-preset image at address 0). Other unscripted
      requests are then left unanswered (the session times out) instead of failing the test.
    - ``chunk_size``: deliver every reply as notification chunks of at most this many bytes
      (182 = what the pedal sends at ATT MTU 185). Exclusive with ``split``.

    Every frame written is recorded in :attr:`sent`. Without ``memory``, a request that is not in
    the script raises ``AssertionError`` (the test is wrong, not the pedal). Scripted labels
    always take precedence over ``memory``.
    """

    def __init__(
        self,
        script: Mapping[str, tuple[bytes, Replies]],
        *,
        split: int | None = None,
        drop: Mapping[str, int] | None = None,
        disconnect_after: int | None = None,
        replies: Mapping[str, Replies] | None = None,
        memory: Mapping[int, bytes] | None = None,
        chunk_size: int | None = None,
    ) -> None:
        if chunk_size is not None and (chunk_size < 1 or split is not None):
            raise ValueError("chunk_size must be >= 1 and cannot be combined with split")
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
        self._chunk_size = chunk_size
        self._memory = (
            None if memory is None else {addr: bytes(block) for addr, block in memory.items()}
        )
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
        memory: Mapping[int, bytes] | None = None,
        chunk_size: int | None = None,
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
            script,
            split=split,
            drop=drop,
            disconnect_after=disconnect_after,
            replies=replies,
            memory=memory,
            chunk_size=chunk_size,
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
        if label is None and self._memory is not None:
            reply = self._memory_reply(frame)
            if reply is not None:
                self._deliver(reply)
            return
        if label is None:
            raise AssertionError(f"FakeTransport: unexpected request {frame.hex(' ')}")
        if self._drop.get(label, 0) > 0:
            self._drop[label] -= 1
            return
        frames = self._replies[label]
        served = self._served.get(label, 0)
        self._served[label] = served + 1
        self._deliver(frames[min(served, len(frames) - 1)])

    def _memory_reply(self, frame: bytes) -> bytes | None:
        """A read reply built from :attr:`_memory`, or ``None`` if the request is not covered."""
        assert self._memory is not None
        try:
            decoded = decode_frame(frame)
        except ProtocolError:  # malformed requests are simply not answered
            return None
        body = decoded.body
        if decoded.command != READ or len(body) != ECHO_LEN or body[0] != MEMORY_TYPE:
            return None
        address = int.from_bytes(body[1:5], "little")
        length = int.from_bytes(body[5:8], "little")
        for start, block in self._memory.items():
            if start <= address and address + length <= start + len(block):
                data = block[address - start : address - start + length]
                return encode_frame(READ, body + data)
        return None

    def _deliver(self, reply: bytes) -> None:
        callback = self._callback
        if callback is None:
            return
        loop = asyncio.get_running_loop()
        if self._chunk_size is not None:
            for start in range(0, len(reply), self._chunk_size):
                loop.call_soon(callback, reply[start : start + self._chunk_size])
            return
        n = self._split or 1
        size, extra = divmod(len(reply), n)
        pos = 0
        for i in range(n):
            step = size + (1 if i < extra else 0)
            loop.call_soon(callback, reply[pos : pos + step])
            pos += step

    async def close(self) -> None:
        """Mark the fake as closed. Idempotent."""
        self.closed = True
