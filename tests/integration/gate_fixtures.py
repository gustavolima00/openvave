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
"""Date of gate session A."""
SESSION_B_DATE = "20261117"
"""Date of gate session B (same day as A, a new connection per command, another preset)."""


@dataclass(frozen=True)
class GateStep:
    step: str
    """Step name, as in the excerpt file name and its ``meta.step``."""
    kind: str
    """Write kind: ``knob_block``, ``block_switch``, ``led_colour`` or ``preset_select``."""
    offset: int | None = None
    """Preset offset of the field (knob/switch/LED), ``None`` for preset select."""
    session: str = "A"
    """Gate session (``A`` or ``B``): a ``confirmed`` row cites excerpts of two sessions."""


SESSION_A: tuple[GateStep, ...] = (
    GateStep("knob_gain", "knob_block", 6),
    GateStep("switch_mod", "block_switch", 1),
    GateStep("switch_amp", "block_switch", 0),
    GateStep("switch_delay", "block_switch", 2),
    GateStep("switch_reverb", "block_switch", 3),
    GateStep("led_colour", "led_colour", 18),
    GateStep("select", "preset_select"),
    GateStep("select_back", "preset_select"),
)

SESSION_B: tuple[GateStep, ...] = (
    # spec 003 M3 (T060): a new connection, another stored preset, another knob than session A
    GateStep("knob_treble", "knob_block", 7, "B"),
    GateStep("select_b", "preset_select", session="B"),
    GateStep("select_b_back", "preset_select", session="B"),
)

ALL_STEPS: tuple[GateStep, ...] = SESSION_A + SESSION_B

SESSION_DATES = {"A": SESSION_A_DATE, "B": SESSION_B_DATE}

RECORDED: dict[str, str] = {
    "knob_gain": "20261117-gate-knob_gain.jsonl",
    "switch_mod": "20261117-gate-switch_mod.jsonl",
    "switch_amp": "20261117-gate-switch_amp.jsonl",
    "switch_delay": "20261117-gate-switch_delay.jsonl",
    "switch_reverb": "20261117-gate-switch_reverb.jsonl",
    "led_colour": "20261117-gate-led_colour.jsonl",
    "select": "20261117-gate-select.jsonl",
    "select_back": "20261117-gate-select_back.jsonl",
    "knob_treble": "20261117-gate-knob_treble.jsonl",
    "select_b": "20261117-gate-select_b.jsonl",
    "select_b_back": "20261117-gate-select_b_back.jsonl",
}
"""Step → committed excerpt file name. Filled in each evidence commit (T055, T062)."""


def excerpt_path(step: GateStep) -> Path:
    default = f"{SESSION_DATES[step.session]}-gate-{step.step}.jsonl"
    return FW96 / RECORDED.get(step.step, default)


def committed_gate_excerpts() -> list[Path]:
    return sorted(FW96.glob("*-gate-*.jsonl"))
