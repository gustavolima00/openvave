"""The server's backup folder (spec 006 research R10, data-model "Backup file names").

Every backup the server writes goes into one folder (``--backup-dir``, default the per-user data
folder), and ``preset_restore`` reads only from it: a file is named, never given as a path, so a
model cannot make the server read arbitrary files.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from openvave.backup import PRESET_KIND, restore_problems
from openvave.cli.mcp import default_backup_dir
from openvave.mcp_server.errors import InvalidFile

FOLDER_MODE = 0o700


def ensure_dir(folder: Path) -> Path:
    """``folder``, created (mode 0700, parents as needed) when missing; :class:`InvalidFile`
    when it exists and is not a folder or cannot be created."""
    if folder.exists() and not folder.is_dir():
        raise InvalidFile(f"backup folder {folder} is not a folder")
    try:
        folder.mkdir(mode=FOLDER_MODE, parents=True, exist_ok=True)
    except OSError as err:
        raise InvalidFile(f"cannot create backup folder {folder}: {err.strerror or err}") from None
    return folder


def manual_backup_path(folder: Path, when: datetime) -> Path:
    """``folder/tankg-backup-<YYYYmmdd-HHMMSS>.json`` that does not exist yet; on a clash
    ``-1``, ``-2`` … (never overwrites, like the CLI's automatic backups)."""
    stem = f"tankg-backup-{when.strftime('%Y%m%d-%H%M%S')}"
    path = folder / f"{stem}.json"
    n = 0
    while path.exists():
        n += 1
        path = folder / f"{stem}-{n}.json"
    return path


def preset_file_path(folder: Path, position: str, when: datetime) -> Path:
    """``folder/tankg-preset-<POS>-<YYYYmmdd-HHMMSS>.json`` that does not exist yet (spec 007
    ``preset_export``); ``-1``, ``-2`` … on a clash."""
    stem = f"tankg-preset-{position}-{when.strftime('%Y%m%d-%H%M%S')}"
    path = folder / f"{stem}.json"
    n = 0
    while path.exists():
        n += 1
        path = folder / f"{stem}-{n}.json"
    return path


def resolve_backup_file(folder: Path, name: str) -> Path:
    """The existing regular file ``name`` inside ``folder`` (links resolved).

    Refused with :class:`InvalidFile`, before anything is read: an empty name, an absolute path,
    a name with a path separator, ``.`` / ``..``, a missing file, or one whose resolved path (after
    links) is outside the folder.
    """
    if not name or name in (".", "..") or "/" in name or "\\" in name or os.path.isabs(name):
        raise InvalidFile(
            f"{name!r} is not a file name in the backup folder {folder} "
            "(give a name listed by backups_list, not a path)"
        )
    base = folder.resolve()
    path = (folder / name).resolve()
    if not path.is_relative_to(base):
        raise InvalidFile(f"{name!r} leads outside the backup folder {folder}")
    if not path.is_file():
        raise InvalidFile(f"no file {name!r} in the backup folder {folder}")
    return path


def _row(path: Path) -> dict[str, Any]:
    row: dict[str, Any] = {
        "file": path.name,
        "kind": "backup",
        "created_at": None,
        "firmware": None,
        "presets": None,
        "restorable": False,
        "importable": False,
        "problems": [],
    }
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except OSError as err:
        row["problems"] = [f"cannot read the file: {err.strerror or err}"]
        return row
    except (UnicodeDecodeError, json.JSONDecodeError) as err:
        row["problems"] = [f"not a JSON backup file ({err})"]
        return row
    if isinstance(document, dict):
        created = document.get("created_at")
        row["created_at"] = created if isinstance(created, str) else None
        identity = document.get("identity")
        if isinstance(identity, dict) and isinstance(identity.get("firmware"), int):
            row["firmware"] = identity["firmware"]
        presets = document.get("presets")
        row["presets"] = len(presets) if isinstance(presets, list) else None
        if document.get("kind") == PRESET_KIND:  # spec 007: one exported preset
            from openvave.models import PresetFile

            row["kind"] = "preset"
            row["presets"] = 1
            try:
                PresetFile.from_document(document)
            except ValueError as err:
                row["problems"] = [str(err)]
            row["importable"] = not row["problems"]
            return row
    problems = restore_problems(document)
    row["problems"] = problems
    row["restorable"] = not problems
    return row


def _sort_key(path: Path, row: dict[str, Any]) -> datetime:
    if row["created_at"] is not None:
        try:
            moment = datetime.fromisoformat(row["created_at"])
            return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)
        except ValueError:
            pass
    return datetime.fromtimestamp(path.stat().st_mtime, UTC)


def list_backups(folder: Path) -> list[dict[str, Any]]:
    """Every ``*.json`` regular file in ``folder``, newest first (``created_at``, else the file
    time), each with the restore checks of ``openvave.backup.restore_problems`` (``kind:
    backup``) or, for an exported preset (``kind: preset``, spec 007), the import checks. A
    missing folder is an empty list (nothing is created)."""
    if not folder.is_dir():
        return []
    rows = []
    for path in folder.iterdir():
        if path.suffix != ".json" or not path.is_file():
            continue
        row = _row(path)
        rows.append((_sort_key(path, row), row))
    rows.sort(key=lambda item: item[0], reverse=True)
    return [row for _, row in rows]


__all__ = [
    "default_backup_dir",
    "ensure_dir",
    "list_backups",
    "manual_backup_path",
    "preset_file_path",
    "resolve_backup_file",
]
