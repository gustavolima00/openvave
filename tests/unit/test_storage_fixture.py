"""The synthetic stored image and its committed capture (T003, research R10)."""

from __future__ import annotations

import json

from openvave.models import Region, RegionRead
from openvave.protocol import BYTE_MAP, decode_region
from tests.support import storage_fixture as sf
from tests.support.captures import load_capture

PUBLIC_1B = "01 00 00 01 0f 04 3c 3c 46 32 32 00 00 00 00 05 04 07 43 16 43"


def test_image_shape() -> None:
    image = sf.synthetic_image()
    assert len(image) == 758
    assert image[:2] == bytes.fromhex("a5 5a")
    assert image[2 + 21 : 2 + 42].hex(" ") == PUBLIC_1B


def test_presets_are_distinct_and_deterministic() -> None:
    presets = sf.synthetic_presets()
    assert len(presets) == 36
    assert len(set(presets)) == 36
    assert presets == sf.synthetic_presets()
    assert sf.synthetic_preset(0) == bytes(
        [0, 0, 0, 0, 0, 0, 66, 77, 88, 99, 110, 121, 4, 15, 26, 37, 48, 3, 0, 0x40, 0x80]
    )


def test_every_mapped_byte_in_range() -> None:
    for i, data in enumerate(sf.synthetic_presets()):
        decoded = decode_region(RegionRead(Region.CURRENT_PRESET, data), 96)
        assert not [f.entry.name for f in decoded.fields if f.out_of_range], sf.position(i)
    assert any(e.region is Region.CURRENT_PRESET for e in BYTE_MAP)


def test_storage_replies_cover_header_presets_image() -> None:
    image = sf.synthetic_image()
    pairs = sf.storage_replies(image)
    assert len(pairs) == 38
    labels = list(pairs)
    assert labels[0] == sf.HEADER_LABEL
    assert labels[-1] == sf.IMAGE_LABEL
    assert labels[1] == "stored preset 1A t4 0x00000002 x21"
    assert labels[36] == "stored preset 9D t4 0x000002e1 x21"
    tx, rx = pairs[sf.IMAGE_LABEL]
    assert tx.hex(" ") == "00 59 23 08 00 00 04 00 00 00 00 f6 02 00 03"
    assert len(rx) == 773
    assert rx[14:-1] == image
    assert pairs[labels[2]][1][14:-1].hex(" ") == PUBLIC_1B


def test_committed_capture_matches_generator() -> None:
    committed = [
        json.loads(line)
        for line in sf.SYNTHETIC_CAPTURE.read_text(encoding="utf-8").splitlines()
        if line
    ]
    assert committed == sf.capture_lines(sf.synthetic_image())
    cap = load_capture(sf.SYNTHETIC_CAPTURE)
    assert cap.meta["firmware"] == 96
    assert "synthetic" in cap.meta["note"]
    for label, (tx, rx) in sf.storage_replies(sf.synthetic_image()).items():
        assert cap.pairs[label] == (tx, rx)
    assert [len(c) for c in cap.rx_chunks[sf.IMAGE_LABEL]] == [182, 182, 182, 182, 45]
