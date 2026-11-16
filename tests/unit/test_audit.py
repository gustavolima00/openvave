"""The SC-004 audit sees every FakeTransport write and flags unsafe command bytes (T024)."""

from __future__ import annotations

from openvave.protocol import build_query
from openvave.transport.fake import FakeTransport
from tests.conftest import SENT_FRAMES
from tests.support.audit import unsafe_frames
from tests.support.captures import FW96_CONNECT, load_capture

CAP = load_capture(FW96_CONNECT)


def test_unsafe_frames_flags_write_erase_and_midi() -> None:
    safe = CAP.ordered_tx
    unsafe = [bytes([0x00, 0x59, cmd]) + safe[1][3:] for cmd in (0x21, 0x22, 0x15)]
    assert unsafe_frames(safe) == []
    assert unsafe_frames(safe + unsafe) == unsafe
    assert unsafe_frames([b"\x00"]) == [b"\x00"]


async def test_audit_records_fake_writes() -> None:
    before = len(SENT_FRAMES)
    fake = FakeTransport.from_capture(FW96_CONNECT)
    await fake.open()
    await fake.write(build_query())
    assert SENT_FRAMES[before:] == [build_query()]
