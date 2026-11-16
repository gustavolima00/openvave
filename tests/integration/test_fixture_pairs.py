"""Each named field has a real step excerpt that moves exactly that field (T035, SC-004)."""

from __future__ import annotations

import pytest

from openvave.models import ByteMapEntry, Region, RegionRead
from openvave.protocol import BYTE_MAP, decode_region, diff, parse_read_reply
from tests.integration.fixture_pairs import FW96, PAIRS, SELECTIONS, FixturePair
from tests.support.captures import load_capture

REGIONS = {"global": Region.GLOBAL, "preset": Region.CURRENT_PRESET}


def reads(path: object, region: Region) -> list[RegionRead]:
    key = next(k for k, r in REGIONS.items() if r is region)
    return [parse_read_reply(region, frame) for frame in load_capture(path).rx_all(key)]


def entry(region: Region, name: str) -> ByteMapEntry:
    return next(e for e in BYTE_MAP if e.region is region and e.name == name)


@pytest.mark.parametrize("pair", [p for p in PAIRS if p.single], ids=lambda p: p.id)
def test_single_step_moves_only_its_field(pair: FixturePair) -> None:
    region = REGIONS[pair.region]
    field = entry(region, pair.name)
    series = reads(pair.path, region)
    assert len(series) >= 2
    moved = 0
    for before, after in zip(series, series[1:], strict=False):
        changes = diff(before, after)
        assert all(c.offset == field.offset for c in changes), (pair.file, changes)
        assert all(c.field == field for c in changes)
        moved += len(changes)
    assert moved >= 1, f"{pair.file}: {pair.name} never moved"
    other = [r for r in REGIONS.values() if r is not region]
    for o in other:
        others = reads(pair.path, o)
        assert all(not diff(a, b) for a, b in zip(others, others[1:], strict=False))
    values = [read.data[field.offset] for read in series]
    if pair.reaches is not None:
        assert (min(values), max(values)) == pair.reaches
    for read in series:
        decoded = decode_region(read, 96)
        (value,) = [f for f in decoded.fields if f.entry == field]
        assert not value.out_of_range, (pair.file, value)


@pytest.mark.parametrize("file", sorted(SELECTIONS))
def test_preset_selection_moves_bank_and_slot(file: str) -> None:
    seen: list[tuple[int, int, int]] = []
    for read in reads(FW96 / file, Region.GLOBAL):
        by_name = {f.entry.name: f for f in decode_region(read, 96).fields}
        assert not any(f.out_of_range for f in by_name.values())
        triple = (
            int(by_name["browse_bank"].interpreted),
            int(by_name["bank"].interpreted),
            int(by_name["slot"].interpreted),
        )
        if not seen or seen[-1] != triple:
            seen.append(triple)
    assert seen == SELECTIONS[file]


def test_every_pair_file_exists_and_is_indexed_once_per_field() -> None:
    keys = [(p.region, p.name, p.file) for p in PAIRS]
    assert len(keys) == len(set(keys))
    for pair in PAIRS:
        assert pair.path.is_file(), pair.file
    committed = {p.name for p in FW96.glob("*-step-*.jsonl")}
    assert committed == {p.file for p in PAIRS}, "every committed step excerpt is indexed"
