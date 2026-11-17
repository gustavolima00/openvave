"""``openvave preset backup``: output, file, refusals and exit codes (T007, contracts/cli.md)."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import pytest

from openvave.cli import main
from openvave.models import DeviceInfo
from openvave.transport import Transport
from openvave.transport.fake import FakeTransport
from tests.support import storage_fixture as sf
from tests.support.captures import FW96_CONNECT, QUERY, load_capture
from tests.unit.test_backup_document import validator

CAP = load_capture(FW96_CONNECT)
PEDAL = DeviceInfo("3F1A-UUID", "TANK-Gv2_BLE", -58)
DEFAULT_NAME = re.compile(r"^tankg-backup-\d{8}-\d{6}\.json$")

Factory = Callable[[str | None, float], Awaitable[tuple[Transport, DeviceInfo | None]]]


def make_fake(image: bytes | None = None, image_reply: bytes | None = None) -> FakeTransport:
    script: dict[str, tuple[bytes, bytes]] = {QUERY: (CAP.tx(QUERY), CAP.rx(QUERY))}
    if image_reply is not None:
        script[sf.IMAGE_LABEL] = (sf.read_request(0, 758), image_reply)
    memory = {0: sf.synthetic_image() if image is None else image}
    return FakeTransport(script, memory=memory, chunk_size=182)


def factory_for(fake: FakeTransport) -> Factory:
    async def factory(
        device_id: str | None, scan_timeout: float
    ) -> tuple[Transport, DeviceInfo | None]:
        return fake, PEDAL

    return factory


def run(
    capsys: pytest.CaptureFixture[str], argv: list[str], fake: FakeTransport | None = None
) -> tuple[int, str, str, FakeTransport]:
    fake = fake or make_fake()
    code = main(argv, transport_factory=factory_for(fake))
    out, err = capsys.readouterr()
    return code, out, err, fake


def test_human_output_and_file(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    target = tmp_path / "b.json"
    code, out, err, fake = run(capsys, ["preset", "backup", "--output", str(target)])
    assert code == 0, err
    lines = out.splitlines()
    assert lines[0] == "Backup of TANK-Gv2 (firmware 96)   36 presets, header a5 5a"
    image = sf.synthetic_image()
    assert lines[1] == "  1A  " + image[2:23].hex(" ")
    assert lines[2] == "  1B  " + sf.PUBLIC_PRESET.hex(" ")
    assert lines[36] == "  9D  " + image[737:758].hex(" ")
    assert lines[37] == "Cross-check with whole-image read: OK"
    assert lines[38] == f"Saved {target}"
    assert len(lines) == 39
    assert {f[2] for f in fake.sent} == {0x11, 0x23}
    doc = json.loads(target.read_text(encoding="utf-8"))
    validator().validate(doc)
    assert doc["image"] == image.hex(" ")
    assert [p.name for p in tmp_path.iterdir()] == ["b.json"]


def test_json_output(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    target = tmp_path / "b.json"
    code, out, err, _ = run(capsys, ["preset", "backup", "--json", "--output", str(target)])
    assert code == 0, err
    doc: dict[str, Any] = json.loads(out)
    assert doc["schema_version"] == 2
    assert doc["command"] == "preset backup"
    assert doc["device"]["name"] == "TANK-Gv2_BLE"
    assert doc["identity"]["firmware"] == 96
    assert doc["saved_to"] == str(target)
    validator().validate(doc["backup"])
    assert doc["backup"] == json.loads(target.read_text(encoding="utf-8"))
    assert doc["read_at"] == doc["backup"]["created_at"]


def test_default_file_name(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    code, out, err, _ = run(capsys, ["preset", "backup"])
    assert code == 0, err
    files = [p.name for p in tmp_path.iterdir()]
    assert len(files) == 1 and DEFAULT_NAME.match(files[0]), files
    assert out.splitlines()[-1] == f"Saved {files[0]}"


def test_existing_target_refused_before_any_read(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    target = tmp_path / "b.json"
    target.write_text("keep", encoding="utf-8")
    code, out, err, fake = run(capsys, ["preset", "backup", "--output", str(target)])
    assert code == 2
    assert fake.sent == []
    assert "--force" in err
    assert out == ""
    assert target.read_text(encoding="utf-8") == "keep"


def test_force_overwrites(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    target = tmp_path / "b.json"
    target.write_text("old", encoding="utf-8")
    code, _, err, _ = run(capsys, ["preset", "backup", "--output", str(target), "--force"])
    assert code == 0, err
    assert json.loads(target.read_text(encoding="utf-8"))["kind"] == "openvave.preset-backup"


def test_mismatch_exits_7_without_file(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    image = bytearray(sf.synthetic_image())
    image[2 + 21 * 35] ^= 0x01
    fake = make_fake(image_reply=sf.read_reply(0, bytes(image)))
    target = tmp_path / "b.json"
    code, out, err, _ = run(capsys, ["preset", "backup", "--output", str(target)], fake)
    assert code == 7
    assert "9D" in err
    assert out == ""
    assert list(tmp_path.iterdir()) == []


def test_unexpected_header_warns(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    fake = make_fake(sf.synthetic_image(header=b"\x00\x00"))
    target = tmp_path / "b.json"
    code, out, err, _ = run(capsys, ["preset", "backup", "--output", str(target)], fake)
    assert code == 0, err
    assert out.splitlines()[0] == (
        "Backup of TANK-Gv2 (firmware 96)   36 presets, header 00 00  UNEXPECTED (expected a5 5a)"
    )
    assert "warning" in err and "header" in err
    assert json.loads(target.read_text(encoding="utf-8"))["warnings"] == ["unexpected_header"]


def test_interrupted_write_leaves_no_file(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from openvave.cli import files

    def broken_dump(document: object, fh: Any, **kwargs: object) -> None:
        fh.write('{"partial": ')
        raise RuntimeError("disk full")

    monkeypatch.setattr(files.json, "dump", broken_dump)
    target = tmp_path / "b.json"
    code, _, err, _ = run(capsys, ["preset", "backup", "--output", str(target)])
    assert code == 1
    assert "disk full" in err
    assert os.listdir(tmp_path) == []


def test_interrupted_force_keeps_old_file(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from openvave.cli import files

    def broken_dump(document: object, fh: Any, **kwargs: object) -> None:
        raise RuntimeError("disk full")

    monkeypatch.setattr(files.json, "dump", broken_dump)
    target = tmp_path / "b.json"
    target.write_text("old", encoding="utf-8")
    code, _, _, _ = run(capsys, ["preset", "backup", "--output", str(target), "--force"])
    assert code == 1
    assert os.listdir(tmp_path) == ["b.json"]
    assert target.read_text(encoding="utf-8") == "old"


def test_preset_dump_still_works(capsys: pytest.CaptureFixture[str]) -> None:
    fake = FakeTransport.from_capture(FW96_CONNECT)
    code, out, err, _ = run(capsys, ["preset", "dump"], fake)
    assert code == 0, err
    assert out.startswith("Current preset")
