"""``openvave preset restore`` (spec 004 T049, contracts/cli.md, FR-019…FR-024)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest

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
COMMIT = "00 59 22 08 00 00 04 00 00 00 f0 00 00 00 0b"
SELECT_1B = "00 59 22 09 00 00 04 01 00 00 e0 01 00 00 01 18"
SELECT_1C = "00 59 22 09 00 00 04 02 00 00 e0 01 00 00 01 17"
OPTS = ["--unsafe", "--experimental"]


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    async def no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr("openvave.session.SEQUENCE_SLEEP", no_sleep)
    monkeypatch.setattr("openvave.session.SELECT_SLEEP", no_sleep)
    monkeypatch.setattr("openvave.session.STATE_SLEEP", no_sleep)


def write_backup(tmp_path: Path, document: dict[str, Any], name: str = "backup-a.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def changed_fake(**kwargs: Any) -> FakeTransport:
    return make_fake(NORMAL, image=rf.image_with(s2=GAIN_90, s9=GAIN_90, s35=GAIN_90), **kwargs)


def run(
    capsys: pytest.CaptureFixture[str], argv: list[str], fake: FakeTransport, tmp_path: Path
) -> tuple[int, str, str]:
    out_dir = tmp_path / "auto"
    out_dir.mkdir(exist_ok=True)
    code = main(
        ["preset", "restore", *argv, "--backup-dir", str(out_dir)],
        transport_factory=factory_for(fake),
    )
    out, err = capsys.readouterr()
    return code, out, err


def automatic(tmp_path: Path) -> list[Path]:
    return sorted((tmp_path / "auto").glob("tankg-backup-*-before-restore*.json"))


def validate(doc: dict[str, Any]) -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    jsonschema.validators.validator_for(schema)(schema).validate(doc)


def test_restore_all_human_output(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    source = write_backup(tmp_path, rf.document())
    fake = changed_fake()
    code, out, err = run(capsys, [str(source), "--all", *OPTS], fake, tmp_path)
    assert code == 0, err
    [saved] = automatic(tmp_path)
    image = write_frame(0, sf.synthetic_image()).hex(" ")
    lines = out.splitlines()
    assert lines[:4] == [
        f"Restore all presets from {source}   UNSAFE: overwrites stored presets",
        "  differ: 1C 3B 9D (3 of 36)",
        f"Backup saved: {saved}",
        "A power loss during the next second has an unknown outcome.",
    ]
    assert lines[4].startswith("  write  00 59 22 fe 02 00 04 00 00 00 00 f6 02 00 a5 5a …")
    assert lines[4].endswith("   ACK   (773 bytes)")
    assert lines[5:] == [
        "  wait   300 ms",
        f"  write  {COMMIT}   ACK   (commit)",
        "  wait   100 ms",
        f"  write  {SELECT_1B}   ACK   (select 1B)",
        f"  verify 36 of 36 presets and header equal {source}   restored",
    ]
    assert [f.hex(" ") for f in writes(fake)] == [image, COMMIT, SELECT_1B]


def test_restore_slot_human_output(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    source = write_backup(tmp_path, rf.document(rf.image_with(s2=P)))
    fake = make_fake(NORMAL, image=rf.image_with(s2=GAIN_90))
    code, out, err = run(capsys, [str(source), "--slot", "1C", *OPTS], fake, tmp_path)
    assert code == 0, err
    [saved] = automatic(tmp_path)
    slot = write_frame(0x2C, P).hex(" ")
    assert out.splitlines() == [
        f"Restore 1C from {source}   UNSAFE: overwrites a stored preset",
        "  [6] gain 90 → 60",
        f"Backup saved: {saved}",
        "A power loss during the next second has an unknown outcome.",
        f"  write  {slot}   ACK",
        "  wait   300 ms",
        f"  write  {COMMIT}   ACK   (commit)",
        "  wait   100 ms",
        f"  write  {SELECT_1C}   ACK   (select 1C)",
        f"  verify stored 1C = {source} 1C, pedal on 1C, buffer = stored   restored",
    ]


def test_dry_run_prints_the_full_image_frame(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    source = write_backup(tmp_path, rf.document())
    fake = changed_fake()
    code, out, err = run(capsys, [str(source), "--all", "--dry-run", *OPTS], fake, tmp_path)
    assert code == 0, err
    image = write_frame(0, sf.synthetic_image()).hex(" ")
    assert f"  write  {image}" in out.splitlines()
    assert out.splitlines()[-1] == "  dry run: nothing sent, no backup taken"
    assert writes(fake) == []
    assert automatic(tmp_path) == []


def test_nothing_to_restore(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    source = write_backup(tmp_path, rf.document())
    fake = make_fake(NORMAL)
    code, out, err = run(capsys, [str(source), "--all", *OPTS], fake, tmp_path)
    assert code == 0, err
    assert out.splitlines() == [f"pedal already matches {source}; nothing sent"]
    assert writes(fake) == []
    assert automatic(tmp_path) == []


@pytest.mark.parametrize("flags", [[], ["--all", "--slot", "1C"]], ids=["neither", "both"])
def test_slot_or_all_exactly_one(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, flags: list[str]
) -> None:
    source = write_backup(tmp_path, rf.document())
    fake = changed_fake()
    code, _, _ = run(capsys, [str(source), *flags, *OPTS], fake, tmp_path)
    assert code == 2
    assert fake.sent == []


def test_invalid_file_exit_2_before_connecting(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    doc = rf.document()
    del doc["presets"][-1]
    source = write_backup(tmp_path, doc)
    fake = changed_fake()
    code, _, err = run(capsys, [str(source), "--all", *OPTS], fake, tmp_path)
    assert code == 2
    assert "36 presets" in err
    assert fake.sent == [] and fake.opened is False


@pytest.mark.parametrize("content", ["not json", "[]"], ids=["text", "list"])
def test_unreadable_file_exit_2(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, content: str
) -> None:
    source = tmp_path / "bad.json"
    source.write_text(content, encoding="utf-8")
    fake = changed_fake()
    code, _, _ = run(capsys, [str(source), "--all", *OPTS], fake, tmp_path)
    assert code == 2
    assert fake.opened is False


def test_missing_file_exit_2(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    fake = changed_fake()
    code, _, err = run(capsys, [str(tmp_path / "none.json"), "--all", *OPTS], fake, tmp_path)
    assert code == 2
    assert fake.opened is False


def test_firmware_mismatch_needs_experimental(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    source = write_backup(tmp_path, rf.document(firmware=97))
    fake = changed_fake()
    code, _, err = run(capsys, [str(source), "--all", "--unsafe"], fake, tmp_path)
    assert code == 1
    assert "firmware_mismatch" in err
    assert writes(fake) == []


def test_without_unsafe_exit_1(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    source = write_backup(tmp_path, rf.document())
    fake = changed_fake()
    code, out, err = run(capsys, [str(source), "--all", "--experimental"], fake, tmp_path)
    assert code == 1 and out == ""
    assert "unsafe_required" in err
    assert {f[2] for f in fake.sent} <= {0x11, 0x23}


def test_json_output_matches_the_schema(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    source = write_backup(tmp_path, rf.document())
    fake = changed_fake()
    code, out, err = run(capsys, [str(source), "--all", "--json", *OPTS], fake, tmp_path)
    assert code == 0, err
    doc = json.loads(out)
    validate(doc)
    [saved] = automatic(tmp_path)
    assert doc["command"] == "preset restore"
    assert doc["backup_saved_to"] == str(saved)
    plan = doc["plan"]
    assert plan["action"] == "restore_all" and plan["source"] == str(source)
    assert plan["changed_slots"] == ["1C", "3B", "9D"]
    assert (plan["target_index"], plan["return_index"]) == (None, 1)
    assert plan["steps"][0]["target"] == "stored_image"
    assert doc["result"]["verified"] is True
    assert "read_back" not in doc["result"]
    assert doc["result"]["mismatched_slots"] == []


def test_verification_mismatch_exit_8(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    source = write_backup(tmp_path, rf.document())
    fake = changed_fake(faults={"stored_image": "corrupt"})
    code, _, err = run(capsys, [str(source), "--all", *OPTS], fake, tmp_path)
    assert code == 8
    assert "9D" in err
    assert "Stored presets may have changed. Nothing was retried." in err
