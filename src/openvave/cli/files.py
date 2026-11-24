"""Output files written by the CLI: atomic, and never overwriting unless asked."""

from __future__ import annotations

import contextlib
import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any


class TargetExistsError(Exception):
    """The output file exists and ``force`` was not given (a usage error, exit 2)."""


def check_target(path: Path, *, force: bool) -> None:
    """Refuse an existing ``path`` unless ``force`` (called before any pedal I/O)."""
    if path.exists() and not force:
        raise TargetExistsError(f"{path} exists; use --force to overwrite it")


def write_json_atomic(path: Path, document: dict[str, Any], *, force: bool) -> None:
    """Write ``document`` to ``path`` via a temp file in the same directory.

    An interrupted write leaves neither a partial ``path`` nor the temp file. With ``force`` an
    existing file is only replaced (``os.replace``) once the new content is complete. Without it
    the complete file is published with a hard link, which fails if ``path`` exists by then, so
    two writers racing for one name never replace each other's file: the loser gets
    :class:`TargetExistsError` (and may pick another name).
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
        if force:
            os.replace(temp, path)
        else:
            _publish_new(temp, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temp)
        raise


def _publish_new(temp: str, path: Path) -> None:
    """Give the complete ``temp`` the name ``path`` only if ``path`` does not exist.

    A hard link is the atomic no-replace rename on POSIX and NTFS. Where links are not
    supported (FAT, some network shares), Windows' ``os.rename`` still refuses an existing
    name atomically; elsewhere the last check and ``os.replace`` are used, as before, so only
    complete files ever appear under ``path``."""
    try:
        os.link(temp, path)
    except FileExistsError:
        raise TargetExistsError(f"{path} exists; use --force to overwrite it") from None
    except OSError:
        if sys.platform == "win32":
            try:
                os.rename(temp, path)
            except FileExistsError:
                raise TargetExistsError(f"{path} exists; use --force to overwrite it") from None
            return
        check_target(path, force=False)
        os.replace(temp, path)
        return
    os.unlink(temp)


def default_backup_dir() -> Path:
    """Where the automatic backup of ``preset save`` / ``preset restore`` goes without
    ``--backup-dir``, in this order: ``$OPENVAVE_BACKUP_DIR``; ``$XDG_DATA_HOME/openvave/backups``;
    on Windows ``%LOCALAPPDATA%\\openvave\\backups``; otherwise
    ``~/.local/share/openvave/backups``. Empty variables count as unset. Until 0.5.0 the default
    was the current directory, which is often a git working tree."""
    explicit = os.environ.get("OPENVAVE_BACKUP_DIR")
    if explicit:
        return Path(explicit).expanduser()
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / "openvave" / "backups"
    local = os.environ.get("LOCALAPPDATA")
    if sys.platform == "win32" and local:
        return Path(local) / "openvave" / "backups"
    return Path.home() / ".local" / "share" / "openvave" / "backups"


def automatic_backup_path(directory: Path, action: str, when: datetime) -> Path:
    """``directory/tankg-backup-<YYYYmmdd-HHMMSS>-before-<action>.json`` that does not exist yet.

    On a name clash a numeric suffix is added (``…-before-save-1.json``, ``-2`` …): the automatic
    backup of ``preset save`` / ``preset restore`` never overwrites a file (spec 004 R9).
    """
    stem = f"tankg-backup-{when.strftime('%Y%m%d-%H%M%S')}-before-{action}"
    path = directory / f"{stem}.json"
    n = 0
    while path.exists():
        n += 1
        path = directory / f"{stem}-{n}.json"
    return path
