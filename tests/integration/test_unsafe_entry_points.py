"""No entry point sends a persistent write without ``unsafe`` (spec 004 SC-005, FR-033, T050).

This module is **not** marked ``persistent_writes``: any stored-slot, commit or image frame sent
here fails the whole test session (``tests/conftest.py``), on top of the asserts below.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from openvave import TankG, WriteRefusedError
from openvave.cli import COMMANDS, main
from tests.contract.test_cli_set import factory_for
from tests.support import restore_fixture as rf
from tests.support import storage_fixture as sf
from tests.support.audit import persistent_write
from tests.support.write_fixture import NORMAL, make_fake

GAIN_90 = sf.PUBLIC_PRESET[:6] + bytes([90]) + sf.PUBLIC_PRESET[7:]
UNSAFE_METHODS = {"plan_save", "save_preset", "plan_restore", "restore"}


async def no_sleep(_: float) -> None:
    return None


def public_methods() -> dict[str, object]:
    return {
        name: member
        for name, member in inspect.getmembers(TankG, inspect.isfunction)
        if not name.startswith("_")
    }


def test_only_save_and_restore_take_unsafe() -> None:
    taking = {
        name
        for name, fn in public_methods().items()
        if "unsafe" in inspect.signature(fn).parameters  # type: ignore[arg-type]
    }
    assert taking == UNSAFE_METHODS
    for name in UNSAFE_METHODS:
        parameter = inspect.signature(getattr(TankG, name)).parameters["unsafe"]
        assert parameter.default is False
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY


async def test_save_without_unsafe_sends_reads_only() -> None:
    fake = make_fake(NORMAL, buffer=GAIN_90)
    async with TankG.over(fake) as pedal:
        for kwargs in ({}, {"experimental": True}, {"to": 2, "experimental": True}):
            with pytest.raises(WriteRefusedError) as err:
                await pedal.save_preset(on_backup=lambda b: None, sleep=no_sleep, **kwargs)  # type: ignore[arg-type]
            assert err.value.reason == "unsafe_required"
    assert {f[2] for f in fake.sent} <= {0x11, 0x23}


async def test_restore_without_unsafe_sends_reads_only() -> None:
    fake = make_fake(NORMAL, image=rf.image_with(s2=GAIN_90))
    backup = rf.backup()
    async with TankG.over(fake) as pedal:
        for kwargs in ({"all": True}, {"slot": 2}, {"all": True, "discard_edits": True}):
            with pytest.raises(WriteRefusedError) as err:
                await pedal.restore(
                    backup,
                    experimental=True,
                    on_backup=lambda b: None,
                    sleep=no_sleep,
                    **kwargs,  # type: ignore[arg-type]
                )
            assert err.value.reason == "unsafe_required"
    assert {f[2] for f in fake.sent} <= {0x11, 0x23}


async def test_every_other_write_action_sends_no_persistent_frame() -> None:
    fake = make_fake(NORMAL, buffer=GAIN_90, status=b"\x01")
    async with TankG.over(fake) as pedal:
        await pedal.set_field("treble", 70, sleep=no_sleep)
        await pedal.reload_preset(sleep=no_sleep)
        await pedal.select_preset(5, sleep=no_sleep)
        await pedal.bypass_on(experimental=True, sleep=no_sleep)
        await pedal.bypass_off(5, sleep=no_sleep)
        await pedal.set_loopback(False, experimental=True, sleep=no_sleep)
        for name in ("plan_save", "plan_restore"):
            assert name in public_methods()
        await pedal.plan_save(to=2)
        await pedal.plan_restore(rf.backup(), all=True)
    assert not any(persistent_write(f) for f in fake.sent)


@pytest.mark.parametrize(
    "argv",
    [
        ["preset", "save"],
        ["preset", "save", "--experimental"],
        ["preset", "save", "--to", "1C", "--experimental"],
        ["preset", "restore", "{backup}", "--all", "--experimental"],
        ["preset", "restore", "{backup}", "--slot", "1C", "--experimental", "--discard-edits"],
    ],
)
def test_cli_without_unsafe_exit_1_reads_only(
    argv: list[str], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "b.json"
    source.write_text(json.dumps(rf.document()), encoding="utf-8")
    if argv[1] == "save":  # unsaved gain 90 on 1B: a save would change 1B or 1C
        fake = make_fake(NORMAL, buffer=GAIN_90)
    else:  # no unsaved edits; stored 1C differs from the file
        fake = make_fake(NORMAL, image=rf.image_with(s2=GAIN_90))
    args = [a.replace("{backup}", str(source)) for a in argv]
    code = main([*args, "--backup-dir", str(tmp_path)], transport_factory=factory_for(fake))
    _, err = capsys.readouterr()
    assert code == 1, err
    assert "unsafe_required" in err
    assert {f[2] for f in fake.sent} <= {0x11, 0x23}
    assert list(tmp_path.glob("tankg-backup-*")) == []


def test_cli_commands_are_known() -> None:
    # a new top-level command must be added to the checks above
    assert set(COMMANDS) == {"info", "preset", "set", "bypass", "loopback"}
