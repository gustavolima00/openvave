"""Preset copy, import, swap and export (spec 007 US5, plan.md).

Copy and import are the ``restore --slot`` sequence with bytes from another slot or a file; swap
writes the current image with two slots exchanged (the confirmed image write), commits and selects
the preset that was loaded; export only reads. All on the synthetic stored image (1B public).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from openvave import PresetFile, TankG, WriteRefusedError
from tests.support import restore_fixture as rf
from tests.support import storage_fixture as sf
from tests.support.write_fixture import NORMAL, make_fake, write_frame, writes

pytestmark = pytest.mark.persistent_writes

P = sf.PUBLIC_PRESET
GAIN_90 = P[:6] + bytes([90]) + P[7:]
COMMIT = bytes.fromhex("00 59 22 08 00 00 04 00 00 00 f0 00 00 00 0b")


def select(index: int) -> bytes:
    return write_frame(0xE0000000 + index, b"\x01")


def slot_write(index: int, data: bytes) -> bytes:
    return write_frame(2 + 21 * index, data)


def slot(image: bytes, index: int) -> bytes:
    return image[2 + 21 * index : 23 + 21 * index]


async def no_sleep(_: float) -> None:
    return None


def stored_image(fake: object) -> bytes:
    return bytes(fake._memory[0])  # type: ignore[attr-defined]


def keep(_: object) -> None:
    return None


def preset_file(data: bytes, firmware: int = 96) -> PresetFile:
    return PresetFile(
        identity=rf.identity(firmware),
        created_at=datetime(2026, 11, 19, 12, 0, tzinfo=UTC),
        source_index=4,
        data=data,
    )


# -- copy ---------------------------------------------------------------------------------------


async def test_copy_writes_the_source_bytes_and_ends_on_the_target() -> None:
    fake = make_fake(NORMAL)
    image = sf.synthetic_image()
    order: list[int] = []
    async with TankG.over(fake) as pedal:  # type: ignore[arg-type]
        plan = await pedal.plan_copy(0, 10, unsafe=True)
        result = await pedal.copy_preset(
            0,
            10,
            unsafe=True,
            on_backup=lambda b: order.append(len(writes(fake))),  # type: ignore[arg-type]
            sleep=no_sleep,
        )
    assert plan.action == "copy"
    assert (plan.target_index, plan.return_index, plan.changed_slots) == (10, 10, (10,))
    assert plan.before == slot(image, 10) and plan.after == slot(image, 0)
    assert plan.refusal is None  # confirmed writes, unsafe given
    assert writes(fake) == [slot_write(10, slot(image, 0)), COMMIT, select(10)]  # type: ignore[arg-type]
    assert order == [0]  # backup before the first write
    assert result.verified is True
    assert slot(stored_image(fake), 10) == slot(image, 0)


async def test_copy_needs_unsafe() -> None:
    fake = make_fake(NORMAL)
    async with TankG.over(fake) as pedal:  # type: ignore[arg-type]
        plan = await pedal.plan_copy(0, 10)
        with pytest.raises(WriteRefusedError) as exc:
            await pedal.copy_preset(0, 10, on_backup=keep, sleep=no_sleep)
    assert plan.refusal == "unsafe_required"
    assert exc.value.reason == "unsafe_required"
    assert writes(fake) == []  # type: ignore[arg-type]


async def test_copy_to_an_equal_slot_sends_nothing() -> None:
    fake = make_fake(NORMAL, image=rf.image_with(s10=slot(sf.synthetic_image(), 0)))
    calls: list[object] = []
    async with TankG.over(fake) as pedal:  # type: ignore[arg-type]
        result = await pedal.copy_preset(0, 10, unsafe=True, on_backup=calls.append)
    assert result.plan.no_change is True and result.steps == () and calls == []
    assert writes(fake) == []  # type: ignore[arg-type]


async def test_copy_to_itself_is_a_value_error() -> None:
    fake = make_fake(NORMAL)
    async with TankG.over(fake) as pedal:  # type: ignore[arg-type]
        with pytest.raises(ValueError):
            await pedal.plan_copy(3, 3)


async def test_copy_refuses_with_unsaved_edits() -> None:
    fake = make_fake(NORMAL, buffer=GAIN_90)  # loaded 1B holds P, the buffer gain 90
    async with TankG.over(fake) as pedal:  # type: ignore[arg-type]
        plan = await pedal.plan_copy(0, 10, unsafe=True)
        allowed = await pedal.plan_copy(0, 10, unsafe=True, discard_edits=True)
    assert plan.refusal == "edits_would_be_discarded"
    assert allowed.refusal is None


# -- import -------------------------------------------------------------------------------------


async def test_import_writes_the_file_bytes() -> None:
    fake = make_fake(NORMAL)
    async with TankG.over(fake) as pedal:  # type: ignore[arg-type]
        result = await pedal.import_preset(
            preset_file(GAIN_90), 6, unsafe=True, on_backup=keep, sleep=no_sleep
        )
    assert result.plan.action == "import"
    assert writes(fake) == [slot_write(6, GAIN_90), COMMIT, select(6)]  # type: ignore[arg-type]
    assert result.verified is True
    assert slot(stored_image(fake), 6) == GAIN_90


async def test_import_from_other_firmware_needs_experimental() -> None:
    fake = make_fake(NORMAL)
    async with TankG.over(fake) as pedal:  # type: ignore[arg-type]
        plan = await pedal.plan_import(preset_file(GAIN_90, firmware=97), 6, unsafe=True)
        allowed = await pedal.plan_import(
            preset_file(GAIN_90, firmware=97), 6, unsafe=True, experimental=True
        )
    assert plan.refusal == "firmware_mismatch"
    assert allowed.refusal is None


# -- swap ---------------------------------------------------------------------------------------


async def test_swap_writes_the_image_with_two_slots_exchanged() -> None:
    fake = make_fake(NORMAL)
    image = sf.synthetic_image()
    expected = rf.image_with(s5=slot(image, 15), s15=slot(image, 5))
    async with TankG.over(fake) as pedal:  # type: ignore[arg-type]
        plan = await pedal.plan_swap(5, 15)
        result = await pedal.swap_presets(5, 15, unsafe=True, on_backup=keep, sleep=no_sleep)
    assert plan.action == "swap"
    assert plan.changed_slots == (5, 15)
    assert (plan.target_index, plan.return_index) == (None, 1)  # back on the loaded 1B
    assert plan.before == image and plan.after == expected
    assert writes(fake) == [write_frame(0, expected), COMMIT, select(1)]  # type: ignore[arg-type]
    assert result.verified is True
    assert stored_image(fake) == expected


async def test_swap_of_equal_slots_sends_nothing() -> None:
    same = slot(sf.synthetic_image(), 5)
    fake = make_fake(NORMAL, image=rf.image_with(s15=same))
    async with TankG.over(fake) as pedal:  # type: ignore[arg-type]
        result = await pedal.swap_presets(5, 15, unsafe=True, on_backup=keep)
    assert result.plan.no_change is True and writes(fake) == []  # type: ignore[arg-type]


async def test_swap_with_itself_is_a_value_error() -> None:
    fake = make_fake(NORMAL)
    async with TankG.over(fake) as pedal:  # type: ignore[arg-type]
        with pytest.raises(ValueError):
            await pedal.plan_swap(5, 5)


async def test_swap_needs_unsafe_and_respects_unsaved_edits() -> None:
    async with TankG.over(make_fake(NORMAL)) as pedal:  # type: ignore[arg-type]
        assert (await pedal.plan_swap(5, 15)).refusal == "unsafe_required"
    async with TankG.over(make_fake(NORMAL, buffer=GAIN_90)) as pedal:  # type: ignore[arg-type]
        assert (await pedal.plan_swap(5, 15, unsafe=True)).refusal == "edits_would_be_discarded"
        assert (await pedal.plan_swap(5, 15, unsafe=True, discard_edits=True)).refusal is None


# -- export -------------------------------------------------------------------------------------


async def test_export_reads_one_slot_only() -> None:
    fake = make_fake(NORMAL)
    async with TankG.over(fake) as pedal:  # type: ignore[arg-type]
        exported = await pedal.export_preset(4)
    assert writes(fake) == []  # type: ignore[arg-type]
    assert exported.source_index == 4
    assert exported.data == slot(sf.synthetic_image(), 4)
    assert exported.identity.firmware == 96


def test_preset_file_document_round_trip() -> None:
    original = preset_file(GAIN_90)
    document = original.to_document()
    assert document["kind"] == "openvave.preset"
    assert document["format_version"] == 1
    assert document["source_position"] == "2A"
    assert document["raw"] == GAIN_90.hex(" ")
    assert {f["name"] for f in document["fields"]} >= {"gain", "led_red"}
    again = PresetFile.from_document(document)
    assert again == original


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"kind": "openvave.preset-backup"}, "preset restore"),
        ({"format_version": 2}, "format_version"),
        ({"raw": "01 02"}, "21 bytes"),
    ],
)
def test_preset_file_rejects_bad_documents(change: dict[str, object], message: str) -> None:
    document = {**preset_file(P).to_document(), **change}
    with pytest.raises(ValueError, match=message):
        PresetFile.from_document(document)
