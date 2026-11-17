"""``TankG.backup()`` over the synthetic stored image (T005, US1)."""

from __future__ import annotations

from datetime import UTC

import pytest

from openvave import Backup, ProtocolError, StoredPreset, TankG
from openvave.models import Region, RegionRead
from openvave.protocol import decode_frame, decode_region
from openvave.transport.fake import FakeTransport
from tests.support import storage_fixture as sf
from tests.support.audit import unsafe_frames
from tests.support.captures import FW96_CONNECT, QUERY, load_capture
from tests.support.mutations import with_payload

CAP = load_capture(FW96_CONNECT)


def make_fake(
    image: bytes | None = None,
    *,
    query_rx: bytes | None = None,
    image_reply: bytes | None = None,
) -> FakeTransport:
    image = sf.synthetic_image() if image is None else image
    script: dict[str, tuple[bytes, bytes]] = {QUERY: (CAP.tx(QUERY), query_rx or CAP.rx(QUERY))}
    if image_reply is not None:
        script[sf.IMAGE_LABEL] = (sf.read_request(0, 758), image_reply)
    return FakeTransport(script, memory={0: image}, chunk_size=182)


def expected_frames() -> list[bytes]:
    return [CAP.tx(QUERY)] + [tx for tx, _ in sf.storage_replies(sf.synthetic_image()).values()]


async def test_backup_reads_header_presets_image() -> None:
    fake = make_fake()
    async with TankG.over(fake) as pedal:
        backup = await pedal.backup()
    assert fake.sent == expected_frames()
    assert {f[2] for f in fake.sent} == {0x11, 0x23}
    assert unsafe_frames(fake.sent) == []
    image = sf.synthetic_image()
    assert isinstance(backup, Backup)
    assert backup.header == bytes.fromhex("a5 5a")
    assert backup.image == image
    assert len(backup.presets) == 36
    assert [p.position for p in backup.presets][:5] == ["1A", "1B", "1C", "1D", "2A"]
    assert backup.presets[-1].position == "9D"
    for i, preset in enumerate(backup.presets):
        assert isinstance(preset, StoredPreset)
        assert preset.index == i
        assert preset.data == image[2 + 21 * i : 23 + 21 * i]
        assert preset.decoded == decode_region(RegionRead(Region.CURRENT_PRESET, preset.data), 96)
    assert backup.created_at.tzinfo is UTC
    assert backup.warnings == ()
    assert backup.identity.firmware == 96


async def test_backup_mismatch_names_position() -> None:
    image = bytearray(sf.synthetic_image())
    image[2 + 21 * 6 + 4] ^= 0x01  # 2C, noise gate, only in the whole-image read
    reply = sf.read_reply(0, bytes(image))
    fake = make_fake(image_reply=reply)
    async with TankG.over(fake) as pedal:
        with pytest.raises(ProtocolError) as exc:
            await pedal.backup()
    assert exc.value.reason == "backup_mismatch"
    assert exc.value.detail is not None and "2C" in exc.value.detail
    assert exc.value.exit_code == 7


async def test_backup_header_mismatch() -> None:
    image = bytearray(sf.synthetic_image())
    image[0] = 0x00
    fake = make_fake(image_reply=sf.read_reply(0, bytes(image)))
    async with TankG.over(fake) as pedal:
        with pytest.raises(ProtocolError) as exc:
            await pedal.backup()
    assert exc.value.reason == "backup_mismatch"
    assert exc.value.detail is not None and "header" in exc.value.detail


async def test_unexpected_header_warns() -> None:
    fake = make_fake(sf.synthetic_image(header=b"\x00\x00"))
    async with TankG.over(fake) as pedal:
        backup = await pedal.backup()
    assert backup.header == b"\x00\x00"
    assert backup.warnings == ("unexpected_header",)


async def test_untested_firmware_warns() -> None:
    original = decode_frame(CAP.rx(QUERY)).body
    fw97 = with_payload(CAP.rx(QUERY), b"TANK-Gv2_097" + original[12:])
    fake = make_fake(query_rx=fw97)
    async with TankG.over(fake) as pedal:
        backup = await pedal.backup()
    assert backup.identity.firmware == 97
    assert backup.warnings == ("untested_firmware",)
    assert backup.presets[0].decoded.firmware_untested is True


async def test_backup_from_committed_capture() -> None:
    fake = FakeTransport.from_capture(sf.SYNTHETIC_CAPTURE, chunk_size=182)
    async with TankG.over(fake) as pedal:
        backup = await pedal.backup()
    assert backup.image == sf.synthetic_image()
    assert fake.sent == expected_frames()
