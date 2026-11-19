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
from openvave.protocol.frame import READ, WRITE, decode_frame, encode_frame

ECHO_LEN = 8
MEMORY_TYPE = 4
STORE_ADDRESS = 0
EDIT_BUFFER = 0x10000000
GLOBAL_ADDRESS = 0x20000000
SELECT_BASE = 0xE0000000
BYPASS_BASE = 0xE1000000
COMMIT_ADDRESS = 0xF0000000
LOOPBACK_ADDRESS = 0xD0000000
PRESET_SIZE = 21
STORE_OFFSET = 2
IMAGE_SIZE = STORE_OFFSET + PRESET_SIZE * 36
WRITE_ACK = bytes.fromhex("00 59 00 01 00 00 00 ff")
WRITE_NAK = bytes.fromhex("00 59 00 01 00 00 01 fe")
"""A write reply with status 1 (no NAK has been seen on hardware; any non-zero status is one)."""
HEADER_LEN = 6
FAULT_KINDS = frozenset(
    {
        "knob_block",
        "block_switch",
        "led_colour",
        "preset_select",
        "bypass",
        "loopback",
        "stored_slot",
        "commit",
        "stored_image",
    }
)
FAULT_ACTIONS = frozenset({"nak", "no_reply", "disconnect", "corrupt", "ignore"})


def _write_kind(address: int, length: int) -> str:
    """The write kind of an allowlisted ``(address, length)`` (see ``protocol.writes``)."""
    if address == COMMIT_ADDRESS:
        return "commit"
    if address >= BYPASS_BASE:
        return "bypass"
    if address >= SELECT_BASE:
        return "preset_select"
    if address == LOOPBACK_ADDRESS:
        return "loopback"
    if address >= EDIT_BUFFER:
        if address == EDIT_BUFFER + 4:
            return "knob_block"
        return "led_colour" if address == EDIT_BUFFER + 18 else "block_switch"
    return "stored_image" if length == IMAGE_SIZE else "stored_slot"


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
      :class:`ConnectionLostError`. :meth:`lose_link` drops the link at any moment instead.
    - ``replies``: ``{label: reply}`` — reply with this frame (or sequence of frames) instead of
      the scripted one.
    - ``memory``: ``{address: bytes}`` — type-4 memory blocks. A read (``0x23``) of type 4 that
      lies entirely inside one block and is not in the script is answered with a correct read
      reply built from the block (e.g. the stored-preset image at address 0). Other unscripted
      requests are then left unanswered (the session times out) instead of failing the test.
    - ``chunk_size``: deliver every reply as notification chunks of at most this many bytes
      (182 = what the pedal sends at ATT MTU 185). Exclusive with ``split``.
    - ``apply_writes``: answer unscripted allowlisted writes (``0x22``) with the ACK and apply
      them to ``memory``: edit-buffer writes change the block at ``0x10000000``; stored-slot and
      stored-image writes change the stored area (block at address 0); a commit only increments
      :attr:`commits`; a preset select
      ``i`` copies stored preset ``i`` (block at address 0) into the edit buffer, sets global
      bytes 0–2 (browsed bank, bank, slot) and leaves edit mode (mode 0 → 1). This models the
      pedal as the app describes it; it is not hardware evidence. A bypass write (``0xE1000000 +
      i``) sets the global slot to ``ff`` and zeroes the edit buffer (mode and bank unchanged, as
      in spec 004 check 2); the next select leaves bypass. A loopback write stores its byte in
      the status block at ``0xD0000000`` (which ``memory`` must then hold). Without
      ``apply_writes``, an unscripted write is a test error.
    - ``select_transient``: after each applied preset select, the next this-many global reads
      return slot ``ff`` (the loading state seen once on hardware).
    - ``faults``: ``{write kind: action}`` — the first applied write of that kind (``stored_slot``,
      ``commit``, ``stored_image``, ``preset_select``, …) misbehaves once: ``nak`` (not applied,
      NAK reply), ``no_reply`` (applied, no reply), ``disconnect`` (applied, then the link drops:
      the :meth:`on_disconnect` callback runs and later writes raise
      :class:`ConnectionLostError`), ``corrupt`` (applied with its last data byte inverted, ACK)
      or ``ignore`` (ACK, not applied). Needs ``apply_writes``.

    A request split over several :meth:`write` calls (the BLE transport splits frames longer than
    one Bluetooth write) is reassembled by its length field before it is handled; :attr:`sent`
    holds whole requests.

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
        apply_writes: bool = False,
        select_transient: int = 0,
        faults: Mapping[str, str] | None = None,
    ) -> None:
        if apply_writes and memory is None:
            raise ValueError("apply_writes needs memory")
        for kind, action in (faults or {}).items():
            if kind not in FAULT_KINDS or action not in FAULT_ACTIONS:
                raise ValueError(f"unknown fault {kind!r}: {action!r}")
        if faults and not apply_writes:
            raise ValueError("faults need apply_writes")
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
        self._apply_writes = apply_writes
        self._select_transient = select_transient
        self._transient_left = 0
        self._callback: Callable[[bytes], None] | None = None
        self._lost: Callable[[], None] | None = None
        self._faults = dict(faults or {})
        self._pending = b""
        self.sent: list[bytes] = []
        """Every request written, in order (a split request once, reassembled)."""
        self.commits = 0
        """Applied commit writes (``0xF0000000``)."""
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
        apply_writes: bool = False,
        select_transient: int = 0,
        faults: Mapping[str, str] | None = None,
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
            apply_writes=apply_writes,
            select_transient=select_transient,
            faults=faults,
        )

    async def open(self) -> None:
        """Mark the fake as connected (nothing else to do)."""
        self.opened = True
        self.closed = False

    def on_notify(self, callback: Callable[[bytes], None]) -> None:
        """Register the callback that receives reply chunks."""
        self._callback = callback

    def on_disconnect(self, callback: Callable[[], None]) -> None:
        """Register the callback run when the link drops (a ``disconnect`` fault or
        :meth:`lose_link`)."""
        self._lost = callback

    def lose_link(self) -> None:
        """Simulate a lost link now (the pedal switched off or out of range, spec 005).

        Runs the :meth:`on_disconnect` callback at once and makes later writes raise
        :class:`ConnectionLostError` until the fake is opened again. A no-op when the fake is not
        open (never opened, or already closed or lost)."""
        if not self.opened or self.closed:
            return
        self.closed = True
        lost = self._lost
        if lost is not None:
            lost()

    def _reassemble(self, chunk: bytes) -> bytes | None:
        """A whole request, or ``None`` while a split request is still incomplete."""
        data = self._pending + chunk
        if len(data) >= HEADER_LEN and data[:2] == b"\x00\x59":
            total = HEADER_LEN + int.from_bytes(data[3:6], "little") + 1
            if len(data) < total:
                self._pending = data
                return None
        self._pending = b""
        return data

    async def write(self, frame: bytes) -> None:
        """Record ``frame`` in :attr:`sent` and schedule its scripted reply (unless dropped)."""
        if not self.opened:
            raise AssertionError("FakeTransport.write() before open()")
        if self.closed:
            raise ConnectionLostError("transport closed")
        whole = self._reassemble(bytes(frame))
        if whole is None:
            return
        frame = whole
        if self._disconnect_after is not None and len(self.sent) >= self._disconnect_after:
            self.closed = True
            raise ConnectionLostError("simulated disconnect")
        self.sent.append(frame)
        label = self._labels.get(frame)
        if label is None and self._apply_writes and frame[2:3] == bytes([WRITE]):
            reply = self._apply_write(frame)
            if reply is not None:
                self._deliver(reply)
            return
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

    def _apply_write(self, frame: bytes) -> bytes | None:
        """Apply an allowlisted write to :attr:`_memory`; the reply (``None``: no reply)."""
        from openvave.protocol.writes import allowed_write_body

        assert self._memory is not None
        body = decode_frame(frame).body
        if not allowed_write_body(body):
            raise AssertionError(f"FakeTransport: write outside the allowlist {frame.hex(' ')}")
        address = int.from_bytes(body[1:5], "little")
        data = body[ECHO_LEN:]
        fault = self._faults.pop(_write_kind(address, len(data)), None)
        if fault == "nak":
            return WRITE_NAK
        if fault == "ignore":
            return WRITE_ACK
        if fault == "corrupt" and data:
            data = data[:-1] + bytes([data[-1] ^ 0xFF])
        if address == COMMIT_ADDRESS:
            self.commits += 1
        elif address >= BYPASS_BASE:
            self._bypass()
        elif address >= SELECT_BASE:
            self._select(address - SELECT_BASE)
        else:
            self._poke(address, data)
        if fault == "no_reply":
            return None
        if fault == "disconnect":
            self.closed = True
            lost = self._lost
            if lost is not None:
                asyncio.get_running_loop().call_soon(lost)
            return None
        return WRITE_ACK

    def _block_at(self, address: int, length: int) -> tuple[int, bytes]:
        assert self._memory is not None
        for start, block in self._memory.items():
            if start <= address and address + length <= start + len(block):
                return start, block
        raise AssertionError(f"FakeTransport: no memory at 0x{address:08x} x{length}")

    def _poke(self, address: int, data: bytes) -> None:
        assert self._memory is not None
        start, block = self._block_at(address, len(data))
        at = address - start
        self._memory[start] = block[:at] + data + block[at + len(data) :]

    def _select(self, index: int) -> None:
        stored = STORE_ADDRESS + STORE_OFFSET + PRESET_SIZE * index
        start, image = self._block_at(stored, PRESET_SIZE)
        self._poke(EDIT_BUFFER, image[stored - start : stored - start + PRESET_SIZE])
        _, glob = self._block_at(GLOBAL_ADDRESS, 4)
        mode = 1 if glob[3] == 0 else glob[3]
        bank, slot = divmod(index, 4)
        self._poke(GLOBAL_ADDRESS, bytes([bank, bank, slot, mode]))
        self._transient_left = self._select_transient

    def _bypass(self) -> None:
        self._poke(EDIT_BUFFER, bytes(PRESET_SIZE))
        _, glob = self._block_at(GLOBAL_ADDRESS, 4)
        self._poke(GLOBAL_ADDRESS, glob[:2] + b"\xff" + glob[3:])

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
                if address == GLOBAL_ADDRESS and length == 4 and self._transient_left > 0:
                    self._transient_left -= 1
                    data = data[:2] + b"\xff" + data[3:]
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
