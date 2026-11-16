"""``TankG``: one read-only session with a pedal (data-model.md, research R9).

Lifecycle: open transport → enable notifications → settle 200 ms → handshake (``0x11``, up to 3
attempts) → reads (``0x23``) → close. Requests are strictly sequential. The transport is always
closed on exit, whatever happened.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from types import TracebackType

from openvave.errors import (
    ConnectionLostError,
    HandshakeError,
    ProtocolError,
    RequestTimeoutError,
)
from openvave.models import DeviceIdentity, DeviceInfo, DeviceSnapshot, Region, RegionRead
from openvave.protocol import (
    FrameAssembler,
    build_query,
    build_read,
    decode_frame,
    parse_identity,
    parse_read_reply,
)
from openvave.protocol.frame import QUERY
from openvave.protocol.identity import TESTED_FIRMWARE
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

    async def snapshot(self) -> DeviceSnapshot:
        """Read all four regions in connect order; ``read_at`` is taken after the last read."""
        regions = {region: await self.read(region) for region in SNAPSHOT_ORDER}
        return DeviceSnapshot(
            device=self._device,
            identity=self.identity,
            regions=regions,
            read_at=datetime.now(UTC),
        )

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
