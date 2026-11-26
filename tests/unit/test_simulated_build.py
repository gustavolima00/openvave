"""Building a simulated pedal from one recorded session (spec 008 US1, FR-001–FR-003, FR-008).

Every check talks to the fake through its transport methods only (requests in, replies out).
Request and reply frames come from the committed captures or from the independent fixture
encoders in ``tests/support``.
"""

from __future__ import annotations

import asyncio
import inspect
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pytest

from openvave import FakeTransport
from tests.support import storage_fixture as sf
from tests.support.captures import (
    CAPTURES_DIR,
    DEVICE_INFO,
    FW96_CONNECT,
    GLOBAL,
    PRESET,
    QUERY,
    STATUS,
    load_capture,
)
from tests.support.mutations import with_payload
from tests.support.write_fixture import write_frame

CAP = load_capture(FW96_CONNECT)
FW96 = CAPTURES_DIR / "fw96"
STORAGE_SYNTHETIC = FW96 / "20261117-storage-synthetic.jsonl"
STEP_GAIN = FW96 / "20261116-step-gain.jsonl"
BYPASSED = FW96 / "20261118-gate-bypass_off.jsonl"
KNOB_WRITE = FW96 / "20261117-gate-normal_knob_gain.jsonl"

GLOBAL_ADDR, BUFFER_ADDR, STATUS_ADDR = 0x20000000, 0x10000000, 0xD0000000


class Collector:
    def __init__(self) -> None:
        self.chunks: list[bytes] = []

    def __call__(self, chunk: bytes) -> None:
        self.chunks.append(chunk)


async def ask(fake: FakeTransport, request: bytes) -> bytes:
    """Send one request to an opened fake and return its whole reply."""
    got = Collector()
    fake.on_notify(got)
    if not fake.opened:
        await fake.open()
    await fake.write(request)
    for _ in range(10):
        await asyncio.sleep(0)
    return b"".join(got.chunks)


async def read(fake: FakeTransport, address: int, length: int) -> bytes:
    """The data of a type-4 read."""
    reply = await ask(fake, sf.read_request(address, length))
    assert reply, f"no reply to 0x{address:08x} x{length}"
    return reply[14:-1]


def by_echo(path: Path, address: int, length: int) -> tuple[bytes, list[bytes]]:
    """The request and every reply of a type-4 read, found by its echo (labels differ between
    capture tools)."""
    echo = bytes([4]) + address.to_bytes(4, "little") + length.to_bytes(3, "little")
    cap = load_capture(path)
    for label, (tx, _) in cap.pairs.items():
        if tx[6:14] == echo:
            return tx, cap.rx_all(label)
    raise AssertionError(f"{path.name} has no read of 0x{address:08x} x{length}")


def records(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def derive(
    tmp_path: Path,
    source: Path = FW96_CONNECT,
    *,
    drop: Iterable[str] = (),
    extra: Iterable[tuple[str, bytes, bytes]] = (),
    replace: dict[str, bytes] | None = None,
) -> Path:
    """A temporary capture: ``source`` without the requests labelled ``drop``, with ``replace``d
    replies and ``extra`` ``(label, request, reply)`` pairs appended."""
    dropped = set(drop)
    out = []
    for record in records(source):
        label = " ".join(record.get("label", "").split())
        if label in dropped or record["event"] == "rx-chunk":
            continue
        if record["event"] == "rx" and replace and label in replace:
            record = {**record, "hex": replace[label].hex(" ")}
        out.append(record)
    for label, tx, rx in extra:
        out.append({"event": "tx", "label": label, "hex": tx.hex(" ")})
        out.append({"event": "rx", "label": label, "hex": rx.hex(" ")})
    path = tmp_path / "derived.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in out), encoding="utf-8")
    return path


# -- the starting state -------------------------------------------------------------------------


async def test_answers_the_recorded_handshake_and_reads() -> None:
    fake = FakeTransport.simulated(FW96_CONNECT)
    for label in (QUERY, DEVICE_INFO, GLOBAL, PRESET, STATUS):
        assert await ask(fake, CAP.tx(label)) == CAP.rx(label), label


async def test_generated_image_equals_the_independent_fixture() -> None:
    fake = FakeTransport.simulated(FW96_CONNECT)
    assert await read(fake, 0, 758) == sf.synthetic_image()


async def test_generated_image_stays_inside_byte_map_ranges() -> None:
    from openvave.models import Encoding, Region
    from openvave.protocol import BYTE_MAP

    image = await read(FakeTransport.simulated(FW96_CONNECT), 0, 758)
    presets = [image[2 + 21 * i : 23 + 21 * i] for i in range(36)]
    assert len(set(presets)) == 36
    for entry in BYTE_MAP:
        if entry.region is not Region.CURRENT_PRESET or entry.encoding is Encoding.UNKNOWN:
            continue
        for preset in presets:
            value = preset[entry.offset]
            if entry.encoding is Encoding.SWITCH:
                assert value in (entry.on_value, entry.off_value)
            elif entry.min is not None and entry.max is not None:
                assert entry.min <= value <= entry.max


def test_storage_only_capture_names_the_missing_global_read() -> None:
    with pytest.raises(ValueError, match="global"):
        FakeTransport.simulated(STORAGE_SYNTHETIC)


async def test_recorded_whole_image_is_used(tmp_path: Path) -> None:
    image = bytes.fromhex("12 34") + bytes(range(21)) * 36
    path = derive(tmp_path, extra=[("img", sf.read_request(0, 758), sf.read_reply(0, image))])
    assert await read(FakeTransport.simulated(path), 0, 758) == image


async def test_image_argument_wins(tmp_path: Path) -> None:
    recorded = bytes(758)
    given = bytes([7]) * 758
    path = derive(tmp_path, extra=[("img", sf.read_request(0, 758), sf.read_reply(0, recorded))])
    assert await read(FakeTransport.simulated(path, image=given), 0, 758) == given
    assert await read(FakeTransport.simulated(FW96_CONNECT, image=given), 0, 758) == given


@pytest.mark.parametrize("size", [0, 757, 759])
def test_image_of_the_wrong_size(size: int) -> None:
    with pytest.raises(ValueError, match="758"):
        FakeTransport.simulated(FW96_CONNECT, image=bytes(size))


async def test_without_status_read_loopback_starts_off(tmp_path: Path) -> None:
    fake = FakeTransport.simulated(derive(tmp_path, drop=[STATUS]))
    assert await read(fake, STATUS_ADDR, 1) == b"\x00"


async def test_watch_capture_starts_from_the_first_reply_of_each() -> None:
    glob_tx, glob_rx = by_echo(STEP_GAIN, GLOBAL_ADDR, 4)
    preset_tx, preset_rx = by_echo(STEP_GAIN, BUFFER_ADDR, 21)
    assert len(set(preset_rx)) > 1, "the watch record changes the preset"
    fake = FakeTransport.simulated(STEP_GAIN)
    assert await ask(fake, glob_tx) == glob_rx[0]
    assert await ask(fake, preset_tx) == preset_rx[0]
    # a second read still answers the starting state: nothing replays the watch record
    assert await ask(fake, preset_tx) == preset_rx[0]


async def test_edit_mode_capture_stores_the_buffer_at_the_loaded_position() -> None:
    glob = by_echo(STEP_GAIN, GLOBAL_ADDR, 4)[1][0][14:-1]
    assert glob[3] == 0, "the step captures are recorded in edit mode"
    buffer = by_echo(STEP_GAIN, BUFFER_ADDR, 21)[1][0][14:-1]
    index = glob[1] * 4 + glob[2]
    fake = FakeTransport.simulated(STEP_GAIN)
    assert await read(fake, 2 + 21 * index, 21) == buffer


def test_bypassed_capture_is_refused() -> None:
    with pytest.raises(ValueError, match="preset"):
        FakeTransport.simulated(BYPASSED)


def test_capture_without_the_query(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="handshake"):
        FakeTransport.simulated(derive(tmp_path, drop=[QUERY]))


def test_capture_without_the_preset_read(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="current preset"):
        FakeTransport.simulated(derive(tmp_path, drop=[PRESET]))


def test_capture_whose_recorded_state_is_unrecognised(tmp_path: Path) -> None:
    other = with_payload(CAP.rx(GLOBAL), bytes([0, 0, 1, 7]))  # mode 7: no such mode
    with pytest.raises(ValueError, match="preset"):
        FakeTransport.simulated(derive(tmp_path, replace={GLOBAL: other}))


async def test_recorded_writes_and_slot_reads_are_not_replayed() -> None:
    cap = load_capture(KNOB_WRITE)
    write = cap.tx("write knob_block t4 0x10000004 x14")
    first = cap.rx_all(PRESET)[0][14:-1]
    fake = FakeTransport.simulated(KNOB_WRITE)
    assert await read(fake, BUFFER_ADDR, 21) == first
    # the recorded stored-slot read is not scripted: the stored image answers
    image = await read(fake, 0, 758)
    assert await read(fake, 0x17, 21) == image[0x17 : 0x17 + 21]
    # the recorded write is applied to memory, not answered from the record
    await ask(fake, write)
    assert await read(fake, BUFFER_ADDR, 21) == first[:4] + write[14:-1] + first[18:]


async def test_unscripted_write_is_applied() -> None:
    fake = FakeTransport.simulated(FW96_CONNECT)
    await ask(fake, write_frame(BUFFER_ADDR + 18, bytes([1, 2, 3])))
    assert (await read(fake, BUFFER_ADDR, 21))[18:] == bytes([1, 2, 3])


@pytest.mark.parametrize(
    "faults", [{"erase": "nak"}, {"knob_block": "explode"}], ids=["kind", "action"]
)
def test_unknown_fault(faults: dict[str, str]) -> None:
    with pytest.raises(ValueError):
        FakeTransport.simulated(FW96_CONNECT, faults=faults)


def test_options_keep_their_meaning() -> None:
    with pytest.raises(ValueError):
        FakeTransport.simulated(FW96_CONNECT, chunk_size=0)


def test_existing_signatures_unchanged() -> None:
    assert str(inspect.signature(FakeTransport.__init__)) == (
        "(self, script: 'Mapping[str, tuple[bytes, Replies]]', *, split: 'int | None' = None, "
        "drop: 'Mapping[str, int] | None' = None, disconnect_after: 'int | None' = None, "
        "replies: 'Mapping[str, Replies] | None' = None, memory: 'Mapping[int, bytes] | None' = "
        "None, chunk_size: 'int | None' = None, apply_writes: 'bool' = False, select_transient: "
        "'int' = 0, faults: 'Mapping[str, str] | None' = None) -> 'None'"
    )
    assert str(inspect.signature(FakeTransport.from_capture)) == (
        "(path: 'str | Path', *, split: 'int | None' = None, drop: 'Mapping[str, int] | None' = "
        "None, disconnect_after: 'int | None' = None, replies: 'Mapping[str, Replies] | None' = "
        "None, memory: 'Mapping[int, bytes] | None' = None, chunk_size: 'int | None' = None, "
        "apply_writes: 'bool' = False, select_transient: 'int' = 0, faults: 'Mapping[str, str] | "
        "None' = None) -> 'FakeTransport'"
    )


def test_simulated_signature() -> None:
    params = inspect.signature(FakeTransport.simulated).parameters
    assert list(params) == ["path", "image", "faults", "select_transient", "chunk_size"]
    assert all(p.kind is inspect.Parameter.KEYWORD_ONLY for p in list(params.values())[1:])
