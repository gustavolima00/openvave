"""``parse_write_reply``: the ACK and every NAK shape (T023, FR-011, research R3)."""

from __future__ import annotations

import pytest

from openvave.errors import ProtocolError, WriteNakError
from openvave.protocol.commands import parse_write_reply
from tests.support import storage_fixture as sf
from tests.support.write_fixture import ACK


def test_ack_is_accepted() -> None:
    assert parse_write_reply(ACK) is None


@pytest.mark.parametrize(
    "reply",
    [
        sf.frame(0x00, b"\x01"),  # status 01
        sf.frame(0x00, b"\xff"),  # status ff
        sf.frame(0x22, b"\x00"),  # command byte 22
        sf.frame(0x23, b"\x00"),  # command byte 23
        sf.frame(0x00, b""),  # 7-byte frame
        sf.frame(0x00, b"\x00\x00"),  # 9-byte frame
    ],
    ids=["status01", "statusff", "cmd22", "cmd23", "len7", "len9"],
)
def test_nak(reply: bytes) -> None:
    with pytest.raises(WriteNakError) as exc:
        parse_write_reply(reply)
    assert exc.value.reply == reply
    assert exc.value.exit_code == 7
    assert isinstance(exc.value, ProtocolError)
    assert reply.hex(" ") in str(exc.value)


def test_bad_checksum_is_a_frame_error() -> None:
    bad = ACK[:-1] + b"\x00"
    with pytest.raises(ProtocolError) as exc:
        parse_write_reply(bad)
    assert exc.value.reason == "bad_checksum"
    assert not isinstance(exc.value, WriteNakError)
