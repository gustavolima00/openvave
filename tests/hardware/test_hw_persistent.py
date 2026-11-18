"""Gate helper for the spec 004 M3 no-op image write. **Writes stored presets on a real pedal.**

Collected only with ``--hardware``, ``OPENVAVE_HW_WRITES=1`` **and** ``OPENVAVE_HW_UNSAFE=1``
(spec 004 R16), so neither a broad ``pytest --hardware`` nor the volatile write gate can reach it.

Step ``image_noop`` (tasks.md T077): read the stored image, then send that same image back
through the save/restore sequence runner (image write → 300 ms → commit → 100 ms → select of the
loaded preset), so the pedal's stored presets cannot change even if it takes only part of the
773-byte request (research R11). The runner takes and hands over the automatic backup first.
Every frame is logged to ``captures/private/<time>-hw-image_noop.jsonl``. The researcher posts the
frame shape and pass criteria, the owner approves in chat, then runs (with ``-s``) and types
``send``. Pass: one ACK after the last chunk, no stray reply, the next reads work, backup equal.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import pytest

from openvave import Backup, TankG
from openvave.trace import trace_hook
from tests.hardware.test_hw_writes import CONFIRM_WORD, confirmed
from tests.support.image_noop import noop_image_plan

pytestmark = [
    pytest.mark.hardware,
    pytest.mark.persistent_writes,
    pytest.mark.skipif(
        os.environ.get("OPENVAVE_HW_WRITES") != "1" or os.environ.get("OPENVAVE_HW_UNSAFE") != "1",
        reason="persistent hardware writes need OPENVAVE_HW_WRITES=1, OPENVAVE_HW_UNSAFE=1 "
        "(and --hardware)",
    ),
]

PRIVATE = Path(__file__).resolve().parents[2] / "captures/private"


def record_path(step: str, when: datetime | None = None) -> Path:
    """``captures/private/<YYYYmmdd-HHMMSS>-hw-<step>.jsonl`` (git-ignored)."""
    stamp = (when or datetime.now()).strftime("%Y%m%d-%H%M%S")
    return PRIVATE / f"{stamp}-hw-{step}.jsonl"


async def image_noop(read_line: Callable[[], str] = sys.stdin.readline) -> None:
    PRIVATE.mkdir(parents=True, exist_ok=True)
    path = record_path("image_noop")
    started = time.monotonic()
    with path.open("w", encoding="utf-8") as log:

        def hook(kind: str, data: bytes) -> None:
            t = round(time.monotonic() - started, 4)
            log.write(json.dumps({"t": t, "event": kind, "hex": data.hex(" ")}) + "\n")

        with trace_hook(hook):
            async with asyncio.timeout(180):
                async with TankG.connect() as pedal:
                    assert pedal.identity.firmware == 96
                    current = await pedal.backup()
                    print(
                        f"image read {current.created_at.isoformat()}: header "
                        f"{current.header.hex(' ')}"
                    )
                    forced = await noop_image_plan(pedal, current)
                    for step in forced.steps:
                        if step.kind == "wait":
                            print(f"  wait   {step.seconds} s")
                        else:
                            frame = step.frame
                            print(f"  write  {frame[:16].hex(' ')} … ({len(frame)} bytes)")
                    if not confirmed(f"type '{CONFIRM_WORD}' to send this sequence:", read_line):
                        pytest.skip("not confirmed; nothing sent")
                    saved: list[Backup] = []
                    result = await pedal._run_sequence(forced, True, saved.append, None, None)
    print(f"verified {result.verified}; steps " + ", ".join(o.status for o in result.steps))
    print(f"record {path}")
    assert saved and saved[0].image == current.image
    assert result.verified


async def test_image_noop() -> None:
    if os.environ.get("OPENVAVE_HW_STEP") != "image_noop":
        pytest.skip("set OPENVAVE_HW_STEP=image_noop")
    await image_noop()
