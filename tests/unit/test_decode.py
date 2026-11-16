"""Pure decoder over the fw96 capture (data-model.md DecodedField/DecodedRegion/ByteChange)."""

from __future__ import annotations

from openvave.models import Encoding, Region, RegionRead
from openvave.protocol import BYTE_MAP, decode_frame, decode_region, diff
from tests.support.captures import DEVICE_INFO, FW96_CONNECT, GLOBAL, PRESET, STATUS, load_capture
from tests.support.mutations import with_region_data

CAP = load_capture(FW96_CONNECT)
ECHO_LEN = 8


def read_of(region: Region, label: str, frame: bytes | None = None) -> RegionRead:
    body = decode_frame(frame if frame is not None else CAP.rx(label)).body
    return RegionRead(region, body[ECHO_LEN:])


PRESET_READ = read_of(Region.CURRENT_PRESET, PRESET)
GLOBAL_READ = read_of(Region.GLOBAL, GLOBAL)
STATUS_READ = read_of(Region.STATUS, STATUS)
DEVICE_READ = read_of(Region.DEVICE_INFO, DEVICE_INFO)


def summary(read: RegionRead) -> list[tuple[int, str | None, int, str, str | None]]:
    return [
        (f.entry.offset, f.entry.name, f.value, f.display, f.entry.confidence)
        for f in decode_region(read, 96).fields
    ]


def test_preset_fields() -> None:
    assert summary(PRESET_READ) == [
        (6, "knob_unknown", 60, "60", "observed"),
        (15, "reverb_decay", 5, "5", "confirmed"),
        (16, "reverb_mix", 4, "4", "hypothesis"),
        (17, "ir_cab", 7, "#7", "hypothesis"),
    ]
    decoded = decode_region(PRESET_READ, 96)
    assert decoded.unknown_offsets == (0, 1, 2, 3, 4, 5, 7, 8, 9, 10, 11, 12, 13, 14, 18, 19, 20)
    assert decoded.read is PRESET_READ
    assert decoded.map_firmware == 96
    assert not decoded.firmware_untested


def test_global_fields() -> None:
    assert summary(GLOBAL_READ) == [(3, "not_in_edit_mode", 1, "on", "observed")]
    decoded = decode_region(GLOBAL_READ, 96)
    assert decoded.unknown_offsets == (0, 1, 2)
    assert decoded.fields[0].interpreted is True


def test_status_all_unknown() -> None:
    decoded = decode_region(STATUS_READ, 96)
    assert decoded.fields == ()
    assert decoded.unknown_offsets == (0,)


def test_device_info_undecoded() -> None:
    decoded = decode_region(DEVICE_READ, 96)
    assert decoded.fields == ()
    assert decoded.unknown_offsets == tuple(range(32))


def test_named_fields_never_display_raw_hex() -> None:
    for read in (PRESET_READ, GLOBAL_READ):
        for f in decode_region(read, 96).fields:
            assert not f.display.startswith("0x"), f
            assert f.raw == read.data[f.entry.offset]
            assert not f.out_of_range


def test_interpreted_types() -> None:
    by_name = {f.entry.name: f for f in decode_region(PRESET_READ, 96).fields}
    assert by_name["reverb_decay"].interpreted == 5
    assert by_name["ir_cab"].interpreted == 7
    assert by_name["ir_cab"].entry.encoding is Encoding.SELECTOR


def test_switch_off() -> None:
    frame = with_region_data(CAP.rx(GLOBAL), 3, 0)
    field = decode_region(read_of(Region.GLOBAL, GLOBAL, frame), 96).fields[0]
    assert (field.display, field.interpreted, field.out_of_range) == ("off", False, False)


def test_switch_out_of_range() -> None:
    frame = with_region_data(CAP.rx(GLOBAL), 3, 7)
    field = decode_region(read_of(Region.GLOBAL, GLOBAL, frame), 96).fields[0]
    assert field.out_of_range
    assert field.display == "7"


def test_out_of_range_not_clamped() -> None:
    frame = with_region_data(CAP.rx(PRESET), 15, 0x80)
    decoded = decode_region(read_of(Region.CURRENT_PRESET, PRESET, frame), 96)
    field = next(f for f in decoded.fields if f.entry.offset == 15)
    assert field.out_of_range
    assert field.raw == field.value == 128
    assert field.display == "128"
    others = [f for f in decoded.fields if f.entry.offset != 15]
    assert not any(f.out_of_range for f in others)


def test_flag_value_is_masked() -> None:
    from dataclasses import replace

    from openvave.protocol import decode as decode_module

    base = next(e for e in BYTE_MAP if e.region is Region.STATUS)
    flag = replace(
        base,
        mask=0x04,
        name="test_flag",
        label="test flag",
        encoding=Encoding.FLAG,
        confidence="hypothesis",
    )
    field = decode_module.decode_field(flag, 0x0D)
    assert (field.raw, field.value, field.interpreted, field.display) == (0x0D, 0x04, True, "on")
    assert not field.out_of_range
    field = decode_module.decode_field(flag, 0x0B)
    assert (field.value, field.interpreted, field.display) == (0, False, "off")


def test_untested_firmware_uses_fw96_map() -> None:
    decoded = decode_region(PRESET_READ, firmware=97)
    assert decoded.firmware_untested
    assert decoded.map_firmware == 96
    assert summary(PRESET_READ) == [
        (f.entry.offset, f.entry.name, f.value, f.display, f.entry.confidence)
        for f in decoded.fields
    ]


def test_diff_identical_is_empty() -> None:
    assert diff(PRESET_READ, PRESET_READ) == ()


def test_diff_lists_changes_in_offset_order() -> None:
    frame = with_region_data(with_region_data(CAP.rx(PRESET), 15, 0x7F), 2, 0x09)
    after = read_of(Region.CURRENT_PRESET, PRESET, frame)
    changes = diff(PRESET_READ, after)
    assert [(c.region, c.offset, c.old, c.new) for c in changes] == [
        (Region.CURRENT_PRESET, 2, 0x00, 0x09),
        (Region.CURRENT_PRESET, 15, 0x05, 0x7F),
    ]
    assert changes[0].field is None
    assert changes[1].field is not None and changes[1].field.name == "reverb_decay"


def test_diff_rejects_different_regions() -> None:
    import pytest

    with pytest.raises(ValueError):
        diff(PRESET_READ, GLOBAL_READ)
