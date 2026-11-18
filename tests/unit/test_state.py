"""``classify(global, buffer)``: the pedal-state rules of spec 004 research R1 / data-model.md."""

from __future__ import annotations

import json

import pytest

from openvave import PedalState
from openvave.protocol import classify
from tests.support import storage_fixture as sf
from tests.support.captures import REPO_ROOT

P = sf.PUBLIC_PRESET
ZERO = bytes(21)
CHECK2 = REPO_ROOT / "captures/fw96/20261117-check2-bypass.jsonl"


def g(mode: int, bank: int = 0, slot: int = 1) -> bytes:
    return bytes([bank, bank, slot, mode])


@pytest.mark.parametrize(
    ("glob", "buffer", "kind", "index", "bank"),
    [
        (g(1), P, "normal", 1, 0),
        (g(0), P, "edit", 1, 0),
        (g(2), P, "tuner", 1, 0),
        (g(1, bank=8, slot=3), P, "normal", 35, 8),
        (g(0, bank=2, slot=0), P, "edit", 8, 2),
        (g(1, slot=0xFF), ZERO, "bypass", None, 0),
        (g(1, bank=3, slot=0xFF), ZERO, "bypass", None, 3),
        (g(1, slot=0xFF), P, "unrecognised", None, 0),  # loading with a non-zero buffer
        (g(1), ZERO, "unrecognised", None, 0),  # all-zero buffer with a valid slot
        (g(0), ZERO, "unrecognised", None, 0),
        (g(3), P, "unrecognised", None, 0),  # unknown mode value
        (g(0xFF), P, "unrecognised", None, 0),
        (g(1, bank=9), P, "unrecognised", None, None),  # bank out of range
        (g(1, slot=4), P, "unrecognised", None, 0),  # slot out of range
        (g(1, bank=9, slot=0xFF), ZERO, "unrecognised", None, None),
    ],
)
def test_state_table(
    glob: bytes, buffer: bytes, kind: str, index: int | None, bank: int | None
) -> None:
    state = classify(glob, buffer)
    assert state == PedalState(kind=kind, index=index, bank=bank)  # type: ignore[arg-type]
    assert state.transient is False
    assert state.label == kind


def test_transient_bypass_is_labelled_loading() -> None:
    state = PedalState(kind="bypass", index=None, bank=0, transient=True)
    assert state.label == "loading"


def test_position_names_the_loaded_preset() -> None:
    assert classify(g(1), P).position == "1B"
    assert classify(g(1, slot=0xFF), ZERO).position is None


@pytest.mark.parametrize(("glob", "buffer"), [(bytes(3), P), (g(1), P[:20]), (g(1) + b"\0", P)])
def test_wrong_lengths_are_rejected(glob: bytes, buffer: bytes) -> None:
    with pytest.raises(ValueError):
        classify(glob, buffer)


def _check2_reads() -> list[tuple[bytes, bytes]]:
    """(global, buffer) pairs in read order from the check 2 capture (bytes straight from rx)."""
    pairs: list[tuple[bytes, bytes]] = []
    glob: bytes | None = None
    for line in CHECK2.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if record["event"] != "rx":
            continue
        label = record["label"]
        data = bytes.fromhex(record["hex"])[14:-1]
        if label.startswith("global"):
            glob = data
        elif label.startswith("preset") and glob is not None:
            pairs.append((glob, data))
            glob = None
    return pairs


def test_check2_capture_classifies_as_bypass_then_normal() -> None:
    kinds = [classify(glob, buffer).kind for glob, buffer in _check2_reads()]
    assert kinds[0] == "normal"
    assert kinds.count("bypass") == 3  # held over three consecutive reads after the write
    assert kinds[1:4] == ["bypass"] * 3
    assert kinds[-1] == "normal"
