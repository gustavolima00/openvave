"""SC-003: whatever opt-ins the assistant passes to a volatile write tool, the pedal never
receives a persistent write, and never a message not yet confirmed unless ``experimental``."""

from __future__ import annotations

from typing import Any

import pytest

from openvave import session
from openvave.protocol.writes import _SHAPES, message_for
from tests.mcp.conftest import CountingFactory, open_harness, options
from tests.support.audit import persistent_violation
from tests.support.write_fixture import EDIT, NORMAL, make_fake, writes

BYPASSED = bytes([0, 0, 0xFF, NORMAL])

CALLS: list[tuple[str, dict[str, Any]]] = [
    ("pedal_set", {"changes": {"gain": 90, "delay_on": "on", "led_colour": "#2040ff"}}),
    ("pedal_set", {"changes": {"mod_fx": "phaser:2", "reverb_decay": 18}}),
    ("preset_select", {"position": "3D"}),
    ("preset_reload", {}),
    ("bypass_on", {}),
    ("bypass_off", {"position": "1B"}),
    ("loopback", {"on": True}),
]
OPT_INS: list[dict[str, Any]] = [{}, {"experimental": True}, {"discard_edits": True}]
STATES = {
    "normal": lambda: make_fake(NORMAL, status=b"\x00"),
    "edit": lambda: make_fake(EDIT, status=b"\x00"),
    "bypass": lambda: make_fake(NORMAL, buffer=bytes(21), glob=BYPASSED, status=b"\x00"),
}
ACCEPTS_DISCARD = {"preset_select", "preset_reload", "bypass_on"}


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    async def instant(_: float) -> None:
        return None

    monkeypatch.setattr(session, "SELECT_SLEEP", instant)


def confirmed(frame: bytes) -> bool:
    """Whether a ``0x22`` write frame's message is ``confirmed`` in the protocol docs."""
    body = frame[6:-1]
    shape = (body[0], int.from_bytes(body[1:5], "little"), int.from_bytes(body[5:8], "little"))
    kind, argument = _SHAPES[shape]
    return message_for(kind, argument).confidence == "confirmed"


@pytest.mark.parametrize("state", sorted(STATES))
@pytest.mark.parametrize("opt_in", OPT_INS, ids=["none", "experimental", "discard_edits"])
@pytest.mark.parametrize(("tool", "args"), CALLS, ids=[f"{t}{i}" for i, (t, _) in enumerate(CALLS)])
async def test_no_persistent_or_unconfirmed_write(tmp_path, state, opt_in, tool, args) -> None:
    if "discard_edits" in opt_in and tool not in ACCEPTS_DISCARD:
        pytest.skip(f"{tool} takes no discard_edits")
    factory = CountingFactory(make=STATES[state])
    async with open_harness(options(tmp_path), factory) as h:
        await h.call(tool, {**args, **opt_in})
    sent = [frame for fake in factory.fakes for frame in writes(fake)]
    assert not [f for f in sent if persistent_violation(f, False)]
    if not opt_in.get("experimental"):
        assert all(confirmed(f) for f in sent), [f.hex(" ") for f in sent]
