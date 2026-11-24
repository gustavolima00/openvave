"""The backup folder, ``preset_backup`` and ``backups_list`` (spec 006 US5, FR-023, R10)."""

from __future__ import annotations

import json
import os
import stat
import sys
from datetime import datetime
from pathlib import Path

import pytest

from openvave.mcp_server import backups
from openvave.mcp_server.errors import InvalidFile
from tests.mcp.conftest import CountingFactory, open_harness, options
from tests.support import restore_fixture as rf
from tests.support.write_fixture import NORMAL, make_fake

WHEN = datetime(2026, 11, 19, 10, 2, 3)


def storage_pedal() -> CountingFactory:
    return CountingFactory(make=lambda: make_fake(NORMAL))


def write(path: Path, document: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


# -- the folder -----------------------------------------------------------------------------------


def test_default_folder_from_xdg(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    assert backups.default_backup_dir() == tmp_path / "data" / "openvave" / "backups"


def test_default_folder_in_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("OPENVAVE_BACKUP_DIR", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    # Path.home() reads USERPROFILE on Windows, not HOME: pin it on every platform.
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(sys, "platform", "darwin")
    assert backups.default_backup_dir() == tmp_path / ".local" / "share" / "openvave" / "backups"


def test_default_folder_on_windows(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("OPENVAVE_BACKUP_DIR", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    monkeypatch.setattr(sys, "platform", "win32")
    assert backups.default_backup_dir() == tmp_path / "Local" / "openvave" / "backups"


def test_ensure_dir_creates_a_private_folder(tmp_path: Path) -> None:
    folder = tmp_path / "a" / "backups"
    assert backups.ensure_dir(folder) == folder
    assert folder.is_dir()
    if os.name == "posix":  # Windows reports no POSIX modes (always 0o777)
        assert stat.S_IMODE(folder.stat().st_mode) == 0o700
    backups.ensure_dir(folder)  # existing: fine


def test_ensure_dir_refuses_a_file(tmp_path: Path) -> None:
    path = tmp_path / "backups"
    path.write_text("x", encoding="utf-8")
    with pytest.raises(InvalidFile, match="not a folder"):
        backups.ensure_dir(path)


def test_manual_backup_path_never_overwrites(tmp_path: Path) -> None:
    first = backups.manual_backup_path(tmp_path, WHEN)
    assert first.name == "tankg-backup-20261119-100203.json"
    first.write_text("{}", encoding="utf-8")
    second = backups.manual_backup_path(tmp_path, WHEN)
    assert second.name == "tankg-backup-20261119-100203-1.json"
    second.write_text("{}", encoding="utf-8")
    assert backups.manual_backup_path(tmp_path, WHEN).name == "tankg-backup-20261119-100203-2.json"


# -- restore file names (used by preset_restore) --------------------------------------------------


def test_resolve_backup_file_inside_the_folder(tmp_path: Path) -> None:
    path = write(tmp_path / "tankg-backup-1.json", rf.document())
    assert backups.resolve_backup_file(tmp_path, "tankg-backup-1.json") == path.resolve()


@pytest.mark.parametrize(
    "name", ["/etc/passwd", "sub/file.json", "..", "../x.json", "a\\b.json", "", "."]
)
def test_resolve_backup_file_refuses_paths(tmp_path: Path, name: str) -> None:
    with pytest.raises(InvalidFile):
        backups.resolve_backup_file(tmp_path / "backups", name)


def test_resolve_backup_file_refuses_a_link_leading_out(tmp_path: Path) -> None:
    folder = tmp_path / "backups"
    folder.mkdir()
    outside = write(tmp_path / "secret.json", rf.document())
    (folder / "link.json").symlink_to(outside)
    with pytest.raises(InvalidFile, match="outside"):
        backups.resolve_backup_file(folder, "link.json")


def test_resolve_backup_file_refuses_a_missing_file(tmp_path: Path) -> None:
    with pytest.raises(InvalidFile, match="no file"):
        backups.resolve_backup_file(tmp_path, "nope.json")


# -- preset_backup / backups_list -----------------------------------------------------------------


async def test_backup_writes_a_verified_file_in_the_folder(tmp_path: Path) -> None:
    folder = tmp_path / "backups"
    async with open_harness(options(tmp_path), storage_pedal()) as h:
        result = await h.ok("preset_backup")
        second = await h.ok("preset_backup")
        listed = await h.ok("backups_list")
    path = Path(result["path"])
    assert path.parent == folder
    assert path.name.startswith("tankg-backup-")
    if os.name == "posix":  # Windows reports no POSIX modes (always 0o777)
        assert stat.S_IMODE(folder.stat().st_mode) == 0o700
    assert json.loads(path.read_text(encoding="utf-8")) == result["backup"]
    assert result["saved_to"] == result["path"]
    assert result["command"] == "preset backup"
    assert len(result["backup"]["presets"]) == 36
    assert result["summary"].startswith("Backup of TANK-Gv2 (firmware 96)")
    assert second["path"] != result["path"]  # never overwritten, even within the same second
    assert listed["folder"] == str(folder)
    assert len(listed["backups"]) == 2
    for row in listed["backups"]:
        assert row["restorable"] is True
        assert row["problems"] == []
        assert row["firmware"] == 96
        assert row["presets"] == 36


async def test_backup_folder_that_is_a_file_fails_before_connecting(tmp_path: Path) -> None:
    (tmp_path / "backups").write_text("x", encoding="utf-8")
    factory = storage_pedal()
    async with open_harness(options(tmp_path), factory) as h:
        text = await h.error("preset_backup")
    assert text.startswith("invalid_file: ")
    assert factory.calls == 0


async def test_backups_list_newest_first_with_problems(tmp_path: Path) -> None:
    folder = tmp_path / "backups"
    old = rf.document()
    old["created_at"] = "2026-11-01T09:00:00+00:00"
    new = rf.document()
    new["created_at"] = "2026-11-18T09:00:00+00:00"
    broken = rf.document()
    broken["created_at"] = "2026-10-01T09:00:00+00:00"
    broken["presets"] = broken["presets"][:35]
    write(folder / "tankg-backup-old.json", old)
    write(folder / "tankg-backup-new.json", new)
    write(folder / "broken.json", broken)
    (folder / "garbage.json").write_text("not json", encoding="utf-8")
    (folder / "notes.txt").write_text("ignored", encoding="utf-8")
    os.utime(folder / "garbage.json", (0, 0))
    factory = CountingFactory()
    async with open_harness(options(tmp_path), factory) as h:
        listed = await h.ok("backups_list")
    names = [row["file"] for row in listed["backups"]]
    assert names[:2] == ["tankg-backup-new.json", "tankg-backup-old.json"]
    assert set(names) == {
        "tankg-backup-new.json",
        "tankg-backup-old.json",
        "broken.json",
        "garbage.json",
    }
    rows = {row["file"]: row for row in listed["backups"]}
    assert rows["broken.json"]["restorable"] is False
    assert any("36 presets" in p for p in rows["broken.json"]["problems"])
    assert rows["garbage.json"]["restorable"] is False
    assert rows["garbage.json"]["created_at"] is None
    assert rows["tankg-backup-new.json"]["created_at"] == "2026-11-18T09:00:00+00:00"
    assert "4 backups" in listed["summary"]
    assert factory.calls == 0  # no pedal


async def test_backups_list_without_a_folder(tmp_path: Path) -> None:
    async with open_harness(options(tmp_path), CountingFactory()) as h:
        listed = await h.ok("backups_list")
    assert listed["backups"] == []
    assert not (tmp_path / "backups").exists()  # listing creates nothing
