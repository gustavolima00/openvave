"""Handshake payload → DeviceIdentity (T025)."""

from __future__ import annotations

import pytest

from openvave.errors import ProtocolError
from openvave.protocol import TESTED_FIRMWARE, decode_frame, parse_identity
from tests.support.captures import FW96_CONNECT, QUERY, load_capture
from tests.support.mutations import with_payload

CAP = load_capture(FW96_CONNECT)
REPLY = CAP.rx(QUERY)


def _payload(frame: bytes) -> bytes:
    return decode_frame(frame).body


def _renamed(text: bytes) -> bytes:
    """The captured payload with its leading ASCII replaced (still 27 bytes)."""
    original = _payload(REPLY)
    return text + original[len(text) :]


def test_tested_firmware() -> None:
    assert frozenset({96}) == TESTED_FIRMWARE


def test_captured_identity() -> None:
    identity = parse_identity(_payload(REPLY))
    assert identity.name == "TANK-Gv2"
    assert identity.firmware == 96
    assert identity.firmware_untested is False
    assert identity.raw == _payload(REPLY)
    assert len(identity.raw) == 27


def test_untested_firmware() -> None:
    frame = with_payload(REPLY, _renamed(b"TANK-Gv2_097"))
    identity = parse_identity(_payload(frame))
    assert identity.name == "TANK-Gv2"
    assert identity.firmware == 97
    assert identity.firmware_untested is True


def test_splits_at_last_underscore() -> None:
    frame = with_payload(REPLY, _renamed(b"TANK_Gv2_096"))
    identity = parse_identity(_payload(frame))
    assert identity.name == "TANK_Gv2"
    assert identity.firmware == 96


@pytest.mark.parametrize(
    "payload_of",
    [
        pytest.param(lambda p: p[:-1], id="too-short"),
        pytest.param(lambda p: p + b"\x00", id="too-long"),
        pytest.param(lambda p: b"", id="empty"),
        pytest.param(lambda p: b"TANK-Gv2-096" + p[12:], id="no-underscore"),
        pytest.param(lambda p: b"TANK-Gv2_09x" + p[12:], id="non-numeric-version"),
        pytest.param(lambda p: b"TANK-Gv2_\x00\x00\x00" + p[12:], id="empty-version"),
        pytest.param(lambda p: b"TANK-G\xe92_096" + p[12:], id="non-ascii"),
    ],
)
def test_bad_identity(payload_of: object) -> None:
    assert callable(payload_of)
    frame = with_payload(REPLY, payload_of(_payload(REPLY)))
    with pytest.raises(ProtocolError) as exc:
        parse_identity(_payload(frame))
    assert exc.value.reason == "bad_identity"
