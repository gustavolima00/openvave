"""Turn the ``--trace`` output of one gate write into a committed excerpt (spec 003 M2/M3).

The CLI's ``--trace`` writes ``TX <hex>``, ``RX chunk <hex>`` and ``RX <hex>`` lines to stderr
(``openvave.trace``). For a gate step the owner keeps that stderr in ``captures/private/``; this
tool turns it into ``captures/fw96/<date>-gate-<step>.jsonl``: a ``meta`` line (firmware, date,
step, the library call to replay) and labelled ``tx``/``rx-chunk``/``rx`` lines that replay with
``FakeTransport.from_capture``. Labels are derived from the frames only (command, type, address,
length), never from ``openvave`` code, so a decoding bug cannot hide in the fixture. Frames are
copied unchanged; every other stderr line (warnings, the CLI's own messages) is dropped.

Spec 004 (M3) adds the sequences: bypass, loopback, save, restore and the no-op image write.
Their traces carry the owner's stored presets (the automatic backup reads all 36 slots and the
whole image), so :func:`sanitise` replaces every preset value that is not already public in
``captures/fw96/`` (FR-037) with a synthetic preset of ``storage_fixture``, in reads and writes
alike, recomputing checksums and re-chunking the notifications. The substitution is one fixed
map per excerpt (same real value → same synthetic value), so every comparison the library makes
during the replay (slot read-back, buffer = stored, image = file) comes out as it did on the
pedal. :func:`build` refuses to emit an excerpt in which :func:`leaks` still finds a value that
is neither public nor synthetic. The input may also be the JSONL frame log of
``tests/hardware/test_hw_persistent.py`` (one ``{"event", "hex"}`` object per line).

Usage (raw traces stay in ``captures/private/``, git-ignored)::

    uv run python -m tests.support.gate_excerpt TRACE STEP DATE OUT CALL...

    CALL: set FIELD VALUE                    # e.g. set gain 90 / set mod_on true
          select POS [--discard-edits]       # POS: 0-35 or 1A-9D
          bypass_on [--discard-edits] | bypass_off POS | loopback on|off
          save [POS] | restore_slot POS [--discard-edits] | restore_all [--discard-edits]
          image_noop

The replayed call always passes ``experimental=True`` (gate session A sends ``hypothesis`` rows)
and, for the persistent calls, ``unsafe=True``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from tests.support import storage_fixture as sf
from tests.support.captures import CAPTURES_DIR

QUERY, READ, WRITE, REPLY = 0x11, 0x23, 0x22, 0x00
GLOBAL, EDIT_BUFFER, DEVICE, SELECT_BASE = 0x20000000, 0x10000000, 0xD0000000, 0xE0000000
STORE_END = 0x2F6
"""Stored image: header at 0 (2 bytes), 36 presets of 21 bytes from offset 2."""
PRESET_SIZE = 21
PRESET_COUNT = 36
IMAGE_SIZE = 2 + PRESET_SIZE * PRESET_COUNT
BYPASS_BASE, COMMIT = 0xE1000000, 0xF0000000
FW96 = CAPTURES_DIR / "fw96"
SYNTHETIC_POOL = 128
"""Synthetic replacements are ``storage_fixture.synthetic_preset(k)`` for ``k < 128``."""
TOOL = "tests/support/gate_excerpt.py"


def position(index: int) -> str:
    bank, slot = divmod(index, 4)
    return f"{bank + 1}{'ABCD'[slot]}"


def _shape(frame: bytes) -> tuple[int, int, int]:
    body = frame[6:-1]
    return body[0], int.from_bytes(body[1:5], "little"), int.from_bytes(body[5:8], "little")


def _slot(address: int, length: int) -> int | None:
    """Stored-preset index of a 21-byte access at ``address``, else ``None``."""
    if length != PRESET_SIZE or not 2 <= address < STORE_END:
        return None
    index, rest = divmod(address - 2, PRESET_SIZE)
    return index if rest == 0 else None


def label(frame: bytes) -> str:
    """A label for a request frame, from its bytes alone."""
    command = frame[2]
    if command == QUERY:
        return "query name/version"
    if command not in (READ, WRITE) or len(frame) < 15:
        return f"cmd 0x{command:02x} {frame.hex(' ')}"
    kind, address, length = _shape(frame)
    where = f"t{kind} 0x{address:08X} x{length}"
    if command == WRITE:
        if address == COMMIT:
            return f"write commit {where}"
        if BYPASS_BASE <= address < BYPASS_BASE + PRESET_COUNT:
            return f"write bypass {position(address - BYPASS_BASE)} {where}"
        if address == DEVICE:
            return f"write loopback {where}"
        if address == 0 and length == IMAGE_SIZE:
            return f"write stored_image {where}"
        if _slot(address, length) is not None:
            return f"write stored_slot {position(_slot(address, length) or 0)} {where}"
        if address >= SELECT_BASE:
            return f"write preset_select {position(address - SELECT_BASE)} {where}"
        if address == EDIT_BUFFER + 4:
            return f"write knob_block {where}"
        if address == EDIT_BUFFER + 18:
            return f"write led_colour {where}"
        if EDIT_BUFFER <= address < EDIT_BUFFER + 4:
            return f"write block_switch {address - EDIT_BUFFER} {where}"
        return f"write {where}"
    if address == GLOBAL:
        return f"global {where}"
    if address == EDIT_BUFFER:
        return f"preset {where}"
    if address == DEVICE and kind == 4 and length == 1:
        return f"status {where}"
    if address == DEVICE:
        return f"device {where}"
    if address == 0 and length == IMAGE_SIZE:
        return f"storage image {where}"
    if address == 0 and length == 2:
        return f"storage header {where}"
    if address < STORE_END and length == PRESET_SIZE and (address - 2) % PRESET_SIZE == 0:
        return f"stored preset {position((address - 2) // PRESET_SIZE)} {where}"
    return f"read {where}"


def parse_trace(text: str) -> list[tuple[str, bytes]]:
    """``(kind, frame)`` for every ``TX``/``RX chunk``/``RX`` line, in order."""
    out: list[tuple[str, bytes]] = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("{"):  # the frame log of tests/hardware/test_hw_persistent.py
            record = json.loads(line)
            if record.get("event") in ("tx", "rx-chunk", "rx", "rx-stray"):
                out.append((record["event"], bytes.fromhex(record["hex"])))
            continue
        for prefix, kind in (("RX chunk ", "rx-chunk"), ("RX stray ", "rx-stray"), ("TX ", "tx")):
            if line.startswith(prefix):
                out.append((kind, bytes.fromhex(line[len(prefix) :])))
                break
        else:
            if line.startswith("RX "):
                out.append(("rx", bytes.fromhex(line[3:])))
    return out


def records(frames: list[tuple[str, bytes]]) -> list[dict[str, Any]]:
    """Labelled JSONL records. A reply belongs to the request before it (the session is serial)."""
    out: list[dict[str, Any]] = []
    pending: str | None = None
    for kind, frame in frames:
        if kind == "tx":
            pending = label(frame)
            out.append({"event": "tx", "label": pending, "hex": frame.hex(" ")})
        elif kind == "rx-chunk":
            out.append({"event": "rx-chunk", "hex": frame.hex(" ")})
        elif kind == "rx":
            if pending is None:
                raise ValueError(f"reply before any request: {frame.hex(' ')}")
            out.append({"event": "rx", "label": pending, "hex": frame.hex(" "), "cmd": frame[2]})
            pending = None
        else:  # rx-stray: kept as a note, never replayed
            out.append({"event": "rx-stray", "hex": frame.hex(" ")})
    return out


def public_presets(directory: Path = FW96, exclude: str | None = None) -> frozenset[bytes]:
    """Every edit-buffer value in the committed captures of ``directory`` (not the synthetic one).

    These preset values are already public (FR-037). Gate excerpts count too, except the file
    named ``exclude`` (the one being checked): a committed excerpt passed :func:`leaks`, so its
    buffers are public, synthetic, or public plus an edit it records (spec 004 M3: the LED step
    starts from the buffer the MOD step left). Anything else that looks like a stored preset
    must not reach a committed excerpt unless it is synthetic.
    """
    out: set[bytes] = set()
    for path in sorted(directory.glob("*.jsonl")):
        if "synthetic" in path.name or path.name == exclude:
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            if r.get("event") != "rx":
                continue
            frame = bytes.fromhex(r["hex"])
            if frame[2] == READ and frame[6:14] == bytes.fromhex("04 00 00 00 10 15 00 00"):
                out.add(frame[14:-1])
    return frozenset(out)


def _presets(image: bytes) -> list[bytes]:
    return [image[2 + PRESET_SIZE * i : 2 + PRESET_SIZE * (i + 1)] for i in range(PRESET_COUNT)]


SYNTHETIC = frozenset(sf.synthetic_preset(k) for k in range(SYNTHETIC_POOL))


class PresetMap:
    """One fixed, injective replacement of non-public preset values (see the module docstring).

    A value first seen in slot ``i`` becomes ``synthetic_preset(i)`` when that is free, else the
    next free ``synthetic_preset(k)`` from ``k = 36``. Public and synthetic values map to
    themselves; ``taken`` (every preset value in the trace) is never used as a replacement.
    """

    def __init__(self, public: frozenset[bytes], taken: frozenset[bytes] = frozenset()) -> None:
        self.public = set(public | SYNTHETIC)
        """Values kept as they are: public, synthetic, or public plus the step's own edit."""
        self.replaced: dict[bytes, bytes] = {}
        self._used: set[bytes] = set(taken)
        self._next = PRESET_COUNT

    def __call__(self, value: bytes, slot: int | None = None) -> bytes:
        if value in self.public:
            return value
        if value in self.replaced:
            return self.replaced[value]
        candidate = sf.synthetic_preset(slot) if slot is not None else None
        while candidate is None or candidate in self._used:
            if self._next >= SYNTHETIC_POOL:
                raise ValueError("too many private preset values in one trace")
            candidate = sf.synthetic_preset(self._next)
            self._next += 1
        self.replaced[value] = candidate
        self._used.add(candidate)
        return candidate

    def image(self, image: bytes) -> bytes:
        return image[:2] + b"".join(self(data, i) for i, data in enumerate(_presets(image)))


def _field_write(frame: bytes) -> tuple[int, bytes] | None:
    """``(offset, data)`` of a write into the edit buffer (knob block, switch, LED colour)."""
    if len(frame) < 15 or frame[2] != WRITE or frame[6] != 4:
        return None
    _, address, length = _shape(frame)
    if not EDIT_BUFFER <= address < EDIT_BUFFER + PRESET_SIZE or length == PRESET_SIZE:
        return None
    return address - EDIT_BUFFER, frame[14:-1]


def _applied(buffer: bytes, write: tuple[int, bytes]) -> bytes:
    offset, data = write
    return buffer[:offset] + data + buffer[offset + len(data) :]


def _with_data(frame: bytes, data: bytes) -> bytes:
    """``frame`` with its data (after the 8-byte type/address/length echo) replaced."""
    return sf.frame(frame[2], frame[6:14] + data)


def _preset_data(frame: bytes, request: bool) -> tuple[str, int | None] | None:
    """What preset data ``frame`` carries: ``("buffer"|"slot"|"image", slot)`` or ``None``."""
    if len(frame) < 15 or frame[2] != (WRITE if request else READ) or frame[6] != 4:
        return None
    _, address, length = _shape(frame)
    if len(frame) != 15 + length:
        return None  # a read request (no data) or a malformed frame
    if address == EDIT_BUFFER and length == PRESET_SIZE and not request:
        return "buffer", None
    if address == 0 and length == IMAGE_SIZE:
        return "image", None
    slot = _slot(address, length)
    return ("slot", slot) if slot is not None else None


def sanitise(
    frames: list[tuple[str, bytes]], public: frozenset[bytes]
) -> tuple[list[tuple[str, bytes]], PresetMap]:
    """Replace non-public preset values in reads and writes (FR-037), keeping the replay valid.

    Edit-buffer replies, stored-slot reads and writes, and whole-image reads and writes go
    through one :class:`PresetMap`; checksums are recomputed and a replaced reply's
    notifications are cut again at the original chunk lengths. Raises :class:`ValueError` when
    a field write (knob block, switch, LED colour) follows a replaced edit buffer: its bytes
    would no longer match the buffer.
    """
    taken: set[bytes] = set()
    for kind, frame in frames:
        found = _preset_data(frame, request=kind == "tx") if kind in ("tx", "rx") else None
        if found is not None:
            data = frame[14:-1]
            taken.update(_presets(data) if found[0] == "image" else [data])
    mapping = PresetMap(public, frozenset(taken))
    out: list[tuple[str, bytes]] = []
    chunks: list[int] = []  # indexes in ``out`` of the notifications of the pending reply
    buffer: bytes | None = None  # last edit-buffer value, ``None`` once one was replaced
    for kind, frame in frames:
        new = frame
        if kind == "rx-chunk":
            chunks.append(len(out))
        elif kind in ("tx", "rx"):
            found = _preset_data(frame, request=kind == "tx")
            data = frame[14:-1]
            field = _field_write(frame) if kind == "tx" else None
            if found is not None:
                what, slot = found
                new = _with_data(
                    frame, mapping.image(data) if what == "image" else mapping(data, slot)
                )
                if what == "buffer":
                    buffer = data if new == frame else None
            elif field is not None:
                if buffer is None:
                    raise ValueError(f"field write without a public edit buffer: {label(frame)}")
                buffer = _applied(buffer, field)
                mapping.public.add(buffer)  # public bytes plus this step's own edit
            if kind == "rx":
                if new != frame:
                    cut = 0
                    for i in chunks:
                        size = len(out[i][1])
                        out[i] = ("rx-chunk", new[cut : cut + size])
                        cut += size
                    if chunks and cut != len(new):
                        raise ValueError("notifications do not add up to the reply")
                chunks = []
        out.append((kind, new))
    return out, mapping


def leaks(lines: list[dict[str, Any]], public: frozenset[bytes]) -> list[str]:
    """Preset values in ``lines`` that are neither public nor synthetic (empty if none).

    An edit-buffer value that an allowed buffer becomes through a field write in the same
    excerpt is allowed too: it holds public bytes plus the step's own edit, no stored content.
    """
    allowed = set(public | SYNTHETIC)
    found: list[str] = []
    buffer: bytes | None = None
    for r in lines:
        if r.get("event") not in ("tx", "rx"):
            continue
        frame = bytes.fromhex(r["hex"])
        what = _preset_data(frame, request=r["event"] == "tx")
        field = _field_write(frame) if r["event"] == "tx" else None
        if field is not None and buffer is not None:
            buffer = _applied(buffer, field)
            allowed.add(buffer)  # an allowed buffer plus the step's own edit
        if what is None:
            continue
        data = frame[14:-1]
        if what[0] == "buffer":
            buffer = data if data in allowed else None
        values = _presets(data) if what[0] == "image" else [data]
        if any(v not in allowed for v in values):
            found.append(f"{r['event']} {r['label']}")
    return found


def parse_index(text: str) -> int:
    """``"2"`` or ``"1C"`` → 2."""
    if text.isdigit():
        index = int(text)
    else:
        bank, slot = text[:-1], text[-1:].upper()
        if not bank.isdigit() or slot not in "ABCD" or not slot:
            raise ValueError(f"bad position {text!r}")
        index = (int(bank) - 1) * 4 + "ABCD".index(slot)
    if not 0 <= index < PRESET_COUNT:
        raise ValueError(f"position {text!r} outside 0-35")
    return index


def _flags(rest: list[str]) -> bool:
    if rest not in ([], ["--discard-edits"]):
        raise ValueError(f"unknown option(s) {rest!r}")
    return rest == ["--discard-edits"]


USAGE = (
    "expected `set FIELD VALUE`, `select POS [--discard-edits]`, `bypass_on [--discard-edits]`, "
    "`bypass_off POS`, `loopback on|off`, `save [POS]`, `restore_slot POS [--discard-edits]`, "
    "`restore_all [--discard-edits]` or `image_noop`"
)


def parse_call(args: list[str]) -> dict[str, Any]:
    """The library call to replay, from the tool's CALL arguments (see the module docstring)."""
    verb, rest = (args[0], args[1:]) if args else ("", [])
    persistent = {"experimental": True, "unsafe": True}
    if verb == "set" and len(rest) == 2:
        value: Any = rest[1]
        if value.lower() in ("true", "false", "on", "off"):
            value = value.lower() in ("true", "on")
        elif value.lstrip("-").isdigit():
            value = int(value)
        return {"call": "set_field", "field": rest[0], "value": value, "experimental": True}
    if verb == "select" and len(rest) in (1, 2):
        return {
            "call": "select_preset",
            "index": parse_index(rest[0]),
            "discard_edits": _flags(rest[1:]),
            "experimental": True,
        }
    if verb == "bypass_on":
        return {"call": "bypass_on", "discard_edits": _flags(rest), "experimental": True}
    if verb == "bypass_off" and len(rest) == 1:
        return {"call": "bypass_off", "index": parse_index(rest[0]), "experimental": True}
    if verb == "loopback" and rest in (["on"], ["off"]):
        return {"call": "set_loopback", "on": rest == ["on"], "experimental": True}
    if verb == "save" and len(rest) <= 1:
        return {"call": "save_preset", "to": parse_index(rest[0]) if rest else None, **persistent}
    if verb == "restore_slot" and len(rest) in (1, 2):
        return {
            "call": "restore",
            "slot": parse_index(rest[0]),
            "discard_edits": _flags(rest[1:]),
            **persistent,
        }
    if verb == "restore_all":
        return {"call": "restore", "all": True, "discard_edits": _flags(rest), **persistent}
    if verb == "image_noop" and not rest:
        return {"call": "image_noop", **persistent}
    raise ValueError(USAGE)


def build(
    text: str,
    step: str,
    date: str,
    call: dict[str, Any],
    public: frozenset[bytes] | None = None,
) -> list[dict[str, Any]]:
    """The excerpt lines: meta, then the sanitised, labelled frames.

    ``public`` defaults to :func:`public_presets` of ``captures/fw96/``. Raises
    :class:`ValueError` if a non-public preset value would remain (FR-037).
    """
    public = (
        public_presets(exclude=f"{date.replace('-', '')}-gate-{step}.jsonl")
        if public is None
        else public
    )
    frames, mapping = sanitise(parse_trace(text), public)
    body = records(frames)
    query = next((r for r in body if r["event"] == "rx" and r["cmd"] == QUERY), None)
    if query is None:
        raise ValueError("no handshake reply in the trace")
    name = bytes.fromhex(query["hex"])[6:-1].split(b"\x00", 1)[0].decode("ascii")
    model, _, fw = name.rpartition("_")
    sanitized = []
    if mapping.replaced:
        sanitized.append(
            f"{len(mapping.replaced)} preset value(s) not public in captures/fw96 replaced by "
            "tests/support/storage_fixture.synthetic_preset values (FR-037)"
        )
    meta = {
        "event": "meta",
        "firmware": int(fw),
        "device": model,
        "date": date,
        "step": step,
        "tool": TOOL,
        "sanitized": sanitized,
        "replay": call,
    }
    lines = [meta, *body]
    leaked = leaks(lines, public)
    if leaked:
        raise ValueError("refusing to emit non-public preset data: " + ", ".join(leaked))
    return lines


def write(lines: list[dict[str, Any]], out: Path) -> None:
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in lines), "utf-8")


def main(argv: list[str]) -> int:
    if len(argv) < 5:
        print(__doc__, file=sys.stderr)
        return 2
    trace, step, date, out = Path(argv[0]), argv[1], argv[2], Path(argv[3])
    lines = build(trace.read_text(encoding="utf-8"), step, date, parse_call(argv[4:]))
    write(lines, out)
    writes = [r for r in lines if r.get("event") == "tx" and r["label"].startswith("write")]
    print(f"{out}: {len(lines)} lines, {len(writes)} write frame(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
