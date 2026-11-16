"""Each mutation helper changes only what it claims (T011)."""

from __future__ import annotations

import pytest

from tests.support import mutations as m
from tests.support.captures import FW96_CONNECT, LABELS, load_capture

CAP = load_capture(FW96_CONNECT)
QUERY_RX = CAP.pairs[LABELS[0]][1]
PRESET_RX = CAP.pairs[LABELS[3]][1]


def _valid_checksum(frame: bytes) -> bool:
    return frame[-1] == (~sum(frame[6:-1])) & 0xFF


def test_flip_checksum() -> None:
    out = m.flip_checksum(PRESET_RX)
    assert out[:-1] == PRESET_RX[:-1]
    assert out[-1] != PRESET_RX[-1]
    assert not _valid_checksum(out)


def test_set_command() -> None:
    out = m.set_command(PRESET_RX, 0x22)
    assert out[2] == 0x22
    assert out[:2] == PRESET_RX[:2] and out[3:] == PRESET_RX[3:]
    assert _valid_checksum(out)  # header is not summed


@pytest.mark.parametrize(
    ("kwargs", "start", "stop", "expected"),
    [
        ({"type": 5}, 6, 7, b"\x05"),
        ({"address": 0x20000000}, 7, 11, (0x20000000).to_bytes(4, "little")),
        ({"length": 20}, 11, 14, (20).to_bytes(3, "little")),
    ],
)
def test_set_echo(kwargs: dict[str, int], start: int, stop: int, expected: bytes) -> None:
    out = m.set_echo(PRESET_RX, **kwargs)
    assert out[start:stop] == expected
    assert out[:start] == PRESET_RX[:start]
    assert out[stop:-1] == PRESET_RX[stop:-1]
    assert _valid_checksum(out)


def test_with_payload_read_reply_keeps_echo() -> None:
    data = bytes(21)
    out = m.with_payload(PRESET_RX, data)
    assert out[6:14] == PRESET_RX[6:14]
    assert out[14:-1] == data
    assert int.from_bytes(out[3:6], "little") == 8 + 21
    assert _valid_checksum(out)


def test_with_payload_query_replaces_body() -> None:
    payload = b"TANK-Gv2_097".ljust(27, b"\x00")
    out = m.with_payload(QUERY_RX, payload)
    assert out[6:-1] == payload
    assert out[:3] == QUERY_RX[:3]
    assert _valid_checksum(out)


def test_with_payload_changes_length() -> None:
    out = m.with_payload(QUERY_RX, b"short")
    assert int.from_bytes(out[3:6], "little") == 5
    assert len(out) == 12
    assert _valid_checksum(out)


def test_truncate() -> None:
    assert m.truncate(PRESET_RX, 10) == PRESET_RX[:10]


@pytest.mark.parametrize("n", [1, 2, 3, 7, len(PRESET_RX)])
def test_split(n: int) -> None:
    chunks = m.split(PRESET_RX, n)
    assert len(chunks) == n
    assert all(chunks)
    assert b"".join(chunks) == PRESET_RX


def test_split_rejects_bad_n() -> None:
    with pytest.raises(ValueError):
        m.split(PRESET_RX, 0)
    with pytest.raises(ValueError):
        m.split(PRESET_RX, len(PRESET_RX) + 1)


def test_with_region_data_rewrites_one_byte() -> None:
    from openvave.protocol import decode_frame

    out = m.with_region_data(PRESET_RX, 15, 0x40)
    assert _valid_checksum(out)
    frame = decode_frame(out)
    data = frame.body[8:]
    original = PRESET_RX[6 + 8 : -1]
    assert data[15] == 0x40
    assert data[:15] == original[:15] and data[16:] == original[16:]
    assert len(out) == len(PRESET_RX)


def test_with_region_data_offset_beyond_data() -> None:
    with pytest.raises(ValueError):
        m.with_region_data(PRESET_RX, 21, 0)
    with pytest.raises(ValueError):
        m.with_region_data(PRESET_RX, -1, 0)
