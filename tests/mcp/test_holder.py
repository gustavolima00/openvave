"""The connection holder through the MCP tools (spec 006 US3, FR-011…FR-014, SC-002)."""

from __future__ import annotations

import asyncio
from pathlib import Path

from openvave.errors import NoDeviceFoundError
from openvave.transport.fake import FakeTransport
from tests.mcp.conftest import CountingFactory, open_harness, options, settle
from tests.support.captures import FW96_CONNECT

QUERY_FRAME = bytes.fromhex("00 59 11 00 00 00 ff")


def queries(fake: FakeTransport) -> int:
    return sum(1 for frame in fake.sent if frame == QUERY_FRAME)


async def test_lazy_start_connects_to_nothing(tmp_path: Path, factory: CountingFactory) -> None:
    async with open_harness(options(tmp_path), factory) as harness:
        tools = await harness.client.list_tools()
        assert {t.name for t in tools.tools} >= {"pedal_status", "pedal_info", "pedal_disconnect"}
        status = await harness.ok("pedal_status")
        assert status["connected"] is False
        assert harness.factory.calls == 0


async def test_many_reads_one_connection(tmp_path: Path, factory: CountingFactory) -> None:
    async with open_harness(options(tmp_path), factory) as harness:
        for _ in range(11):
            await harness.ok("pedal_info")
        assert harness.factory.calls == 1
        assert harness.holder.opens == 1
        assert queries(harness.factory.fake) == 1


async def test_disconnect_is_idempotent_and_next_call_reconnects(
    tmp_path: Path, factory: CountingFactory
) -> None:
    async with open_harness(options(tmp_path), factory) as harness:
        first = await harness.ok("pedal_disconnect")
        assert first["was_connected"] is False
        await harness.ok("pedal_info")
        fake = harness.factory.fake
        result = await harness.ok("pedal_disconnect")
        assert result["was_connected"] is True
        assert fake.closed
        assert (await harness.ok("pedal_disconnect"))["was_connected"] is False
        assert (await harness.ok("pedal_status"))["connected"] is False
        await harness.ok("pedal_info")
        assert harness.factory.calls == 2


async def test_idle_release_closes_and_next_call_reconnects(
    tmp_path: Path, factory: CountingFactory
) -> None:
    async with open_harness(options(tmp_path), factory) as harness:
        await harness.ok("pedal_info")
        assert harness.sleep.calls == [300.0]
        fake = harness.factory.fake
        await harness.sleep.fire()
        assert fake.closed
        assert (await harness.ok("pedal_status"))["connected"] is False
        await harness.ok("pedal_info")
        assert harness.factory.calls == 2


async def test_idle_timer_rearmed_by_each_call(tmp_path: Path, factory: CountingFactory) -> None:
    async with open_harness(options(tmp_path), factory) as harness:
        await harness.ok("pedal_info")
        await harness.ok("pedal_info")
        await settle()
        # the first timer was cancelled when the second call started: firing leaves one release
        assert len(harness.sleep.calls) == 2
        await harness.sleep.fire()
        assert (await harness.ok("pedal_status"))["connected"] is False


async def test_idle_release_zero_never_arms(tmp_path, factory: CountingFactory) -> None:
    async with open_harness(options(tmp_path, idle_release=0), factory) as h:
        await h.ok("pedal_info")
        assert h.sleep.calls == []
        assert (await h.ok("pedal_status"))["connected"] is True


async def test_lost_between_calls_reopens_once(tmp_path: Path, factory: CountingFactory) -> None:
    async with open_harness(options(tmp_path), factory) as harness:
        await harness.ok("pedal_info")
        harness.factory.fake.lose_link()
        assert (await harness.ok("pedal_status"))["connected"] is False
        await harness.ok("pedal_info")
        assert harness.factory.calls == 2


async def test_lost_during_a_call_is_an_error_then_next_call_reopens(tmp_path) -> None:
    made: list[int] = []

    def make() -> FakeTransport:
        made.append(1)
        # the first connection drops after the handshake and two reads
        after = 3 if len(made) == 1 else None
        return FakeTransport.from_capture(FW96_CONNECT, disconnect_after=after)

    factory = CountingFactory(make=make)
    async with open_harness(options(tmp_path), factory) as h:
        message = await h.error("pedal_info")
        assert message.startswith("connection_lost: ")
        first = factory.fake
        assert len(first.sent) == 3  # nothing sent after the loss
        status = await h.ok("pedal_status")
        assert status["connected"] is False
        assert status["last_error"].startswith("connection_lost: ")
        await h.ok("pedal_info")
        assert factory.calls == 2
        assert len(first.sent) == 3  # nothing resent on the old link


async def test_failed_reopen_is_an_error_and_server_keeps_running(
    tmp_path: Path, factory: CountingFactory
) -> None:
    async with open_harness(options(tmp_path), factory) as harness:
        await harness.ok("pedal_info")
        harness.factory.fake.lose_link()
        harness.factory.error = NoDeviceFoundError("no TANK-Gv2_BLE found")
        message = await harness.error("pedal_info")
        assert message.splitlines()[0] == "no_device_found: no TANK-Gv2_BLE found"
        assert "phone app" in message
        assert harness.factory.calls == 2  # one attempt, no retry
        harness.factory.error = None
        await harness.ok("pedal_info")


async def test_pedal_operations_are_serialised(tmp_path: Path, factory: CountingFactory) -> None:
    async with open_harness(options(tmp_path), factory) as harness:
        holder = harness.holder
        entered = asyncio.Event()
        release = asyncio.Event()
        order: list[str] = []

        async def first() -> None:
            async with holder.use():
                order.append("first in")
                entered.set()
                await release.wait()
                order.append("first out")

        async def second() -> None:
            await entered.wait()
            async with holder.use():
                order.append("second in")

        tasks = [asyncio.create_task(first()), asyncio.create_task(second())]
        await entered.wait()
        await settle()
        assert order == ["first in"]
        status = await harness.ok("pedal_status")  # never waits behind a pedal call
        assert status["connected"] is True
        release.set()
        await asyncio.gather(*tasks)
        assert order == ["first in", "first out", "second in"]
        assert holder.opens == 1


async def test_concurrent_tool_calls_share_one_connection(
    tmp_path: Path, factory: CountingFactory
) -> None:
    async with open_harness(options(tmp_path), factory) as harness:
        results = await asyncio.gather(*(harness.call("pedal_info") for _ in range(3)))
        assert not any(r.is_error for r in results)
        assert harness.factory.calls == 1


async def test_shutdown_closes_the_connection(tmp_path, factory: CountingFactory) -> None:
    async with open_harness(options(tmp_path), factory) as h:
        await h.ok("pedal_info")
        fake = factory.fake
    assert fake.closed
