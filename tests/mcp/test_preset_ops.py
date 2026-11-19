"""``preset_copy`` / ``preset_swap`` / ``preset_import`` / ``preset_export`` (spec 007 US5 in the
MCP server): the CLI's frames and documents, ``unsafe`` required, the automatic backup in the
backup folder first, import only from that folder, export into it."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from openvave import PresetFile
from openvave.cli import main
from openvave.transport.fake import FakeTransport
from tests.mcp.conftest import PEDAL, CountingFactory, open_harness, options
from tests.support import restore_fixture as rf
from tests.support import storage_fixture as sf
from tests.support.write_fixture import NORMAL, make_fake, writes

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


def folder(tmp_path: Path) -> Path:
    return tmp_path / "backups"


def automatic(tmp_path: Path, action: str) -> list[Path]:
    return sorted(folder(tmp_path).glob(f"tankg-backup-*-before-{action}*.json"))


def put_preset(tmp_path: Path, data: bytes, firmware: int = 96, name: str = "tone.json") -> Path:
    folder(tmp_path).mkdir(exist_ok=True)
    document = PresetFile(
        identity=rf.identity(firmware),
        created_at=datetime(2026, 11, 19, 12, 0, tzinfo=UTC),
        source_index=4,
        data=data,
    ).to_document()
    path = folder(tmp_path) / name
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def cli_run_sync(capsys: pytest.CaptureFixture[str], argv: list[str], fake: FakeTransport) -> Any:
    async def factory(target, scan_timeout):  # type: ignore[no-untyped-def]
        return fake, PEDAL

    code = main([*argv, "--json"], transport_factory=factory)
    out = capsys.readouterr().out
    assert code == 0, out
    return json.loads(out)


async def cli_run(capsys: pytest.CaptureFixture[str], argv: list[str], fake: FakeTransport) -> Any:
    return await asyncio.to_thread(cli_run_sync, capsys, argv, fake)


def strip(document: dict[str, Any]) -> dict[str, Any]:
    document = {k: v for k, v in document.items() if k not in VOLATILE}
    if "plan" in document:
        document["plan"] = {k: v for k, v in document["plan"].items() if k != "source"}
    return document


# -- parity with the CLI ------------------------------------------------------------------------


@pytest.mark.parametrize("dry_run", [False, True], ids=["run", "dry_run"])
async def test_copy_equals_the_cli(tmp_path, capsys, dry_run) -> None:
    cli_dir = tmp_path / "cli"
    cli_dir.mkdir()
    cli_fake = make_fake(NORMAL)
    flags = ["--dry-run"] if dry_run else []
    expected = await cli_run(
        capsys,
        ["preset", "copy", "1A", "3C", "--unsafe", "--backup-dir", str(cli_dir), *flags],
        cli_fake,
    )
    factory = CountingFactory(make=lambda: make_fake(NORMAL))
    async with open_harness(options(tmp_path), factory) as h:
        result = await h.ok(
            "preset_copy", {"source": "1A", "target": "3C", "unsafe": True, "dry_run": dry_run}
        )
    assert writes(factory.fake) == writes(cli_fake)
    assert strip(result) == strip(expected)
    if dry_run:
        assert writes(factory.fake) == []
        assert automatic(tmp_path, "copy") == []
    else:
        [saved] = automatic(tmp_path, "copy")
        assert result["backup_saved_to"] == str(saved)
        assert "copied and verified" in result["summary"]


async def test_swap_equals_the_cli(tmp_path, capsys) -> None:
    cli_dir = tmp_path / "cli"
    cli_dir.mkdir()
    cli_fake = make_fake(NORMAL)
    expected = await cli_run(
        capsys,
        ["preset", "swap", "2B", "4D", "--unsafe", "--backup-dir", str(cli_dir)],
        cli_fake,
    )
    factory = CountingFactory(make=lambda: make_fake(NORMAL))
    async with open_harness(options(tmp_path), factory) as h:
        result = await h.ok("preset_swap", {"first": "2B", "second": "4D", "unsafe": True})
    assert writes(factory.fake) == writes(cli_fake)
    assert strip(result) == strip(expected)
    assert result["plan"]["changed_slots"] == ["2B", "4D"]
    assert automatic(tmp_path, "swap")
    assert "swapped and verified" in result["summary"]


async def test_import_equals_the_cli(tmp_path, capsys) -> None:
    source = put_preset(tmp_path, GAIN_90)
    cli_dir = tmp_path / "cli"
    cli_dir.mkdir()
    cli_fake = make_fake(NORMAL)
    expected = await cli_run(
        capsys,
        ["preset", "import", str(source), "--to", "2C", "--unsafe", "--backup-dir", str(cli_dir)],
        cli_fake,
    )
    factory = CountingFactory(make=lambda: make_fake(NORMAL))
    async with open_harness(options(tmp_path), factory) as h:
        result = await h.ok("preset_import", {"file": source.name, "to": "2C", "unsafe": True})
    assert writes(factory.fake) == writes(cli_fake)
    assert strip(result) == strip(expected)
    assert result["plan"]["source"] == source.name
    assert automatic(tmp_path, "import")


# -- refusals -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("tool", "args"),
    [
        ("preset_copy", {"source": "1A", "target": "3C"}),
        ("preset_swap", {"first": "2B", "second": "4D"}),
        ("preset_import", {"file": "tone.json", "to": "2C"}),
    ],
)
async def test_without_unsafe_nothing_is_sent(tmp_path, tool, args) -> None:
    put_preset(tmp_path, GAIN_90)
    factory = CountingFactory(make=lambda: make_fake(NORMAL))
    async with open_harness(options(tmp_path), factory) as h:
        text = await h.error(tool, args)
    assert text.startswith("unsafe_required: ")
    assert writes(factory.fake) == []
    assert list(folder(tmp_path).glob("tankg-backup-*")) == []


@pytest.mark.parametrize(
    ("tool", "args", "kind"),
    [
        ("preset_copy", {"source": "1A", "target": "1a"}, "invalid_value"),
        ("preset_swap", {"first": "2B", "second": "2B"}, "invalid_value"),
        ("preset_copy", {"source": "10A", "target": "1A"}, "invalid_value"),
        ("preset_import", {"file": "../tone.json", "to": "2C"}, "invalid_file"),
        ("preset_import", {"file": "missing.json", "to": "2C"}, "invalid_file"),
    ],
)
async def test_bad_arguments_are_refused_before_connecting(tmp_path, tool, args, kind) -> None:
    factory = CountingFactory(make=lambda: make_fake(NORMAL))
    async with open_harness(options(tmp_path), factory) as h:
        text = await h.error(tool, {**args, "unsafe": True})
    assert text.startswith(f"{kind}: ")
    assert factory.calls == 0


async def test_import_of_a_backup_file_points_to_restore(tmp_path) -> None:
    folder(tmp_path).mkdir()
    (folder(tmp_path) / "full.json").write_text(json.dumps(rf.document()), encoding="utf-8")
    factory = CountingFactory(make=lambda: make_fake(NORMAL))
    async with open_harness(options(tmp_path), factory) as h:
        text = await h.error("preset_import", {"file": "full.json", "to": "2C", "unsafe": True})
    assert text.startswith("invalid_file: ")
    assert "preset_restore" in text
    assert factory.calls == 0


# -- export and the folder listing --------------------------------------------------------------


async def test_export_writes_a_preset_file_into_the_folder(tmp_path) -> None:
    factory = CountingFactory(make=lambda: make_fake(NORMAL))
    async with open_harness(options(tmp_path), factory) as h:
        result = await h.ok("preset_export", {"position": "2A"})
        listing = await h.ok("backups_list", {})
    assert writes(factory.fake) == []
    path = Path(result["path"])
    assert path.parent == folder(tmp_path)
    assert path.name.startswith("tankg-preset-2A-")
    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["kind"] == "openvave.preset"
    assert document["raw"] == sf.synthetic_image()[2 + 21 * 4 : 23 + 21 * 4].hex(" ")
    assert result["raw"] == document["raw"]
    [row] = [r for r in listing["backups"] if r["file"] == path.name]
    assert row["kind"] == "preset"
    assert row["importable"] is True
    assert row["restorable"] is False


async def test_exported_file_can_be_imported(tmp_path) -> None:
    factory = CountingFactory(make=lambda: make_fake(NORMAL))
    async with open_harness(options(tmp_path), factory) as h:
        exported = await h.ok("preset_export", {"position": "2A"})
        result = await h.ok(
            "preset_import",
            {"file": Path(exported["path"]).name, "to": "3C", "unsafe": True},
        )
    assert result["plan"]["action"] == "import"
    assert "imported and verified" in result["summary"]
