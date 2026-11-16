"""The committed captures are well-formed, valid frames and free of identifiers (T010)."""

from __future__ import annotations

import json
import re

import pytest

from tests.support.captures import CAPTURES_DIR, FW96_CONNECT, LABELS, load_capture

MAC_LIKE = re.compile(r"(?i)\b[0-9a-f]{2}([:-])[0-9a-f]{2}(\1[0-9a-f]{2}){4}\b")


def _frame_ok(frame: bytes) -> None:
    assert frame[:2] == b"\x00\x59"
    n = int.from_bytes(frame[3:6], "little")
    assert len(frame) == n + 7
    assert frame[-1] == (~sum(frame[6:-1])) & 0xFF


def test_meta_and_pairs() -> None:
    cap = load_capture(FW96_CONNECT)
    assert cap.meta["event"] == "meta"
    assert cap.meta["firmware"] == 96
    assert list(cap.pairs) == list(LABELS)
    assert len(cap.pairs) == 5
    assert cap.ordered_tx == [tx for tx, _ in cap.pairs.values()]


def test_every_frame_valid() -> None:
    cap = load_capture(FW96_CONNECT)
    for tx, rx in cap.pairs.values():
        _frame_ok(tx)
        _frame_ok(rx)
        assert tx[2] == rx[2]


def test_rx_chunks_concatenate_to_rx() -> None:
    cap = load_capture(FW96_CONNECT)
    for label, (_, rx) in cap.pairs.items():
        assert b"".join(cap.rx_chunks[label]) == rx


@pytest.mark.parametrize("path", sorted(CAPTURES_DIR.glob("**/*.jsonl")), ids=str)
def test_no_mac_like_identifiers_in_meta_or_labels(path: object) -> None:
    for line in open(str(path), encoding="utf-8"):
        record = json.loads(line)
        texts = [record.get("label", "")]
        if record.get("event") == "meta":
            texts.append(json.dumps(record))
        for text in texts:
            assert not MAC_LIKE.search(text), f"MAC-like value in {path}: {text!r}"
