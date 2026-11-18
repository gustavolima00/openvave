"""Shared pytest configuration."""

from __future__ import annotations

import functools
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
PERSISTENT_VIOLATIONS: list[tuple[str, bytes]] = []
"""``(test id, frame)`` of every persistent write sent by a test not marked
``persistent_writes`` (spec 004 SC-005, R5)."""
_CURRENT: dict[str, object] = {"test": None, "allowed": False}


@pytest.fixture(autouse=True)
def _persistent_marker(request: pytest.FixtureRequest) -> Iterator[None]:
    """Persistent frames are allowed only while a test marked ``persistent_writes`` runs."""
    _CURRENT["test"] = request.node.nodeid
    _CURRENT["allowed"] = request.node.get_closest_marker("persistent_writes") is not None
    try:
        yield
    finally:
        _CURRENT["test"], _CURRENT["allowed"] = None, False


@pytest.fixture(scope="session", autouse=True)
def _sc004_audit() -> Iterator[list[bytes]]:
    """Fail the session if any frame written to a FakeTransport is not a query, a read or an
    allowlisted write (``tests/support/audit.py``)."""
    from openvave.transport.fake import FakeTransport
    from tests.support.audit import persistent_violation, unsafe_frames

    original = FakeTransport.write

    @functools.wraps(original)
    async def audited_write(self: FakeTransport, frame: bytes) -> None:
        # record whole requests: chunks of a split request are counted once reassembled
        before = len(self.sent)
        try:
            await original(self, frame)
        finally:
            for request in self.sent[before:]:
                SENT_FRAMES.append(bytes(request))
                if persistent_violation(request, bool(_CURRENT["allowed"])):
                    PERSISTENT_VIOLATIONS.append((str(_CURRENT["test"]), bytes(request)))

    FakeTransport.write = audited_write  # type: ignore[method-assign]
    try:
        yield SENT_FRAMES
    finally:
        FakeTransport.write = original  # type: ignore[method-assign]
    if PERSISTENT_VIOLATIONS:
        pytest.fail(
            "SC-005 violated: persistent writes sent by tests not marked persistent_writes: "
            + "; ".join(f"{test}: {frame.hex(' ')}" for test, frame in PERSISTENT_VIOLATIONS),
            pytrace=False,
        )
    bad = unsafe_frames(SENT_FRAMES, allow_persistent=True)
    if bad:
        pytest.fail(
            "SC-004/FR-013 violated: frames outside the command allowlist were sent: "
            + ", ".join(f.hex(" ") for f in bad),
            pytrace=False,
        )
