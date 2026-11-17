"""Query/read builders and read-reply parsing against the capture (T015)."""

from __future__ import annotations

import pytest

from openvave.errors import ProtocolError
from openvave.models import Region, RegionRead
from openvave.protocol.commands import (
    build_query,
    build_read,
    build_storage_read,
    parse_read_reply,
    parse_storage_reply,
)
from openvave.protocol.storage import StorageRead
from tests.support import mutations as m
from tests.support import storage_fixture as sf
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


# -- storage reads (spec 003, T002) ---------------------------------------------------------------

STORAGE_IMAGE_READ = "00 59 23 08 00 00 04 00 00 00 00 f6 02 00 03"


def test_build_storage_read_image() -> None:
    assert build_storage_read(StorageRead.image()).hex(" ") == STORAGE_IMAGE_READ


def test_build_storage_read_preset_address() -> None:
    frame = build_storage_read(StorageRead.preset(2))
    assert frame[6:14] == bytes([4, 0x2C, 0, 0, 0, 21, 0, 0])
    assert frame == sf.read_request(0x2C, 21)


def test_build_storage_read_header() -> None:
    assert build_storage_read(StorageRead.header()) == sf.read_request(0, 2)


def test_build_storage_read_rejects_region_and_raw() -> None:
    with pytest.raises(TypeError):
        build_storage_read(Region.CURRENT_PRESET)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        build_storage_read((4, 0, 2))  # type: ignore[arg-type]


def test_parse_storage_reply() -> None:
    image = sf.synthetic_image()
    pairs = sf.storage_replies(image)
    assert parse_storage_reply(StorageRead.image(), pairs[sf.IMAGE_LABEL][1]) == image
    assert parse_storage_reply(StorageRead.header(), pairs[sf.HEADER_LABEL][1]) == image[:2]
    reply = pairs[sf.preset_label(2)][1]
    assert parse_storage_reply(StorageRead.preset(2), reply) == image[2 + 42 : 2 + 63]


def _storage_reason(target: StorageRead, frame: bytes) -> tuple[str, str | None]:
    with pytest.raises(ProtocolError) as exc:
        parse_storage_reply(target, frame)
    return exc.value.reason, exc.value.detail


def test_parse_storage_reply_errors() -> None:
    reply = sf.storage_replies(sf.synthetic_image())[sf.preset_label(2)][1]
    target = StorageRead.preset(2)
    assert _storage_reason(target, m.set_command(reply, 0x11))[0] == "wrong_command"
    assert _storage_reason(StorageRead.preset(3), reply) == ("echo_mismatch", "address")
    assert _storage_reason(target, m.set_echo(reply, type=5)) == ("echo_mismatch", "type")
    assert _storage_reason(target, m.set_echo(reply, length=20)) == ("echo_mismatch", "length")
    assert _storage_reason(target, m.with_payload(reply, b"\x00" * 20))[0] == "short_data"
    assert _storage_reason(target, m.flip_checksum(reply))[0] == "bad_checksum"


def test_build_read_unchanged_for_regions() -> None:
    for region in Region:
        assert build_read(region) == CAP.tx(REGION_LABELS[region])
