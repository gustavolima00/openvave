"""Helpers for the spec 005 CLI contract tests: run ``main`` with a fake scanner, read and seed
the temporary configuration (``OPENVAVE_CONFIG`` is set per test by ``tests/conftest.py``)."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from openvave.cli import main
from openvave.devices import KnownDevices, default_config_path
from openvave.models import DeviceInfo
from openvave.transport import Transport
from tests.support.scanner import forbidden_scanner

CONTRACTS = Path(__file__).resolve().parents[2] / "specs" / "005-device-selection" / "contracts"
WHEN = datetime(2026, 11, 19, 10, 2, tzinfo=UTC)

Factory = Callable[[str | None, float], Awaitable[tuple[Transport, DeviceInfo | None]]]


def config_path() -> Path:
    return default_config_path()


def seed(*selections: tuple[str, str | None], default: str | None = "last") -> KnownDevices:
    """Write a configuration with these ``(identifier, nickname)`` selected in order. The last
    one is the default unless ``default`` is ``None`` (no default) or another identifier."""
    known = KnownDevices.load(config_path())
    for identifier, nickname in selections:
        known = known.select(identifier, nickname, name="TANK-Gv2_BLE", now=WHEN)
    if default is None:
        known = known.forget()
    elif default != "last":
        known = known.select(default, now=WHEN)
    known.save()
    return known


def file_bytes() -> bytes | None:
    path = config_path()
    return path.read_bytes() if path.exists() else None


def run(
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    *,
    scanner: Callable[..., Any] = forbidden_scanner,
    factory: Factory | None = None,
) -> tuple[int, str, str]:
    code = main(argv, scanner_factory=scanner, transport_factory=factory)
    out, err = capsys.readouterr()
    return code, out, err


def validate(document: Any, schema_name: str) -> None:
    schema = json.loads((CONTRACTS / schema_name).read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(document, schema, cls=jsonschema.Draft202012Validator)
