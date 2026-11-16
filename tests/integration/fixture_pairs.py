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
    """``global`` or ``preset`` (record names)."""
    name: str
    """Byte map name."""
    file: str
    """Excerpt file name under ``captures/fw96/``."""
    reaches: tuple[int, int] | None = None
    """Exact (min, max) of the raw value over the excerpt, when it is a sweep."""
    single: bool = True

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
    _step("preset", "knob_unknown", "gain", (60, 127)),
    _step("preset", "amp_type", "amp_type", (0, 4)),
    _step("preset", "noise_gate", "noise_gate", (2, 15)),
    # session 6 (18:47), labelled block switches and modes
    _step("preset", "amp_on", "amp_on", (0, 1)),
    _step("preset", "mod_on", "mod_on", (0, 1)),
    _step("preset", "delay_on", "delay_on", (0, 1)),
    _step("preset", "reverb_on", "reverb_on", (0, 1)),
    _step("global", "not_in_edit_mode", "mode-1847", (0, 2)),
    # session 4 (18:43), modes again on a separate connection
    _step("global", "not_in_edit_mode", "mode-1843", (0, 2)),
    # session 3 (18:41), preset walk
    FixturePair("global", "browse_bank", "20261116-step-preset_select-bank.jsonl", single=False),
    FixturePair("global", "bank", "20261116-step-preset_select-bank.jsonl", single=False),
    FixturePair("global", "slot", "20261116-step-preset_select-slots.jsonl", single=False),
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
