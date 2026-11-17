"""Hardware write tests are double opt-in: ``--hardware`` and ``OPENVAVE_HW_WRITES=1`` (T042)."""

from __future__ import annotations

import os

import pytest

from tests.hardware import test_hw_writes as hw


def _marks(name: str) -> list[pytest.Mark]:
    return [m.mark if hasattr(m, "mark") else m for m in hw.pytestmark if _name(m) == name]


def _name(mark: object) -> str:
    return getattr(getattr(mark, "mark", mark), "name", "")


def test_write_module_needs_hardware_flag() -> None:
    assert _marks("hardware")


def test_write_module_needs_env_flag() -> None:
    skips = _marks("skipif")
    assert len(skips) == 1
    condition = skips[0].args[0]
    assert condition is (os.environ.get("OPENVAVE_HW_WRITES") != "1")


def test_confirmation_requires_the_exact_word(capsys: pytest.CaptureFixture[str]) -> None:
    assert hw.confirmed("?", lambda: "send\n") is True
    for answer in ("", "\n", "yes\n", "Send\n", "send it\n"):
        assert hw.confirmed("?", lambda a=answer: a) is False
    capsys.readouterr()


def test_env_flag_unset_in_ci() -> None:
    # The default suite must never be able to collect the write gate as runnable.
    if os.environ.get("OPENVAVE_HW_WRITES") == "1":
        pytest.skip("OPENVAVE_HW_WRITES=1 is set in this shell")
    assert _marks("skipif")[0].args[0] is True
