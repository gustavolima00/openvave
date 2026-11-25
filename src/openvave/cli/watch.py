"""``openvave watch``: poll, print and record per-byte changes (contracts/cli.md, research R5/R10).

Read-only: polling goes through :meth:`TankG.watch`, which sends only ``0x23`` reads after the
``0x11`` handshake. The session record is a capture-format JSONL file
(``specs/002-preset-byte-map/contracts/session-record.md``), flushed after every line; its
``tx``/``rx-chunk``/``rx`` lines come from :func:`openvave.trace.trace_hook`.

Labels are read from stdin on a daemon thread (portable; a blocked ``readline`` never delays
exit). A line ``q``/``quit``, Ctrl-C or ``--duration`` stops the watch; EOF only stops reading.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import signal
import sys
import threading
import time
from collections.abc import Callable, Iterator, Mapping
from datetime import date, datetime
from pathlib import Path
from typing import Any, Protocol

from openvave import __version__
from openvave.cli import choice, render
from openvave.errors import ConnectionLostError, OpenvaveError, RequestTimeoutError
from openvave.models import (
    DecodedRegion,
    DeviceIdentity,
    PedalState,
    Region,
    WatchChange,
    WatchStart,
)
from openvave.protocol import classify, decode_frame
from openvave.protocol.frame import QUERY, READ
from openvave.session import MIN_WATCH_INTERVAL, TankG
from openvave.trace import trace_hook
from openvave.transport import Transport

QUIT_WORDS = frozenset({"q", "quit"})
HINT_AFTER = 30.0
HINT = "hint: no preset byte changed in 30 s and the pedal is not in edit mode"
MODE_FIELD = "mode"
"""Global mode byte (byte map, global[3]): 0 edit, 1 normal, 2 tuner."""
EDIT_MODE = 0
TICK = 0.05
"""Seconds between checks of ``--duration`` and the edit-mode hint."""
PLATFORMS = {"darwin": "macOS", "linux": "Linux", "win32": "Windows"}
RECORD_DIR = Path("captures") / "private"

TransportFactory = choice.TransportFactory
"""``(device_id, scan_timeout) -> (transport, device)``, as in :mod:`openvave.cli`."""


class Clock(Protocol):
    """Time source of a watch run (injectable so CLI tests run instantly)."""

    def monotonic(self) -> float: ...

    async def sleep(self, seconds: float) -> None: ...


class SystemClock:
    """The real clock."""

    def monotonic(self) -> float:
        return time.monotonic()

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


class LineSource(Protocol):
    def readline(self) -> str: ...


class UsageError(Exception):
    """Invalid ``watch`` options (exit 2)."""


# -- options --------------------------------------------------------------------------------------


def check_record_path(path: Path) -> None:
    """Refuse a record inside a ``captures/`` folder unless it is under ``captures/private/``."""
    folders = path.resolve().parts[:-1]
    if "captures" not in folders:
        return
    i = len(folders) - 1 - folders[::-1].index("captures")
    if i + 1 >= len(folders) or folders[i + 1] != "private":
        raise UsageError(
            f"--record {path}: raw session records must stay out of git; use a path under "
            "captures/private/ or outside captures/"
        )


def validate(args: argparse.Namespace, now: datetime | None = None) -> None:
    """Check ``watch`` options and set ``args.record_path`` (a :class:`Path` or ``None``)."""
    if not args.interval >= MIN_WATCH_INTERVAL:
        raise UsageError(f"--interval must be at least {MIN_WATCH_INTERVAL:g} s")
    if args.duration is not None and not args.duration > 0:
        raise UsageError("--duration must be greater than 0")
    if args.no_record:
        args.record_path = None
        return
    if args.record is not None:
        path = Path(args.record)
    else:
        path = RECORD_DIR / f"{(now or datetime.now()):%Y%m%d-%H%M%S}-watch.jsonl"
    check_record_path(path)
    args.record_path = path


# -- session record ---------------------------------------------------------------------------


class RecordWriter:
    """Capture-format JSONL; lines before :meth:`open` (the handshake) are buffered."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._fh: Any = None
        self._pending: list[dict[str, Any]] = []

    def open(self, meta: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self.path, "w", encoding="utf-8")
        self._write(meta)
        for record in self._pending:
            self._write(record)
        self._pending = []

    def write(self, record: dict[str, Any]) -> None:
        if self._fh is None:
            self._pending.append(record)
        else:
            self._write(record)

    def _write(self, record: dict[str, Any]) -> None:
        self._fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._fh.flush()

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None


def frame_label(frame: bytes) -> str:
    """Record label of a frame: ``query``, ``global``, ``preset``, ``status`` (or other)."""
    try:
        decoded = decode_frame(frame)
    except OpenvaveError:
        return "unknown"
    if decoded.command == QUERY:
        return "query"
    body = decoded.body
    if decoded.command == READ and len(body) >= 8:
        key = (body[0], int.from_bytes(body[1:5], "little"), int.from_bytes(body[5:8], "little"))
        for region in Region:
            if region.value == key:
                return render.WATCH_REGION_KEYS.get(region, "device info")
    return "unknown"


# -- the run --------------------------------------------------------------------------------------


class WatchRun:
    """State of one ``openvave watch`` invocation (data-model.md "Watch session")."""

    def __init__(
        self,
        *,
        interval: float,
        duration: float | None,
        record: RecordWriter | None,
        json_mode: bool,
        clock: Clock,
    ) -> None:
        self.interval = interval
        self.duration = duration
        self.record = record
        # Shown with "/" on every OS so human and JSON output match across platforms.
        self.record_name = record.path.as_posix() if record is not None else None
        self.json_mode = json_mode
        self.clock = clock
        self.started_at = clock.monotonic()
        self.polling_since: float | None = None
        """Run time when polling began (after connecting): ``--duration`` counts from here."""
        self.stopped = asyncio.Event()
        self.stop_reason: str | None = None
        self.finished = False
        self.begun = False
        self.label: str | None = None
        self.label_at: float | None = None
        self.preset_changed_at: float | None = None
        self.outside_edit_mode: bool | None = None
        self.hinted = False
        self.changes = 0
        self.cycles = 0
        self.pedal_state: PedalState | None = None
        """Last reported state; a bypass-looking cycle is ``loading`` until the next confirms it."""
        self._cycle_data: dict[str, bytes] = {}
        self._previous_data: tuple[bytes, bytes] | None = None

    # time

    def now(self) -> float:
        return self.clock.monotonic() - self.started_at

    def _t(self) -> float:
        return round(self.now(), 4)

    # output

    def _emit(self, line: str) -> None:
        print(line, flush=True)

    def _record(self, record: dict[str, Any]) -> None:
        if self.record is not None:
            self.record.write(record)

    # frames (trace hook)

    def on_frame(self, kind: str, data: bytes) -> None:
        if kind == "rx-stray":
            return
        record: dict[str, Any] = {"t": self._t(), "event": kind}
        label = frame_label(data) if kind in ("tx", "rx") else None
        if label is not None:
            record["label"] = label
        record["hex"] = data.hex(" ")
        if kind == "rx":
            record["cmd"] = data[2]
            if self.begun and label in ("global", "preset"):
                self._cycle_data[label] = data[14:-1]
            if self.begun and label == "status":
                self.cycles += 1
        self._record(record)
        if kind == "rx" and self.begun and label == "status":
            self._end_cycle()

    # pedal state (spec 004 R1, R13)

    def _next_state(self, glob: bytes, preset: bytes) -> PedalState:
        """The state to report: one bypass-looking cycle is ``loading``, two are ``bypass``."""
        state = classify(glob, preset)
        if state.kind != "bypass":
            return state
        confirmed = self.pedal_state is not None and self.pedal_state.kind == "bypass"
        return PedalState(kind="bypass", index=None, bank=state.bank, transient=not confirmed)

    def _state_from(self, regions: Mapping[Region, DecodedRegion]) -> PedalState | None:
        glob, preset = regions.get(Region.GLOBAL), regions.get(Region.CURRENT_PRESET)
        if glob is None or preset is None:
            return None
        return self._next_state(glob.read.data, preset.read.data)

    def _end_cycle(self) -> None:
        """A cycle whose global and preset bytes did not change yields no change event: confirm
        a pending ``loading`` here (the only state that can change without a byte changing)."""
        glob, preset = self._cycle_data.get("global"), self._cycle_data.get("preset")
        self._cycle_data = {}
        if glob is None or preset is None:
            return
        current = (glob, preset)
        unchanged = current == self._previous_data
        self._previous_data = current
        state = self.pedal_state
        if unchanged and state is not None and state.transient and not self.json_mode:
            self._report_state(self._next_state(glob, preset))

    def _report_state(self, state: PedalState | None) -> None:
        if state is None or state == self.pedal_state:
            return
        self.pedal_state = state
        if not self.json_mode:
            self._emit(render.watch_state_line(state, self.now()))

    # lifecycle

    def begin(self, identity: DeviceIdentity, transport: Transport | None) -> None:
        """After the handshake: open the record with its ``meta`` line."""
        self.begun = True
        self.polling_since = self.now()
        if self.record is not None:
            self.record.open(
                {
                    "event": "meta",
                    "firmware": identity.firmware,
                    "device": identity.name,
                    "platform": PLATFORMS.get(sys.platform, sys.platform),
                    "att_mtu": getattr(transport, "att_mtu", None),
                    "date": date.today().isoformat(),
                    "tool": f"openvave watch {__version__}",
                    "interval": self.interval,
                    "sanitized": [],
                }
            )

    def stop(self, reason: str) -> None:
        if self.stop_reason is None:
            self.stop_reason = reason
            self.stopped.set()

    def finish(self, error: OpenvaveError | None) -> None:
        """Write the ``stop`` line and the summary (also after a connection failure)."""
        if error is None:
            reason, message = self.stop_reason or "quit", None
        elif isinstance(error, ConnectionLostError | RequestTimeoutError):
            reason, message = "connection_lost", str(error)
        else:
            reason, message = "protocol_error", str(error)
        self.finished = True
        t = self.now()
        self._record({"t": round(t, 4), "event": "stop", "reason": reason, "error": message})
        if self.record is not None:
            self.record.close()
        if self.json_mode:
            document = render.watch_stop_json(t, reason, message, self.changes, self.cycles)
            self._emit(render.json_line(document))
        else:
            self._emit(render.watch_summary(t, self.changes, self.cycles, self.record_name))

    # events

    def on_line(self, line: str | None) -> None:
        """A stdin line (``None`` = EOF, which only stops label reading)."""
        if line is None or self.finished or self.stop_reason is not None:
            return
        text = line.strip()
        if not text:
            return
        if text in QUIT_WORDS:
            self.stop("quit")
            return
        self.label, self.label_at = text, self.now()
        t = self._t()
        self._record({"t": t, "event": "label", "text": text})
        if self.json_mode:
            self._emit(render.json_line(render.watch_label_json(text, t)))
        else:
            self._emit(render.watch_label_line(text))

    def _track(self, regions: Mapping[Region, DecodedRegion]) -> None:
        decoded = regions.get(Region.GLOBAL)
        if decoded is None:
            return
        for field in decoded.fields:
            if field.entry.name == MODE_FIELD and not field.out_of_range:
                self.outside_edit_mode = field.value != EDIT_MODE

    def on_start(self, event: WatchStart) -> None:
        self._track(event.regions)
        self.pedal_state = self._state_from(event.regions)
        t = self.now()
        if self.json_mode:
            document = render.watch_start_json(
                event, t, self.interval, self.record_name, self.pedal_state
            )
            self._emit(render.json_line(document))
        else:
            for line in render.watch_header(
                event, self.interval, self.record_name, self.pedal_state
            ):
                self._emit(line)

    def on_change(self, event: WatchChange) -> None:
        self._track(event.regions)
        t = self.now()
        self.changes += len(event.changes)
        if any(c.region is Region.CURRENT_PRESET for c in event.changes):
            self.preset_changed_at = t
        for change in event.changes:
            self._record(
                {
                    "t": round(t, 4),
                    "event": "change",
                    "cycle": event.cycle,
                    "region": render.WATCH_REGION_KEYS[change.region],
                    "offset": change.offset,
                    "old": change.old,
                    "new": change.new,
                    "label": self.label,
                }
            )
        state = self._state_from(event.regions)
        named = render.names_shown(self.pedal_state, state or self.pedal_state)
        if self.json_mode:
            if state is not None:
                self.pedal_state = state
            document = render.watch_change_json(event, t, self.label, self.pedal_state, named)
            self._emit(render.json_line(document))
        else:
            for line in render.watch_change_lines(event, t, named):
                self._emit(line)
            self._report_state(state)

    # timing

    def check(self) -> None:
        """``--duration`` elapsed? Time for the edit-mode hint?"""
        now = self.now()
        if self.duration is not None and self._remaining() <= 0:
            self.stop("duration")
        if (
            not self.hinted
            and self.label_at is not None
            and self.outside_edit_mode
            and (self.preset_changed_at is None or self.preset_changed_at < self.label_at)
            and now - self.label_at >= HINT_AFTER
        ):
            self.hinted = True
            print(HINT, file=sys.stderr, flush=True)

    def _remaining(self) -> float:
        """Seconds of ``--duration`` left (infinite without one)."""
        if self.duration is None:
            return float("inf")
        return (
            self.polling_since + self.duration - self.now()
            if self.polling_since is not None
            else self.duration
        )

    async def sleep(self, seconds: float) -> None:
        """The pause between poll cycles; ends the run exactly at ``--duration``."""
        self.check()
        if self.duration is not None:
            remaining = self._remaining()
            if remaining <= seconds:
                await self.clock.sleep(max(remaining, 0.0))
                self.stop("duration")
                await asyncio.Event().wait()  # cancelled by run()
        await self.clock.sleep(seconds)

    async def tick(self) -> None:
        while True:
            await asyncio.sleep(TICK)
            self.check()

    async def poll(self, pedal: TankG) -> None:
        async with contextlib.aclosing(pedal.watch(self.interval, sleep=self.sleep)) as events:
            async for event in events:
                if isinstance(event, WatchStart):
                    self.on_start(event)
                else:
                    self.on_change(event)

    async def until_stopped(self, pedal: TankG) -> OpenvaveError | None:
        """Poll until a stop request or a failure; return the failure, if any."""
        poller = asyncio.create_task(self.poll(pedal))
        ticker = asyncio.create_task(self.tick())
        waiter = asyncio.create_task(self.stopped.wait())
        try:
            await asyncio.wait({poller, waiter}, return_when=asyncio.FIRST_COMPLETED)
        except asyncio.CancelledError:  # Ctrl-C where no signal handler could be installed
            self.stop("interrupt")
        finally:
            for task in (poller, ticker, waiter):
                task.cancel()
            results = await asyncio.gather(poller, ticker, waiter, return_exceptions=True)
        outcome = results[0]
        if isinstance(outcome, OpenvaveError):
            return outcome
        if isinstance(outcome, BaseException) and not isinstance(outcome, asyncio.CancelledError):
            raise outcome
        return None


def _start_reader(
    stdin: LineSource, loop: asyncio.AbstractEventLoop, on_line: Callable[[str | None], None]
) -> None:
    def read() -> None:
        while True:
            try:
                line = stdin.readline()
            except (OSError, ValueError):
                line = ""
            try:
                loop.call_soon_threadsafe(on_line, line or None)
            except RuntimeError:  # the loop is closed: the watch is over
                return
            if not line:
                return

    threading.Thread(target=read, name="openvave-watch-stdin", daemon=True).start()


@contextlib.contextmanager
def _sigint(loop: asyncio.AbstractEventLoop, handler: Callable[[], None]) -> Iterator[None]:
    try:
        loop.add_signal_handler(signal.SIGINT, handler)
    except (NotImplementedError, RuntimeError, ValueError):  # Windows, or not the main thread
        yield
        return
    try:
        yield
    finally:
        loop.remove_signal_handler(signal.SIGINT)


async def run(
    args: argparse.Namespace,
    factory: TransportFactory,
    stdin: LineSource,
    clock: Clock,
) -> int:
    """Connect, watch until stopped, write the ``stop`` line. Re-raises a polling failure after
    recording it (the caller maps it to exit 6 / 7)."""
    path: Path | None = args.record_path
    watch = WatchRun(
        interval=args.interval,
        duration=args.duration,
        record=RecordWriter(path) if path is not None else None,
        json_mode=args.json,
        clock=clock,
    )
    transport: list[Transport] = []

    loop = asyncio.get_running_loop()
    with trace_hook(watch.on_frame):
        async with choice.pedal_session(args, factory, on_transport=transport.append) as pedal:
            watch.begin(pedal.identity, transport[0] if transport else None)
            _start_reader(stdin, loop, watch.on_line)
            with _sigint(loop, lambda: watch.stop("interrupt")):
                error = await watch.until_stopped(pedal)
    watch.finish(error)
    if error is not None:
        raise error
    return 0
