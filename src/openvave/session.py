"""``TankG``: one session with a pedal (data-model.md, research R9; spec 003 research R5).

Lifecycle: open transport → enable notifications → settle 200 ms → handshake (``0x11``, up to 3
attempts) → reads (``0x23``) → close. Requests are strictly sequential. The transport is always
closed on exit, whatever happened.

:meth:`TankG.watch` is the only polling API: :meth:`~TankG.read` and :meth:`~TankG.snapshot` read
once, and nothing polls unless a caller iterates ``watch()`` (spec 002 FR-001/FR-003).

Writes (spec 003) go through one guarded path: :meth:`~TankG.set_field` and
:meth:`~TankG.select_preset` build the same :class:`~openvave.models.WritePlan` as
:meth:`~TankG.plan_set` / :meth:`~TankG.plan_select` (reads only), refuse unless every check
passes, send at most one allowlisted ``0x22`` frame, check the ACK and re-read to verify. A write
is never retried.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncGenerator, Awaitable, Callable, Iterable
from datetime import UTC, datetime
from types import TracebackType

from openvave.errors import (
    ConnectionLostError,
    HandshakeError,
    ProtocolError,
    RequestTimeoutError,
    WriteNotAppliedError,
    WriteRefusedError,
)
from openvave.models import (
    Backup,
    DecodedRegion,
    DeviceIdentity,
    DeviceInfo,
    DeviceSnapshot,
    PedalState,
    Region,
    RegionRead,
    WatchChange,
    WatchEvent,
    WatchStart,
    WritePlan,
    WriteResult,
)
from openvave.protocol import (
    FrameAssembler,
    build_query,
    build_read,
    build_storage_read,
    build_write,
    classify,
    decode_frame,
    decode_region,
    diff,
    parse_identity,
    parse_read_reply,
    parse_storage_reply,
    parse_write_reply,
)
from openvave.protocol.bytemap import REVERB_SECTION_STEPS, TYPED_FIELDS, type_parts, type_raw
from openvave.protocol.frame import QUERY
from openvave.protocol.identity import TESTED_FIRMWARE
from openvave.protocol.state import EDIT
from openvave.protocol.storage import EXPECTED_HEADER, PRESET_COUNT, StorageRead, position
from openvave.protocol.writes import (
    LED_LENGTH,
    WRITABLE_FIELDS,
    WritableField,
    WriteTarget,
    message_for,
    rebuild_knob_block,
    sendable_by_default,
)
from openvave.trace import trace_rx, trace_rx_chunk, trace_rx_stray, trace_tx
from openvave.transport import Transport

logger = logging.getLogger("openvave")

SETTLE_DELAY = 0.2
"""Seconds to wait after enabling notifications before the first command (as the app does)."""
HANDSHAKE_ATTEMPTS = 3
DEFAULT_TIMEOUT = 2.0
DEFAULT_SCAN_TIMEOUT = 5.0

SNAPSHOT_ORDER = (Region.DEVICE_INFO, Region.GLOBAL, Region.CURRENT_PRESET, Region.STATUS)
"""Read order of :meth:`TankG.snapshot` (the order the app and the fw96 capture use)."""

WATCH_REGIONS = (Region.GLOBAL, Region.CURRENT_PRESET, Region.STATUS)
"""Regions :meth:`TankG.watch` may poll, and its default (device info never changes)."""
MIN_WATCH_INTERVAL = 0.2
"""Smallest :meth:`TankG.watch` interval in seconds (research R4)."""

Sleep = Callable[[float], Awaitable[object]]

LOADING_SLOT = 0xFF
"""Global byte 2 while a preset loads."""
SELECT_WAIT = 0.1
"""Seconds to wait after a select ACK, and between global re-reads (as the app, R9)."""
SELECT_TRIES = 10
"""Global reads after a select before giving up on slot ``ff``."""
SELECT_SLEEP: Sleep = asyncio.sleep
"""Default sleep of :meth:`TankG.select_preset` (patched by tests)."""
BYPASS_CONFIRM_DELAY = 0.3
"""Seconds between a bypass-looking read and the read that confirms it (spec 004 R1)."""
STATE_SLEEP: Sleep = asyncio.sleep
"""Default sleep of the bypass confirmation (patched by tests)."""

STATE_REFUSALS = {"tuner": "tuner_mode", "bypass": "bypassed", "unrecognised": "unrecognised_state"}
"""Refusal reason of a write attempted in a state that allows none (spec 004 data-model)."""

FieldValue = int | bool | str | tuple[int, int, int] | tuple[str | None, int]
"""A value for :meth:`TankG.set_field`: int (knob/selector raw value), bool or ``on``/``off``
(switch), ``(r, g, b)`` / ``"#rrggbb"`` / ``"r,g,b"`` (``led_colour``), or ``(type, position)``
for a field in :data:`~openvave.protocol.TYPED_FIELDS`: ``("spring", 10)``, or ``(None, 10)``
for position 10 of the type the preset already uses."""

TransportSource = Callable[[], Awaitable[tuple[Transport, DeviceInfo | None]]]
"""Coroutine factory producing the transport to use and, if known, the device it reaches."""


class TankG:
    """A read-only session with one Tank-G.

    Use as an async context manager: ``async with TankG.connect() as pedal`` (BLE) or
    ``async with TankG.over(transport) as pedal`` (any :class:`~openvave.transport.Transport`).
    The handshake runs on enter; :attr:`identity` is available inside the block.
    """

    def __init__(self, source: TransportSource, *, timeout: float = DEFAULT_TIMEOUT) -> None:
        self._source = source
        self._timeout = timeout
        self._transport: Transport | None = None
        self._device: DeviceInfo | None = None
        self._identity: DeviceIdentity | None = None
        self._lock = asyncio.Lock()
        self._assembler = FrameAssembler(on_stray=trace_rx_stray)
        self._waiter: asyncio.Future[bytes] | None = None

    # -- construction -------------------------------------------------------------------------

    @classmethod
    def over(
        cls,
        transport: Transport,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        device: DeviceInfo | None = None,
    ) -> TankG:
        """A session over an already-built transport (e.g. :class:`FakeTransport`)."""

        async def source() -> tuple[Transport, DeviceInfo | None]:
            return transport, device

        return cls(source, timeout=timeout)

    @classmethod
    def connect(
        cls,
        device: str | None = None,
        *,
        scan_timeout: float = DEFAULT_SCAN_TIMEOUT,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> TankG:
        """A session over BLE: scan, pick the single pedal (or ``device``), connect."""
        from openvave.transport.ble import open_ble

        async def source() -> tuple[Transport, DeviceInfo | None]:
            return await open_ble(device, scan_timeout)

        return cls(source, timeout=timeout)

    # -- public state -------------------------------------------------------------------------

    @property
    def identity(self) -> DeviceIdentity:
        """Name and firmware from the handshake. Only available inside ``async with``."""
        if self._identity is None:
            raise RuntimeError("TankG.identity is only available inside 'async with'")
        return self._identity

    @property
    def device(self) -> DeviceInfo | None:
        """The discovered device, or ``None`` when the transport was supplied directly."""
        return self._device

    # -- reads ------------------------------------------------------------------------------

    async def read(self, region: Region) -> RegionRead:
        """Read one of the four known regions (command ``0x23``). Not retried on failure.

        Raises :class:`TypeError` for anything that is not a :class:`Region` member: there is no
        address-based read.
        """
        if not isinstance(region, Region):
            raise TypeError(f"region must be a Region member, not {type(region).__name__}")
        frame = await self._request(build_read(region))
        return parse_read_reply(region, frame)

    async def snapshot(self, *, sleep: Sleep | None = None) -> DeviceSnapshot:
        """Read all four regions in connect order; ``read_at`` is taken after the last read.

        ``pedal_state`` is classified from the global block and edit buffer. When they look like
        bypass, both are read again 300 ms later and the snapshot keeps the second reads (spec
        004 R1, R13). ``sleep`` is injectable for tests.
        """
        regions = {region: await self.read(region) for region in SNAPSHOT_ORDER}
        state = classify(regions[Region.GLOBAL].data, regions[Region.CURRENT_PRESET].data)
        if state.kind == "bypass":
            await (sleep or STATE_SLEEP)(BYPASS_CONFIRM_DELAY)
            regions[Region.GLOBAL] = await self.read(Region.GLOBAL)
            regions[Region.CURRENT_PRESET] = await self.read(Region.CURRENT_PRESET)
            state = classify(regions[Region.GLOBAL].data, regions[Region.CURRENT_PRESET].data)
        return DeviceSnapshot(
            device=self._device,
            identity=self.identity,
            regions=regions,
            read_at=datetime.now(UTC),
            pedal_state=state,
        )

    async def state(self, *, sleep: Sleep | None = None) -> PedalState:
        """The pedal state (spec 004 R1): reads the global block and the edit buffer only.

        A bypass-looking read (slot ``ff``, buffer all zero) is confirmed by a second read of
        both 300 ms later; if that read differs, the state is taken from it (the first one was a
        preset loading). ``sleep`` is injectable for tests.
        """
        state, *_ = await self._read_state(sleep)
        return state

    async def _read_state(
        self, sleep: Sleep | None = None
    ) -> tuple[PedalState, RegionRead, RegionRead, tuple[bytes, ...]]:
        """State, global block, edit buffer and the read frames sent (bypass confirmed)."""
        glob, glob_frame = await self._read_with_frame(Region.GLOBAL)
        buffer, buffer_frame = await self._read_with_frame(Region.CURRENT_PRESET)
        frames: tuple[bytes, ...] = (glob_frame, buffer_frame)
        state = classify(glob.data, buffer.data)
        if state.kind == "bypass":
            await (sleep or STATE_SLEEP)(BYPASS_CONFIRM_DELAY)
            glob, glob_frame = await self._read_with_frame(Region.GLOBAL)
            buffer, buffer_frame = await self._read_with_frame(Region.CURRENT_PRESET)
            frames += (glob_frame, buffer_frame)
            state = classify(glob.data, buffer.data)
        return state, glob, buffer, frames

    async def backup(self) -> Backup:
        """Read every stored preset and cross-check it (read-only, spec 003 research R1).

        Reads the image header, the 36 stored presets one by one, then the whole 758-byte image
        in one request, and checks that the image equals header + presets. Sends only ``0x23``
        reads, one at a time, nothing else and no polling. ``created_at`` is taken after the last
        read. ``warnings`` gets ``unexpected_header`` when the header is not ``a5 5a`` and
        ``untested_firmware`` when the firmware is not in ``TESTED_FIRMWARE``.

        Raises :class:`ProtocolError` with reason ``backup_mismatch`` (detail: the differing
        positions) when the two copies disagree; other read errors propagate unchanged.
        """
        from openvave.backup import stored_preset

        identity = self.identity
        header = await self._storage_read(StorageRead.header())
        presets = tuple(
            [
                stored_preset(i, await self._storage_read(StorageRead.preset(i)), identity.firmware)
                for i in range(PRESET_COUNT)
            ]
        )
        image = await self._storage_read(StorageRead.image())
        warnings: list[str] = []
        if header != EXPECTED_HEADER:
            warnings.append("unexpected_header")
        if identity.firmware_untested:
            warnings.append("untested_firmware")
        return Backup(
            identity=identity,
            created_at=datetime.now(UTC),
            header=header,
            image=image,
            presets=presets,
            warnings=tuple(warnings),
        )

    async def _storage_read(self, target: StorageRead) -> bytes:
        return parse_storage_reply(target, await self._request(build_storage_read(target)))

    # -- writes (spec 003) ---------------------------------------------------------------------

    async def plan_set(
        self,
        field: str,
        value: FieldValue,
        *,
        experimental: bool = False,
        sleep: Sleep | None = None,
    ) -> WritePlan:
        """Plan a one-field change of the edit buffer: reads global and the edit buffer only.

        Allowed in normal and edit mode (spec 004 FR-001); refused in tuner mode
        (``tuner_mode``), bypass (``bypassed``) and any other state (``unrecognised_state``).
        ``plan.refusal`` names what :meth:`set_field` would refuse with the same arguments.
        Raises :class:`WriteRefusedError` (``unknown_field``) for a field that cannot be written
        and :class:`ValueError` for a value of the wrong type or syntax, including a section
        value for a field without observed sections.
        """
        spec = WRITABLE_FIELDS.get(field)
        if spec is None:
            valid = ", ".join(WRITABLE_FIELDS)
            raise WriteRefusedError(
                "unknown_field", f"unknown field {field!r}; writable fields: {valid}"
            )
        typed = _typed_value(spec, value)
        keep_type = typed is not None and typed[0] is None
        wanted = None if keep_type else _field_bytes(spec, value)
        state, glob, buffer, reads = await self._read_state(sleep)
        type_missing = False
        if keep_type:
            assert typed is not None
            current_type, _ = type_parts(field, buffer.data[spec.offset])
            if current_type is None:
                type_missing = True
            else:
                wanted = _field_bytes(spec, type_raw(field, current_type, typed[1]))
        target = spec.target()
        current = buffer.data[spec.offset : spec.offset + len(wanted)] if wanted else b""
        data = b""
        if wanted is not None:
            if spec.kind == "knob_block":
                data = rebuild_knob_block(buffer.data, spec.offset, wanted[0])
            else:
                data = wanted
        refusal = STATE_REFUSALS.get(state.kind)
        if refusal is None and type_missing:
            refusal = "type_required"
        if refusal is None:
            refusal = "out_of_range" if wanted is None else self._gate(target, experimental)
        return WritePlan(
            action=f"set {field}",
            target=target,
            data=data,
            frame=build_write(target, data) if data else b"",
            reads=reads,
            before=buffer,
            global_before=glob,
            no_change=wanted is not None and current == wanted,
            refusal=refusal,
            confidence=message_for(target.kind, target.argument).confidence,
            field=field,
        )

    async def set_field(
        self,
        field: str,
        value: FieldValue,
        *,
        experimental: bool = False,
        sleep: Sleep | None = None,
    ) -> WriteResult:
        """Change one field of the current preset in the edit buffer (never saved).

        Builds :meth:`plan_set`'s plan, raises :class:`WriteRefusedError` if it is refused,
        returns at once (``plan.no_change``, nothing sent) if the value is already set, else
        sends the one write, checks the ACK (:class:`WriteNakError`, exit 7), re-reads the edit
        buffer and global block, and raises :class:`WriteNotAppliedError` (exit 8, carrying the
        result) unless the targeted bytes now equal the request. ``experimental=True`` allows
        messages that are not ``confirmed`` and untested firmware (FR-014/015). Works in normal
        and edit mode (spec 004); the change is never saved (:meth:`reload_preset` discards it).
        """
        plan = await self.plan_set(field, value, experimental=experimental, sleep=sleep)
        self._raise_refusal(plan)
        if plan.no_change:
            return WriteResult(plan, b"", plan.before, plan.global_before, (), applied=True)
        reply = await self._send_once(plan)
        after = await self.read(Region.CURRENT_PRESET)
        glob = await self.read(Region.GLOBAL)
        spec = WRITABLE_FIELDS[field]
        wanted = plan.data
        if spec.kind == "knob_block":
            applied = after.data[4:18] == wanted
        else:
            applied = after.data[spec.offset : spec.offset + len(wanted)] == wanted
        return self._finish(plan, reply, after, glob, applied)

    async def plan_select(
        self, index: int, *, discard_edits: bool = False, experimental: bool = False
    ) -> WritePlan:
        """Plan loading stored preset ``index`` (0–35): reads global and the edit buffer only.

        Raises :class:`ValueError` for an index outside 0–35.
        """
        target = WriteTarget.preset_select(index)
        glob, glob_frame = await self._read_with_frame(Region.GLOBAL)
        buffer, buffer_frame = await self._read_with_frame(Region.CURRENT_PRESET)
        refusal = None
        if glob.data[3] == EDIT and not discard_edits:
            refusal = "edits_would_be_discarded"
        else:
            refusal = self._gate(target, experimental)
        data = b"\x01"
        return WritePlan(
            action=f"select {position(index)}",
            target=target,
            data=data,
            frame=build_write(target, data),
            reads=(glob_frame, buffer_frame),
            before=buffer,
            global_before=glob,
            no_change=False,
            refusal=refusal,
            confidence=message_for(target.kind, target.argument).confidence,
        )

    async def select_preset(
        self,
        index: int,
        *,
        discard_edits: bool = False,
        experimental: bool = False,
        sleep: Sleep | None = None,
    ) -> WriteResult:
        """Load stored preset ``index`` (0–35) with the preset-select write (spec 003 US3).

        In edit mode the pedal's unsaved edits would be lost: refused unless
        ``discard_edits=True``. After the ACK, waits 100 ms, reads global until the slot is not
        ``ff`` (at most 10 reads, 100 ms apart), then reads the edit buffer and stored preset
        ``index``. Applied iff bank/slot match ``index`` and the buffer equals the stored preset;
        otherwise :class:`WriteNotAppliedError`. ``sleep`` is injectable for tests.
        """
        plan = await self.plan_select(index, discard_edits=discard_edits, experimental=experimental)
        self._raise_refusal(plan)
        return await self._run_select(plan, index, sleep or SELECT_SLEEP)

    async def _run_select(self, plan: WritePlan, index: int, wait: Sleep) -> WriteResult:
        """Send a select plan and verify it (shared by select and reload)."""
        reply = await self._send_once(plan)
        glob = plan.global_before
        for _ in range(SELECT_TRIES):
            await wait(SELECT_WAIT)
            glob = await self.read(Region.GLOBAL)
            if glob.data[2] != LOADING_SLOT:
                break
        else:
            buffer = await self.read(Region.CURRENT_PRESET)
            raise WriteNotAppliedError(
                self._result(plan, reply, buffer, glob, applied=False),
                f"{plan.action}: the pedal still reports a loading slot (ff) after "
                f"{SELECT_TRIES} reads",
            )
        after = await self.read(Region.CURRENT_PRESET)
        stored = await self._storage_read(StorageRead.preset(index))
        bank, slot = divmod(index, 4)
        applied = glob.data[1] == bank and glob.data[2] == slot and after.data == stored
        return self._finish(plan, reply, after, glob, applied)

    async def plan_reload(
        self,
        *,
        discard_edits: bool = False,
        experimental: bool = False,
        sleep: Sleep | None = None,
    ) -> WritePlan:
        """Plan discarding unsaved edits: select the loaded preset again (spec 004 R4).

        Reads global, the edit buffer and the loaded stored preset. ``no_change`` when the buffer
        already equals the stored preset (nothing to discard). In edit mode it needs
        ``discard_edits``; in tuner mode it is refused (``tuner_mode``). When the pedal reports
        no loaded slot (bypass, unrecognised state) there is nothing to plan: raises
        :class:`WriteRefusedError` (``bypassed`` / ``unrecognised_state``).
        """
        state, glob, buffer, reads = await self._read_state(sleep)
        if state.index is None:
            reason = STATE_REFUSALS.get(state.kind, "unrecognised_state")
            raise WriteRefusedError(reason, f"refused ({reason}): {self._refusal_text(reason)}")
        index = state.index
        target = WriteTarget.preset_select(index)
        stored_target = StorageRead.preset(index)
        stored_frame = build_storage_read(stored_target)
        stored = parse_storage_reply(stored_target, await self._request(stored_frame))
        refusal = STATE_REFUSALS.get(state.kind)
        if refusal is None and state.kind == "edit" and not discard_edits:
            refusal = "edits_would_be_discarded"
        if refusal is None:
            refusal = self._gate(target, experimental)
        data = b"\x01"
        return WritePlan(
            action=f"reload {position(index)}",
            target=target,
            data=data,
            frame=build_write(target, data),
            reads=(*reads, stored_frame),
            before=buffer,
            global_before=glob,
            no_change=buffer.data == stored,
            refusal=refusal,
            confidence=message_for(target.kind, target.argument).confidence,
        )

    async def reload_preset(
        self,
        *,
        discard_edits: bool = False,
        experimental: bool = False,
        sleep: Sleep | None = None,
    ) -> WriteResult:
        """Discard unsaved edits by selecting the loaded preset again (spec 004 US1, FR-005).

        Builds :meth:`plan_reload`'s plan and raises :class:`WriteRefusedError` if it is refused.
        Nothing to discard (buffer = stored preset): returns at once, nothing sent. Otherwise
        runs the preset-select path of :meth:`select_preset` and verifies that the pedal is on
        the same preset with the buffer equal to the stored bytes. ``sleep`` is injectable.
        """
        wait = sleep or SELECT_SLEEP
        plan = await self.plan_reload(
            discard_edits=discard_edits, experimental=experimental, sleep=sleep
        )
        self._raise_refusal(plan)
        if plan.no_change:
            return WriteResult(plan, b"", plan.before, plan.global_before, (), applied=True)
        index = plan.target.argument
        assert index is not None
        return await self._run_select(plan, index, wait)

    def _gate(self, target: WriteTarget, experimental: bool) -> str | None:
        """Firmware and confidence gate (FR-014/015, research R4)."""
        if experimental:
            return None
        identity = self.identity
        message = message_for(target.kind, target.argument)
        if identity.firmware_untested or identity.firmware not in message.firmware:
            return "untested_firmware"
        if not sendable_by_default(target.kind, target.argument, identity.firmware):
            return "experimental_required"
        return None

    def _raise_refusal(self, plan: WritePlan) -> None:
        reason = plan.refusal
        if reason is None:
            return
        raise WriteRefusedError(reason, f"refused ({reason}): {self._refusal_text(reason, plan)}")

    def _refusal_text(self, reason: str, plan: WritePlan | None = None) -> str:
        action = plan.action if plan is not None else "value"
        messages = {
            "out_of_range": f"{action}: value out of range for this field",
            "untested_firmware": (
                f"firmware {self.identity.firmware} is not covered by a confirmed write gate; "
                "pass --experimental (experimental=True) to send anyway"
            ),
            "edits_would_be_discarded": (
                "the pedal is in edit mode and selecting a preset discards its unsaved edits; "
                "pass --discard-edits (discard_edits=True) to go on anyway"
            ),
            "tuner_mode": "the pedal is in tuner mode; leave the tuner on the pedal first",
            "type_required": (
                f"{plan.field if plan else 'the field'} sits between two types (the module is "
                "off there), so there is no current type to keep; pass a type "
                "(--type, or (type, position) in the library)"
            ),
            "bypassed": (
                "the pedal is bypassed and does not report its loaded slot; select a preset to "
                "leave bypass (openvave preset select <position>)"
            ),
            "unrecognised_state": (
                "the pedal reports a state openvave does not recognise (global block / edit "
                "buffer); check it with openvave info"
            ),
        }
        if reason == "experimental_required" and plan is not None:
            return (
                f"{plan.target.kind} is '{plan.confidence}' in the protocol docs "
                "(Write messages); pass --experimental (experimental=True) to send it"
            )
        return messages.get(reason, reason)

    async def _send_once(self, plan: WritePlan) -> bytes:
        """Send the plan's one write frame and check the ACK. Never retried."""
        reply = await self._request(plan.frame)
        parse_write_reply(reply)
        return reply

    def _result(
        self, plan: WritePlan, reply: bytes, after: RegionRead, glob: RegionRead, *, applied: bool
    ) -> WriteResult:
        changes = diff(plan.global_before, glob) + diff(plan.before, after)
        return WriteResult(plan, reply, after, glob, changes, applied)

    def _finish(
        self, plan: WritePlan, reply: bytes, after: RegionRead, glob: RegionRead, applied: bool
    ) -> WriteResult:
        result = self._result(plan, reply, after, glob, applied=applied)
        if not applied:
            raise WriteNotAppliedError(result)
        return result

    async def _read_with_frame(self, region: Region) -> tuple[RegionRead, bytes]:
        frame = build_read(region)
        return parse_read_reply(region, await self._request(frame)), frame

    def watch(
        self,
        interval: float = 0.5,
        *,
        regions: Iterable[Region] = WATCH_REGIONS,
        cycles: int | None = None,
        sleep: Sleep = asyncio.sleep,
    ) -> AsyncGenerator[WatchEvent, None]:
        """Poll ``regions`` every ``interval`` seconds and yield what changed (read-only).

        Each cycle reads the regions in order with ``0x23`` (one request in flight at a time).
        The first cycle yields a :class:`WatchStart`; later cycles yield one
        :class:`WatchChange` each when at least one byte differs from the previous cycle, and
        nothing otherwise. ``interval`` is the time between cycle starts: a cycle that overruns
        it starts the next one at once (no overlap, no backlog). ``cycles`` stops after that many
        cycles (``None``: until the caller stops iterating). ``sleep`` is injectable for tests.

        Raises :class:`ValueError` (at call time) for ``interval`` < 0.2, ``cycles`` < 1, or
        ``regions`` that are empty, repeated or not among global / current preset / status.
        Errors while polling (e.g. :class:`ConnectionLostError`) propagate out of the iterator.
        """
        if interval < MIN_WATCH_INTERVAL:
            raise ValueError(f"interval must be at least {MIN_WATCH_INTERVAL} s, got {interval}")
        if cycles is not None and cycles < 1:
            raise ValueError(f"cycles must be at least 1, got {cycles}")
        watched = tuple(regions)
        if not watched or len(set(watched)) != len(watched):
            raise ValueError("regions must be a non-empty sequence without repeats")
        for region in watched:
            if region not in WATCH_REGIONS:
                raise ValueError(f"watch() cannot poll {region!r}")
        return self._watch(interval, watched, cycles, sleep)

    async def _watch(
        self,
        interval: float,
        regions: tuple[Region, ...],
        cycles: int | None,
        sleep: Sleep,
    ) -> AsyncGenerator[WatchEvent, None]:
        identity = self.identity
        started = time.monotonic()
        previous: dict[Region, RegionRead] | None = None
        cycle = 0
        while cycles is None or cycle < cycles:
            cycle_start = time.monotonic()
            cycle += 1
            reads = {region: await self.read(region) for region in regions}
            decoded: dict[Region, DecodedRegion] = {
                region: decode_region(read, identity.firmware) for region, read in reads.items()
            }
            t = time.monotonic() - started
            if previous is None:
                yield WatchStart(t=t, identity=identity, regions=decoded)
            else:
                changes = tuple(c for r in regions for c in diff(previous[r], reads[r]))
                if changes:
                    yield WatchChange(t=t, cycle=cycle, changes=changes, regions=decoded)
            previous = reads
            if cycles is not None and cycle >= cycles:
                break
            delay = cycle_start + interval - time.monotonic()
            if delay > 0:
                await sleep(delay)

    # -- context manager ----------------------------------------------------------------------

    async def __aenter__(self) -> TankG:
        transport, self._device = await self._source()
        self._transport = transport
        try:
            transport.on_notify(self._on_notify)
            set_lost = getattr(transport, "on_disconnect", None)
            if callable(set_lost):
                set_lost(self._connection_lost)
            await transport.open()
            await asyncio.sleep(SETTLE_DELAY)
            self._identity = await self._handshake()
        except BaseException:
            await self._close()
            raise
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self._close()

    async def _close(self) -> None:
        waiter, self._waiter = self._waiter, None
        if waiter is not None and not waiter.done():
            waiter.cancel()
        self._assembler.reset()
        transport, self._transport = self._transport, None
        if transport is not None:
            await transport.close()

    # -- protocol -----------------------------------------------------------------------------

    async def _handshake(self) -> DeviceIdentity:
        last: Exception | None = None
        for attempt in range(1, HANDSHAKE_ATTEMPTS + 1):
            try:
                frame = await self._request(build_query())
                decoded = decode_frame(frame)
                if decoded.command != QUERY:
                    raise ProtocolError("wrong_command", f"0x{decoded.command:02x}")
                identity = parse_identity(decoded.body)
            except (RequestTimeoutError, ProtocolError) as err:
                logger.debug("handshake attempt %d/%d failed: %s", attempt, HANDSHAKE_ATTEMPTS, err)
                last = err
                continue
            if identity.firmware_untested:
                tested = ", ".join(str(v) for v in sorted(TESTED_FIRMWARE))
                logger.warning(
                    "firmware %d is untested (tested: %s); byte layouts may differ",
                    identity.firmware,
                    tested,
                )
            return identity
        raise HandshakeError(
            f"handshake failed after {HANDSHAKE_ATTEMPTS} attempts: {last}"
        ) from last

    async def _request(self, frame: bytes) -> bytes:
        """Send one request and wait for the next complete frame (one in flight at a time)."""
        async with self._lock:
            transport = self._transport
            if transport is None:
                raise ConnectionLostError("session is closed")
            self._assembler.reset()
            waiter: asyncio.Future[bytes] = asyncio.get_running_loop().create_future()
            self._waiter = waiter
            try:
                trace_tx(frame)
                await transport.write(frame)
                try:
                    async with asyncio.timeout(self._timeout):
                        return await waiter
                except TimeoutError:
                    raise RequestTimeoutError(
                        f"no reply within {self._timeout:g} s to {frame.hex(' ')}"
                    ) from None
            finally:
                if self._waiter is waiter:
                    self._waiter = None
                self._assembler.reset()

    def _on_notify(self, chunk: bytes) -> None:
        trace_rx_chunk(chunk)
        for frame in self._assembler.feed(chunk):
            trace_rx(frame)
            waiter = self._waiter
            if waiter is not None and not waiter.done():
                waiter.set_result(frame)
            else:
                trace_rx_stray(frame)

    def _connection_lost(self) -> None:
        waiter = self._waiter
        if waiter is not None and not waiter.done():
            waiter.set_exception(ConnectionLostError("the pedal disconnected"))


def _parse_colour(value: FieldValue) -> tuple[int, ...]:
    if isinstance(value, tuple):
        parts = value
    elif isinstance(value, str):
        text = value.strip()
        if len(text) == 7 and text.startswith("#"):
            try:
                return tuple(bytes.fromhex(text[1:]))
            except ValueError:
                pass
        else:
            pieces = text.split(",")
            if len(pieces) == LED_LENGTH and all(p.strip().lstrip("-").isdigit() for p in pieces):
                return tuple(int(p) for p in pieces)
        raise ValueError(f"led_colour must be #rrggbb or r,g,b, got {value!r}")
    else:
        raise ValueError(f"led_colour must be (r, g, b), #rrggbb or r,g,b, got {value!r}")
    if len(parts) != LED_LENGTH or not all(
        isinstance(p, int) and not isinstance(p, bool) for p in parts
    ):
        raise ValueError(f"led_colour must be three integers, got {value!r}")
    return tuple(p for p in parts if isinstance(p, int))


def _typed_value(spec: WritableField, value: FieldValue) -> tuple[str | None, int] | None:
    """``(type, position)`` if ``value`` is a typed value, else ``None``; checked for syntax.

    Raises :class:`ValueError` for a typed value on a field without types, an unknown type, or a
    position that is not an integer 1–40.
    """
    if not (isinstance(value, tuple) and len(value) == 2):
        return None
    type_name, step = value
    if not (type_name is None or isinstance(type_name, str)):
        return None
    if spec.name not in TYPED_FIELDS:
        names = ", ".join(sorted(TYPED_FIELDS))
        raise ValueError(f"{spec.name} has no knob types; fields with types: {names}")
    if isinstance(step, bool) or not isinstance(step, int):
        raise ValueError(f"position must be an integer, got {step!r}")
    if type_name is None:
        if not 1 <= step <= REVERB_SECTION_STEPS:
            raise ValueError(f"position must be 1–{REVERB_SECTION_STEPS}, got {step}")
    else:
        type_raw(spec.name, type_name, step)  # raises for an unknown type or position
    return type_name, step


def _field_bytes(spec: WritableField, value: FieldValue) -> bytes | None:
    """The bytes a field value writes at ``spec.offset``, or ``None`` if out of range.

    Raises :class:`ValueError` for a value of the wrong type or syntax.
    """
    if spec.kind == "led_colour":
        rgb = _parse_colour(value)
        return bytes(rgb) if all(0 <= c <= 0xFF for c in rgb) else None
    typed = _typed_value(spec, value)
    if typed is not None:
        type_name, step = typed
        assert type_name is not None, "resolve the current type before _field_bytes"
        value = type_raw(spec.name, type_name, step)
    entry = spec.entry
    assert entry is not None
    if spec.kind == "block_switch":
        if isinstance(value, str) and value.lower() in ("on", "off"):
            value = value.lower() == "on"
        if not isinstance(value, bool):
            raise ValueError(f"{spec.name} takes on/off (True/False), got {value!r}")
        raw = entry.on_value if value else entry.off_value
        assert raw is not None
        return bytes([raw])
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{spec.name} takes an integer, got {value!r}")
    assert entry.min is not None and entry.max is not None
    return bytes([value]) if entry.min <= value <= entry.max else None
