"""Committed gate excerpts carry no more than they should (spec 003 M2, T048, FR-020).

Every ``captures/fw96/*-gate-*.jsonl``: only ``0x11``/``0x23`` and allowlisted ``0x22`` requests
(the independent audit allowlist), no device-info read (identifiers), stored-image reads limited
to the header and presets already public in the committed fw96 step captures, and a meta line
with firmware 96, a date and the step name of its file. The checks run on a synthetic excerpt
too, so they are exercised before the first real one exists.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from tests.integration.gate_fixtures import FW96, committed_gate_excerpts
from tests.support import gate_excerpt as ge
from tests.support import storage_fixture as sf
from tests.support.audit import unsafe_frames
from tests.support.write_fixture import ACK, write_frame

DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
STEP = re.compile(r"^\d{8}-gate-(?P<step>[a-z0-9_]+)\.jsonl$")


def public_presets() -> set[bytes]:
    """Every edit-buffer value in the committed, non-synthetic, non-gate fw96 captures."""
    out: set[bytes] = set()
    for path in sorted(FW96.glob("*.jsonl")):
        if "-gate-" in path.name or "synthetic" in path.name:
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            if r.get("event") != "rx":
                continue
            frame = bytes.fromhex(r["hex"])
            if frame[2] == 0x23 and frame[6:14] == bytes.fromhex("04 00 00 00 10 15 00 00"):
                out.add(frame[14:-1])
    return out


PUBLIC = public_presets()


def problems(name: str, records: list[dict[str, Any]]) -> list[str]:
    """Why an excerpt may not be committed (empty if it may)."""
    found: list[str] = []
    meta = records[0]
    m = STEP.match(name)
    if meta.get("event") != "meta":
        return ["first line is not meta"]
    if meta.get("firmware") != 96:
        found.append(f"firmware {meta.get('firmware')!r}")
    if not DATE.match(str(meta.get("date", ""))):
        found.append(f"date {meta.get('date')!r}")
    if m is None or meta.get("step") != m["step"]:
        found.append(f"step {meta.get('step')!r} does not match {name}")
    tx = [bytes.fromhex(r["hex"]) for r in records if r["event"] == "tx"]
    if unsafe_frames(tx):
        found.append("unsafe request: " + ", ".join(f.hex(" ") for f in unsafe_frames(tx)))
    for r in records:
        if r["event"] != "rx":
            continue
        frame = bytes.fromhex(r["hex"])
        if frame[2] != 0x23 or len(frame) < 15:
            continue
        kind, address, length = ge._shape(frame)
        if address == ge.DEVICE or kind != 4:
            found.append(f"identifier read {r['label']}")
        elif address < ge.STORE_END and not (address == 0 and length == 2):
            data = frame[14:-1]
            if length != ge.PRESET_SIZE or data not in PUBLIC:
                found.append(f"non-public stored read {r['label']}")
    return found


def test_public_presets_are_known() -> None:
    assert sf.PUBLIC_PRESET in PUBLIC
    assert len(PUBLIC) > 5


@pytest.mark.parametrize("path", committed_gate_excerpts(), ids=lambda p: p.name)
def test_committed_gate_excerpt_is_clean(path: Path) -> None:
    records = [json.loads(line) for line in path.read_text("utf-8").splitlines() if line]
    assert problems(path.name, records) == []


def _trace(*frames: tuple[str, bytes]) -> str:
    return "\n".join(f"{'TX' if k == 'tx' else 'RX'} {f.hex(' ')}" for k, f in frames)


QUERY_TX = bytes.fromhex("00 59 11 00 00 00 ff")
QUERY_RX = bytes.fromhex(
    "00 59 11 1b 00 00 54 41 4e 4b 2d 47 76 32 5f 30 39 36" + " 00" * 15 + " b7"
)


def _read(address: int, data: bytes) -> tuple[bytes, bytes]:
    echo = bytes([4]) + address.to_bytes(4, "little") + len(data).to_bytes(3, "little")
    return sf.frame(0x23, echo), sf.frame(0x23, echo + data)


def _excerpt(*extra: tuple[str, bytes], name: str = "select") -> list[dict[str, Any]]:
    frames = [("tx", QUERY_TX), ("rx", QUERY_RX), *extra]
    return ge.build(_trace(*frames), name, "2026-11-17", {"call": "set_field"})


def test_clean_synthetic_excerpt_passes() -> None:
    stored_tx, stored_rx = _read(2 + 21, sf.PUBLIC_PRESET)
    head_tx, head_rx = _read(0, b"\xa5\x5a")
    sel = write_frame(0xE0000001, b"\x01")
    records = _excerpt(
        ("tx", sel), ("rx", ACK), ("tx", head_tx), ("rx", head_rx), ("tx", stored_tx),
        ("rx", stored_rx),
    )  # fmt: skip
    assert problems("20261117-gate-select.jsonl", records) == []


def test_non_public_stored_read_is_rejected() -> None:
    tx, rx = _read(2 + 21 * 7, bytes(range(21)))
    found = problems("20261117-gate-select.jsonl", _excerpt(("tx", tx), ("rx", rx)))
    assert found == ["non-public stored read stored preset 2D t4 0x00000095 x21"]


def test_unsafe_write_and_identifier_read_are_rejected() -> None:
    commit = write_frame(0xF0000000, b"\x01")
    dev_tx = sf.frame(0x23, bytes.fromhex("05 00 00 00 d0 20 00 00"))
    dev_rx = sf.frame(0x23, bytes.fromhex("05 00 00 00 d0 20 00 00") + bytes(32))
    found = problems(
        "20261117-gate-select.jsonl",
        _excerpt(("tx", commit), ("rx", ACK), ("tx", dev_tx), ("rx", dev_rx)),
    )
    assert len(found) == 2
    assert found[0].startswith("unsafe request")
    assert found[1].startswith("identifier read")


def test_meta_must_match_the_file_name() -> None:
    found = problems("20261117-gate-knob_gain.jsonl", _excerpt(name="select"))
    assert found == ["step 'select' does not match 20261117-gate-knob_gain.jsonl"]
