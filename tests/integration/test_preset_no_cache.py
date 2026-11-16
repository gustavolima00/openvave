"""``preset dump`` reads the pedal every time; nothing is cached between runs (T050, US3-3)."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable

import pytest

from openvave.cli import main
from openvave.models import DeviceInfo
from openvave.protocol import decode_frame
from openvave.transport import Transport
from openvave.transport.fake import FakeTransport
from tests.support.captures import FW96_CONNECT, PRESET, load_capture
from tests.support.mutations import with_payload

CAP = load_capture(FW96_CONNECT)
ECHO_LEN = 8
KNOB = 6

Factory = Callable[[str | None, float], Awaitable[tuple[Transport, DeviceInfo | None]]]


def factory_for(fake: FakeTransport) -> Factory:
    async def factory(
        device_id: str | None, scan_timeout: float
    ) -> tuple[Transport, DeviceInfo | None]:
        return fake, None

    return factory


def dump(capsys: pytest.CaptureFixture[str], fake: FakeTransport) -> str:
    code = main(["preset", "dump", "--json"], transport_factory=factory_for(fake))
    out, err = capsys.readouterr()
    assert code == 0, err
    data: str = json.loads(out)["preset"]["data"]
    return data


def test_second_run_sees_new_preset_bytes(capsys: pytest.CaptureFixture[str]) -> None:
    original = decode_frame(CAP.rx(PRESET)).body[ECHO_LEN:]
    turned = bytearray(original)
    turned[KNOB] = (turned[KNOB] + 1) % 256
    first = dump(capsys, FakeTransport.from_capture(FW96_CONNECT))
    second = dump(
        capsys,
        FakeTransport.from_capture(
            FW96_CONNECT, replies={PRESET: with_payload(CAP.rx(PRESET), bytes(turned))}
        ),
    )
    assert first == original.hex(" ")
    assert second == bytes(turned).hex(" ")
    assert first != second
