"""The suite never touches the developer's own known-pedals file (spec 005 T002, R13)."""

from __future__ import annotations

import os
from pathlib import Path


def test_config_points_into_tmp_path(tmp_path: Path) -> None:
    config = Path(os.environ["OPENVAVE_CONFIG"])
    assert config.is_relative_to(tmp_path)
    assert not config.exists()


def test_device_environment_is_unset() -> None:
    assert "OPENVAVE_DEVICE" not in os.environ
