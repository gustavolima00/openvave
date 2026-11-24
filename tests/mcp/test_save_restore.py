"""``preset_save`` / ``preset_restore``: the CLI's ``--unsafe`` rules and frames, the automatic
backup in the backup folder first, restore confined to that folder (spec 006 US5,
contracts/tools.md). The client here declares no elicitation, so nobody is asked (CLI parity);
the prompt itself is in ``test_elicitation.py``."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

import pytest

from openvave.cli import main
from openvave.transport.fake import FakeTransport
from tests.mcp.conftest import PEDAL, CountingFactory, open_harness, options
from tests.support import restore_fixture as rf
from tests.support import storage_fixture as sf
from tests.support.write_fixture import EDIT, NORMAL, make_fake, writes

pytestmark = pytest.mark.persistent_writes

P = sf.PUBLIC_PRESET
GAIN_90 = P[:6] + bytes([90]) + P[7:]
VOLATILE = ("read_at", "summary", "reminder", "backup_saved_to", "path")


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    async def no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr("openvave.session.SEQUENCE_SLEEP", no_sleep)
    monkeypatch.setattr("openvave.session.SELECT_SLEEP", no_sleep)
    monkeypatch.setattr("openvave.session.STATE_SLEEP", no_sleep)


def image_1c_public() -> bytes:
    presets = sf.synthetic_presets()
    presets[2] = P
    return sf.HEADER + b"".join(presets)


def edited_fake(**kwargs: Any) -> FakeTransport:
    """Normal mode on 1B, the edit buffer has gain 90, 1C holds the public preset."""
    return make_fake(NORMAL, buffer=GAIN_90, image=image_1c_public(), **kwargs)


def changed_fake(**kwargs: Any) -> FakeTransport:
    """Normal mode; 1C, 3B and 9D differ from ``rf.document()``."""
    return make_fake(NORMAL, image=rf.image_with(s2=GAIN_90, s9=GAIN_90, s35=GAIN_90), **kwargs)


def backup_folder(tmp_path: Path) -> Path:
    return tmp_path / "backups"


def put_backup(tmp_path: Path, document: dict[str, Any], name: str = "source.json") -> Path:
    folder = backup_folder(tmp_path)
    folder.mkdir(exist_ok=True)
    path = folder / name
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def automatic(tmp_path: Path, action: str) -> list[Path]:
    return sorted(backup_folder(tmp_path).glob(f"tankg-backup-*-before-{action}*.json"))


def cli_run_sync(
    capsys: pytest.CaptureFixture[str], argv: list[str], fake: FakeTransport
) -> tuple[int, Any]:
    async def factory(target, scan_timeout):  # type: ignore[no-untyped-def]
        return fake, PEDAL

    code = main([*argv, "--json"], transport_factory=factory)
    out = capsys.readouterr().out
    return code, json.loads(out) if out.strip() else None


async def cli_run(
    capsys: pytest.CaptureFixture[str], argv: list[str], fake: FakeTransport
) -> tuple[int, Any]:
    return await asyncio.to_thread(cli_run_sync, capsys, argv, fake)


def strip(document: dict[str, Any]) -> dict[str, Any]:
    document = {k: v for k, v in document.items() if k not in VOLATILE}
    if "plan" in document:
        document["plan"] = {k: v for k, v in document["plan"].items() if k != "source"}
    return document


# -- parity with the CLI ---------------------------------------------------------------------------


@pytest.mark.parametrize("dry_run", [False, True], ids=["run", "dry_run"])
async def test_save_equals_the_cli(tmp_path, capsys, dry_run) -> None:
    cli_dir = tmp_path / "cli"
    cli_dir.mkdir()
    cli_fake = edited_fake()
    flags = ["--dry-run"] if dry_run else []
    code, expected = await cli_run(
        capsys,
        ["preset", "save", "--to", "1C", "--unsafe", "--backup-dir", str(cli_dir), *flags],
        cli_fake,
    )
    assert code == 0
    factory = CountingFactory(make=edited_fake)
    async with open_harness(options(tmp_path), factory) as h:
        result = await h.ok("preset_save", {"to": "1C", "unsafe": True, "dry_run": dry_run})
    assert writes(factory.fake) == writes(cli_fake)
    assert strip(result) == strip(expected)
    if dry_run:
        assert writes(factory.fake) == []
        assert result["backup_saved_to"] is None
        assert result["reminder"] == "dry run: nothing sent"
        assert not backup_folder(tmp_path).exists() or automatic(tmp_path, "save") == []
    else:
        [saved] = automatic(tmp_path, "save")
        assert result["backup_saved_to"] == str(saved)
        assert str(saved) in result["reminder"]
        assert len(writes(factory.fake)) == 3


@pytest.mark.parametrize(
    ("args", "flags"),
    [
        ({"all": True}, ["--all"]),
        ({"slot": "1C"}, ["--slot", "1C"]),
        ({"slot": 2}, ["--slot", "2"]),
    ],
    ids=["all", "slot", "slot_index"],
)
async def test_restore_equals_the_cli(tmp_path, capsys, args, flags) -> None:
    source = put_backup(tmp_path, rf.document())
    cli_dir = tmp_path / "cli"
    cli_dir.mkdir()
    cli_fake = changed_fake()
    code, expected = await cli_run(
        capsys,
        ["preset", "restore", str(source), *flags, "--unsafe", "--backup-dir", str(cli_dir)],
        cli_fake,
    )
    assert code == 0
    factory = CountingFactory(make=changed_fake)
    async with open_harness(options(tmp_path), factory) as h:
        result = await h.ok("preset_restore", {"file": source.name, "unsafe": True, **args})
    assert writes(factory.fake) == writes(cli_fake)
    assert strip(result) == strip(expected)
    assert result["plan"]["source"] == source.name
    [saved] = automatic(tmp_path, "restore")
    assert result["backup_saved_to"] == str(saved)


async def test_save_to_the_loaded_slot_by_default(tmp_path) -> None:
    factory = CountingFactory(make=lambda: make_fake(NORMAL, buffer=GAIN_90))
    async with open_harness(options(tmp_path), factory) as h:
        result = await h.ok("preset_save", {"unsafe": True})
    assert result["plan"]["target_index"] == 1
    assert "1B" in result["summary"]


async def test_nothing_to_save_takes_no_backup(tmp_path) -> None:
    factory = CountingFactory(make=lambda: make_fake(NORMAL))
    async with open_harness(options(tmp_path), factory) as h:
        result = await h.ok("preset_save", {"unsafe": True})
    assert result["plan"]["no_change"] is True
    assert writes(factory.fake) == []
    assert automatic(tmp_path, "save") == []
    assert "nothing sent" in result["summary"]


# -- refusals before sending ----------------------------------------------------------------------


async def test_save_without_unsafe_is_refused_with_nothing_sent(tmp_path) -> None:
    factory = CountingFactory(make=edited_fake)
    async with open_harness(options(tmp_path), factory) as h:
        text = await h.error("preset_save", {"to": "1C"})
    assert text.startswith("unsafe_required: ")
    assert writes(factory.fake) == []
    assert automatic(tmp_path, "save") == []


async def test_save_dry_run_without_unsafe_shows_the_refusal(tmp_path) -> None:
    factory = CountingFactory(make=edited_fake)
    async with open_harness(options(tmp_path), factory) as h:
        result = await h.ok("preset_save", {"to": "1C", "dry_run": True})
    assert result["plan"]["refusal"] == "unsafe_required"
    assert "refused: unsafe_required" in result["summary"]
    assert writes(factory.fake) == []


async def test_save_in_edit_mode_is_refused(tmp_path) -> None:
    factory = CountingFactory(make=lambda: make_fake(EDIT, buffer=GAIN_90))
    async with open_harness(options(tmp_path), factory) as h:
        text = await h.error("preset_save", {"unsafe": True})
    assert text.startswith("edit_mode: ")
    assert writes(factory.fake) == []


async def test_bad_position_is_refused_before_connecting(tmp_path) -> None:
    factory = CountingFactory(make=edited_fake)
    async with open_harness(options(tmp_path), factory) as h:
        text = await h.error("preset_save", {"to": "10A", "unsafe": True})
    assert text.startswith("invalid_value: ")
    assert factory.calls == 0


async def test_restore_without_unsafe_is_refused(tmp_path) -> None:
    source = put_backup(tmp_path, rf.document())
    factory = CountingFactory(make=changed_fake)
    async with open_harness(options(tmp_path), factory) as h:
        text = await h.error("preset_restore", {"file": source.name, "all": True})
    assert text.startswith("unsafe_required: ")
    assert writes(factory.fake) == []
    assert automatic(tmp_path, "restore") == []


async def test_restore_firmware_mismatch_needs_experimental(tmp_path) -> None:
    source = put_backup(tmp_path, rf.document(firmware=97))
    factory = CountingFactory(make=changed_fake)
    async with open_harness(options(tmp_path), factory) as h:
        text = await h.error("preset_restore", {"file": source.name, "all": True, "unsafe": True})
    assert text.startswith("firmware_mismatch: ")
    assert writes(factory.fake) == []


async def test_restore_with_unsaved_edits_needs_discard_edits(tmp_path) -> None:
    source = put_backup(tmp_path, rf.document())

    def make() -> FakeTransport:
        return changed_fake(buffer=GAIN_90)

    factory = CountingFactory(make=make)
    async with open_harness(options(tmp_path), factory) as h:
        text = await h.error("preset_restore", {"file": source.name, "all": True, "unsafe": True})
        assert text.startswith("edits_would_be_discarded: ")
        assert writes(factory.fake) == []
        await h.ok(
            "preset_restore",
            {"file": source.name, "all": True, "unsafe": True, "discard_edits": True},
        )
    assert len(writes(factory.fake)) == 3


@pytest.mark.parametrize(
    "args",
    [{}, {"slot": "1C", "all": True}, {"all": False}],
    ids=["neither", "both", "all_false"],
)
async def test_restore_needs_slot_xor_all(tmp_path, args) -> None:
    source = put_backup(tmp_path, rf.document())
    factory = CountingFactory(make=changed_fake)
    async with open_harness(options(tmp_path), factory) as h:
        text = await h.error("preset_restore", {"file": source.name, "unsafe": True, **args})
    assert text.startswith("invalid_value: ")
    assert factory.calls == 0


# -- restore confinement ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    ["/etc/passwd", "sub/source.json", "../source.json", "..", "", "missing.json"],
    ids=["absolute", "separator", "dotdot", "parent", "empty", "missing"],
)
async def test_restore_file_outside_the_folder_is_refused_before_connecting(tmp_path, name) -> None:
    put_backup(tmp_path, rf.document())
    (tmp_path / "source.json").write_text(json.dumps(rf.document()), encoding="utf-8")
    factory = CountingFactory(make=changed_fake)
    async with open_harness(options(tmp_path), factory) as h:
        text = await h.error("preset_restore", {"file": name, "all": True, "unsafe": True})
    assert text.startswith("invalid_file: ")
    assert factory.calls == 0


async def test_restore_symlink_leading_out_is_refused(tmp_path) -> None:
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps(rf.document()), encoding="utf-8")
    folder = backup_folder(tmp_path)
    folder.mkdir()
    os.symlink(outside, folder / "link.json")
    factory = CountingFactory(make=changed_fake)
    async with open_harness(options(tmp_path), factory) as h:
        text = await h.error("preset_restore", {"file": "link.json", "all": True, "unsafe": True})
    assert text.startswith("invalid_file: ")
    assert factory.calls == 0


async def test_restore_of_a_corrupt_file_is_refused_before_connecting(tmp_path) -> None:
    document = rf.document()
    del document["presets"][-1]
    source = put_backup(tmp_path, document)
    factory = CountingFactory(make=changed_fake)
    async with open_harness(options(tmp_path), factory) as h:
        text = await h.error("preset_restore", {"file": source.name, "all": True, "unsafe": True})
    assert text.startswith("invalid_file: ")
    assert "36 presets" in text
    assert factory.calls == 0


# -- the automatic backup --------------------------------------------------------------------


async def test_automatic_backup_is_the_pedal_before_the_save(tmp_path) -> None:
    from openvave import Backup

    factory = CountingFactory(make=edited_fake)
    async with open_harness(options(tmp_path), factory) as h:
        await h.ok("preset_save", {"to": "1C", "unsafe": True})
    [saved] = automatic(tmp_path, "save")
    backup = Backup.from_document(json.loads(saved.read_text(encoding="utf-8")))
    assert backup.image == image_1c_public()
    if os.name == "posix":  # Windows reports no POSIX modes
        assert (backup_folder(tmp_path).stat().st_mode & 0o777) == 0o700


async def test_backup_write_failure_sends_nothing(tmp_path, monkeypatch) -> None:
    """Any platform: the automatic backup's writer fails, so nothing reaches the pedal."""
    from openvave.cli import files

    def refuse(*_args: Any, **_kwargs: Any) -> None:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(files, "write_json_atomic", refuse)
    factory = CountingFactory(make=edited_fake)
    async with open_harness(options(tmp_path), factory) as h:
        text = await h.error("preset_save", {"to": "1C", "unsafe": True})
    assert text.startswith("invalid_file: ")
    assert "Permission denied" in text
    assert "nothing was written to the pedal" in text
    assert writes(factory.fake) == []
    assert automatic(tmp_path, "save") == []


@pytest.mark.skipif(
    os.name != "posix" or os.geteuid() == 0,
    reason="needs POSIX folder permissions, which Windows and root do not enforce",
)
async def test_read_only_backup_folder_sends_nothing(tmp_path) -> None:
    """The same failure from a real read-only folder (POSIX only)."""
    folder = backup_folder(tmp_path)
    folder.mkdir()
    folder.chmod(0o500)
    factory = CountingFactory(make=edited_fake)
    try:
        async with open_harness(options(tmp_path), factory) as h:
            text = await h.error("preset_save", {"to": "1C", "unsafe": True})
    finally:
        folder.chmod(0o700)
    assert text.startswith("invalid_file: ")
    assert "nothing was written to the pedal" in text
    assert writes(factory.fake) == []


async def test_failure_mid_sequence_carries_the_partial_document_and_the_backup(tmp_path) -> None:
    factory = CountingFactory(make=lambda: edited_fake(faults={"commit": "nak"}))
    async with open_harness(options(tmp_path), factory) as h:
        text = await h.error("preset_save", {"to": "1C", "unsafe": True})
    [saved] = automatic(tmp_path, "save")
    lines = text.splitlines()
    assert lines[0].startswith("write_nak: ")
    assert any(line.startswith("backup: ") and saved.name in line for line in lines)
    [partial] = [line for line in lines if line.startswith("partial: ")]
    document = json.loads(partial.removeprefix("partial: "))
    assert document["command"] == "preset save"
    assert document["backup_saved_to"] == str(saved)
    assert [s["status"] for s in document["result"]["steps"]][:3] == ["acked", "waited", "nak"]


async def test_automatic_backup_never_replaces_a_file_published_after_the_check(
    tmp_path, monkeypatch
) -> None:
    """Two servers sharing the folder in the same second (spec 006 T064, Codex review of
    0475c9e [P2]): the name chosen here is published by the other server before this one writes
    it, so this backup goes to the next name and the other recovery snapshot stays intact."""
    from openvave.cli import files

    folder = backup_folder(tmp_path)
    folder.mkdir()
    taken = folder / "tankg-backup-20261124-120000-before-save.json"
    real_path, real_check = files.automatic_backup_path, files.check_target
    names = iter([taken])

    def racing_path(directory: Path, action: str, when: Any) -> Path:
        return next(names, None) or real_path(directory, action, when)

    def racing_check(path: Path, *, force: bool) -> None:
        if path == taken:
            # Every check finds nothing; the other server publishes the name right after.
            if not taken.exists():
                taken.write_text("the other server's backup", encoding="utf-8")
            return
        real_check(path, force=force)

    monkeypatch.setattr(files, "automatic_backup_path", racing_path)
    monkeypatch.setattr(files, "check_target", racing_check)
    factory = CountingFactory(make=edited_fake)
    async with open_harness(options(tmp_path), factory) as h:
        result = await h.ok("preset_save", {"to": "1C", "unsafe": True})
    assert taken.read_text(encoding="utf-8") == "the other server's backup"
    assert result["backup_saved_to"] != str(taken)
    assert Path(result["backup_saved_to"]).parent == folder
    assert len(writes(factory.fake)) == 3
