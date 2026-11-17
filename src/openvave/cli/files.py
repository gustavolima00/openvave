"""Output files written by the CLI: atomic, and never overwriting unless asked."""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


class TargetExistsError(Exception):
    """The output file exists and ``force`` was not given (a usage error, exit 2)."""


def check_target(path: Path, *, force: bool) -> None:
    """Refuse an existing ``path`` unless ``force`` (called before any pedal I/O)."""
    if path.exists() and not force:
        raise TargetExistsError(f"{path} exists; use --force to overwrite it")


def write_json_atomic(path: Path, document: dict[str, Any], *, force: bool) -> None:
    """Write ``document`` to ``path`` via a temp file in the same directory and ``os.replace``.

    An interrupted write leaves neither a partial ``path`` nor the temp file; an existing file is
    only replaced once the new content is complete.
    """
    check_target(path, force=force)
    directory = path.parent if str(path.parent) else Path(".")
    fd, temp = tempfile.mkstemp(dir=directory, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(document, fh, indent=2)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        check_target(path, force=force)
        os.replace(temp, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temp)
        raise
