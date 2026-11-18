"""The command audit sees every FakeTransport write and flags unsafe frames (T024 of 001, T026)."""

from __future__ import annotations

import pytest

from openvave.protocol import build_query
from openvave.transport.fake import FakeTransport
from tests.conftest import SENT_FRAMES
from tests.support import storage_fixture as sf
from tests.support.audit import persistent_violation, persistent_write, unsafe_frames
from tests.support.captures import FW96_CONNECT, load_capture
from tests.support.write_fixture import write_frame

CAP = load_capture(FW96_CONNECT)

ALLOWED_WRITES = [
    write_frame(0x10000004, bytes(14)),
    write_frame(0x10000000, b"\x01"),
    write_frame(0x10000003, b"\x00"),
    write_frame(0x10000012, bytes.fromhex("ff 00 00")),
    write_frame(0xE0000000, b"\x01"),
    write_frame(0xE0000023, b"\x01"),
    write_frame(0xE1000001, b"\x01"),  # bypass 1B (spec 004 M1)
    write_frame(0xE1000023, b"\x01"),
    write_frame(0xD0000000, b"\x00"),  # loopback off
    write_frame(0xD0000000, b"\x01"),  # loopback on
]
FORBIDDEN_WRITES = {
    "commit": write_frame(0xF0000000, b""),
    "loopback-02": write_frame(0xD0000000, b"\x02"),
    "loopback-x2": write_frame(0xD0000000, b"\x01\x01"),
    "loopback-t5": sf.frame(0x22, bytes.fromhex("05 00 00 00 d0 01 00 00 01")),
    "bypass-36": write_frame(0xE1000024, b"\x01"),
    "bypass-00": write_frame(0xE1000001, b"\x00"),
    "stored-0": write_frame(0x0, bytes(758)),
    "stored-2": write_frame(0x2, bytes(21)),
    "knob-1byte": write_frame(0x10000004, b"\x05"),
    "buffer-21": write_frame(0x10000000, bytes(21)),
    "switch-4": write_frame(0x10000004, b"\x01"),
    "select-36": write_frame(0xE0000024, b"\x01"),
    "select-00": write_frame(0xE0000006, b"\x00"),
    "type-6": sf.frame(0x22, bytes.fromhex("06 04 00 00 10 0e 00 00") + bytes(14)),
    "erase": sf.frame(0x21, bytes.fromhex("06 00 00 00 00 00 10 00")),
}


def test_reads_and_queries_are_safe() -> None:
    assert unsafe_frames(CAP.ordered_tx) == []


def test_erase_and_midi_and_short_frames_are_unsafe() -> None:
    safe = CAP.ordered_tx
    unsafe = [bytes([0x00, 0x59, cmd]) + safe[1][3:] for cmd in (0x21, 0x15)]
    assert unsafe_frames(safe + unsafe) == unsafe
    assert unsafe_frames([b"\x00"]) == [b"\x00"]


@pytest.mark.parametrize("frame", ALLOWED_WRITES, ids=lambda f: f[6:11].hex())
def test_allowlisted_writes_are_safe(frame: bytes) -> None:
    assert unsafe_frames([frame]) == []


@pytest.mark.parametrize("name", sorted(FORBIDDEN_WRITES))
def test_forbidden_writes_are_unsafe(name: str) -> None:
    frame = FORBIDDEN_WRITES[name]
    assert unsafe_frames([frame]) == [frame]


def test_a_bare_0x22_header_is_unsafe() -> None:
    frame = bytes([0x00, 0x59, 0x22]) + CAP.ordered_tx[1][3:]
    assert unsafe_frames([frame]) == [frame]


async def test_audit_records_fake_writes() -> None:
    before = len(SENT_FRAMES)
    fake = FakeTransport.from_capture(FW96_CONNECT)
    await fake.open()
    await fake.write(build_query())
    assert SENT_FRAMES[before:] == [build_query()]


# -- persistent writes (spec 004 M2, T050) ------------------------------------------------------

PERSISTENT = {
    "slot-1a": write_frame(0x02, bytes(21)),
    "slot-1c": write_frame(0x2C, sf.PUBLIC_PRESET),
    "slot-9d": write_frame(0x2E1, bytes(21)),
    "commit": write_frame(0xF0000000, b""),
    "image": write_frame(0x0, sf.synthetic_image()),
}
NEVER = {
    "slot-addr-3": write_frame(0x03, bytes(21)),
    "slot-36": write_frame(0x2F6, bytes(21)),
    "slot-20b": write_frame(0x02, bytes(20)),
    "commit-data": write_frame(0xF0000000, b"\x00"),
    "image-header-0000": write_frame(0x0, bytes(758)),
    "image-757": write_frame(0x0, sf.synthetic_image()[:757]),
    "global-mode": write_frame(0x20000003, b"\x01"),
    "edit-buffer-21": write_frame(0x10000000, bytes(21)),
}


@pytest.mark.parametrize("name", sorted(PERSISTENT))
def test_persistent_writes_are_unsafe_unless_allowed(name: str) -> None:
    frame = PERSISTENT[name]
    assert persistent_write(frame)
    assert unsafe_frames([frame]) == [frame]
    assert unsafe_frames([frame], allow_persistent=True) == []


@pytest.mark.parametrize("name", sorted(NEVER))
def test_other_stored_global_and_buffer_writes_are_never_allowed(name: str) -> None:
    frame = NEVER[name]
    assert not persistent_write(frame)
    assert unsafe_frames([frame], allow_persistent=True) == [frame]


def test_persistent_violation_needs_the_marker() -> None:
    frame = PERSISTENT["commit"]
    assert persistent_violation(frame, allowed=False) is True
    assert persistent_violation(frame, allowed=True) is False
    assert persistent_violation(write_frame(0xE0000001, b"\x01"), allowed=False) is False


def test_this_test_is_not_marked(request: pytest.FixtureRequest) -> None:
    from tests.conftest import _CURRENT

    assert _CURRENT["allowed"] is False
    assert request.node.get_closest_marker("persistent_writes") is None


@pytest.mark.persistent_writes
def test_a_marked_test_is_allowed() -> None:
    from tests.conftest import _CURRENT

    assert _CURRENT["allowed"] is True
