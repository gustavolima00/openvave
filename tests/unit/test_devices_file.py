"""The known-pedals file: load, save, validation (spec 005 T005, research R1–R2)."""

from __future__ import annotations

import json
import os
import stat
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from openvave import devices as devices_module
from openvave.devices import KnownDevices
from openvave.errors import ConfigError

SCHEMA_PATH = (
    Path(__file__).parents[2]
    / "specs"
    / "005-device-selection"
    / "contracts"
    / "devices-file.schema.json"
)
A = "8F3A21C4-0000-4000-8000-000000000001"
B = "AA:BB:CC:DD:EE:02"
NOW = datetime(2026, 11, 19, 10, 0, tzinfo=UTC)
LATER = datetime(2026, 11, 19, 11, 30, tzinfo=UTC)


def validate(document: Any) -> None:
    schema = json.loads(SCHEMA_PATH.read_text())
    validator_cls = jsonschema.validators.validator_for(schema)
    validator_cls(schema, format_checker=validator_cls.FORMAT_CHECKER).validate(document)


def sample(path: Path) -> KnownDevices:
    return (
        KnownDevices(path=path)
        .select(B, "home", name="TANK-Gv2_BLE", now=NOW)
        .select(A, "stage", now=NOW)
        .record_seen(A, "TANK-Gv2_BLE", 96, now=LATER)
    )


def device_doc(identifier: str = A, nickname: str | None = "stage", **extra: Any) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "identifier": identifier,
        "nickname": nickname,
        "added_at": "2026-11-19T10:00:00+00:00",
        "selected_at": None,
        "last_name": None,
        "last_firmware": None,
        "last_seen_at": None,
    }
    doc.update(extra)
    return doc


def write(path: Path, document: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document))


def test_missing_file_loads_empty(tmp_path: Path) -> None:
    path = tmp_path / "nothing" / "devices.json"
    known = KnownDevices.load(path)
    assert known.devices == ()
    assert known.default is None
    assert known.path == path
    assert not path.exists()  # loading never creates it


def test_load_without_argument_uses_default_path(tmp_path: Path) -> None:
    # conftest points OPENVAVE_CONFIG at a temporary file
    known = KnownDevices.load()
    assert known.path == Path(os.environ["OPENVAVE_CONFIG"])
    assert known.devices == ()


def test_save_then_load_is_equal(tmp_path: Path) -> None:
    path = tmp_path / "cfg" / "devices.json"
    known = sample(path)
    known.save()
    assert KnownDevices.load(path) == known


def test_saved_json_validates(tmp_path: Path) -> None:
    path = tmp_path / "devices.json"
    sample(path).save()
    document = json.loads(path.read_text())
    validate(document)
    assert document["format_version"] == 1
    assert document["default"] == A
    assert [d["identifier"] for d in document["devices"]] == [B, A]
    stage = document["devices"][1]
    assert stage["last_firmware"] == 96
    assert stage["last_seen_at"] == "2026-11-19T11:30:00+00:00"


def test_empty_saved_json_validates(tmp_path: Path) -> None:
    path = tmp_path / "devices.json"
    KnownDevices(path=path).save()
    document = json.loads(path.read_text())
    validate(document)
    assert document == {"format_version": 1, "default": None, "devices": []}


def test_unknown_keys_survive_a_rewrite(tmp_path: Path) -> None:
    path = tmp_path / "devices.json"
    write(
        path,
        {
            "format_version": 1,
            "default": A,
            "devices": [device_doc(colour="red", notes={"room": "studio"})],
            "comment": "kept",
        },
    )
    known = KnownDevices.load(path).rename("stage", "live").select(B, now=NOW)
    known.save()
    document = json.loads(path.read_text())
    validate(document)
    assert document["comment"] == "kept"
    live = document["devices"][0]
    assert live["nickname"] == "live"
    assert live["colour"] == "red"
    assert live["notes"] == {"room": "studio"}
    assert "colour" not in document["devices"][1]


def test_save_creates_the_directory(tmp_path: Path) -> None:
    path = tmp_path / "a" / "b" / "devices.json"
    sample(path).save()
    assert path.is_file()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX file modes")
def test_file_mode_is_0600(tmp_path: Path) -> None:
    path = tmp_path / "devices.json"
    path.write_text("{}")
    path.chmod(0o644)
    sample(path).save()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_save_is_atomic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "devices.json"
    original = sample(path)
    original.save()
    before = path.read_bytes()

    def broken_dump(*args: Any, **kwargs: Any) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(devices_module.json, "dump", broken_dump)
    with pytest.raises(OSError, match="disk full"):
        original.forget_all().save()
    assert path.read_bytes() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["devices.json"]  # no temporary left


def test_save_failing_replace_leaves_no_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "devices.json"

    def broken_replace(src: Any, dst: Any) -> None:
        raise OSError("read-only")

    monkeypatch.setattr(devices_module.os, "replace", broken_replace)
    with pytest.raises(OSError, match="read-only"):
        sample(path).save()
    assert list(tmp_path.iterdir()) == []


def test_naive_times_are_read_as_utc(tmp_path: Path) -> None:
    path = tmp_path / "devices.json"
    write(
        path,
        {
            "format_version": 1,
            "default": None,
            "devices": [device_doc(added_at="2026-11-19T10:00:00")],
        },
    )
    (device,) = KnownDevices.load(path).devices
    assert device.added_at == NOW


INVALID: dict[str, Any] = {
    "not_json": "{not json",
    "not_an_object": [],
    "format_version_2": {"format_version": 2, "default": None, "devices": []},
    "format_version_missing": {"default": None, "devices": []},
    "format_version_true": {"format_version": True, "default": None, "devices": []},
    "default_missing": {"format_version": 1, "devices": []},
    "devices_missing": {"format_version": 1, "default": None},
    "devices_not_a_list": {"format_version": 1, "default": None, "devices": {}},
    "default_not_in_devices": {"format_version": 1, "default": B, "devices": [device_doc()]},
    "default_wrong_type": {"format_version": 1, "default": 3, "devices": []},
    "duplicate_identifier": {
        "format_version": 1,
        "default": None,
        "devices": [device_doc(nickname="a1"), device_doc(A.lower(), "b1")],
    },
    "duplicate_nickname_case": {
        "format_version": 1,
        "default": None,
        "devices": [device_doc(A, "Stage"), device_doc(B, "stage")],
    },
    "device_not_an_object": {"format_version": 1, "default": None, "devices": ["x"]},
    "identifier_wrong_type": {"format_version": 1, "default": None, "devices": [device_doc(5)]},
    "identifier_empty": {"format_version": 1, "default": None, "devices": [device_doc("")]},
    "nickname_wrong_type": {
        "format_version": 1,
        "default": None,
        "devices": [device_doc(nickname=7)],
    },
    "nickname_bad": {"format_version": 1, "default": None, "devices": [device_doc(nickname="a b")]},
    "firmware_wrong_type": {
        "format_version": 1,
        "default": None,
        "devices": [device_doc(last_firmware="96")],
    },
    "firmware_bool": {
        "format_version": 1,
        "default": None,
        "devices": [device_doc(last_firmware=True)],
    },
    "firmware_negative": {
        "format_version": 1,
        "default": None,
        "devices": [device_doc(last_firmware=-1)],
    },
    "time_wrong_type": {"format_version": 1, "default": None, "devices": [device_doc(added_at=0)]},
    "time_not_a_time": {
        "format_version": 1,
        "default": None,
        "devices": [device_doc(added_at="soon")],
    },
    "field_missing": {
        "format_version": 1,
        "default": None,
        "devices": [{k: v for k, v in device_doc().items() if k != "last_name"}],
    },
}


@pytest.mark.parametrize("case", sorted(INVALID))
def test_invalid_file(tmp_path: Path, case: str) -> None:
    path = tmp_path / "devices.json"
    content = INVALID[case]
    path.write_text(content if isinstance(content, str) else json.dumps(content))
    with pytest.raises(ConfigError) as info:
        KnownDevices.load(path)
    assert info.value.reason == "invalid_file"
    assert info.value.path == path
    assert str(path) in str(info.value)
    assert info.value.problem


def test_unreadable_file(tmp_path: Path) -> None:
    path = tmp_path / "devices.json"
    path.mkdir()  # a directory where the file should be
    with pytest.raises(ConfigError) as info:
        KnownDevices.load(path)
    assert info.value.reason == "invalid_file"
    assert info.value.path == path
