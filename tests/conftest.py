"""Shared pytest configuration."""

from __future__ import annotations

from collections.abc import Iterator

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--hardware",
        action="store_true",
        default=False,
        help="run tests that need a real Tank-G pedal",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--hardware"):
        return
    skip = pytest.mark.skip(reason="needs --hardware and a real Tank-G")
    for item in items:
        if "hardware" in item.keywords:
            item.add_marker(skip)


SENT_FRAMES: list[bytes] = []
"""Every frame written to any FakeTransport during this test session (SC-004 audit)."""


@pytest.fixture(scope="session", autouse=True)
def _sc004_audit() -> Iterator[list[bytes]]:
    """Fail the session if any frame written to a FakeTransport is not a query/read."""
    from openvave.transport.fake import FakeTransport
    from tests.support.audit import unsafe_frames

    original = FakeTransport.write

    async def audited_write(self: FakeTransport, frame: bytes) -> None:
        SENT_FRAMES.append(bytes(frame))
        await original(self, frame)

    FakeTransport.write = audited_write  # type: ignore[method-assign]
    try:
        yield SENT_FRAMES
    finally:
        FakeTransport.write = original  # type: ignore[method-assign]
    bad = unsafe_frames(SENT_FRAMES)
    if bad:
        pytest.fail(
            "SC-004 violated: non read-only frames were sent: "
            + ", ".join(f.hex(" ") for f in bad),
            pytrace=False,
        )
