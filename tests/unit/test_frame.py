"""Frame codec against the fw96 capture (T013, Constitution III)."""

from __future__ import annotations

import pytest

from openvave.errors import ProtocolError, UnsafeCommandError
from openvave.protocol.frame import ALLOWED_COMMANDS, checksum, decode_frame, encode_frame
from tests.support import mutations as m
from tests.support.captures import FW96_CONNECT, LABELS, QUERY, load_capture

CAP = load_capture(FW96_CONNECT)
READ_LABELS = [label for label in LABELS if label != QUERY]


def test_query_request_bytes() -> None:
    assert encode_frame(0x11, b"") == bytes.fromhex("00 59 11 00 00 00 ff")
    assert encode_frame(0x11, b"") == CAP.tx(QUERY)


@pytest.mark.parametrize("label", READ_LABELS)
def test_read_requests_encode_identically(label: str) -> None:
    tx = CAP.tx(label)
    assert encode_frame(0x23, tx[6:-1]) == tx


@pytest.mark.parametrize("label", LABELS)
@pytest.mark.parametrize("side", ["tx", "rx"])
def test_captured_frames_round_trip(label: str, side: str) -> None:
    raw = CAP.tx(label) if side == "tx" else CAP.rx(label)
    frame = decode_frame(raw)
    assert frame.command == raw[2]
    assert frame.body == raw[6:-1]
    assert encode_frame(frame.command, frame.body) == raw


def test_checksum_excludes_header() -> None:
    rx = CAP.rx(LABELS[3])
    assert checksum(rx[6:-1]) == rx[-1]
    assert checksum(b"") == 0xFF


@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        (lambda f: b"\x01" + f[1:], "bad_marker"),
        (lambda f: f[:1] + b"\x5a" + f[2:], "bad_marker"),
        (lambda f: m.truncate(f, len(f) - 1), "length_mismatch"),
        (lambda f: f + b"\x00", "length_mismatch"),
        (lambda f: m.truncate(f, 4), "length_mismatch"),
        (m.flip_checksum, "bad_checksum"),
    ],
    ids=["marker0", "marker1", "short", "long", "header-only", "checksum"],
)
@pytest.mark.parametrize("label", LABELS)
def test_decode_rejections(label: str, mutate: object, reason: str) -> None:
    bad = mutate(CAP.rx(label))  # type: ignore[operator]
    with pytest.raises(ProtocolError) as exc:
        decode_frame(bad)
    assert exc.value.reason == reason


def test_decode_accepts_any_command_byte() -> None:
    # Decoding never refuses a command byte; the session checks it against the request.
    frame = decode_frame(m.set_command(CAP.rx(LABELS[1]), 0x22))
    assert frame.command == 0x22


@pytest.mark.parametrize("command", range(256))
def test_only_query_and_read_encode(command: int) -> None:
    if command in (0x11, 0x23):
        assert encode_frame(command, b"")[2] == command
    else:
        with pytest.raises(UnsafeCommandError):
            encode_frame(command, b"")


def test_allowlist_is_exactly_query_and_read() -> None:
    assert frozenset({0x11, 0x23}) == ALLOWED_COMMANDS
