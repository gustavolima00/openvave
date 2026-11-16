"""Excerpt cutting keeps meta, handshake and whole cycles (tests/support/excerpt.py)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.support.excerpt import cut, read_record
from tests.support.watch import write_watch_capture

CYCLES = [{}, {"preset": {15: 64}}, {"preset": {15: 127}}, {}]


def test_cut_keeps_meta_handshake_and_cycles(tmp_path: Path) -> None:
    records = read_record(write_watch_capture(tmp_path / "r.jsonl", CYCLES))
    excerpt = cut(records, 2, 3)
    assert excerpt[0]["event"] == "meta"
    assert [r.get("label") for r in excerpt if r["event"] == "tx"] == [
        "query",
        *["global", "preset", "status"] * 2,
    ]
    presets = [
        bytes.fromhex(r["hex"])[29]
        for r in excerpt
        if r["event"] == "rx" and r["label"] == "preset"
    ]
    assert presets[-2:] == [64, 127]


@pytest.mark.parametrize("bounds", [(0, 1), (2, 1), (1, 5)])
def test_cut_rejects_bad_bounds(tmp_path: Path, bounds: tuple[int, int]) -> None:
    records = read_record(write_watch_capture(tmp_path / "r.jsonl", CYCLES))
    with pytest.raises(ValueError):
        cut(records, *bounds)
