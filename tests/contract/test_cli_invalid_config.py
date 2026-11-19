"""An invalid ``devices.json`` (spec 005 T021, contracts/cli.md, research R2).

``scan`` still lists pedals with a warning; commands that need the configuration exit 2 with the
path, the problem and the ``forget --all`` hint.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.support.cli005 import config_path, run
from tests.support.scanner import TANK, UUID_1, fake_scanner

HINT = "hint: fix the file or reset it with: openvave forget --all\n"


@pytest.fixture
def invalid() -> Path:
    path = config_path()
    path.parent.mkdir(parents=True)
    path.write_text('{"format_version": 2, "default": null, "devices": []}', encoding="utf-8")
    return path


def test_scan_warns_and_lists(capsys: pytest.CaptureFixture[str], invalid: Path) -> None:
    code, out, err = run(
        capsys, ["scan", "--scan-timeout", "0.1"], scanner=fake_scanner([(UUID_1, TANK, -58)])
    )
    assert code == 0
    assert out.startswith(f"  {UUID_1}  {TANK}  -58 dBm\n")
    assert (
        f"warning: {invalid}: unsupported format_version 2 (expected 1) (nicknames unavailable)\n"
        in err
    )


@pytest.mark.parametrize(
    "argv",
    [["device"], ["select", "stage"], ["select", UUID_1, "--offline"], ["device", "--check"]],
)
def test_commands_needing_the_file_exit_2(
    capsys: pytest.CaptureFixture[str], invalid: Path, argv: list[str]
) -> None:
    code, out, err = run(capsys, argv)
    assert code == 2
    assert out == ""
    assert err == f"error: {invalid}: unsupported format_version 2 (expected 1)\n{HINT}"
