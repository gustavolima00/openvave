"""Index of committed step excerpts: which byte map field each one evidences (T035, FR-020).

``single`` steps moved one control only: every cycle-to-cycle change in the excerpt is on that
field's byte. ``reaches`` is the exact (min, max) of the field's raw value over the excerpt.
Selection steps (``single=False``) change a preset and its stored bytes together; they evidence
the global bank/slot fields and are checked separately.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tests.support.captures import CAPTURES_DIR

FW96 = CAPTURES_DIR / "fw96"


@dataclass(frozen=True)
class FixturePair:
    region: str
    """``global``, ``preset`` or ``status`` (record names)."""
    name: str
    """Byte map name."""
    file: str
    """Excerpt file name under ``captures/fw96/``."""
    reaches: tuple[int, int] | None = None
    """Exact (min, max) of the raw value over the excerpt, when it is a sweep."""
    single: bool = True
    gate: bool = False
    """A gate excerpt (one openvave write, then re-reads; record labels ``preset t4 0x10000000
    x21`` …) rather than a ``watch`` step (labels ``preset`` …). Spec 007: fields no pedal control
    moves (LED colour, loopback) are evidenced by openvave's own write and its re-read."""
    moves: tuple[int, ...] = ()
    """Other offsets allowed to move in the same step (the LED colour's three bytes move in one
    write); empty = only the field's own byte."""

    @property
    def path(self) -> Path:
        return FW96 / self.file

    @property
    def id(self) -> str:
        return f"{self.region}.{self.name}:{self.file}"


def _step(
    region: str, name: str, field: str, reaches: tuple[int, int] | None = None
) -> FixturePair:
    return FixturePair(region, name, f"20261116-step-{field}.jsonl", reaches)


def _gate(region: str, name: str, file: str, moves: tuple[int, ...] = ()) -> FixturePair:
    return FixturePair(region, name, file, gate=True, moves=moves)


_LED = (18, 19, 20)
_LED_STEPS = (
    "20261118-gate-normal_led_colour.jsonl",  # spec 004 session A: ff 00 00, LED turned red
    "20261119-gate-led_colour_c.jsonl",  # spec 007 session C: 00 ff 00, LED turned green
)
_LOOPBACK_STEPS = (
    "20261118-gate-loopback_off.jsonl",  # spec 004 session A
    "20261118-gate-loopback_on.jsonl",
    "20261119-gate-loopback_on_c.jsonl",  # spec 007 session C
    "20261119-gate-loopback_off_c.jsonl",
)

PAIRS: tuple[FixturePair, ...] = (
    # session 2 (2026-11-16 18:25), one knob at a time in edit mode
    _step("preset", "reverb_decay", "reverb_decay", (0, 127)),
    _step("preset", "reverb_mix", "reverb_mix", (0, 127)),
    _step("preset", "ir_cab", "ir_cab", (0, 8)),
    _step("preset", "delay_time", "delay_time", (0, 127)),
    _step("preset", "delay_mix", "delay_mix", (0, 127)),
    _step("preset", "mod_speed", "mod_speed", (0, 127)),
    _step("preset", "mod_fx", "mod_fx", (0, 127)),
    _step("preset", "volume", "volume", (20, 64)),
    _step("preset", "bass", "bass", (50, 91)),
    _step("preset", "middle", "middle", (60, 80)),
    _step("preset", "treble", "treble", (0, 13)),
    _step("preset", "gain", "gain", (60, 127)),
    _step("preset", "amp_type", "amp_type", (0, 4)),
    _step("preset", "noise_gate", "noise_gate", (2, 15)),
    # session 6 (18:47), labelled block switches and modes
    _step("preset", "amp_on", "amp_on", (0, 1)),
    _step("preset", "mod_on", "mod_on", (0, 1)),
    _step("preset", "delay_on", "delay_on", (0, 1)),
    _step("preset", "reverb_on", "reverb_on", (0, 1)),
    _step("global", "mode", "mode-1847", (0, 2)),
    # session 4 (18:43), modes again on a separate connection
    _step("global", "mode", "mode-1843", (0, 2)),
    # session 7 (19:17), labelled second pass: every knob, selector and switch again
    *(
        _step("preset", name, f"{field}-1917", (0, 127))
        for name, field in (
            ("noise_gate", "noise_gate"),
            ("gain", "gain"),
            ("treble", "treble"),
            ("middle", "middle"),
            ("bass", "bass"),
            ("volume", "volume"),
            ("mod_fx", "mod_fx"),
            ("mod_speed", "mod_speed"),
            ("delay_mix", "delay_mix"),
            ("delay_time", "delay_time"),
            ("reverb_decay", "reverb_decay"),
            ("reverb_mix", "reverb_mix"),
        )
    ),
    _step("preset", "amp_type", "amp_type-1917", (0, 8)),
    _step("preset", "ir_cab", "ir_cab-1917", (0, 8)),
    *(
        _step("preset", f"{b}_on", f"{b}_on-1917", (0, 1))
        for b in ("amp", "mod", "delay", "reverb")
    ),
    # session 3 (18:41), preset walk
    FixturePair("global", "browse_bank", "20261116-step-preset_select-bank.jsonl", single=False),
    FixturePair("global", "bank", "20261116-step-preset_select-bank.jsonl", single=False),
    FixturePair("global", "slot", "20261116-step-preset_select-slots.jsonl", single=False),
    # spec 007: gate excerpts for the bytes no pedal control moves
    *(
        _gate("preset", name, file, _LED)
        for name in ("led_red", "led_green", "led_blue")
        for file in _LED_STEPS
    ),
    *(_gate("status", "loopback", file) for file in _LOOPBACK_STEPS),
)

SELECTIONS: dict[str, list[tuple[int, int, int]]] = {
    # (browse_bank, bank, slot) per cycle, consecutive repeats removed
    "20261116-step-preset_select-slots.jsonl": [
        (8, 8, 3),  # 9D
        (0, 8, 3),  # browsing bank 1
        (0, 0, 0),  # 1A
        (0, 0, 1),  # 1B
        (0, 0, 2),  # 1C
        (0, 0, 3),  # 1D
    ],
    "20261116-step-preset_select-bank.jsonl": [
        (0, 0, 3),  # 1D
        (1, 0, 3),  # browsing bank 2
        (1, 1, 0),  # 2A
    ],
}
