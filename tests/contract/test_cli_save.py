"""``openvave preset save`` (spec 004 T048, contracts/cli.md, FR-012…FR-018, FR-028…FR-031)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from openvave.cli import files, main
from openvave.transport.fake import FakeTransport
from tests.contract.test_cli_set import factory_for
from tests.support import storage_fixture as sf
from tests.support.captures import REPO_ROOT
from tests.support.write_fixture import EDIT, NORMAL, make_fake, write_frame, writes

pytestmark = pytest.mark.persistent_writes

SCHEMA = REPO_ROOT / "specs/004-remote-edit-save-restore/contracts/sequence-result.schema.json"
P = sf.PUBLIC_PRESET
GAIN_90 = P[:6] + bytes([90]) + P[7:]
SLOT_1B = write_frame(0x17, GAIN_90).hex(" ")
SLOT_1C = write_frame(0x2C, GAIN_90).hex(" ")
COMMIT = "00 59 22 08 00 00 04 00 00 00 f0 00 00 00 0b"
SELECT_1B = "00 59 22 09 00 00 04 01 00 00 e0 01 00 00 01 18"
SELECT_1C = "00 59 22 09 00 00 04 02 00 00 e0 01 00 00 01 17"
UNSAFE_OPTS = ["--unsafe", "--experimental"]


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
    return make_fake(NORMAL, buffer=GAIN_90, image=image_1c_public(), **kwargs)


def run(
    capsys: pytest.CaptureFixture[str], argv: list[str], fake: FakeTransport, tmp_path: Path
) -> tuple[int, str, str]:
    code = main(
        ["preset", "save", *argv, "--backup-dir", str(tmp_path)],
        transport_factory=factory_for(fake),
    )
    out, err = capsys.readouterr()
    return code, out, err


def validate(doc: dict[str, Any]) -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    jsonschema.validators.validator_for(schema)(schema).validate(doc)


def backups(tmp_path: Path) -> list[Path]:
    return sorted(tmp_path.glob("tankg-backup-*-before-save*.json"))


def test_save_to_human_output(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    fake = edited_fake()
    code, out, err = run(capsys, ["--to", "1C", *UNSAFE_OPTS], fake, tmp_path)
    assert code == 0, err
    [saved] = backups(tmp_path)
    assert out.splitlines() == [
        "Save current sound to 1C (index 2)   UNSAFE: overwrites a stored preset",
        "  [6] gain 60 → 90",
        f"Backup saved: {saved}",
        "A power loss during the next second has an unknown outcome.",
        f"  write  {SLOT_1C}   ACK",
        "  wait   300 ms",
        f"  write  {COMMIT}   ACK   (commit)",
        "  wait   100 ms",
        f"  write  {SELECT_1C}   ACK   (select 1C)",
        "  verify stored 1C = written bytes, pedal on 1C, buffer = stored   saved",
    ]
    assert [f.hex(" ") for f in writes(fake)] == [SLOT_1C, COMMIT, SELECT_1C]


def test_automatic_backup_file_is_a_valid_backup_of_the_pedal_before_the_save(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    from openvave import Backup

    fake = edited_fake()
    code, _, err = run(capsys, ["--to", "1C", *UNSAFE_OPTS], fake, tmp_path)
    assert code == 0, err
    [saved] = backups(tmp_path)
    backup = Backup.from_document(json.loads(saved.read_text(encoding="utf-8")))
    assert backup.image == image_1c_public()  # taken before the slot write


def test_save_to_loaded_slot_by_default(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    fake = make_fake(NORMAL, buffer=GAIN_90)
    code, out, err = run(capsys, UNSAFE_OPTS, fake, tmp_path)
    assert code == 0, err
    assert out.splitlines()[0] == (
        "Save current sound to 1B (index 1)   UNSAFE: overwrites a stored preset"
    )
    assert [f.hex(" ") for f in writes(fake)] == [SLOT_1B, COMMIT, SELECT_1B]


def test_dry_run_prints_every_step_and_writes_no_backup(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    fake = edited_fake()
    code, out, err = run(capsys, ["--to", "1C", "--dry-run", *UNSAFE_OPTS], fake, tmp_path)
    assert code == 0, err
    assert out.splitlines() == [
        "Save current sound to 1C (index 2)   UNSAFE: overwrites a stored preset",
        "  [6] gain 60 → 90",
        f"  write  {SLOT_1C}",
        "  wait   300 ms",
        f"  write  {COMMIT}   (commit)",
        "  wait   100 ms",
        f"  write  {SELECT_1C}   (select 1C)",
        "  dry run: nothing sent, no backup taken",
    ]
    assert writes(fake) == []
    assert list(tmp_path.iterdir()) == []


def test_dry_run_without_opt_ins_prints_the_refusal(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    fake = edited_fake()
    code, out, err = run(capsys, ["--to", "1C", "--dry-run"], fake, tmp_path)
    assert code == 0, err
    refusal = [line for line in out.splitlines() if "refused" in line]
    assert len(refusal) == 1
    assert "unsafe_required" in refusal[0]
    assert "--unsafe" in refusal[0]
    assert "--experimental" not in refusal[0]  # spec 004 T090: stored_slot/commit confirmed
    assert writes(fake) == []


def test_without_unsafe_exit_1_and_reads_only(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    fake = edited_fake()
    code, out, err = run(capsys, ["--to", "1C", "--experimental"], fake, tmp_path)
    assert code == 1
    assert out == ""
    assert "unsafe_required" in err and "--unsafe" in err
    assert "overwrite" in err
    assert {f[2] for f in fake.sent} <= {0x11, 0x23}
    assert list(tmp_path.iterdir()) == []


def test_without_experimental_saves(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    # spec 004 T090: confirmed by gate sessions A and B, so --unsafe alone is enough
    fake = edited_fake()
    code, out, err = run(capsys, ["--to", "1C", "--unsafe"], fake, tmp_path)
    assert code == 0, err
    assert "saved" in out
    assert len(writes(fake)) == 3
    assert len(backups(tmp_path)) == 1


def test_refused_in_edit_mode(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    fake = make_fake(EDIT, buffer=GAIN_90)
    code, _, err = run(capsys, UNSAFE_OPTS, fake, tmp_path)
    assert code == 1
    assert "edit_mode" in err
    assert writes(fake) == []


def test_no_change(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    fake = make_fake(NORMAL)
    code, out, err = run(capsys, UNSAFE_OPTS, fake, tmp_path)
    assert code == 0, err
    assert out.splitlines() == ["1B already holds this sound; nothing sent"]
    assert writes(fake) == []
    assert list(tmp_path.iterdir()) == []


def test_json_output_matches_the_schema(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    fake = edited_fake()
    code, out, err = run(capsys, ["--to", "1C", "--json", *UNSAFE_OPTS], fake, tmp_path)
    assert code == 0, err
    doc = json.loads(out)
    validate(doc)
    [saved] = backups(tmp_path)
    assert doc["command"] == "preset save"
    assert doc["backup_saved_to"] == str(saved)
    plan = doc["plan"]
    assert plan["action"] == "save" and plan["pedal_state"] == "normal"
    assert (plan["target_index"], plan["return_index"]) == (2, 2)
    assert plan["changed_slots"] == ["1C"]
    assert plan["diff"] == [{"offset": 6, "before": 60, "after": 90, "name": "gain"}]
    assert [s["kind"] for s in plan["steps"]] == ["write", "wait", "write", "wait", "write"]
    assert plan["steps"][0] == {"kind": "write", "target": "stored_slot", "frame": SLOT_1C}
    assert plan["dry_run"] is False and plan["refusal"] is None
    result = doc["result"]
    assert [s["status"] for s in result["steps"]] == [
        "acked",
        "waited",
        "acked",
        "waited",
        "acked",
    ]
    assert result["verified"] is True and result["stored_may_have_changed"] is True
    assert result["read_back"] == GAIN_90.hex(" ")


def test_json_dry_run(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    fake = edited_fake()
    code, out, err = run(capsys, ["--to", "1C", "--json", "--dry-run"], fake, tmp_path)
    assert code == 0, err
    doc = json.loads(out)
    validate(doc)
    assert doc["backup_saved_to"] is None
    assert doc["plan"]["dry_run"] is True
    assert doc["plan"]["refusal"] == "unsafe_required"
    assert "result" not in doc


def test_failure_report_on_lost_link(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    fake = edited_fake(faults={"commit": "disconnect"})
    code, out, err = run(capsys, ["--to", "1C", *UNSAFE_OPTS], fake, tmp_path)
    assert code == 6
    [saved] = backups(tmp_path)
    lines = err.splitlines()
    assert lines[0].startswith("error: ")
    assert lines[1:] == [
        "  slot write 1C   ACK",
        "  commit          no reply",
        "  select 1C       not sent",
        "Stored presets may have changed. Nothing was retried.",
        "Check:   openvave preset backup",
        f"Undo:    openvave preset restore {saved} --all --unsafe",
    ]
    assert "Backup saved" in out  # printed before the first write


def test_failure_report_on_nak(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    fake = edited_fake(faults={"stored_slot": "nak"})
    code, _, err = run(capsys, ["--to", "1C", *UNSAFE_OPTS], fake, tmp_path)
    assert code == 7
    assert "  slot write 1C   NAK" in err.splitlines()
    assert "  commit          not sent" in err.splitlines()
    assert "Stored presets may have changed. Nothing was retried." in err


def test_failure_report_on_read_back_mismatch(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    fake = edited_fake(faults={"stored_slot": "corrupt"})
    code, _, err = run(capsys, ["--to", "1C", *UNSAFE_OPTS], fake, tmp_path)
    assert code == 8
    assert "  commit          not sent" in err.splitlines()
    assert f"  expected {GAIN_90.hex(' ')}" in err.splitlines()
    assert any(line.startswith("  read     ") for line in err.splitlines())


def test_failure_json_carries_the_steps(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    fake = edited_fake(faults={"commit": "disconnect"})
    code, out, err = run(capsys, ["--to", "1C", "--json", *UNSAFE_OPTS], fake, tmp_path)
    assert code == 6
    doc = json.loads(out)
    validate(doc)
    [saved] = backups(tmp_path)
    assert doc["backup_saved_to"] == str(saved)
    assert [s["status"] for s in doc["result"]["steps"]] == [
        "acked",
        "waited",
        "no_reply",
        "not_sent",
        "not_sent",
    ]
    assert doc["result"]["stored_may_have_changed"] is True
    assert doc["result"]["verified"] is False
    assert err.startswith("error: ")


def test_bad_position_is_a_usage_error(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    fake = edited_fake()
    code, _, err = run(capsys, ["--to", "10A", *UNSAFE_OPTS], fake, tmp_path)
    assert code == 2
    assert fake.sent == []


def test_missing_backup_dir_is_a_usage_error(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    fake = edited_fake()
    code = main(
        ["preset", "save", *UNSAFE_OPTS, "--backup-dir", str(tmp_path / "nope")],
        transport_factory=factory_for(fake),
    )
    _, err = capsys.readouterr()
    assert code == 2
    assert "backup-dir" in err
    assert fake.sent == []


def test_automatic_backup_never_overwrites(tmp_path: Path) -> None:
    when = datetime(2026, 11, 18, 10, 15, 0)
    first = files.automatic_backup_path(tmp_path, "save", when)
    assert first == tmp_path / "tankg-backup-20261118-101500-before-save.json"
    first.write_text("{}")
    second = files.automatic_backup_path(tmp_path, "save", when)
    assert second == tmp_path / "tankg-backup-20261118-101500-before-save-1.json"
    second.write_text("{}")
    assert files.automatic_backup_path(tmp_path, "restore", when).name == (
        "tankg-backup-20261118-101500-before-restore.json"
    )
    assert files.automatic_backup_path(tmp_path, "save", when).name.endswith("-save-2.json")
