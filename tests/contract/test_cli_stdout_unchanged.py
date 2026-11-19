"""0.4.0 output is kept when a pedal is chosen (spec 005 T037, SC-006).

For every pedal command: stdout with a default pedal selected equals stdout with no
configuration (the only pedal in range), with equal exit codes; JSON documents differ only by
``device.nickname`` and ``device.chosen_by``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from tests.support import choice as ch
from tests.support.cli005 import seed
from tests.support.scanner import TANK, UUID_1

TIME = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?(\+00:00|Z)?|\d{8}-\d{6}")


@pytest.fixture(autouse=True)
def _fast(monkeypatch: pytest.MonkeyPatch) -> None:
    ch.no_waits(monkeypatch)


def two_runs(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, command: str, extra: list[str]
) -> tuple[tuple[int, str], tuple[int, str]]:
    argv = [*ch.command_argvs(tmp_path)[command], *extra]
    code, plain, _ = ch.run(capsys, argv, ch.Pedals([(UUID_1, TANK, -58)], command))
    seed((UUID_1, "stage"))
    chosen_code, chosen, err = ch.run(capsys, argv, ch.Pedals([(UUID_1, TANK, -58)], command))
    if "--json" not in extra:
        assert "(selected)" in err
    return (code, TIME.sub("<time>", plain)), (chosen_code, TIME.sub("<time>", chosen))


@pytest.mark.parametrize("command", ch.COMMAND_IDS)
def test_human_stdout_and_exit_code_unchanged(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, command: str
) -> None:
    plain, chosen = two_runs(capsys, tmp_path, command, [])
    assert chosen == plain


def without_choice(document: Any) -> Any:
    if isinstance(document, dict):
        out = {}
        for key, value in document.items():
            if key == "device" and isinstance(value, dict):
                value = {k: v for k, v in value.items() if k not in ("nickname", "chosen_by")}
            out[key] = without_choice(value)
        return out
    if isinstance(document, list):
        return [without_choice(item) for item in document]
    return document


@pytest.mark.parametrize("command", [c for c in ch.COMMAND_IDS if c != "watch"])
def test_json_differs_only_by_the_choice(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, command: str
) -> None:
    (code, plain), (chosen_code, chosen) = two_runs(capsys, tmp_path, command, ["--json"])
    assert chosen_code == code
    if not plain.strip():
        assert not chosen.strip()
        return
    plain_doc, chosen_doc = json.loads(plain), json.loads(chosen)
    assert without_choice(chosen_doc) == without_choice(plain_doc)
    assert plain_doc["device"]["chosen_by"] == "only_one_found"
    assert plain_doc["device"]["nickname"] is None
    assert chosen_doc["device"]["chosen_by"] == "selected"
    assert chosen_doc["device"]["nickname"] == "stage"
