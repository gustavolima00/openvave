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
    # the fw96 capture is stored preset 1B (watch sessions, 2026-11-16)
    assert summary(PRESET_READ) == [
        (0, "amp_on", 1, "on", "confirmed"),
        (1, "mod_on", 0, "off", "confirmed"),
        (2, "delay_on", 0, "off", "confirmed"),
        (3, "reverb_on", 1, "on", "confirmed"),
        (4, "noise_gate", 15, "15", "confirmed"),
        (5, "amp_type", 4, "#4", "confirmed"),
        (6, "knob_unknown", 60, "60", "confirmed"),
        (7, "treble", 60, "60", "confirmed"),
        (8, "middle", 70, "70", "confirmed"),
        (9, "bass", 50, "50", "confirmed"),
        (10, "volume", 50, "50", "confirmed"),
        (11, "mod_fx", 0, "0", "confirmed"),
        (12, "mod_speed", 0, "0", "confirmed"),
        (13, "delay_mix", 0, "0", "confirmed"),
        (14, "delay_time", 0, "0", "confirmed"),
        (15, "reverb_decay", 5, "5", "confirmed"),
        (16, "reverb_mix", 4, "4", "confirmed"),
        (17, "ir_cab", 7, "#7", "confirmed"),
    ]
    decoded = decode_region(PRESET_READ, 96)
    assert decoded.unknown_offsets == (18, 19, 20)
    assert decoded.read is PRESET_READ
    assert decoded.map_firmware == 96
    assert not decoded.firmware_untested


def test_global_fields() -> None:
    assert summary(GLOBAL_READ) == [
        (0, "browse_bank", 0, "0", "observed"),
        (1, "bank", 0, "0", "observed"),
        (2, "slot", 1, "1", "observed"),
        (3, "not_in_edit_mode", 1, "normal", "confirmed"),
    ]
    decoded = decode_region(GLOBAL_READ, 96)
    assert decoded.unknown_offsets == ()
    assert decoded.fields[3].interpreted == 1


def test_mode_values() -> None:
    for raw, display in ((0, "edit"), (1, "normal"), (2, "tuner")):
        frame = with_region_data(CAP.rx(GLOBAL), 3, raw)
        field = decode_region(read_of(Region.GLOBAL, GLOBAL, frame), 96).fields[3]
        assert (field.display, field.interpreted, field.out_of_range) == (display, raw, False)


def test_slot_loading_state_is_out_of_range() -> None:
    frame = with_region_data(CAP.rx(GLOBAL), 2, 0xFF)
    field = decode_region(read_of(Region.GLOBAL, GLOBAL, frame), 96).fields[2]
    assert field.out_of_range
    assert field.display == "255"


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
    frame = with_region_data(CAP.rx(PRESET), 0, 0)
    field = decode_region(read_of(Region.CURRENT_PRESET, PRESET, frame), 96).fields[0]
    assert field.entry.encoding is Encoding.SWITCH
    assert (field.display, field.interpreted, field.out_of_range) == ("off", False, False)


def test_switch_out_of_range() -> None:
    frame = with_region_data(CAP.rx(PRESET), 0, 7)
    field = decode_region(read_of(Region.CURRENT_PRESET, PRESET, frame), 96).fields[0]
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
    frame = with_region_data(with_region_data(CAP.rx(PRESET), 15, 0x7F), 19, 0x09)
    after = read_of(Region.CURRENT_PRESET, PRESET, frame)
    changes = diff(PRESET_READ, after)
    assert [(c.region, c.offset, c.old, c.new) for c in changes] == [
        (Region.CURRENT_PRESET, 15, 0x05, 0x7F),
        (Region.CURRENT_PRESET, 19, 0x16, 0x09),
    ]
    assert changes[0].field is not None and changes[0].field.name == "reverb_decay"
    assert changes[1].field is None


def test_diff_rejects_different_regions() -> None:
    import pytest

    with pytest.raises(ValueError):
        diff(PRESET_READ, GLOBAL_READ)
