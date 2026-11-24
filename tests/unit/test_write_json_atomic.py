"""``openvave.cli.files.write_json_atomic`` never replaces a file it did not mean to (spec 006
T064, Codex review of 0475c9e [P2]): without ``force`` the complete file is published with a
no-replace step, so a writer that loses a race for a name gets ``TargetExistsError`` instead of
silently replacing the winner's file."""

from __future__ import annotations

import json
import os
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


def test_without_hard_links_only_complete_files_appear(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FAT or a share without links: the file is still published whole from the temp file,
    and a name that exists at the last check is refused."""

    def no_links(src: object, dst: object) -> None:
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(files.os, "link", no_links)
    target = tmp_path / "b.json"
    files.write_json_atomic(target, {"a": 1}, force=False)
    assert json.loads(target.read_text(encoding="utf-8")) == {"a": 1}
    assert os.listdir(tmp_path) == ["b.json"]

    with pytest.raises(files.TargetExistsError):
        files.write_json_atomic(target, {"a": 2}, force=False)
    assert json.loads(target.read_text(encoding="utf-8")) == {"a": 1}
    assert os.listdir(tmp_path) == ["b.json"]


def test_force_still_replaces(tmp_path: Path) -> None:
    target = tmp_path / "b.json"
    target.write_text("old", encoding="utf-8")
    files.write_json_atomic(target, {"a": 1}, force=True)
    assert json.loads(target.read_text(encoding="utf-8")) == {"a": 1}
    assert os.listdir(tmp_path) == ["b.json"]
