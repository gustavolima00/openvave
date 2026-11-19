"""``openvave preset copy|swap|export|import`` (spec 007 US5, plan.md)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from openvave import PresetFile
from openvave.cli import main
from openvave.transport.fake import FakeTransport
from tests.contract.test_cli_set import factory_for
from tests.support import restore_fixture as rf
from tests.support import storage_fixture as sf
from tests.support.captures import REPO_ROOT
from tests.support.write_fixture import NORMAL, make_fake, write_frame, writes

pytestmark = pytest.mark.persistent_writes

SCHEMA = REPO_ROOT / "specs/004-remote-edit-save-restore/contracts/sequence-result.schema.json"
P = sf.PUBLIC_PRESET
GAIN_90 = P[:6] + bytes([90]) + P[7:]
IMAGE = sf.synthetic_image()
COMMIT = "00 59 22 08 00 00 04 00 00 00 f0 00 00 00 0b"


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    async def no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr("openvave.session.SEQUENCE_SLEEP", no_sleep)
    monkeypatch.setattr("openvave.session.SELECT_SLEEP", no_sleep)
    monkeypatch.setattr("openvave.session.STATE_SLEEP", no_sleep)


def slot(image: bytes, index: int) -> bytes:
    return image[2 + 21 * index : 23 + 21 * index]


def hexs(frame: bytes) -> str:
    return frame.hex(" ")


def select(index: int) -> str:
    return hexs(write_frame(0xE0000000 + index, b"\x01"))


def run(
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    fake: FakeTransport,
    tmp_path: Path,
    *,
    persistent: bool = True,
) -> tuple[int, str, str]:
    extra: list[str] = []
    if persistent:
        out_dir = tmp_path / "auto"
        out_dir.mkdir(exist_ok=True)
        extra = ["--backup-dir", str(out_dir)]
    code = main(["preset", *argv, *extra], transport_factory=factory_for(fake))
    out, err = capsys.readouterr()
    return code, out, err


def validate(doc: dict[str, Any]) -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    jsonschema.validators.validator_for(schema)(schema).validate(doc)


def automatic(tmp_path: Path, action: str) -> list[Path]:
    return sorted((tmp_path / "auto").glob(f"tankg-backup-*-before-{action}*.json"))


def preset_path(tmp_path: Path, data: bytes, firmware: int = 96) -> Path:
    document = PresetFile(
        identity=rf.identity(firmware),
        created_at=datetime(2026, 11, 19, 12, 0, tzinfo=UTC),
        source_index=4,
        data=data,
    ).to_document()
    path = tmp_path / "tone.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


# -- copy ---------------------------------------------------------------------------------------


def test_copy_human_output(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    fake = make_fake(NORMAL)
    code, out, err = run(capsys, ["copy", "1A", "3C", "--unsafe"], fake, tmp_path)
    assert code == 0, err
    [saved] = automatic(tmp_path, "copy")
    lines = out.splitlines()
    assert lines[0] == "Copy 1A to 3C (index 10)   UNSAFE: overwrites a stored preset"
    assert f"Backup saved: {saved}" in lines
    slot_frame = hexs(write_frame(2 + 21 * 10, slot(IMAGE, 0)))
    assert f"  write  {slot_frame}   ACK" in lines
    assert f"  write  {select(10)}   ACK   (select 3C)" in lines
    assert lines[-1] == ("  verify stored 3C = 1A, pedal on 3C, buffer = stored   copied")
    assert [hexs(f) for f in writes(fake)] == [slot_frame, COMMIT, select(10)]


def test_copy_needs_unsafe(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    fake = make_fake(NORMAL)
    code, _, err = run(capsys, ["copy", "1A", "3C"], fake, tmp_path)
    assert code == 1
    assert "unsafe_required" in err and "--unsafe" in err
    assert writes(fake) == []


def test_copy_dry_run_json(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    fake = make_fake(NORMAL)
    code, out, err = run(
        capsys, ["copy", "1A", "3C", "--unsafe", "--dry-run", "--json"], fake, tmp_path
    )
    assert code == 0, err
    doc = json.loads(out)
    validate(doc)
    assert doc["command"] == "preset copy"
    assert doc["plan"]["action"] == "copy"
    assert doc["plan"]["source"] == "1A"
    assert doc["plan"]["changed_slots"] == ["3C"]
    assert "result" not in doc
    assert writes(fake) == []


def test_copy_same_slot_is_a_usage_error(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    fake = make_fake(NORMAL)
    code, _, err = run(capsys, ["copy", "2B", "2B", "--unsafe"], fake, tmp_path)
    assert code == 2
    assert "same" in err
    assert fake.sent == []


# -- swap ---------------------------------------------------------------------------------------


def test_swap_human_output(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    fake = make_fake(NORMAL)
    code, out, err = run(capsys, ["swap", "2B", "4D", "--unsafe"], fake, tmp_path)
    assert code == 0, err
    lines = out.splitlines()
    assert lines[0] == "Swap 2B and 4D   UNSAFE: overwrites stored presets"
    assert lines[1] == "  differ: 2B 4D (2 of 36)"
    assert automatic(tmp_path, "swap")
    assert lines[-1] == "  verify 36 of 36 presets and header as planned   swapped"
    expected = rf.image_with(s5=slot(IMAGE, 15), s15=slot(IMAGE, 5))
    assert [hexs(f) for f in writes(fake)] == [
        hexs(write_frame(0, expected)),
        COMMIT,
        select(1),
    ]


def test_swap_dry_run_json_validates(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    code, out, err = run(
        capsys, ["swap", "2B", "4D", "--unsafe", "--dry-run", "--json"], make_fake(NORMAL), tmp_path
    )
    assert code == 0, err
    doc = json.loads(out)
    validate(doc)
    assert doc["plan"]["action"] == "swap"
    assert doc["plan"]["changed_slots"] == ["2B", "4D"]


def test_swap_same_slot_is_a_usage_error(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    code, _, err = run(capsys, ["swap", "2B", "2b", "--unsafe"], make_fake(NORMAL), tmp_path)
    assert code == 2
    assert "itself" in err


# -- export / import ----------------------------------------------------------------------------


def test_export_writes_a_preset_file(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    fake = make_fake(NORMAL)
    target = tmp_path / "out.json"
    code, out, err = run(
        capsys, ["export", "2A", "--output", str(target)], fake, tmp_path, persistent=False
    )
    assert code == 0, err
    assert writes(fake) == []
    doc = json.loads(target.read_text(encoding="utf-8"))
    assert doc["kind"] == "openvave.preset"
    assert doc["source_position"] == "2A"
    assert doc["raw"] == hexs(slot(IMAGE, 4))
    assert f"Saved {target}" in out


def test_export_never_overwrites_without_force(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    target = tmp_path / "out.json"
    target.write_text("{}")
    fake = make_fake(NORMAL)
    code, _, err = run(
        capsys, ["export", "2A", "--output", str(target)], fake, tmp_path, persistent=False
    )
    assert code == 2
    assert "--force" in err
    assert fake.sent == []


def test_import_human_output(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    source = preset_path(tmp_path, GAIN_90)
    fake = make_fake(NORMAL)
    code, out, err = run(capsys, ["import", str(source), "--to", "2C", "--unsafe"], fake, tmp_path)
    assert code == 0, err
    lines = out.splitlines()
    assert lines[0] == f"Import {source} into 2C (index 6)   UNSAFE: overwrites a stored preset"
    assert lines[-1] == f"  verify stored 2C = {source}, pedal on 2C, buffer = stored   imported"
    assert [hexs(f) for f in writes(fake)] == [
        hexs(write_frame(2 + 21 * 6, GAIN_90)),
        COMMIT,
        select(6),
    ]


def test_import_of_a_backup_file_points_to_restore(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    path = tmp_path / "backup.json"
    path.write_text(json.dumps(rf.document()), encoding="utf-8")
    fake = make_fake(NORMAL)
    code, _, err = run(capsys, ["import", str(path), "--to", "2C", "--unsafe"], fake, tmp_path)
    assert code == 2
    assert "preset restore" in err
    assert fake.sent == []


def test_import_from_other_firmware_needs_experimental(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    source = preset_path(tmp_path, GAIN_90, firmware=97)
    fake = make_fake(NORMAL)
    code, _, err = run(capsys, ["import", str(source), "--to", "2C", "--unsafe"], fake, tmp_path)
    assert code == 1
    assert "firmware_mismatch" in err
    assert writes(fake) == []
