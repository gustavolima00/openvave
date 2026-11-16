"""Cut a committed excerpt from a private ``openvave watch`` record (session-record.md).

An excerpt keeps the ``meta`` line, the handshake frames, and every line of poll cycles
``first..last`` (``tx``/``rx-chunk``/``rx`` plus the ``label``/``change`` events written while
those cycles ran). Cycle *k* starts at the *k*-th ``global`` request after the handshake, the
same numbering as the record's ``change`` events. Nothing is rewritten, so the excerpt replays
with ``FakeTransport.from_capture`` and its ``change`` lines are the record's own.

Usage (raw records stay in ``captures/private/``, git-ignored)::

    uv run python -m tests.support.excerpt RECORD FIRST LAST OUT
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

FIRST_REGION = "global"


def read_record(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def cycle_starts(records: list[dict[str, Any]]) -> list[int]:
    """Line index of the first request of each poll cycle (index 0 = cycle 1)."""
    return [
        i for i, r in enumerate(records) if r["event"] == "tx" and r.get("label") == FIRST_REGION
    ]


def cut(records: list[dict[str, Any]], first: int, last: int) -> list[dict[str, Any]]:
    """``meta`` + handshake + cycles ``first..last`` (1-based, inclusive)."""
    if records[0]["event"] != "meta":
        raise ValueError("a record starts with its meta line")
    starts = cycle_starts(records)
    if not 1 <= first <= last <= len(starts):
        raise ValueError(f"cycles must be within 1..{len(starts)}, got {first}..{last}")
    handshake = [r for r in records[1 : starts[0]] if r["event"] in ("tx", "rx-chunk", "rx")]
    end = starts[last] if last < len(starts) else len(records)
    body = [r for r in records[starts[first - 1] : end] if r["event"] != "stop"]
    return [records[0], *handshake, *body]


def write(records: list[dict[str, Any]], out: Path) -> None:
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), "utf-8")


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print(__doc__, file=sys.stderr)
        return 2
    record, first, last, out = Path(argv[0]), int(argv[1]), int(argv[2]), Path(argv[3])
    excerpt = cut(read_record(record), first, last)
    write(excerpt, out)
    changes = [r for r in excerpt if r["event"] == "change"]
    print(f"{out}: {len(excerpt)} lines, cycles {first}..{last}, {len(changes)} change events")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
