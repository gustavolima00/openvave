"""The committed captures are well-formed, valid frames and free of identifiers (T010)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from tests.support.captures import CAPTURES_DIR, FW96_CONNECT, LABELS, PRESET, load_capture

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


COMMITTED = sorted(
    p for p in CAPTURES_DIR.glob("**/*.jsonl") if "private" not in p.relative_to(CAPTURES_DIR).parts
)
"""Committed captures only: ``captures/private/`` is git-ignored raw material."""


@pytest.mark.parametrize("path", COMMITTED, ids=lambda p: str(p.relative_to(CAPTURES_DIR)))
def test_no_mac_like_identifiers_in_meta_or_labels(path: object) -> None:
    for line in open(str(path), encoding="utf-8"):
        record = json.loads(line)
        texts = [record.get("label") or "", record.get("text") or ""]
        if record.get("event") == "meta":
            texts.append(json.dumps(record))
        for text in texts:
            assert not MAC_LIKE.search(text), f"MAC-like value in {path}: {text!r}"


@pytest.mark.parametrize("path", COMMITTED, ids=lambda p: str(p.relative_to(CAPTURES_DIR)))
def test_committed_frames_valid(path: object) -> None:
    cap = load_capture(str(path))
    for label, frames in cap.all_rx.items():
        _frame_ok(cap.tx(label))
        for frame in frames:
            _frame_ok(frame)


def test_repeated_labels_rx_all_in_order(tmp_path: Path) -> None:
    from tests.support.watch import BASE, region_reply, write_watch_capture

    path = write_watch_capture(
        tmp_path / "seq.jsonl", [{}, {"preset": {15: 64}}, {"preset": {15: 127}}]
    )
    cap = load_capture(path)
    assert cap.rx_all("preset") == [
        region_reply("preset"),
        region_reply("preset", {15: 64}),
        region_reply("preset", {15: 127}),
    ]
    assert len(cap.rx_all("global")) == 3
    # tx()/rx() keep returning the first occurrence (compatibility with single-reply captures)
    assert cap.rx("preset") == region_reply("preset")
    assert cap.tx("preset") == BASE.tx(PRESET)
    assert list(cap.pairs) == ["query", "global", "preset", "status"]


def test_rx_all_on_single_reply_capture() -> None:
    cap = load_capture(FW96_CONNECT)
    for label in LABELS:
        assert cap.rx_all(label) == [cap.rx(label)]


def test_watch_record_events_are_accepted(tmp_path: Path) -> None:
    from tests.support.watch import write_watch_capture

    path = write_watch_capture(tmp_path / "seq.jsonl", [{}])
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"t": 1.0, "event": "label", "text": "step"}) + "\n")
        fh.write(
            json.dumps(
                {
                    "t": 1.1,
                    "event": "change",
                    "cycle": 2,
                    "region": "preset",
                    "offset": 15,
                    "old": 5,
                    "new": 6,
                    "label": "step",
                }
            )
            + "\n"
        )
        fh.write(json.dumps({"t": 2.0, "event": "stop", "reason": "quit", "error": None}) + "\n")
    cap = load_capture(path)
    assert [r["event"] for r in cap.records[-3:]] == ["label", "change", "stop"]
