"""Index of the gate-session excerpts (spec 003 M2/M3, T047): one per approved hardware write.

Each excerpt is cut from the owner's ``--trace`` output by ``tests/support/gate_excerpt.py`` and
lives at ``captures/fw96/<date>-gate-<step>.jsonl``. A step is listed in :data:`RECORDED` (step →
file name) only in the evidence commit that adds its excerpt; until then its replay test is a
strict ``xfail`` on the expected file name.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tests.support.captures import CAPTURES_DIR

FW96 = CAPTURES_DIR / "fw96"
SESSION_A_DATE = "20261117"
"""Expected date of gate session A (the file name of a not-yet-recorded step)."""


@dataclass(frozen=True)
class GateStep:
    step: str
    """Step name, as in the excerpt file name and its ``meta.step``."""
    kind: str
    """Write kind: ``knob_block``, ``block_switch``, ``led_colour`` or ``preset_select``."""
    offset: int | None = None
    """Preset offset of the field (knob/switch/LED), ``None`` for preset select."""


SESSION_A: tuple[GateStep, ...] = (
    GateStep("knob_gain", "knob_block", 6),
    GateStep("switch_mod", "block_switch", 1),
    GateStep("switch_amp", "block_switch", 0),
    GateStep("switch_delay", "block_switch", 2),
    GateStep("switch_reverb", "block_switch", 3),
    GateStep("led_colour", "led_colour", 18),
    GateStep("select", "preset_select"),
)

RECORDED: dict[str, str] = {}
"""Step → committed excerpt file name. Filled in the evidence commit (T055)."""


def excerpt_path(step: GateStep) -> Path:
    return FW96 / RECORDED.get(step.step, f"{SESSION_A_DATE}-gate-{step.step}.jsonl")


def committed_gate_excerpts() -> list[Path]:
    return sorted(FW96.glob("*-gate-*.jsonl"))
