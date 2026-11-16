"""Query/read builders and read-reply parsing against the capture (T015)."""

from __future__ import annotations

import pytest

from openvave.errors import ProtocolError
from openvave.models import Region, RegionRead
from openvave.protocol.commands import build_query, build_read, parse_read_reply
from tests.support import mutations as m
from tests.support.captures import (
    DEVICE_INFO,
    FW96_CONNECT,
    GLOBAL,
    PRESET,
    QUERY,
    STATUS,
    load_capture,
)

CAP = load_capture(FW96_CONNECT)
REGION_LABELS = {
    Region.DEVICE_INFO: DEVICE_INFO,
    Region.GLOBAL: GLOBAL,
    Region.CURRENT_PRESET: PRESET,
    Region.STATUS: STATUS,
}


def test_build_query() -> None:
    assert build_query() == CAP.tx(QUERY)


@pytest.mark.parametrize("region", list(Region))
def test_build_read_matches_capture(region: Region) -> None:
    assert build_read(region) == CAP.tx(REGION_LABELS[region])


def test_build_read_rejects_raw_address() -> None:
    with pytest.raises(TypeError):
        build_read(0x10000000)  # type: ignore[arg-type]


def test_region_table() -> None:
    assert [(r.type, r.address, r.length) for r in Region] == [
        (5, 0xD0000000, 32),
        (4, 0x20000000, 4),
        (4, 0x10000000, 21),
        (4, 0xD0000000, 1),
    ]


@pytest.mark.parametrize("region", list(Region))
def test_parse_captured_replies(region: Region) -> None:
    rx = CAP.rx(REGION_LABELS[region])
    read = parse_read_reply(region, rx)
    assert read == RegionRead(region=region, data=rx[14:-1])
    assert len(read.data) == region.length


def test_parse_preset_data_value() -> None:
    read = parse_read_reply(Region.CURRENT_PRESET, CAP.rx(PRESET))
    # Same bytes as specs/protocol/command-layer.md "First values read from hardware".
    assert read.data.hex(" ") == "01 00 00 01 0f 04 3c 3c 46 32 32 00 00 00 00 05 04 07 43 16 43"


def _reason(region: Region, frame: bytes) -> tuple[str, str | None]:
    with pytest.raises(ProtocolError) as exc:
        parse_read_reply(region, frame)
    return exc.value.reason, exc.value.detail


def test_wrong_command() -> None:
    rx = m.set_command(CAP.rx(GLOBAL), 0x11)
    assert _reason(Region.GLOBAL, rx)[0] == "wrong_command"


def test_echo_mismatch_type() -> None:
    rx = m.set_echo(CAP.rx(GLOBAL), type=5)
    assert _reason(Region.GLOBAL, rx) == ("echo_mismatch", "type")


def test_echo_mismatch_address() -> None:
    rx = m.set_echo(CAP.rx(GLOBAL), address=0x10000000)
    assert _reason(Region.GLOBAL, rx) == ("echo_mismatch", "address")


def test_echo_mismatch_length() -> None:
    rx = m.set_echo(CAP.rx(GLOBAL), length=5)
    assert _reason(Region.GLOBAL, rx) == ("echo_mismatch", "length")


def test_reply_for_other_region_is_echo_mismatch() -> None:
    # STATUS and DEVICE_INFO share an address; type and length still tell them apart.
    assert _reason(Region.STATUS, CAP.rx(DEVICE_INFO))[0] == "echo_mismatch"


def test_short_data() -> None:
    rx = m.with_payload(CAP.rx(GLOBAL), b"\x00\x00\x01")
    assert _reason(Region.GLOBAL, rx)[0] == "short_data"


def test_body_shorter_than_echo() -> None:
    # A 0x23 reply whose body is only 2 bytes: built from the query reply.
    rx = m.with_payload(m.set_command(CAP.rx(QUERY), 0x11), b"\x04\x00")
    rx = m.set_command(rx, 0x23)
    assert _reason(Region.GLOBAL, rx)[0] == "short_data"


def test_corrupt_frame_propagates_decode_reason() -> None:
    assert _reason(Region.GLOBAL, m.flip_checksum(CAP.rx(GLOBAL)))[0] == "bad_checksum"
