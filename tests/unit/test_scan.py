"""Early-stopping BLE scan (spec 004 M0 gate, SC-001): no Bluetooth involved.

A scan used to wait its whole timeout (5 s) even after the pedal had been seen. It now stops
``SCAN_GRACE`` seconds after the first pedal advertising ``TANK-Gv2_BLE`` (so a second pedal in
that window still gives "more than one pedal"), and at once when the ``--device`` identifier is
seen. ``discover()`` still scans for the whole timeout (it lists every pedal).
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace, TracebackType
from typing import Any

import pytest

from openvave.devices import KnownDevices, Target
from openvave.errors import MultipleDevicesError, NoDeviceFoundError, TargetNotFoundError
from openvave.transport import ble
from openvave.transport.ble import BLE_NAME, select_device
from tests.support.scanner import SPEAKER as SPEAKER_ID
from tests.support.scanner import TANK, UUID_1, UUID_2, UUID_3
from tests.support.scanner import fake_scanner as timed_scanner

PEDAL_A = ("AAAA-1111", BLE_NAME, -58)
PEDAL_B = ("BBBB-2222", BLE_NAME, -71)
SPEAKER = ("DDDD-4444", "Some Speaker", -40)


def fake_scanner(schedule: list[tuple[float, tuple[str, str, int]]]) -> Callable[..., Any]:
    """A BleakScanner stand-in that reports each advertisement at its time (seconds)."""

    class FakeScanner:
        def __init__(self, detection_callback: Callable[[Any, Any], None]) -> None:
            self._callback = detection_callback
            self._handles: list[asyncio.TimerHandle] = []

        async def __aenter__(self) -> FakeScanner:
            loop = asyncio.get_running_loop()
            for at, (address, name, rssi) in schedule:
                device = SimpleNamespace(address=address, name=name)
                adv = SimpleNamespace(local_name=name, rssi=rssi)
                self._handles.append(loop.call_later(at, self._callback, device, adv))
            return self

        async def __aexit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            tb: TracebackType | None,
        ) -> None:
            for handle in self._handles:
                handle.cancel()

    return FakeScanner


async def scan(
    schedule: list[tuple[float, tuple[str, str, int]]],
    *,
    timeout: float = 2.0,
    grace: float = 0.1,
    wanted: str | None = None,
    stop_early: bool = True,
) -> tuple[list[str], float]:
    started = time.monotonic()
    devices = await ble._scan(
        timeout,
        wanted_id=wanted,
        stop_early=stop_early,
        grace=grace,
        scanner_factory=fake_scanner(schedule),
    )
    return sorted(devices), time.monotonic() - started


async def test_one_pedal_stops_after_the_grace_period() -> None:
    found, elapsed = await scan([(0.02, SPEAKER), (0.05, PEDAL_A)])
    assert found == [PEDAL_A[0], SPEAKER[0]]
    assert 0.1 <= elapsed < 0.5  # first match at 0.05 s + 0.1 s grace, far below the 2 s timeout


async def test_second_pedal_within_grace_is_still_reported() -> None:
    found, _ = await scan([(0.05, PEDAL_A), (0.1, PEDAL_B)])
    assert found == [PEDAL_A[0], PEDAL_B[0]]
    with pytest.raises(MultipleDevicesError):
        select_device([ble.DeviceInfo(a, BLE_NAME, r) for a, _, r in (PEDAL_A, PEDAL_B)], None)


async def test_pedal_after_the_grace_period_is_not_waited_for() -> None:
    found, elapsed = await scan([(0.05, PEDAL_A), (1.5, PEDAL_B)])
    assert found == [PEDAL_A[0]]
    assert elapsed < 0.5


async def test_wanted_device_stops_at_once() -> None:
    found, elapsed = await scan([(0.05, SPEAKER), (0.3, PEDAL_A)], wanted="dddd-4444", grace=1.0)
    assert SPEAKER[0] in found
    assert elapsed < 0.25  # no grace period with --device


async def test_no_pedal_scans_the_whole_timeout() -> None:
    found, elapsed = await scan([(0.05, SPEAKER)], timeout=0.4)
    assert found == [SPEAKER[0]]
    assert elapsed >= 0.4


async def test_without_stop_early_the_whole_timeout_is_used() -> None:
    found, elapsed = await scan([(0.05, PEDAL_A)], timeout=0.4, stop_early=False)
    assert found == [PEDAL_A[0]]
    assert elapsed >= 0.4


async def test_open_ble_uses_the_early_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    async def fake_scan(timeout: float, **options: Any) -> dict[str, Any]:
        calls.append({"timeout": timeout, **options})
        device = SimpleNamespace(address=PEDAL_A[0], name=BLE_NAME)
        return {PEDAL_A[0]: (device, ble.DeviceInfo(PEDAL_A[0], BLE_NAME, -58))}

    monkeypatch.setattr(ble, "_scan", fake_scan)
    _, chosen = await ble.open_ble(None, 5.0)
    assert chosen.identifier == PEDAL_A[0]
    assert calls == [
        {"timeout": 5.0, "wanted_id": None, "stop_early": True, "scanner_factory": None}
    ]


def test_default_grace_is_one_second() -> None:
    assert ble.SCAN_GRACE == 1.0


# --- spec 005: scan() for ``openvave scan`` (T015) ----------------------------------------------

WHEN = datetime(2026, 11, 19, 10, 0, tzinfo=UTC)


def ids(entries: list[Any]) -> list[str]:
    return [e.device.identifier for e in entries]


async def test_scan_orders_tank_g_by_signal_strength() -> None:
    entries = await ble.scan(
        0.1,
        scanner_factory=timed_scanner(
            [(UUID_3, TANK, None), (UUID_2, TANK, -61), (UUID_1, TANK, -58), (SPEAKER_ID, "S", -30)]
        ),
    )
    assert ids(entries) == [UUID_1, UUID_2, UUID_3]
    assert all(e.tank_g for e in entries)
    assert not any(e.known or e.selected or e.device.nickname for e in entries)


async def test_scan_ties_are_ordered_by_identifier() -> None:
    entries = await ble.scan(
        0.1, scanner_factory=timed_scanner([(UUID_2, TANK, -60), (UUID_1, TANK, -60)])
    )
    assert ids(entries) == [UUID_1, UUID_2]


async def test_scan_include_all_lists_other_advertisers_after_the_pedals() -> None:
    entries = await ble.scan(
        0.1,
        include_all=True,
        scanner_factory=timed_scanner(
            [(SPEAKER_ID, "Some Speaker", -30), (UUID_1, TANK, -70), ("CCCC", "", None)]
        ),
    )
    assert ids(entries) == [UUID_1, SPEAKER_ID, "CCCC"]
    assert [e.tank_g for e in entries] == [True, False, False]


async def test_scan_annotates_known_pedals(tmp_path: Path) -> None:
    known = (
        KnownDevices(path=tmp_path / "d.json")
        .select(UUID_2, "home", now=WHEN)
        .select(UUID_1.lower(), "stage", now=WHEN)
    )
    entries = await ble.scan(
        0.1,
        known=known,
        scanner_factory=timed_scanner(
            [(UUID_1, TANK, -58), (UUID_2, TANK, -61), (UUID_3, TANK, -70)]
        ),
    )
    by_id = {e.device.identifier: e for e in entries}
    assert by_id[UUID_1].device.nickname == "stage"
    assert by_id[UUID_1].known and by_id[UUID_1].selected
    assert by_id[UUID_2].device.nickname == "home"
    assert by_id[UUID_2].known and not by_id[UUID_2].selected
    assert not by_id[UUID_3].known and by_id[UUID_3].device.nickname is None


async def test_scan_uses_the_whole_timeout_after_a_pedal_is_seen() -> None:
    started = time.monotonic()
    entries = await ble.scan(
        0.4,
        scanner_factory=timed_scanner([(0.02, (UUID_1, TANK, -58)), (0.3, (UUID_2, TANK, -61))]),
    )
    assert time.monotonic() - started >= 0.4
    assert ids(entries) == [UUID_1, UUID_2]  # the late pedal is listed too (FR-003)


async def test_discover_is_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[float, dict[str, Any]]] = []

    async def fake_scan(timeout: float, **options: Any) -> dict[str, Any]:
        calls.append((timeout, options))
        a = SimpleNamespace(address=UUID_1, name=TANK)
        s = SimpleNamespace(address=SPEAKER_ID, name="S")
        return {
            UUID_1: (a, ble.DeviceInfo(UUID_1, TANK, -58)),
            SPEAKER_ID: (s, ble.DeviceInfo(SPEAKER_ID, "S", -30)),
        }

    monkeypatch.setattr(ble, "_scan", fake_scan)
    assert await ble.discover(3.0) == [ble.DeviceInfo(UUID_1, TANK, -58)]
    assert calls == [(3.0, {})]


# --- spec 005 M2: open_ble / locate with a Target (T034) ---------------------------------------

STAGE = Target(UUID_1, "stage", "selected")


async def locate(
    target: Target | str | None,
    adverts: list[tuple[float, tuple[str, str, int | None]]],
    *,
    timeout: float = 0.4,
) -> tuple[ble.DeviceInfo, float]:
    started = time.monotonic()
    _, chosen = await ble.locate(target, timeout, scanner_factory=timed_scanner(adverts))
    return chosen, time.monotonic() - started


async def test_target_stops_at_first_sight() -> None:
    chosen, elapsed = await locate(
        STAGE, [(0.02, (UUID_2, TANK, -50)), (0.05, (UUID_1, TANK, -58))], timeout=2.0
    )
    assert chosen.identifier == UUID_1
    assert elapsed < 0.5  # no grace period, far below the timeout


async def test_target_device_carries_nickname_and_chosen_by() -> None:
    chosen, _ = await locate(STAGE, [(0.01, (UUID_1, TANK, -58))])
    assert (chosen.nickname, chosen.chosen_by, chosen.rssi) == ("stage", "selected", -58)


async def test_target_matches_case_insensitively() -> None:
    target = Target(UUID_1.lower(), None, "environment")
    chosen, _ = await locate(target, [(0.01, (UUID_1, TANK, -58))])
    assert chosen.identifier == UUID_1
    assert chosen.chosen_by == "environment"


async def test_target_absent_others_seen_lists_tank_g_strongest_first() -> None:
    with pytest.raises(TargetNotFoundError) as caught:
        await locate(
            STAGE,
            [
                (0.01, (UUID_3, TANK, -70)),
                (0.02, (SPEAKER_ID, "Some Speaker", -30)),
                (0.03, (UUID_2, TANK, -61)),
            ],
            timeout=0.2,
        )
    err = caught.value
    assert err.target == STAGE
    assert [d.identifier for d in err.seen] == [UUID_2, UUID_3]
    assert err.exit_code == 3
    assert str(err) == f"stage ({UUID_1}) not found"


async def test_target_absent_waits_the_timeout_and_nothing_seen() -> None:
    started = time.monotonic()
    with pytest.raises(TargetNotFoundError) as caught:
        await ble.locate(STAGE, 0.2, scanner_factory=timed_scanner([]))
    assert caught.value.seen == ()
    assert time.monotonic() - started >= 0.2


async def test_no_target_one_pedal_is_only_one_found() -> None:
    chosen, _ = await locate(None, [(0.01, (UUID_1, TANK, -58)), (0.02, (SPEAKER_ID, "S", -30))])
    assert chosen.identifier == UUID_1
    assert chosen.chosen_by == "only_one_found"
    assert chosen.nickname is None


async def test_no_target_no_pedal() -> None:
    with pytest.raises(NoDeviceFoundError) as caught:
        await locate(None, [(0.01, (SPEAKER_ID, "S", -30))], timeout=0.1)
    assert not isinstance(caught.value, TargetNotFoundError)


async def test_no_target_several_pedals_strongest_first() -> None:
    with pytest.raises(MultipleDevicesError) as caught:
        await locate(None, [(0.01, (UUID_2, TANK, -61)), (0.02, (UUID_1, TANK, -58))])
    assert [d.identifier for d in caught.value.candidates] == [UUID_1, UUID_2]


async def test_plain_identifier_string_is_device_option() -> None:
    chosen, _ = await locate(UUID_1, [(0.01, (UUID_1, TANK, -58))])
    assert chosen.chosen_by == "device_option"
    assert chosen.nickname is None
    with pytest.raises(TargetNotFoundError, match=f"device {UUID_2} not found"):
        await locate(UUID_2, [(0.01, (UUID_1, TANK, -58))], timeout=0.1)


async def test_target_is_connected_whatever_its_name() -> None:
    chosen, _ = await locate(
        Target(SPEAKER_ID, None, "device_option"), [(0.01, (SPEAKER_ID, "Some Speaker", -30))]
    )
    assert chosen.name == "Some Speaker"


async def test_open_ble_builds_the_transport_for_the_located_device() -> None:
    transport, chosen = await ble.open_ble(
        STAGE, 0.4, scanner_factory=timed_scanner([(0.01, (UUID_1, TANK, -58))])
    )
    assert isinstance(transport, ble.BleakTransport)
    assert chosen.chosen_by == "selected"


def test_select_device_keeps_its_signature() -> None:
    found = [ble.DeviceInfo(UUID_1, TANK, -58)]
    assert select_device(found, UUID_1.lower()).identifier == UUID_1
    assert select_device(found, None).chosen_by is None
