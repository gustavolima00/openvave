"""``openvave.cli.files.write_json_atomic`` never replaces a file it did not mean to (spec 006
T064, Codex review of 0475c9e [P2]): without ``force`` the complete file is published with a
no-replace step, so a writer that loses a race for a name gets ``TargetExistsError`` instead of
silently replacing the winner's file."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from openvave.cli import files


def _race(monkeypatch: pytest.MonkeyPatch) -> None:
    """Let the existence checks pass, as if the other writer created the file just after."""
    monkeypatch.setattr(files, "check_target", lambda path, *, force: None)


def test_a_new_file_is_written(tmp_path: Path) -> None:
    target = tmp_path / "b.json"
    files.write_json_atomic(target, {"a": 1}, force=False)
    assert json.loads(target.read_text(encoding="utf-8")) == {"a": 1}
    assert os.listdir(tmp_path) == ["b.json"]


def test_a_file_created_after_the_check_is_not_replaced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "b.json"
    target.write_text("first writer", encoding="utf-8")
    _race(monkeypatch)
    with pytest.raises(files.TargetExistsError):
        files.write_json_atomic(target, {"a": 1}, force=False)
    assert target.read_text(encoding="utf-8") == "first writer"
    assert os.listdir(tmp_path) == ["b.json"]  # no temp file left


def _no_links(monkeypatch: pytest.MonkeyPatch) -> None:
    def no_links(src: object, dst: object) -> None:
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(files.os, "link", no_links)


@pytest.mark.skipif(sys.platform == "win32", reason="Windows renames without replacing")
def test_without_hard_links_posix_refuses_rather_than_risk_a_replace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FAT or a share without links offers no atomic no-replace step on POSIX: refuse."""
    _no_links(monkeypatch)
    target = tmp_path / "b.json"
    with pytest.raises(OSError, match="does not support hard links"):
        files.write_json_atomic(target, {"a": 1}, force=False)
    assert os.listdir(tmp_path) == []  # neither the file nor the temp file


@pytest.mark.skipif(sys.platform != "win32", reason="os.rename replaces on POSIX")
def test_without_hard_links_windows_renames_without_replacing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _no_links(monkeypatch)
    target = tmp_path / "b.json"
    files.write_json_atomic(target, {"a": 1}, force=False)
    assert json.loads(target.read_text(encoding="utf-8")) == {"a": 1}
    _race(monkeypatch)
    with pytest.raises(files.TargetExistsError):
        files.write_json_atomic(target, {"a": 2}, force=False)
    assert json.loads(target.read_text(encoding="utf-8")) == {"a": 1}
    assert os.listdir(tmp_path) == ["b.json"]


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privileges on Windows")
def test_a_dangling_link_counts_as_taken(tmp_path: Path) -> None:
    """Name allocation skips a dangling link, which the no-replace publish would refuse."""
    from datetime import datetime

    when = datetime(2026, 11, 24, 12, 0, 0)
    first = files.automatic_backup_path(tmp_path, "save", when)
    os.symlink(tmp_path / "gone.json", first)
    second = files.automatic_backup_path(tmp_path, "save", when)
    assert second != first and second.name.endswith("-before-save-1.json")
    with pytest.raises(files.TargetExistsError):
        files.write_json_atomic(first, {"a": 1}, force=False)


def test_force_still_replaces(tmp_path: Path) -> None:
    target = tmp_path / "b.json"
    target.write_text("old", encoding="utf-8")
    files.write_json_atomic(target, {"a": 1}, force=True)
    assert json.loads(target.read_text(encoding="utf-8")) == {"a": 1}
    assert os.listdir(tmp_path) == ["b.json"]


def test_other_link_errors_keep_their_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Codex round 3 [P3]: a full disk is reported as such, not as missing hard links."""
    import errno

    def full(src: object, dst: object) -> None:
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(files.os, "link", full)
    with pytest.raises(OSError) as caught:
        files.write_json_atomic(tmp_path / "b.json", {"a": 1}, force=False)
    assert caught.value.errno == errno.ENOSPC
    assert "hard links" not in str(caught.value)
    assert os.listdir(tmp_path) == []
