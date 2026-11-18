"""Pedal state for the spec 003 write tests (M1): edit buffer, global block, stored image.

Frames here are built without ``openvave`` code (``storage_fixture.frame``), so a fixture cannot
hide an encoder bug. The pedal starts on stored preset 1B (index 1) with the public fw96 preset
in its edit buffer, like ``captures/fw96/20261116-probe-connect.jsonl``.
"""

from __future__ import annotations

from collections.abc import Mapping

from openvave.transport.fake import FakeTransport, Replies
from tests.support import storage_fixture as sf
from tests.support.captures import FW96_CONNECT, QUERY, load_capture
from tests.support.mutations import with_payload

CAP = load_capture(FW96_CONNECT)
EDIT_BUFFER = 0x10000000
GLOBAL = 0x20000000
ACK = bytes.fromhex("00 59 00 01 00 00 00 ff")
EDIT, NORMAL, TUNER = 0, 1, 2
FW97_QUERY_RX = with_payload(CAP.rx(QUERY), b"TANK-Gv2_097" + CAP.rx(QUERY)[18:-1])


def global_block(mode: int, bank: int = 0, slot: int = 1) -> bytes:
    """``browse bank, bank, slot, mode`` (0-based bank and slot; slot 1 = B)."""
    return bytes([bank, bank, slot, mode])


def write_frame(address: int, data: bytes) -> bytes:
    """An independent encoding of a type-4 ``0x22`` write (frame layout from command-layer.md)."""
    body = bytes([4]) + address.to_bytes(4, "little") + len(data).to_bytes(3, "little") + data
    return sf.frame(0x22, body)


def nak(status: int = 1) -> bytes:
    return sf.frame(0x00, bytes([status]))


def make_fake(
    mode: int = EDIT,
    *,
    buffer: bytes = sf.PUBLIC_PRESET,
    image: bytes | None = None,
    apply_writes: bool = True,
    select_transient: int = 0,
    script: Mapping[str, tuple[bytes, Replies]] | None = None,
    query_rx: bytes | None = None,
    cls: type[FakeTransport] = FakeTransport,
    glob: bytes | None = None,
) -> FakeTransport:
    """A fake pedal on 1B: stored image at 0, edit buffer, global block; ACKs allowlisted writes.

    ``glob`` replaces the whole global block (e.g. slot ``ff`` for bypass, spec 004).
    """
    full: dict[str, tuple[bytes, Replies]] = {QUERY: (CAP.tx(QUERY), query_rx or CAP.rx(QUERY))}
    full.update(script or {})
    memory = {
        0: sf.synthetic_image() if image is None else image,
        EDIT_BUFFER: buffer,
        GLOBAL: global_block(mode) if glob is None else glob,
    }
    return cls(full, memory=memory, apply_writes=apply_writes, select_transient=select_transient)


def writes(fake: FakeTransport) -> list[bytes]:
    """The ``0x22`` frames the fake received."""
    return [f for f in fake.sent if f[2] == 0x22]
