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

:meth:`~TankG.set_fields` changes several fields over the same session (batch edit): one pair of
reads, then the knob block (every knob field in one frame, rebuilt from that read), the block
switches and the LED colour, each acknowledged and verified by a re-read before the next is sent.
The whole batch is refused before anything is sent if any field would be refused.

Persistent writes (spec 004) have one path only: :meth:`~TankG.save_preset` and
:meth:`~TankG.restore` run a fixed :class:`~openvave.models.SequencePlan` through the sequence
runner, which refuses without ``unsafe=True``, takes and hands over a full backup before the first
write, checks every ACK, and attaches the step report to any error raised mid-sequence.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import time
from collections.abc import AsyncGenerator, Awaitable, Callable, Iterable, Mapping
from datetime import UTC, datetime
from types import TracebackType

from openvave.errors import (
    ConnectionLostError,
    HandshakeError,
    OpenvaveError,
    ProtocolError,
    RequestTimeoutError,
    WriteNakError,
    WriteNotAppliedError,
    WriteRefusedError,
)
from openvave.models import (
    Backup,
    DecodedRegion,
    DeviceIdentity,
    DeviceInfo,
    DeviceSnapshot,
    EditPlan,
    EditResult,
    EditWrite,
    EditWriteOutcome,
    FieldEdit,
    FieldStatus,
    PedalState,
    Region,
    RegionRead,
    SequenceAction,
    SequencePlan,
    SequenceResult,
    SequenceStep,
    StepOutcome,
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
from openvave.protocol.storage import (
    EXPECTED_HEADER,
    PRESET_COUNT,
    PRESET_SIZE,
    STORE_OFFSET,
    StorageRead,
    position,
)
from openvave.protocol.writes import (
    EDIT_BUFFER,
    KNOB_COUNT,
    KNOB_FIRST,
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
SEQUENCE_REFUSALS = {**STATE_REFUSALS, "edit": "edit_mode"}
"""Save and restore run in normal mode only (spec 004 data-model)."""
SLOT_WAIT = 0.3
"""Seconds between the slot or image write and the commit (the app's save path, R8)."""
COMMIT_WAIT = 0.1
"""Seconds between the commit and the select (the app's save path, R8)."""
SEQUENCE_SLEEP: Sleep = asyncio.sleep
"""Default sleep of the save/restore waits (patched by tests)."""

OnBackup = Callable[[Backup], object]
"""Called with the automatic backup before the first persistent write; may be a coroutine
function. If it raises, nothing is written."""
OnPlan = Callable[[SequencePlan], object]
"""Called with the plan right before the automatic backup (only when the sequence will run)."""

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

    async def plan_set_fields(
        self,
        changes: Mapping[str, FieldValue] | Iterable[tuple[str, FieldValue]],
        *,
        experimental: bool = False,
        sleep: Sleep | None = None,
    ) -> EditPlan:
        """Plan a change of several fields of the edit buffer: reads global and the edit buffer
        once, sends nothing.

        ``changes`` maps field names to values as :meth:`set_field` takes them (a mapping, or
        ``(field, value)`` pairs). Knob fields share **one** knob-block frame rebuilt from the
        edit-buffer read; each block switch and the LED colour get their own frame. Fields that
        already hold their value add nothing. ``plan.refusal`` is the first refusal in request
        order (state refusals first); a refused batch sends nothing. Raises
        :class:`WriteRefusedError` (``unknown_field``) and :class:`ValueError` (wrong type or
        syntax, a field given twice, no field at all) before any read.
        """
        requests = _edit_requests(changes)
        state, glob, buffer, reads = await self._read_state(sleep)
        data = buffer.data
        resolved: list[tuple[WritableField, bytes | None, str | None]] = []
        for spec, typed, wanted in requests:
            refusal = None
            if typed is not None and typed[0] is None:
                current_type, _ = type_parts(spec.name, data[spec.offset])
                if current_type is None:
                    refusal = "type_required"
                else:
                    wanted = _field_bytes(spec, type_raw(spec.name, current_type, typed[1]))
            if wanted is None and refusal is None:
                refusal = "out_of_range"
            resolved.append((spec, wanted, refusal))

        def changed(spec: WritableField, wanted: bytes | None) -> bool:
            return wanted is not None and data[spec.offset : spec.offset + len(wanted)] != wanted

        writes: list[EditWrite] = []
        knobs = [(s, w) for s, w, _ in resolved if s.kind == "knob_block" and changed(s, w)]
        if knobs:
            block = bytearray(data[KNOB_FIRST : KNOB_FIRST + KNOB_COUNT])
            for spec, wanted in knobs:
                assert wanted is not None
                block[spec.offset - KNOB_FIRST] = wanted[0]
            writes.append(_edit_frame(WriteTarget.knob_block(), bytes(block), knobs))
        others = sorted(
            ((s, w) for s, w, _ in resolved if s.kind != "knob_block" and changed(s, w)),
            key=lambda item: item[0].offset,
        )
        for spec, wanted in others:
            assert wanted is not None
            writes.append(_edit_frame(spec.target(), wanted, [(spec, wanted)]))
        gates = {w.target: self._gate(w.target, experimental) for w in writes}

        state_refusal = STATE_REFUSALS.get(state.kind)
        fields: list[FieldEdit] = []
        for spec, wanted, refusal in resolved:
            size = len(wanted) if wanted else (LED_LENGTH if spec.kind == "led_colour" else 1)
            current = data[spec.offset : spec.offset + size]
            no_change = wanted is not None and current == wanted
            if refusal is None and not no_change:
                refusal = gates.get(spec.target())
            fields.append(
                FieldEdit(
                    field=spec.name,
                    target=spec.target(),
                    offset=spec.offset,
                    current=current,
                    wanted=wanted or b"",
                    no_change=no_change,
                    refusal=state_refusal or refusal,
                )
            )
        refused = next((f for f in fields if f.refusal is not None), None)
        return EditPlan(
            state=state,
            fields=tuple(fields),
            writes=tuple(writes),
            reads=reads,
            before=buffer,
            global_before=glob,
            refusal=refused.refusal if refused is not None else None,
            refused_field=None if refused is None or state_refusal else refused.field,
        )

    async def set_fields(
        self,
        changes: Mapping[str, FieldValue] | Iterable[tuple[str, FieldValue]],
        *,
        experimental: bool = False,
        sleep: Sleep | None = None,
    ) -> EditResult:
        """Change several fields of the current preset in the edit buffer over this one session
        (never saved).

        Builds :meth:`plan_set_fields`'s plan and raises :class:`WriteRefusedError` if any
        field refuses it (nothing is sent). Otherwise sends the plan's frames in order — the knob
        block first, right after the edit-buffer read it was rebuilt from — and after each one
        checks the ACK and re-reads the edit buffer before sending the next. Stops at the first
        problem, without retrying: a NAK (:class:`WriteNakError`), a lost link or timeout, or a
        re-read that does not show the write (:class:`WriteNotAppliedError`, ``result`` None).
        The error carries the partial :class:`~openvave.models.EditResult` in ``.edit``: which
        fields were applied, which are unknown and which were not sent. Nothing to change →
        returns at once, nothing sent. ``experimental=True`` as for :meth:`set_field`.
        """
        plan = await self.plan_set_fields(changes, experimental=experimental, sleep=sleep)
        if plan.refusal is not None:
            text = self._edit_refusal_text(plan)
            raise WriteRefusedError(plan.refusal, f"refused ({plan.refusal}): {text}")
        status: dict[str, FieldStatus] = {
            f.field: "unchanged" if f.no_change else "not_sent" for f in plan.fields
        }
        wanted = {f.field: f for f in plan.fields}
        outcomes: list[EditWriteOutcome] = []
        after: RegionRead | None = None

        def result(glob: RegionRead | None = None) -> EditResult:
            rest = tuple(EditWriteOutcome(w, "not_sent") for w in plan.writes[len(outcomes) :])
            changes_ = (diff(plan.global_before, glob) if glob is not None else ()) + (
                diff(plan.before, after) if after is not None else ()
            )
            return EditResult(
                plan=plan,
                writes=tuple(outcomes) + rest,
                field_status=tuple((f.field, status[f.field]) for f in plan.fields),
                after=after,
                global_after=glob,
                changes=changes_,
            )

        try:
            for edit in plan.writes:
                try:
                    reply = await self._request(edit.frame)
                    parse_write_reply(reply)
                except OpenvaveError as err:
                    nak = isinstance(err, WriteNakError)
                    reply_ = err.reply if isinstance(err, WriteNakError) else b""
                    outcomes.append(EditWriteOutcome(edit, "nak" if nak else "no_reply", reply_))
                    status.update(dict.fromkeys(edit.fields, "unknown"))
                    raise
                outcomes.append(EditWriteOutcome(edit, "acked", reply))
                status.update(dict.fromkeys(edit.fields, "unknown"))
                after = await self.read(Region.CURRENT_PRESET)
                start = edit.target.address - EDIT_BUFFER
                applied = after.data[start : start + len(edit.data)] == edit.data
                outcomes[-1] = EditWriteOutcome(edit, "acked", reply, applied)
                for name in edit.fields:
                    f = wanted[name]
                    shown = after.data[f.offset : f.offset + len(f.wanted)] == f.wanted
                    status[name] = "applied" if shown else "not_applied"
                if not applied:
                    names = ", ".join(n for n in edit.fields if status[n] == "not_applied")
                    left = [n for n, s in status.items() if s == "not_sent"]
                    tail = f"; not sent: {', '.join(left)}" if left else ""
                    raise WriteNotAppliedError(
                        None, f"set {names}: acknowledged but not applied (re-read differs){tail}"
                    )
            glob = await self.read(Region.GLOBAL)
        except OpenvaveError as err:
            if err.edit is None:
                err.edit = result()
            raise
        return result(glob)

    def _edit_refusal_text(self, plan: EditPlan) -> str:
        reason = plan.refusal or ""
        edit = next((f for f in plan.fields if f.field == plan.refused_field), None)
        if edit is None:
            return self._refusal_text(reason)
        if reason == "experimental_required":
            confidence = message_for(edit.target.kind, edit.target.argument).confidence
            text = (
                f"{edit.target.kind} is '{confidence}' in the protocol docs (Write messages); "
                "pass --experimental (experimental=True) to send it"
            )
        elif reason == "out_of_range":
            text = "value out of range for this field"
        else:
            text = self._refusal_text(reason)
        return f"{edit.field}: {text}"

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

    # -- bypass and loopback (spec 004 US2, US5) ------------------------------------------------

    async def plan_bypass_on(
        self,
        *,
        discard_edits: bool = False,
        experimental: bool = False,
        sleep: Sleep | None = None,
    ) -> WritePlan:
        """Plan bypassing the pedal: reads global, the edit buffer and the loaded stored preset.

        Allowed in normal mode only (``edit_mode``, ``tuner_mode``, ``unrecognised_state``
        otherwise). Unsaved edits (buffer ≠ stored preset) need ``discard_edits``
        (``edits_would_be_discarded``). Already bypassed: ``no_change`` with an empty frame (the
        target is then a placeholder for slot A of the reported bank, since the loaded slot is
        not reported). The bypass message is ``observed`` (not ``confirmed``), so
        ``experimental`` is needed.
        """
        state, glob, buffer, reads = await self._read_state(sleep)
        if state.kind == "bypass":
            target = WriteTarget.bypass(4 * (state.bank or 0))
            return WritePlan(
                action="bypass on",
                target=target,
                data=b"",
                frame=b"",
                reads=reads,
                before=buffer,
                global_before=glob,
                no_change=True,
                refusal=None,
                confidence=message_for(target.kind, target.argument).confidence,
            )
        if state.index is None or state.kind == "tuner":
            reason = STATE_REFUSALS.get(state.kind, "unrecognised_state")
            raise WriteRefusedError(reason, f"refused ({reason}): {self._refusal_text(reason)}")
        index = state.index
        target = WriteTarget.bypass(index)
        stored_target = StorageRead.preset(index)
        stored_frame = build_storage_read(stored_target)
        stored = parse_storage_reply(stored_target, await self._request(stored_frame))
        refusal: str | None = None
        if state.kind == "edit":
            refusal = "edit_mode"
        elif buffer.data != stored and not discard_edits:
            refusal = "edits_would_be_discarded"
        else:
            refusal = self._gate(target, experimental)
        data = b"\x01"
        return WritePlan(
            action=f"bypass on {position(index)}",
            target=target,
            data=data,
            frame=build_write(target, data),
            reads=(*reads, stored_frame),
            before=buffer,
            global_before=glob,
            no_change=False,
            refusal=refusal,
            confidence=message_for(target.kind, target.argument).confidence,
        )

    async def bypass_on(
        self,
        *,
        discard_edits: bool = False,
        experimental: bool = False,
        sleep: Sleep | None = None,
    ) -> WriteResult:
        """Bypass the pedal (spec 004 US2, FR-007…FR-010): ``01`` to ``0xE1000000 + i``.

        Builds :meth:`plan_bypass_on`'s plan and raises :class:`WriteRefusedError` if it is
        refused. Already bypassed: returns at once, nothing sent. Otherwise sends the one write,
        checks the ACK, re-reads global and the edit buffer, and is applied iff the slot reads
        ``ff`` and the buffer is all zero (else :class:`WriteNotAppliedError`). The result's
        ``return_index`` is the preset to give :meth:`bypass_off`. Volatile; never retried.
        """
        plan = await self.plan_bypass_on(
            discard_edits=discard_edits, experimental=experimental, sleep=sleep
        )
        self._raise_refusal(plan)
        if plan.no_change:
            return WriteResult(plan, b"", plan.before, plan.global_before, (), applied=True)
        reply = await self._send_once(plan)
        glob = await self.read(Region.GLOBAL)
        after = await self.read(Region.CURRENT_PRESET)
        applied = classify(glob.data, after.data).kind == "bypass"
        result = WriteResult(
            plan,
            reply,
            after,
            glob,
            diff(plan.global_before, glob) + diff(plan.before, after),
            applied,
            return_index=plan.target.argument,
        )
        if not applied:
            raise WriteNotAppliedError(
                result, f"{plan.action}: acknowledged but the pedal does not read as bypassed"
            )
        return result

    async def plan_bypass_off(
        self, index: int, *, experimental: bool = False, sleep: Sleep | None = None
    ) -> WritePlan:
        """Plan leaving bypass by selecting preset ``index`` (0–35): reads global and the buffer.

        Allowed only when the pedal is bypassed (confirmed by a second read); otherwise
        ``not_bypassed`` (normal), ``edit_mode``, ``tuner_mode`` or ``unrecognised_state``. The
        write is the confirmed preset select. Raises :class:`ValueError` for an index outside
        0–35.
        """
        target = WriteTarget.preset_select(index)
        state, glob, buffer, reads = await self._read_state(sleep)
        refusals = {**STATE_REFUSALS, "normal": "not_bypassed", "edit": "edit_mode"}
        refusal = None if state.kind == "bypass" else refusals[state.kind]
        if refusal is None:
            refusal = self._gate(target, experimental)
        data = b"\x01"
        return WritePlan(
            action=f"bypass off {position(index)}",
            target=target,
            data=data,
            frame=build_write(target, data),
            reads=reads,
            before=buffer,
            global_before=glob,
            no_change=False,
            refusal=refusal,
            confidence=message_for(target.kind, target.argument).confidence,
        )

    async def bypass_off(
        self,
        index: int,
        *,
        experimental: bool = False,
        sleep: Sleep | None = None,
    ) -> WriteResult:
        """Leave bypass by selecting preset ``index`` (spec 004 FR-007, FR-009, FR-010).

        Only when the pedal is bypassed (:meth:`plan_bypass_off`); then the select path of
        :meth:`select_preset`, verified by the pedal showing ``index`` with the buffer equal to
        the stored preset. The index is required: the pedal does not report its slot while
        bypassed. ``sleep`` is injectable for tests.
        """
        plan = await self.plan_bypass_off(index, experimental=experimental, sleep=sleep)
        self._raise_refusal(plan)
        return await self._run_select(plan, index, sleep or SELECT_SLEEP)

    async def plan_loopback(
        self, on: bool, *, experimental: bool = False, sleep: Sleep | None = None
    ) -> WritePlan:
        """Plan setting the loopback flag: reads global, the edit buffer and the status byte.

        ``plan.before`` is the status byte (``0xD0000000`` × 1). Allowed in every recognised
        state; refused in an unrecognised one. ``no_change`` when the flag already has the value.
        The message is ``observed`` (not ``confirmed``), so ``experimental`` is needed.
        """
        target = WriteTarget.loopback()
        state, glob, _, reads = await self._read_state(sleep)
        status, status_frame = await self._read_with_frame(Region.STATUS)
        data = b"\x01" if on else b"\x00"
        refusal = (
            "unrecognised_state"
            if state.kind == "unrecognised"
            else self._gate(target, experimental)
        )
        return WritePlan(
            action=f"loopback {'on' if on else 'off'}",
            target=target,
            data=data,
            frame=build_write(target, data),
            reads=(*reads, status_frame),
            before=status,
            global_before=glob,
            no_change=status.data == data,
            refusal=refusal,
            confidence=message_for(target.kind, target.argument).confidence,
        )

    async def set_loopback(
        self, on: bool, *, experimental: bool = False, sleep: Sleep | None = None
    ) -> WriteResult:
        """Set the loopback flag (spec 004 US5, FR-026): one 1-byte write to ``0xD0000000``.

        Builds :meth:`plan_loopback`'s plan and raises :class:`WriteRefusedError` if refused.
        Equal value: returns at once, nothing sent. Otherwise sends the write, checks the ACK and
        re-reads the status byte (``result.after``) and global; applied iff the byte now equals
        the request (else :class:`WriteNotAppliedError`). Never followed by a commit or a retry.
        """
        plan = await self.plan_loopback(on, experimental=experimental, sleep=sleep)
        self._raise_refusal(plan)
        if plan.no_change:
            return WriteResult(plan, b"", plan.before, plan.global_before, (), applied=True)
        reply = await self._send_once(plan)
        glob = await self.read(Region.GLOBAL)
        after = await self.read(Region.STATUS)
        return self._finish(plan, reply, after, glob, after.data == plan.data)

    # -- save and restore (spec 004 US3, US4): the only path to persistent writes --------------

    async def plan_save(
        self,
        to: int | None = None,
        *,
        unsafe: bool = False,
        experimental: bool = False,
        sleep: Sleep | None = None,
    ) -> SequencePlan:
        """Plan storing the edit buffer in slot ``to`` (default: the loaded slot). Reads only.

        Reads global, the edit buffer and the target slot. ``no_change`` when the slot already
        holds the buffer. ``plan.refusal`` is what :meth:`save_preset` would refuse with the same
        opt-ins: ``edit_mode`` / ``tuner_mode`` / ``bypassed`` / ``unrecognised_state`` (normal
        mode only), then ``unsafe_required``, then ``untested_firmware`` /
        ``experimental_required``. When there is no target (bypassed or unrecognised, ``to``
        not given) raises :class:`WriteRefusedError`. :class:`ValueError` for ``to`` outside
        0–35.
        """
        if to is not None:
            WriteTarget.stored_slot(to)  # validates the index
        state, _, buffer, reads = await self._read_state(sleep)
        index = to if to is not None else state.index
        if index is None:
            self._refuse_state(state)
        assert index is not None
        current, frame = await self._stored_with_frame(index)
        return self._slot_plan(
            "save", state, index, current, buffer.data, (*reads, frame), unsafe, experimental
        )

    async def save_preset(
        self,
        to: int | None = None,
        *,
        unsafe: bool = False,
        experimental: bool = False,
        on_backup: OnBackup,
        on_plan: OnPlan | None = None,
        sleep: Sleep | None = None,
    ) -> SequenceResult:
        """Store the edit buffer in slot ``to`` (default: the loaded slot). **Persistent.**

        Builds :meth:`plan_save`'s plan and raises :class:`WriteRefusedError` if it is refused
        (``unsafe=True`` is always required). Nothing to save: returns at once, nothing sent, no
        backup. Otherwise runs the sequence (spec 004 R8, R9): ``on_plan(plan)`` → full backup
        (:meth:`backup`, cross-checked) → ``on_backup(backup)`` → slot write → read the slot
        back (a mismatch stops before the commit) → 300 ms → commit → 100 ms → select → verify
        (slot = bytes written, pedal on the target, buffer = slot). Every write's ACK is checked;
        nothing is retried. Errors raised after the first write carry ``.sequence`` (the step
        report); a failed verification raises :class:`WriteNotAppliedError`.
        """
        plan = await self.plan_save(to, unsafe=unsafe, experimental=experimental, sleep=sleep)
        return await self._run_sequence(plan, experimental, on_backup, on_plan, sleep)

    async def plan_restore(
        self,
        backup: Backup,
        *,
        slot: int | None = None,
        all: bool = False,  # the contract's name: restore(backup, all=True)
        unsafe: bool = False,
        experimental: bool = False,
        discard_edits: bool = False,
        sleep: Sleep | None = None,
    ) -> SequencePlan:
        """Plan restoring slot ``slot`` or ``all`` presets from ``backup``. Reads only.

        Pass exactly one of ``slot`` (0–35) and ``all=True`` (else :class:`ValueError`, as for a
        backup whose header is not ``a5 5a``). Slot: reads global, the buffer, the slot and the
        loaded slot; the sequence is the save sequence with the file's bytes. All: reads global,
        the buffer and the whole image; the sequence writes the file's image, commits and selects
        the preset that was loaded. ``changed_slots`` lists the slots that differ;
        ``no_change`` when none does. Refusals, in order: pedal state (normal mode only),
        ``edits_would_be_discarded`` (unsaved edits and no ``discard_edits``: every restore ends
        with a select), ``firmware_mismatch`` (file from another firmware, no ``experimental``),
        ``unsafe_required``, then the confidence gate.
        """
        if (slot is None) == (not all):
            raise ValueError("pass exactly one of slot=<index> or all=True")
        if slot is not None:
            WriteTarget.stored_slot(slot)  # validates the index
        if backup.header != EXPECTED_HEADER:
            raise ValueError(
                f"backup header {backup.header.hex(' ')} is not {EXPECTED_HEADER.hex(' ')}"
            )
        state, _, buffer, reads = await self._read_state(sleep)
        if state.index is None:
            self._refuse_state(state)
        assert state.index is not None
        loaded = state.index
        mismatch = backup.identity.firmware != self.identity.firmware
        if slot is not None:
            current, frame = await self._stored_with_frame(slot)
            reads = (*reads, frame)
            loaded_stored = current
            if loaded != slot:
                loaded_stored, frame = await self._stored_with_frame(loaded)
                reads = (*reads, frame)
            return self._slot_plan(
                "restore_slot",
                state,
                slot,
                current,
                backup.presets[slot].data,
                reads,
                unsafe,
                experimental,
                edits_pending=buffer.data != loaded_stored and not discard_edits,
                firmware_mismatch=mismatch,
            )
        image_read = StorageRead.image()
        image_frame = build_storage_read(image_read)
        image = parse_storage_reply(image_read, await self._request(image_frame))
        start = STORE_OFFSET + PRESET_SIZE * loaded
        changed = tuple(
            i for i in range(PRESET_COUNT) if _slot_bytes(image, i) != _slot_bytes(backup.image, i)
        )
        no_change = image == backup.image
        image_target = WriteTarget.stored_image()
        steps = _sequence_steps(_write_step(image_target, backup.image), loaded)
        return SequencePlan(
            action="restore_all",
            state=state,
            target_index=None,
            return_index=loaded,
            before=image,
            after=backup.image,
            changed_slots=changed,
            diff=(),
            steps=() if no_change else steps,
            no_change=no_change,
            refusal=self._sequence_refusal(
                state,
                [s.target for s in steps if s.target is not None],
                no_change=no_change,
                unsafe=unsafe,
                experimental=experimental,
                edits_pending=buffer.data != image[start : start + PRESET_SIZE]
                and not discard_edits,
                firmware_mismatch=mismatch,
            ),
            reads=(*reads, image_frame),
        )

    async def restore(
        self,
        backup: Backup,
        *,
        slot: int | None = None,
        all: bool = False,  # the contract's name
        unsafe: bool = False,
        experimental: bool = False,
        discard_edits: bool = False,
        on_backup: OnBackup,
        on_plan: OnPlan | None = None,
        sleep: Sleep | None = None,
    ) -> SequenceResult:
        """Restore slot ``slot`` or ``all`` presets from ``backup``. **Persistent.**

        Builds :meth:`plan_restore`'s plan and raises :class:`WriteRefusedError` if it is
        refused (``unsafe=True`` is always required). Nothing differs: returns at once, nothing
        sent, no backup. Otherwise runs the sequence as :meth:`save_preset` does (automatic
        backup first). A full restore is verified by a full backup read compared with the file;
        mismatching slots are in ``result.mismatched_slots`` of the
        :class:`WriteNotAppliedError`'s ``.sequence``.
        """
        plan = await self.plan_restore(
            backup,
            slot=slot,
            all=all,
            unsafe=unsafe,
            experimental=experimental,
            discard_edits=discard_edits,
            sleep=sleep,
        )
        return await self._run_sequence(plan, experimental, on_backup, on_plan, sleep)

    def _slot_plan(
        self,
        action: SequenceAction,
        state: PedalState,
        index: int,
        before: bytes,
        after: bytes,
        reads: tuple[bytes, ...],
        unsafe: bool,
        experimental: bool,
        *,
        edits_pending: bool = False,
        firmware_mismatch: bool = False,
    ) -> SequencePlan:
        no_change = before == after
        steps = _sequence_steps(_write_step(WriteTarget.stored_slot(index), after), index)
        changes = diff(
            RegionRead(Region.CURRENT_PRESET, before), RegionRead(Region.CURRENT_PRESET, after)
        )
        return SequencePlan(
            action=action,
            state=state,
            target_index=index,
            return_index=index,
            before=before,
            after=after,
            changed_slots=() if no_change else (index,),
            diff=changes,
            steps=() if no_change else steps,
            no_change=no_change,
            refusal=self._sequence_refusal(
                state,
                [s.target for s in steps if s.target is not None],
                no_change=no_change,
                unsafe=unsafe,
                experimental=experimental,
                edits_pending=edits_pending,
                firmware_mismatch=firmware_mismatch,
            ),
            reads=reads,
        )

    def _sequence_refusal(
        self,
        state: PedalState,
        targets: list[WriteTarget],
        *,
        no_change: bool,
        unsafe: bool,
        experimental: bool,
        edits_pending: bool,
        firmware_mismatch: bool,
    ) -> str | None:
        """Refusal of a save/restore plan (spec 004 R6): state first; nothing else when nothing
        would be sent."""
        reason = SEQUENCE_REFUSALS.get(state.kind)
        if reason is not None or no_change:
            return reason
        if edits_pending:
            return "edits_would_be_discarded"
        if firmware_mismatch and not experimental:
            return "firmware_mismatch"
        if not unsafe:
            return "unsafe_required"
        for target in targets:
            gate = self._gate(target, experimental)
            if gate is not None:
                return gate
        return None

    def _refuse_state(self, state: PedalState) -> None:
        reason = SEQUENCE_REFUSALS.get(state.kind, "unrecognised_state")
        raise WriteRefusedError(reason, f"refused ({reason}): {self._refusal_text(reason)}")

    def _raise_sequence_refusal(self, plan: SequencePlan, experimental: bool) -> None:
        reason = plan.refusal
        if reason is None:
            return
        targets = [s.target for s in plan.steps if s.target is not None]
        pending = [t for t in targets if not experimental and self._gate(t, False) is not None]
        kinds = ", ".join(sorted({t.kind for t in pending}))
        if reason == "unsafe_required":
            text = (
                f"{_ACTION_NAMES[plan.action]} overwrites "
                f"{'stored presets' if plan.action == 'restore_all' else 'a stored preset'}; "
                "pass --unsafe (unsafe=True) to accept that"
            )
            if pending:
                text += (
                    f", and --experimental (experimental=True): {kinds} "
                    "are not confirmed in the protocol docs yet"
                )
        elif reason == "experimental_required":
            text = (
                f"{kinds} are not confirmed in the protocol docs (Write messages) yet; "
                "pass --experimental (experimental=True) to send them"
            )
        else:
            text = self._refusal_text(reason)
        raise WriteRefusedError(reason, f"refused ({reason}): {text}")

    async def _run_sequence(
        self,
        plan: SequencePlan,
        experimental: bool,
        on_backup: OnBackup,
        on_plan: OnPlan | None,
        sleep: Sleep | None,
    ) -> SequenceResult:
        """The sequence runner (spec 004 R8, R9, R15): the only sender of persistent writes."""
        self._raise_sequence_refusal(plan, experimental)
        if plan.no_change:
            unchanged = plan.before if plan.action != "restore_all" else None
            return SequenceResult(plan, (), False, True, unchanged, None)
        assert plan.refusal is None and plan.steps
        if on_plan is not None:
            await _maybe_await(on_plan(plan))
        backup = await self.backup()
        await _maybe_await(on_backup(backup))
        wait = sleep or SEQUENCE_SLEEP
        outcomes: list[StepOutcome] = []
        may_change = False
        read_back: bytes | None = None

        def result(verified: bool = False, mismatched: tuple[int, ...] = ()) -> SequenceResult:
            rest = [StepOutcome(s, "not_sent") for s in plan.steps[len(outcomes) :]]
            return SequenceResult(
                plan, (*outcomes, *rest), may_change, verified, read_back, backup, mismatched
            )

        try:
            for step in plan.steps:
                if step.kind == "wait":
                    assert step.seconds is not None
                    await wait(step.seconds)
                    outcomes.append(StepOutcome(step, "waited"))
                    continue
                target = step.target
                assert target is not None
                may_change = may_change or target.persistent
                try:
                    reply = await self._request(step.frame)
                except (ConnectionLostError, RequestTimeoutError):
                    outcomes.append(StepOutcome(step, "no_reply"))
                    raise
                try:
                    parse_write_reply(reply)
                except ProtocolError:
                    outcomes.append(StepOutcome(step, "nak", reply))
                    raise
                outcomes.append(StepOutcome(step, "acked", reply))
                if target.kind == "stored_slot":
                    assert target.argument is not None
                    read_back = await self._storage_read(StorageRead.preset(target.argument))
                    if read_back != step.data:
                        raise WriteNotAppliedError(
                            None,
                            f"{_ACTION_NAMES[plan.action]}: slot {position(target.argument)} "
                            "reads back different bytes after the slot write; stopped before "
                            "the commit",
                        )
            verified, mismatched, read_back, problem = await self._verify_sequence(plan, sleep)
            if not verified:
                raise WriteNotAppliedError(
                    None, problem, sequence=result(verified=False, mismatched=mismatched)
                )
        except OpenvaveError as err:
            if err.sequence is None:
                err.sequence = result()
            raise
        return result(verified=True)

    async def _verify_sequence(
        self, plan: SequencePlan, sleep: Sleep | None
    ) -> tuple[bool, tuple[int, ...], bytes, str]:
        """``(verified, mismatched slots, read-back, problem)`` after the select step."""
        index = plan.return_index
        assert index is not None
        wait = sleep or SELECT_SLEEP
        glob = await self.read(Region.GLOBAL)
        for _ in range(SELECT_TRIES):
            await wait(SELECT_WAIT)
            glob = await self.read(Region.GLOBAL)
            if glob.data[2] != LOADING_SLOT:
                break
        buffer = await self.read(Region.CURRENT_PRESET)
        bank, slot = divmod(index, 4)
        on_target = glob.data[1] == bank and glob.data[2] == slot
        name = _ACTION_NAMES[plan.action]
        if plan.action == "restore_all":
            after = await self.backup()
            mismatched = tuple(
                i
                for i in range(PRESET_COUNT)
                if _slot_bytes(after.image, i) != _slot_bytes(plan.after, i)
            )
            image_ok = after.image == plan.after
            loaded_ok = buffer.data == _slot_bytes(after.image, index)
            problems = []
            if not image_ok:
                where = ", ".join(position(i) for i in mismatched) or "the header"
                problems.append(f"the stored image differs from the file at {where}")
            if not on_target:
                problems.append(f"the pedal is not on {position(index)}")
            elif not loaded_ok:
                problems.append("the edit buffer differs from the stored preset")
            ok = image_ok and on_target and loaded_ok
            return ok, mismatched, after.image, f"{name}: acknowledged, but " + "; ".join(problems)
        stored = await self._storage_read(StorageRead.preset(index))
        problems = []
        if stored != plan.after:
            problems.append(f"stored {position(index)} differs from the bytes written")
        if not on_target:
            problems.append(f"the pedal is not on {position(index)}")
        elif buffer.data != stored:
            problems.append("the edit buffer differs from the stored preset")
        ok = not problems
        return ok, (), stored, f"{name}: acknowledged, but " + "; ".join(problems)

    async def _stored_with_frame(self, index: int) -> tuple[bytes, bytes]:
        target = StorageRead.preset(index)
        frame = build_storage_read(target)
        return parse_storage_reply(target, await self._request(frame)), frame

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
                "the pedal has unsaved edits and selecting a preset discards them; "
                "pass --discard-edits (discard_edits=True) to go on anyway"
            ),
            "tuner_mode": "the pedal is in tuner mode; leave the tuner on the pedal first",
            "type_required": (
                f"{plan.field if plan else 'the field'} sits between two types (the module is "
                "off there), so there is no current type to keep; pass a type "
                "(--type, or (type, position) in the library)"
            ),
            "bypassed": (
                "the pedal is bypassed and does not report its loaded slot; leave bypass with "
                "openvave bypass off <position> (bypass_off(index) in the library)"
            ),
            "edit_mode": (
                "the pedal is in edit mode; leave edit mode on the pedal first (bypass, save "
                "and restore work in normal mode only)"
            ),
            "not_bypassed": (
                "the pedal is not bypassed; to load a preset use openvave preset select <position>"
            ),
            "unrecognised_state": (
                "the pedal reports a state openvave does not recognise (global block / edit "
                "buffer); check it with openvave info"
            ),
            "firmware_mismatch": (
                "the backup file comes from another firmware version than the pedal's; pass "
                "--experimental (experimental=True) to restore it anyway"
            ),
            "unsafe_required": (
                "this overwrites stored presets; pass --unsafe (unsafe=True) to accept that"
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


def _edit_requests(
    changes: Mapping[str, FieldValue] | Iterable[tuple[str, FieldValue]],
) -> list[tuple[WritableField, tuple[str | None, int] | None, bytes | None]]:
    """Check a batch edit before any I/O: ``(spec, typed value, wanted bytes)`` per field.

    ``wanted`` is ``None`` when out of range or when the type is to be kept (resolved after the
    read). Raises :class:`WriteRefusedError` (``unknown_field``) and :class:`ValueError`.
    """
    items = list(changes.items()) if isinstance(changes, Mapping) else list(changes)
    if not items:
        raise ValueError("set_fields needs at least one field")
    seen: set[str] = set()
    requests = []
    for field, value in items:
        if field in seen:
            raise ValueError(f"{field} given twice")
        seen.add(field)
        spec = WRITABLE_FIELDS.get(field)
        if spec is None:
            valid = ", ".join(WRITABLE_FIELDS)
            raise WriteRefusedError(
                "unknown_field", f"unknown field {field!r}; writable fields: {valid}"
            )
        typed = _typed_value(spec, value)
        keep_type = typed is not None and typed[0] is None
        requests.append((spec, typed, None if keep_type else _field_bytes(spec, value)))
    return requests


def _edit_frame(
    target: WriteTarget, data: bytes, fields: list[tuple[WritableField, bytes | None]]
) -> EditWrite:
    return EditWrite(
        target=target,
        data=data,
        frame=build_write(target, data),
        fields=tuple(spec.name for spec, _ in fields),
        confidence=message_for(target.kind, target.argument).confidence,
    )


_ACTION_NAMES = {
    "save": "preset save",
    "restore_slot": "preset restore",
    "restore_all": "preset restore",
}


def _slot_bytes(image: bytes, index: int) -> bytes:
    start = STORE_OFFSET + PRESET_SIZE * index
    return image[start : start + PRESET_SIZE]


def _write_step(target: WriteTarget, data: bytes) -> SequenceStep:
    return SequenceStep("write", target, data, build_write(target, data))


def _sequence_steps(first: SequenceStep, select: int) -> tuple[SequenceStep, ...]:
    """``first`` → 300 ms → commit → 100 ms → select ``select`` (the app's save path, R8)."""
    return (
        first,
        SequenceStep("wait", seconds=SLOT_WAIT),
        _write_step(WriteTarget.commit(), b""),
        SequenceStep("wait", seconds=COMMIT_WAIT),
        _write_step(WriteTarget.preset_select(select), b"\x01"),
    )


async def _maybe_await(value: object) -> None:
    if inspect.isawaitable(value):
        await value
