"""Helpers for ``watch`` tests: changed-data sequences, a fake clock, scripted stdin (T017–T021).

Changed-data sequences start from the fw96 capture and apply :func:`with_region_data` (checksum
recomputed), so no reply frame is ever typed by hand (FR-022). A *cycle* is a mapping
``{"global" | "preset" | "status": {offset: value}}`` of changes against the fw96 baseline (not
against the previous cycle); ``{}`` is the unchanged baseline.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from openvave.transport.fake import FakeTransport
from tests.support.captures import (
    DEVICE_INFO,
    FW96_CONNECT,
    GLOBAL,
    PRESET,
    QUERY,
    STATUS,
    load_capture,
)
from tests.support.mutations import with_region_data

BASE = load_capture(FW96_CONNECT)
REGION_LABELS = {"global": GLOBAL, "preset": PRESET, "status": STATUS}
"""Short region key (as in watch records) → label in the fw96 connect capture."""
WATCH_ORDER = ("global", "preset", "status")

Cycle = Mapping[str, Mapping[int, int]]


def region_reply(key: str, changes: Mapping[int, int] | None = None) -> bytes:
    """The fw96 reply for region ``key`` with ``changes`` applied (checksum recomputed)."""
    frame = BASE.rx(REGION_LABELS[key])
    for offset, value in (changes or {}).items():
        frame = with_region_data(frame, offset, value)
    return frame


def watch_script(cycles: Sequence[Cycle]) -> dict[str, tuple[bytes, bytes | list[bytes]]]:
    """A :class:`FakeTransport` script serving one reply per cycle (the last one repeats)."""
    script: dict[str, tuple[bytes, bytes | list[bytes]]] = {
        QUERY: (BASE.tx(QUERY), BASE.rx(QUERY)),
        DEVICE_INFO: (BASE.tx(DEVICE_INFO), BASE.rx(DEVICE_INFO)),
    }
    for key in WATCH_ORDER:
        label = REGION_LABELS[key]
        script[label] = (BASE.tx(label), [region_reply(key, c.get(key)) for c in cycles])
    return script


def watch_fake(cycles: Sequence[Cycle], **options: Any) -> FakeTransport:
    return FakeTransport(watch_script(cycles), **options)


def write_watch_capture(path: Path, cycles: Sequence[Cycle]) -> Path:
    """Write a capture with repeated labels (``query`` then ``global``/``preset``/``status`` per
    cycle), in the watch record format."""
    lines: list[dict[str, Any]] = [
        {**BASE.meta, "tool": "tests.support.watch", "sanitized": []},
    ]
    t = 0.0

    def pair(label: str, tx: bytes, rx: bytes) -> None:
        nonlocal t
        t += 0.05
        lines.append({"t": round(t, 4), "event": "tx", "label": label, "hex": tx.hex(" ")})
        lines.append({"t": round(t, 4), "event": "rx-chunk", "hex": rx.hex(" ")})
        lines.append(
            {"t": round(t, 4), "event": "rx", "label": label, "hex": rx.hex(" "), "cmd": rx[2]}
        )

    pair("query", BASE.tx(QUERY), BASE.rx(QUERY))
    for cycle in cycles:
        for key in WATCH_ORDER:
            pair(key, BASE.tx(REGION_LABELS[key]), region_reply(key, cycle.get(key)))
    path.write_text("".join(json.dumps(line) + "\n" for line in lines), encoding="utf-8")
    return path


class SleepRecorder:
    """Injected ``sleep`` that records its arguments and returns at once."""

    def __init__(self) -> None:
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)
        await asyncio.sleep(0)


class FakeClock:
    """CLI clock: ``sleep`` advances the time instantly (tests run in milliseconds)."""

    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.now += max(seconds, 0.0)
        await asyncio.sleep(0)


class ScriptedStdin:
    """A stdin whose lines are released once the fake transport has seen enough writes.

    ``lines`` are ``(write_count, text)``: the line becomes readable when the fake has written
    ``write_count`` frames. After the last line, ``readline`` returns ``""`` (EOF).
    """

    def __init__(self, lines: Sequence[tuple[int, str]] = ()) -> None:
        self._lines = list(lines)
        self._cond = threading.Condition()
        self._count = 0
        self._next = 0
        self._entries = 0
        self._closed = False

    def readline(self) -> str:
        with self._cond:
            self._entries += 1
            self._cond.notify_all()
            if self._next >= len(self._lines):
                return ""
            at, text = self._lines[self._next]
            self._cond.wait_for(lambda: self._count >= at or self._closed)
            if self._closed:
                return ""
            self._next += 1
            self._cond.notify_all()
            return text + "\n"

    def written(self, count: int) -> None:
        with self._cond:
            self._count = count
            self._cond.notify_all()

    def close(self) -> None:
        with self._cond:
            self._closed = True
            self._cond.notify_all()

    def _pending(self) -> bool:
        """A released line not yet handed over to the event loop."""
        with self._cond:
            if self._closed:
                return False
            releasable = self._next < len(self._lines) and self._lines[self._next][0] <= self._count
            # The reader hands a line to the loop, then calls readline() again.
            handed_over = self._entries > self._next
            return releasable or not handed_over

    async def settle(self, timeout: float = 2.0) -> None:
        """Wait until every released line reached the event loop and was processed."""
        deadline = time.monotonic() + timeout
        while self._pending():
            if time.monotonic() > deadline:
                raise AssertionError("scripted stdin: the CLI did not read the released line")
            await asyncio.sleep(0.001)
        for _ in range(5):
            await asyncio.sleep(0)


class GatedFake(FakeTransport):
    """A :class:`FakeTransport` that releases scripted stdin lines and runs hooks per write."""

    def __init__(
        self,
        script: Mapping[str, tuple[bytes, bytes | Sequence[bytes]]],
        stdin: ScriptedStdin | None = None,
        hooks: Mapping[int, Callable[[], None]] | None = None,
        **options: Any,
    ) -> None:
        super().__init__(script, **options)
        self.stdin = stdin
        self.hooks = dict(hooks or {})

    async def write(self, frame: bytes) -> None:
        await super().write(frame)
        count = len(self.sent)
        hook = self.hooks.get(count)
        if hook is not None:
            hook()
        if self.stdin is not None:
            self.stdin.written(count)
            if count > 1:  # the reader starts after the handshake
                await self.stdin.settle()

    async def close(self) -> None:
        await super().close()
        if self.stdin is not None:
            self.stdin.close()


def cycle_write(cycle: int) -> int:
    """Write count of the first request (global) of watch cycle ``cycle`` (1-based)."""
    return 1 + 3 * (cycle - 1) + 1
