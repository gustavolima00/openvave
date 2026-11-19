"""Tool results: the CLI's ``--json`` documents plus a short ``summary`` (research R6)."""

from __future__ import annotations

from typing import Any


def with_summary(document: dict[str, Any], human: str) -> dict[str, Any]:
    """``document`` with ``summary``: the first non-empty line of the CLI's human output."""
    summary = next((line.strip() for line in human.splitlines() if line.strip()), "")
    return {"summary": summary, **document}


__all__ = ["with_summary"]
