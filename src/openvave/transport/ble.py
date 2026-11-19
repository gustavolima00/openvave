"""BLE transport and discovery via ``bleak`` (research R2, R8).

This is the only module that uses ``bleak``, and it imports it lazily so that importing
:func:`select_device` (pure) or running the hardware-free test suite never loads a BLE backend.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from openvave.errors import (
    BluetoothUnavailableError,
    ConnectionLostError,
    MultipleDevicesError,
    NoDeviceFoundError,
    TargetNotFoundError,
)
from openvave.models import DeviceInfo, ScanEntry

if TYPE_CHECKING:
    from bleak import BleakClient
    from bleak.backends.characteristic import BleakGATTCharacteristic
    from bleak.backends.device import BLEDevice
    from bleak.backends.scanner import AdvertisementData

    from openvave.devices import KnownDevices, Target
    from openvave.transport import Transport

logger = logging.getLogger("openvave")

BLE_NAME = "TANK-Gv2_BLE"
"""Advertised local name of the pedal's BLE identity (confirmed). ``TANK-Gv2`` is Classic."""
WRITE_UUID = "0000ae41-0000-1000-8000-00805f9b34fb"
"""Requests: write without response."""
NOTIFY_UUID = "0000ae42-0000-1000-8000-00805f9b34fb"
"""Replies: notifications."""


DEFAULT_ATT_MTU = 23
"""BLE's minimum ATT MTU, used when the platform does not report the negotiated one."""
ATT_WRITE_OVERHEAD = 3
"""ATT header bytes of a write-without-response: one write carries ``MTU − 3`` bytes."""


def split_frame(frame: bytes, mtu: int) -> list[bytes]:
    """``frame`` as consecutive chunks of at most ``mtu − 3`` bytes, in order (spec 004 R11).

    A frame that fits is returned as one chunk. Raises :class:`ValueError` for an MTU that leaves
    no room for data.
    """
    size = mtu - ATT_WRITE_OVERHEAD
    if size < 1:
        raise ValueError(f"ATT MTU {mtu} leaves no room for data")
    return [frame[i : i + size] for i in range(0, len(frame), size)] or [frame]


def select_device(found: Sequence[DeviceInfo], wanted_id: str | None) -> DeviceInfo:
    """Pick the pedal to connect to from a scan result (pure).

    With ``wanted_id`` the device with that identifier is returned whatever its name; otherwise
    exactly one device advertising :data:`BLE_NAME` must be present.
    """
    if wanted_id is not None:
        for device in found:
            if device.identifier.lower() == wanted_id.lower():
                return device
        raise NoDeviceFoundError(f"device {wanted_id} not found")
    matches = [d for d in found if d.name == BLE_NAME]
    if not matches:
        raise NoDeviceFoundError(f"no {BLE_NAME} found")
    if len(matches) > 1:
        raise MultipleDevicesError(matches)
    return matches[0]


def error_message(err: BaseException) -> str:
    """Human message of an exception: its first string argument (bleak errors carry extra
    arguments such as a reason enum), else ``str(err)``, else the class name."""
    if err.args and isinstance(err.args[0], str) and err.args[0]:
        return err.args[0]
    return str(err) or type(err).__name__


def _map_bleak_error(err: BaseException, during: str) -> Exception:
    """Translate a bleak/OS error into an openvave error."""
    import bleak.exc

    not_available = getattr(bleak.exc, "BleakBluetoothNotAvailableError", None)
    if not_available is not None and isinstance(err, not_available):
        return BluetoothUnavailableError(f"Bluetooth unavailable: {error_message(err)}")
    text = error_message(err).lower()
    if any(k in text for k in ("powered off", "turned off", "unauthorized", "not authorized")):
        return BluetoothUnavailableError(f"Bluetooth unavailable: {error_message(err)}")
    if isinstance(err, PermissionError):
        return BluetoothUnavailableError(f"Bluetooth permission denied: {error_message(err)}")
    return ConnectionLostError(f"{during} failed: {error_message(err)}")


SCAN_GRACE = 1.0
"""Seconds a scan keeps listening after the first pedal is seen, so a second pedal still gives
"more than one pedal" (spec 004 M0 gate, SC-001: the full 5 s scan made every command ~11 s)."""


async def _scan(
    timeout: float,
    *,
    wanted_id: str | None = None,
    stop_early: bool = False,
    grace: float = SCAN_GRACE,
    scanner_factory: Callable[..., Any] | None = None,
) -> dict[str, tuple[BLEDevice, DeviceInfo]]:
    """Scan for at most ``timeout`` seconds; every advertiser seen, by address.

    With ``stop_early`` the scan ends ``grace`` seconds after the first device advertising
    :data:`BLE_NAME`, or at once when ``wanted_id`` (case-insensitive) is seen. Without it, the
    whole timeout is used (``discover``). ``scanner_factory`` replaces ``BleakScanner`` in tests.
    """
    from bleak.exc import BleakError

    if scanner_factory is None:
        from bleak import BleakScanner

        scanner_factory = BleakScanner
    devices: dict[str, tuple[BLEDevice, DeviceInfo]] = {}
    done = asyncio.Event()
    loop = asyncio.get_running_loop()
    grace_timer: list[asyncio.TimerHandle] = []
    wanted = wanted_id.lower() if wanted_id is not None else None

    def seen(ble_device: BLEDevice, adv: AdvertisementData) -> None:
        name = adv.local_name or ble_device.name or ""
        info = DeviceInfo(identifier=ble_device.address, name=name, rssi=adv.rssi)
        devices[ble_device.address] = (ble_device, info)
        if not stop_early:
            return
        if wanted is not None:
            if ble_device.address.lower() == wanted:
                done.set()
        elif name == BLE_NAME and not grace_timer:
            grace_timer.append(loop.call_later(grace, done.set))

    try:
        async with scanner_factory(detection_callback=seen):
            try:
                async with asyncio.timeout(timeout):
                    await done.wait()
            except TimeoutError:
                pass
    except (BleakError, OSError) as err:
        raise _map_bleak_error(err, "scan") from err
    finally:
        for handle in grace_timer:
            handle.cancel()
    return devices


async def discover(timeout: float = 5.0) -> list[DeviceInfo]:
    """Scan for ``timeout`` seconds and return every pedal advertising :data:`BLE_NAME`."""
    devices = await _scan(timeout)
    return [info for _, info in devices.values() if info.name == BLE_NAME]


def strongest_first(devices: Sequence[DeviceInfo]) -> list[DeviceInfo]:
    """``devices`` by signal strength, strongest first, unknown strength last, ties by
    identifier (spec 005 data model, "ScanEntry" order)."""
    return sorted(
        devices,
        key=lambda d: (d.rssi is None, -(d.rssi or 0), d.identifier.casefold()),
    )


async def scan(
    timeout: float = 5.0,
    *,
    include_all: bool = False,
    known: KnownDevices | None = None,
    scanner_factory: Callable[..., Any] | None = None,
) -> list[ScanEntry]:
    """Search for pedals for the whole ``timeout``; connects to nothing (spec 005 R6, FR-003).

    Rows: every advertiser of :data:`BLE_NAME`, strongest first (unknown strength last, ties by
    identifier); with ``include_all`` the other advertisers follow in the same order, with
    ``tank_g=False``. With ``known`` (a :class:`~openvave.KnownDevices`) each row carries the
    pedal's ``nickname``, ``known`` and ``selected``. ``scanner_factory`` replaces
    ``BleakScanner`` in tests.
    """
    found = [info for _, info in (await _scan(timeout, scanner_factory=scanner_factory)).values()]
    tank = strongest_first([d for d in found if d.name == BLE_NAME])
    others = strongest_first([d for d in found if d.name != BLE_NAME]) if include_all else []
    default = known.default_identifier if known is not None else None
    entries: list[ScanEntry] = []
    for device in (*tank, *others):
        entry = known.find(device.identifier) if known is not None else None
        if entry is not None and entry.identifier.casefold() != device.identifier.casefold():
            entry = None  # find() also matches nicknames; only the identifier counts here
        entries.append(
            ScanEntry(
                device=replace(device, nickname=entry.nickname) if entry else device,
                tank_g=device.name == BLE_NAME,
                known=entry is not None,
                selected=entry is not None
                and default is not None
                and default.casefold() == device.identifier.casefold(),
            )
        )
    return entries


async def seek(
    identifier: str | None,
    timeout: float,
    *,
    scanner_factory: Callable[..., Any] | None = None,
) -> list[DeviceInfo]:
    """Every advertiser seen by a scan that stops early: at once when ``identifier`` is seen
    (case-insensitive), or :data:`SCAN_GRACE` after the first Tank-G when it is ``None``. Used by
    ``openvave select`` and ``device --check``."""
    devices = await _scan(
        timeout, wanted_id=identifier, stop_early=True, scanner_factory=scanner_factory
    )
    return [info for _, info in devices.values()]


IdentifyFactory = Callable[[DeviceInfo], Awaitable["Transport"]]
"""``device -> transport`` (not yet open) used by :func:`identify`; injectable for tests."""


async def _ble_transport(device: DeviceInfo) -> Transport:
    return BleakTransport(device.identifier)


async def identify(
    entries: Sequence[ScanEntry],
    *,
    timeout: float = 2.0,
    transport_factory: IdentifyFactory | None = None,
) -> list[ScanEntry]:
    """Firmware of each Tank-G row, connecting to one pedal at a time in the given order
    (spec 005 R7). Only the confirmed ``0x11`` handshake is sent; the connection closes at once.

    A row whose connection or handshake fails gets ``identify_error`` (the error's message) and
    the next pedal is still tried. Rows that are not a Tank-G are returned unchanged.
    """
    from openvave.session import TankG

    make = transport_factory or _ble_transport
    result: list[ScanEntry] = []
    for entry in entries:
        if not entry.tank_g:
            result.append(entry)
            continue
        try:
            transport = await make(entry.device)
            async with TankG.over(transport, timeout=timeout, device=entry.device) as pedal:
                firmware = pedal.identity.firmware
        except Exception as err:  # noqa: BLE001 - recorded on the row, the search goes on
            logger.debug("identify %s failed: %r", entry.device.identifier, err)
            result.append(replace(entry, firmware=None, identify_error=error_message(err)))
        else:
            result.append(replace(entry, firmware=firmware, identify_error=None))
    return result


class BleakTransport:
    """:class:`~openvave.transport.Transport` over a BLE GATT connection."""

    def __init__(self, device: BLEDevice | str) -> None:
        self._device = device
        self._client: BleakClient | None = None
        self._callback: Callable[[bytes], None] | None = None
        self._lost: Callable[[], None] | None = None
        self._closing = False

    def on_notify(self, callback: Callable[[bytes], None]) -> None:
        self._callback = callback

    @property
    def att_mtu(self) -> int | None:
        """Negotiated ATT MTU while connected (recorded in ``watch`` session records)."""
        client = self._client
        if client is None or not client.is_connected:
            return None
        return int(client.mtu_size)

    def on_disconnect(self, callback: Callable[[], None]) -> None:
        """Called if the link drops while open (the session fails the pending request)."""
        self._lost = callback

    async def open(self) -> None:
        from bleak import BleakClient
        from bleak.exc import BleakError

        self._closing = False
        client = BleakClient(self._device, disconnected_callback=self._disconnected)
        self._client = client
        try:
            await client.connect()
            await client.start_notify(NOTIFY_UUID, self._notified)
        except (BleakError, OSError, TimeoutError) as err:
            await self.close()
            raise _map_bleak_error(err, "connect") from err

    async def write(self, frame: bytes) -> None:
        """Write one frame; a frame longer than ``ATT MTU − 3`` goes out as consecutive chunks
        (:func:`split_frame`, spec 004 R11). Only the 773-byte image write is that long."""
        from bleak.exc import BleakError

        client = self._client
        if client is None or not client.is_connected:
            raise ConnectionLostError("not connected")
        try:
            for chunk in split_frame(frame, self.att_mtu or DEFAULT_ATT_MTU):
                await client.write_gatt_char(WRITE_UUID, chunk, response=False)
        except (BleakError, OSError) as err:
            raise ConnectionLostError(f"write failed: {error_message(err)}") from err

    async def close(self) -> None:
        self._closing = True
        client, self._client = self._client, None
        if client is None:
            return
        try:
            if client.is_connected:
                await client.disconnect()
        except Exception as err:  # noqa: BLE001 - closing must never raise
            logger.debug("ignoring error while disconnecting: %s", err)

    def _notified(self, _char: BleakGATTCharacteristic, data: bytearray) -> None:
        if self._callback is not None:
            self._callback(bytes(data))

    def _disconnected(self, _client: BleakClient) -> None:
        if not self._closing and self._lost is not None:
            self._lost()


async def locate(
    target: Target | str | None,
    scan_timeout: float,
    *,
    scanner_factory: Callable[..., Any] | None = None,
) -> tuple[BLEDevice, DeviceInfo]:
    """Scan for the pedal a command acts on (spec 005 R5, data model "Scan outcome").

    With a :class:`~openvave.devices.Target` (a plain identifier string counts as ``--device``)
    the scan stops when that identifier is seen, whatever its advertised name; when it is not
    seen within ``scan_timeout`` :class:`TargetNotFoundError` carries the Tank-G pedals that were
    seen, strongest first, and nothing else is chosen instead. Without a target the 0.4.0 rules
    apply: exactly one Tank-G (``chosen_by="only_one_found"``), else
    :class:`NoDeviceFoundError` or :class:`MultipleDevicesError` (candidates strongest first).
    The returned :class:`DeviceInfo` carries ``nickname`` and ``chosen_by``.
    """
    from openvave.devices import Target

    if isinstance(target, str):
        target = Target(target, None, "device_option")
    devices = await _scan(
        scan_timeout,
        wanted_id=target.identifier if target is not None else None,
        stop_early=True,
        scanner_factory=scanner_factory,
    )
    found = strongest_first([info for _, info in devices.values()])
    if target is None:
        chosen = replace(select_device(found, None), chosen_by="only_one_found")
    else:
        wanted = target.identifier.casefold()
        match = next((d for d in found if d.identifier.casefold() == wanted), None)
        if match is None:
            raise TargetNotFoundError(target, [d for d in found if d.name == BLE_NAME])
        chosen = replace(match, nickname=target.nickname, chosen_by=target.chosen_by)
    return devices[chosen.identifier][0], chosen


async def open_ble(
    target: Target | str | None,
    scan_timeout: float,
    *,
    scanner_factory: Callable[..., Any] | None = None,
) -> tuple[BleakTransport, DeviceInfo]:
    """Scan, choose the pedal (:func:`locate`) and build (not yet open) its transport."""
    ble_device, chosen = await locate(target, scan_timeout, scanner_factory=scanner_factory)
    return BleakTransport(ble_device), chosen
