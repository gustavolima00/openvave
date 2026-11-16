"""Invariants of the byte map table (data-model.md, FR-006, FR-009, FR-010, SC-002)."""

from __future__ import annotations

from collections import defaultdict

import pytest

from openvave.models import ByteMapEntry, Encoding, Region
from openvave.protocol import BYTE_MAP, MAP_FIRMWARE
from tests.support.captures import CAPTURES_DIR, REPO_ROOT

MAPPED_REGIONS = (Region.GLOBAL, Region.CURRENT_PRESET, Region.STATUS)
RANGED = (Encoding.CONTINUOUS, Encoding.SELECTOR, Encoding.INDEX)


def entries(region: Region) -> list[ByteMapEntry]:
    return [e for e in BYTE_MAP if e.region is region]


def test_map_firmware() -> None:
    assert MAP_FIRMWARE == 96


@pytest.mark.parametrize("region", MAPPED_REGIONS, ids=lambda r: r.name)
def test_every_offset_covered(region: Region) -> None:
    covered = {e.offset for e in entries(region)}
    assert covered == set(range(region.length))


def test_total_coverage_is_26() -> None:
    assert sum(len({e.offset for e in entries(r)}) for r in MAPPED_REGIONS) == 26


def test_offsets_within_region() -> None:
    for e in BYTE_MAP:
        assert 0 <= e.offset < e.region.length, e


def test_device_info_has_no_entries() -> None:
    assert entries(Region.DEVICE_INFO) == []


def test_no_overlap() -> None:
    by_offset: dict[tuple[Region, int], list[ByteMapEntry]] = defaultdict(list)
    for e in BYTE_MAP:
        by_offset[(e.region, e.offset)].append(e)
    for key, group in by_offset.items():
        whole = [e for e in group if e.mask is None]
        if whole:
            assert len(group) == 1, f"{key}: whole-byte entry shares its offset"
            continue
        assert all(e.encoding is Encoding.FLAG for e in group), key
        seen = 0
        for e in group:
            assert e.mask is not None and 0 < e.mask <= 0xFF, e
            assert seen & e.mask == 0, f"{key}: flag masks overlap"
            seen |= e.mask


def test_mask_only_for_flags() -> None:
    for e in BYTE_MAP:
        assert (e.mask is not None) == (e.encoding is Encoding.FLAG), e


def test_names_unique_per_region() -> None:
    names = [(e.region, e.name) for e in BYTE_MAP if e.name is not None]
    assert len(names) == len(set(names))


def test_name_none_iff_unknown() -> None:
    for e in BYTE_MAP:
        assert (e.name is None) == (e.encoding is Encoding.UNKNOWN), e
        assert (e.confidence is None) == (e.encoding is Encoding.UNKNOWN), e
        if e.name is not None:
            assert e.name.isidentifier() and e.name == e.name.lower(), e


def test_ranges() -> None:
    for e in BYTE_MAP:
        if e.encoding in RANGED:
            assert e.min is not None and e.max is not None, e
            assert e.min <= e.max, e
        else:
            assert e.min is None and e.max is None, e
        if e.encoding is Encoding.SWITCH:
            assert e.on_value is not None and e.off_value is not None, e
            assert e.on_value != e.off_value, e
        else:
            assert e.on_value is None and e.off_value is None, e
        if e.labels:
            assert e.encoding is Encoding.SELECTOR, e


def test_firmware_recorded() -> None:
    for e in BYTE_MAP:
        assert e.firmware == MAP_FIRMWARE, e


def test_observed_entries_cite_existing_captures() -> None:
    for e in BYTE_MAP:
        for path in e.evidence:
            full = REPO_ROOT / path
            assert full.is_file(), f"{e.name}: {path} does not exist"
            assert full.resolve().is_relative_to(CAPTURES_DIR), path
            assert "private" not in full.relative_to(CAPTURES_DIR).parts, path
        if e.confidence == "observed":
            assert len(e.evidence) >= 1, e
        if e.confidence == "confirmed":
            assert len(set(e.evidence)) >= 2, f"{e.name}: confirmed needs two sessions"


def test_every_observed_field_has_a_fixture_pair() -> None:
    """No observed/confirmed row without its real before/after excerpt (FR-009, FR-020)."""
    from tests.integration.fixture_pairs import PAIRS

    keys = {"global": Region.GLOBAL, "preset": Region.CURRENT_PRESET}
    indexed = {(keys[p.region], p.name) for p in PAIRS}
    for e in BYTE_MAP:
        if e.confidence in ("observed", "confirmed"):
            assert (e.region, e.name) in indexed, f"{e.name}: no fixture pair"


def test_confirmed_fields_have_pairs_from_two_sessions() -> None:
    from tests.integration.fixture_pairs import PAIRS

    for e in BYTE_MAP:
        if e.confidence != "confirmed":
            continue
        sessions = {path for path in e.evidence}
        assert len(sessions) >= 2, e.name
        assert any(p.name == e.name for p in PAIRS)


def test_per_preset_bytes_are_named_or_documented() -> None:
    """Each byte that differs between compared presets is named, or its notes say so (T048)."""
    from tests.support.bytemap_doc import load_comparison

    columns, rows = load_comparison()
    assert len(columns) >= 5, "SC-008: at least five presets compared"
    regions = {"preset": Region.CURRENT_PRESET, "global": Region.GLOBAL, "status": Region.STATUS}
    for region_name, offset, values in rows:
        assert len(values) == len(columns)
        assert len(set(values)) > 1, f"{region_name}[{offset}] does not differ"
        (e,) = [x for x in BYTE_MAP if x.region is regions[region_name] and x.offset == offset]
        if e.name is None:
            assert "differs per preset" in e.notes, f"{region_name}[{offset}]: {e.notes!r}"
