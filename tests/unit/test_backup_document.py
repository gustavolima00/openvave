"""Backup ↔ JSON document (T006, research R7, contracts/backup.schema.json)."""

from __future__ import annotations

import copy
import json
import re
from datetime import UTC, datetime
from typing import Any

import jsonschema
import pytest
from referencing import Registry, Resource

from openvave import Backup, ProtocolError, StoredPreset, __version__
from openvave.backup import from_document, to_document
from openvave.models import DeviceIdentity, Region, RegionRead
from openvave.protocol import decode_region
from tests.support import storage_fixture as sf
from tests.support.captures import REPO_ROOT

SCHEMA_PATH = REPO_ROOT / "specs/003-preset-backup-edit-writes/contracts/backup.schema.json"
FIELD_SCHEMA_PATH = REPO_ROOT / "specs/002-preset-byte-map/contracts/decoded-field.schema.json"
FIELD_REF = "../../002-preset-byte-map/contracts/decoded-field.schema.json"
HEX = re.compile(r"^([0-9a-f]{2}( [0-9a-f]{2})*)?$")
IDENTITY = DeviceIdentity(
    raw=b"TANK-Gv2_096".ljust(27, b"\x00"), name="TANK-Gv2", firmware=96, firmware_untested=False
)
CREATED = datetime(2026, 11, 17, 10, 5, 0, tzinfo=UTC)


def make_backup(image: bytes | None = None, warnings: tuple[str, ...] = ()) -> Backup:
    image = sf.synthetic_image() if image is None else image
    presets = tuple(
        StoredPreset(
            index=i,
            position=sf.position(i),
            data=image[2 + 21 * i : 23 + 21 * i],
            decoded=decode_region(
                RegionRead(Region.CURRENT_PRESET, image[2 + 21 * i : 23 + 21 * i]), 96
            ),
        )
        for i in range(36)
    )
    return Backup(
        identity=IDENTITY,
        created_at=CREATED,
        header=image[:2],
        image=image,
        presets=presets,
        warnings=warnings,
    )


def validator() -> jsonschema.protocols.Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    field_schema = json.loads(FIELD_SCHEMA_PATH.read_text(encoding="utf-8"))
    registry: Registry = Registry().with_resource(FIELD_REF, Resource.from_contents(field_schema))
    cls = jsonschema.validators.validator_for(schema)
    return cls(schema, registry=registry)


def test_document_validates_against_schema() -> None:
    doc = make_backup().to_document()
    validator().validate(doc)
    assert doc["kind"] == "openvave.preset-backup"
    assert doc["format_version"] == 1
    assert doc["tool"] == f"openvave {__version__}"
    assert doc["created_at"] == "2026-11-17T10:05:00+00:00"
    assert doc["header"] == "a5 5a"
    assert doc["layout"] == {
        "type": 4,
        "address": "0x00000000",
        "store_offset": 2,
        "preset_size": 21,
        "preset_count": 36,
    }
    first = doc["presets"][6]
    assert (first["index"], first["position"], first["bank"], first["slot"]) == (6, "2C", 2, "C")
    assert doc["presets"][1]["raw"] == sf.PUBLIC_PRESET.hex(" ")
    assert doc["presets"][1]["unknown_offsets"] == []
    assert len(doc["image"].split()) == 758


def test_document_hex_fields_lowercase() -> None:
    doc = make_backup().to_document()
    for value in [doc["header"], doc["image"], doc["identity"]["raw"]] + [
        p["raw"] for p in doc["presets"]
    ]:
        assert HEX.match(value)


def test_field_items_match_decoded_field_schema() -> None:
    field_schema = json.loads(FIELD_SCHEMA_PATH.read_text(encoding="utf-8"))
    doc = make_backup().to_document()
    for preset in doc["presets"]:
        assert len(preset["fields"]) == 21
        for item in preset["fields"]:
            jsonschema.validate(item, field_schema)


def _keys(value: Any) -> list[str]:
    if isinstance(value, dict):
        return [k for k in value] + [k for v in value.values() for k in _keys(v)]
    if isinstance(value, list):
        return [k for v in value for k in _keys(v)]
    return []


def test_no_device_identifier() -> None:
    doc = make_backup().to_document()
    keys = {k.lower() for k in _keys(doc)}
    assert not keys & {"identifier", "mac", "address_ble", "uuid", "device", "rssi"}


def test_round_trip() -> None:
    backup = make_backup(warnings=("unexpected_header",))
    doc = backup.to_document()
    again = Backup.from_document(doc)
    assert again == backup
    assert again.to_document() == doc
    assert from_document(to_document(backup, __version__)) == backup


def test_document_is_json_serialisable() -> None:
    doc = make_backup().to_document()
    assert json.loads(json.dumps(doc)) == doc


def test_image_disagrees_with_presets() -> None:
    doc = make_backup().to_document()
    bad = copy.deepcopy(doc)
    raw = bytearray.fromhex(bad["presets"][6]["raw"])
    raw[0] ^= 1
    bad["presets"][6]["raw"] = raw.hex(" ")
    with pytest.raises(ProtocolError) as exc:
        Backup.from_document(bad)
    assert exc.value.reason == "backup_mismatch"
    assert exc.value.detail is not None and "2C" in exc.value.detail


@pytest.mark.parametrize(("key", "value"), [("kind", "other"), ("format_version", 2)])
def test_wrong_kind_or_version(key: str, value: object) -> None:
    doc = make_backup().to_document()
    doc[key] = value
    with pytest.raises(ValueError):
        Backup.from_document(doc)


def test_constructor_checks_invariant() -> None:
    backup = make_backup()
    with pytest.raises(ProtocolError):
        Backup(
            identity=backup.identity,
            created_at=backup.created_at,
            header=b"\x00\x00",
            image=backup.image,
            presets=backup.presets,
            warnings=(),
        )
    with pytest.raises(ValueError):
        Backup(
            identity=backup.identity,
            created_at=backup.created_at,
            header=backup.header,
            image=backup.image,
            presets=backup.presets[:35],
            warnings=(),
        )
