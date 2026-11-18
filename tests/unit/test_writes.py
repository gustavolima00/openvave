"""``WriteTarget`` allowlist, ``build_write`` frames and the knob-block rebuild (T021, US2)."""

from __future__ import annotations

import dataclasses

import pytest

from openvave.errors import UnsafeCommandError
from openvave.protocol.commands import build_write
from openvave.protocol.frame import checksum, encode_frame
from openvave.protocol.writes import WriteTarget, allowed_write_body, rebuild_knob_block
from tests.support import storage_fixture as sf
from tests.support.write_fixture import write_frame

GAIN_90 = "00 59 22 16 00 00 04 04 00 00 10 0e 00 00 0f 04 5a 3c 46 32 32 00 00 00 00 05 04 07 76"
SELECT_6 = "00 59 22 09 00 00 04 06 00 00 e0 01 00 00 01 13"


def test_knob_block_target() -> None:
    t = WriteTarget.knob_block()
    assert (t.kind, t.type, t.address, t.length, t.argument) == (
        "knob_block",
        4,
        0x10000004,
        14,
        None,
    )


@pytest.mark.parametrize("k", range(4))
def test_block_switch_targets(k: int) -> None:
    t = WriteTarget.block_switch(k)
    assert (t.kind, t.type, t.address, t.length, t.argument) == (
        "block_switch",
        4,
        0x10000000 + k,
        1,
        k,
    )


def test_led_colour_target() -> None:
    t = WriteTarget.led_colour()
    assert (t.kind, t.type, t.address, t.length, t.argument) == (
        "led_colour",
        4,
        0x10000012,
        3,
        None,
    )


@pytest.mark.parametrize("i", [0, 6, 35])
def test_preset_select_targets(i: int) -> None:
    t = WriteTarget.preset_select(i)
    assert (t.kind, t.type, t.address, t.length, t.argument) == (
        "preset_select",
        4,
        0xE0000000 + i,
        1,
        i,
    )


@pytest.mark.parametrize(
    "make",
    [
        lambda: WriteTarget.block_switch(4),
        lambda: WriteTarget.block_switch(-1),
        lambda: WriteTarget.preset_select(36),
        lambda: WriteTarget.preset_select(-1),
    ],
    ids=["switch4", "switch-1", "select36", "select-1"],
)
def test_out_of_range_arguments(make: object) -> None:
    with pytest.raises(ValueError):
        make()  # type: ignore[operator]


def test_no_address_based_construction() -> None:
    with pytest.raises(TypeError):
        WriteTarget("knob_block", 4, 0x0, 14, None)  # type: ignore[call-arg]
    with pytest.raises((TypeError, ValueError)):
        WriteTarget(kind="led_colour", type=4, address=0xF0000000, length=0, argument=None)  # type: ignore[call-arg]


@pytest.mark.parametrize(
    "changes",
    [
        {"address": 0x00000002},
        {"address": 0xF0000000},
        {"address": 0xD0000000},
        {"length": 21},
        {"argument": 7},
        {"kind": "preset_select"},
    ],
)
def test_replace_cannot_escape_the_allowlist(changes: dict[str, object]) -> None:
    with pytest.raises((TypeError, ValueError)):
        dataclasses.replace(WriteTarget.knob_block(), **changes)  # type: ignore[arg-type]


def test_knob_block_vector_gain_90() -> None:
    data = rebuild_knob_block(sf.PUBLIC_PRESET, 6, 90)
    assert build_write(WriteTarget.knob_block(), data) == bytes.fromhex(GAIN_90)


def test_preset_select_vector() -> None:
    assert build_write(WriteTarget.preset_select(6), b"\x01") == bytes.fromhex(SELECT_6)


def test_block_switch_frame() -> None:
    frame = build_write(WriteTarget.block_switch(1), b"\x01")
    body = bytes.fromhex("04 01 00 00 10 01 00 00 01")
    assert frame == bytes.fromhex("00 59 22 09 00 00") + body + bytes([checksum(body)])
    assert frame == write_frame(0x10000001, b"\x01")


def test_led_colour_frame() -> None:
    frame = build_write(WriteTarget.led_colour(), bytes.fromhex("ff 00 00"))
    assert frame == write_frame(0x10000012, bytes.fromhex("ff 00 00"))
    assert frame[3:6] == bytes([11, 0, 0])


@pytest.mark.parametrize(
    ("target", "data"),
    [
        (WriteTarget.knob_block(), bytes(13)),
        (WriteTarget.knob_block(), bytes(15)),
        (WriteTarget.block_switch(0), b""),
        (WriteTarget.led_colour(), b"\xff\x00"),
        (WriteTarget.preset_select(0), b"\x01\x01"),
    ],
)
def test_wrong_data_length(target: WriteTarget, data: bytes) -> None:
    with pytest.raises(ValueError):
        build_write(target, data)


@pytest.mark.parametrize("data", [b"\x00", b"\x02", b"\xff"])
def test_preset_select_data_is_always_01(data: bytes) -> None:
    with pytest.raises(ValueError):
        build_write(WriteTarget.preset_select(3), data)


def test_build_write_requires_a_target() -> None:
    with pytest.raises(TypeError):
        build_write((4, 0x10000004, 14), bytes(14))  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "body",
    [
        b"",
        bytes.fromhex("04 00 00 00 f0 00 00 00"),  # commit
        bytes.fromhex("04 02 00 00 00 15 00 00") + bytes(21),  # stored preset 0
        bytes.fromhex("04 00 00 00 d0 01 00 00 02"),  # loopback flag, data 02
        bytes.fromhex("04 00 00 00 d0 02 00 00 01 01"),  # loopback, 2 bytes
        bytes.fromhex("05 00 00 00 d0 01 00 00 01"),  # loopback, type 5
        bytes.fromhex("04 24 00 00 e1 01 00 00 01"),  # bypass 36
        bytes.fromhex("04 01 00 00 e1 01 00 00 00"),  # bypass data 00
        bytes.fromhex("04 04 00 00 10 01 00 00 05"),  # 1-byte knob write
        bytes.fromhex("04 06 00 00 e0 01 00 00 00"),  # select with data 00
        bytes.fromhex("06 04 00 00 10 0e 00 00") + bytes(14),  # wrong type
    ],
    ids=[
        "empty",
        "commit",
        "stored",
        "loopback02",
        "loopback-x2",
        "loopback-t5",
        "bypass36",
        "bypass00",
        "knob1",
        "select00",
        "type6",
    ],
)
def test_encode_frame_refuses_writes_outside_the_allowlist(body: bytes) -> None:
    with pytest.raises(UnsafeCommandError):
        encode_frame(0x22, body)


def test_encode_frame_accepts_allowlisted_write_body() -> None:
    frame = bytes.fromhex(SELECT_6)
    assert encode_frame(0x22, frame[6:-1]) == frame


def test_rebuild_knob_block_changes_one_byte() -> None:
    buffer = sf.PUBLIC_PRESET
    for offset in range(4, 18):
        block = rebuild_knob_block(buffer, offset, 99)
        assert len(block) == 14
        expected = bytearray(buffer[4:18])
        expected[offset - 4] = 99
        assert block == bytes(expected)


@pytest.mark.parametrize("offset", [0, 3, 18, 20, -1])
def test_rebuild_knob_block_offset_outside_4_17(offset: int) -> None:
    with pytest.raises(ValueError):
        rebuild_knob_block(sf.PUBLIC_PRESET, offset, 1)


def test_rebuild_knob_block_needs_a_full_buffer() -> None:
    with pytest.raises(ValueError):
        rebuild_knob_block(sf.PUBLIC_PRESET[:20], 6, 1)


# -- spec 004 M1: bypass and loopback (T023) --------------------------------------------------

BYPASS_1 = "00 59 22 09 00 00 04 01 00 00 e1 01 00 00 01 17"
LOOPBACK_OFF = "00 59 22 09 00 00 04 00 00 00 d0 01 00 00 00 2a"
LOOPBACK_ON = "00 59 22 09 00 00 04 00 00 00 d0 01 00 00 01 29"


@pytest.mark.parametrize("i", [0, 1, 35])
def test_bypass_targets(i: int) -> None:
    t = WriteTarget.bypass(i)
    assert (t.kind, t.type, t.address, t.length, t.argument) == ("bypass", 4, 0xE1000000 + i, 1, i)
    assert t.persistent is False


def test_loopback_target() -> None:
    t = WriteTarget.loopback()
    assert (t.kind, t.type, t.address, t.length, t.argument) == (
        "loopback",
        4,
        0xD0000000,
        1,
        None,
    )
    assert t.persistent is False


def test_003_targets_are_not_persistent() -> None:
    targets = [
        WriteTarget.knob_block(),
        WriteTarget.block_switch(0),
        WriteTarget.led_colour(),
        WriteTarget.preset_select(0),
    ]
    assert [t.persistent for t in targets] == [False] * 4


def test_bypass_vector() -> None:
    assert build_write(WriteTarget.bypass(1), b"\x01") == bytes.fromhex(BYPASS_1)
    assert build_write(WriteTarget.bypass(1), b"\x01") == write_frame(0xE1000001, b"\x01")


def test_loopback_vectors() -> None:
    assert build_write(WriteTarget.loopback(), b"\x00") == bytes.fromhex(LOOPBACK_OFF)
    assert build_write(WriteTarget.loopback(), b"\x01") == bytes.fromhex(LOOPBACK_ON)


@pytest.mark.parametrize("i", [36, -1, 0x100])
def test_bypass_index_out_of_range(i: int) -> None:
    with pytest.raises(ValueError):
        WriteTarget.bypass(i)


def test_bypass_index_must_be_an_int() -> None:
    with pytest.raises(TypeError):
        WriteTarget.bypass(True)


@pytest.mark.parametrize("data", [b"\x00", b"\x02", b"\xff", b"", b"\x01\x01"])
def test_bypass_data_is_always_01(data: bytes) -> None:
    with pytest.raises(ValueError):
        build_write(WriteTarget.bypass(1), data)


@pytest.mark.parametrize("data", [b"\x02", b"\xff", b"", b"\x00\x00"])
def test_loopback_data_is_00_or_01(data: bytes) -> None:
    with pytest.raises(ValueError):
        build_write(WriteTarget.loopback(), data)


@pytest.mark.parametrize(
    "changes",
    [{"address": 0xE1000024}, {"argument": 36}, {"length": 2}, {"kind": "loopback"}],
)
def test_replace_cannot_move_a_bypass_off_the_allowlist(changes: dict[str, object]) -> None:
    with pytest.raises((TypeError, ValueError)):
        dataclasses.replace(WriteTarget.bypass(1), **changes)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("body", "allowed"),
    [
        (bytes.fromhex(BYPASS_1)[6:-1], True),
        (bytes.fromhex("04 00 00 00 e1 01 00 00 01"), True),
        (bytes.fromhex("04 23 00 00 e1 01 00 00 01"), True),
        (bytes.fromhex(LOOPBACK_OFF)[6:-1], True),
        (bytes.fromhex(LOOPBACK_ON)[6:-1], True),
        (bytes.fromhex("04 24 00 00 e1 01 00 00 01"), False),  # 0xE1000000 + 36
        (bytes.fromhex("04 01 00 00 e1 01 00 00 00"), False),  # bypass data 00
        (bytes.fromhex("04 00 00 00 d0 02 00 00 01 01"), False),  # 0xD0000000 x2
        (bytes.fromhex("05 00 00 00 d0 01 00 00 01"), False),  # 0xD0000000 type 5
        (bytes.fromhex("04 00 00 00 d0 01 00 00 02"), False),  # loopback data 02
    ],
)
def test_allowed_write_body_bypass_and_loopback(body: bytes, allowed: bool) -> None:
    assert allowed_write_body(body) is allowed
