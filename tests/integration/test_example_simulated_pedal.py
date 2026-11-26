"""The documented simulated-pedal example runs without a pedal (spec 008 FR-024, quickstart §2).

The example saves and restores on the simulated pedal, so it sends persistent writes (to the
fake only) and this test carries the ``persistent_writes`` marker.
"""

from __future__ import annotations

import ast
import runpy

import pytest

from openvave.protocol import PANEL_GROUPS
from tests.support.captures import REPO_ROOT

EXAMPLE = REPO_ROOT / "docs" / "examples" / "simulated_pedal.py"


@pytest.mark.persistent_writes
def test_example_runs(capsys: pytest.CaptureFixture[str]) -> None:
    runpy.run_path(str(EXAMPLE), run_name="__main__")
    out = capsys.readouterr().out
    lines = out.splitlines()
    assert any("MASTER" in line for line in lines)
    assert any("D/AMP" in line for line in lines)
    assert out.index("MASTER") < out.index("D/AMP")
    for group in PANEL_GROUPS:
        assert any(line.startswith(f"{group.name}:") for line in lines), group.name
    assert "saved: verified" in out
    assert "frames sent:" in out


def test_example_uses_public_imports_only() -> None:
    tree = ast.parse(EXAMPLE.read_text(encoding="utf-8"))
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
        elif isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
    project = {m for m in modules if m.split(".")[0] in ("openvave", "tests")}
    assert project <= {"openvave", "openvave.protocol"}, project
