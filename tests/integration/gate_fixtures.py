"""Index of the gate-session excerpts (spec 003 M2/M3, T047; spec 004 M3/M4, T068, T085).

Spec 003 steps send one volatile write each. Spec 004 steps run one CLI command each (``openvave
--trace``), or the no-op image helper (``tests/hardware/test_hw_persistent.py``): bypass,
loopback and the field writes in normal mode send one write; save, restore and the image write
run the persistent sequence (write → commit → select) after the automatic backup.

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
SPEC004_SESSION_A_DATE = "20261118"
"""Expected date of spec 004 gate session A; :data:`RECORDED` names the real files."""
SPEC004_SESSION_B_DATE = "20261118"
"""Expected date of spec 004 gate session B (after a power cycle, a new connection per command,
another loaded preset and another target slot than session A)."""
SPEC007_SESSION_C_DATE = "20261119"
"""Date of spec 007 gate session C."""


@dataclass(frozen=True)
class GateStep:
    step: str
    """Step name, as in the excerpt file name and its ``meta.step``."""
    kind: str
    """Write kind: ``knob_block``, ``block_switch``, ``led_colour`` or ``preset_select`` (spec
    003); spec 004 adds ``bypass``, ``bypass_off``, ``loopback`` and the persistent sequences
    ``save``, ``restore_slot``, ``restore_all`` and ``image_noop``."""
    offset: int | None = None
    """Preset offset of the field (knob/switch/LED), ``None`` otherwise."""
    session: str = "A"
    """Gate session (``A`` or ``B``): a ``confirmed`` row cites excerpts of two sessions."""
    spec: str = "003"
    """The spec whose gate sends this step."""

    @property
    def persistent(self) -> bool:
        """True for the steps whose sequence writes stored presets (commit included)."""
        return self.kind in PERSISTENT_KINDS


PERSISTENT_KINDS = frozenset({"save", "restore_slot", "restore_all", "image_noop"})


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

SPEC003_STEPS: tuple[GateStep, ...] = SESSION_A + SESSION_B

SPEC004_SESSION_A: tuple[GateStep, ...] = (
    # spec 004 M3 (T072-T078): every new message sent once by openvave, in this order
    GateStep("bypass", "bypass", spec="004"),
    GateStep("bypass_off", "bypass_off", spec="004"),
    GateStep("normal_switch_mod", "block_switch", 1, spec="004"),
    GateStep("normal_led_colour", "led_colour", 18, spec="004"),
    GateStep("loopback_off", "loopback", spec="004"),
    GateStep("loopback_on", "loopback", spec="004"),
    GateStep("save", "save", spec="004"),
    GateStep("restore_slot", "restore_slot", spec="004"),
    GateStep("image_noop", "image_noop", spec="004"),
    GateStep("restore_all", "restore_all", spec="004"),
)

SPEC004_SESSION_B: tuple[GateStep, ...] = (
    # spec 004 M4 (T086-T089): the second, independent session that confirms the rows
    GateStep("bypass_b", "bypass", session="B", spec="004"),
    GateStep("bypass_off_b", "bypass_off", session="B", spec="004"),
    GateStep("save_b", "save", session="B", spec="004"),
    GateStep("restore_slot_b", "restore_slot", session="B", spec="004"),
    GateStep("restore_all_b", "restore_all", session="B", spec="004"),
)

SPEC004_STEPS: tuple[GateStep, ...] = SPEC004_SESSION_A + SPEC004_SESSION_B

SPEC007_SESSION_C: tuple[GateStep, ...] = (
    # spec 007 gate session C (2026-11-19, runbook specs/007-mapping-gaps/gate-session-c.md): the
    # second independent session for the block switches, LED colour and loopback; a new connection
    # per command, normal mode, preset 1B
    GateStep("switch_amp_c", "block_switch", 0, session="C", spec="007"),
    GateStep("switch_mod_c", "block_switch", 1, session="C", spec="007"),
    GateStep("switch_reverb_c", "block_switch", 3, session="C", spec="007"),
    GateStep("led_colour_c", "led_colour", 18, session="C", spec="007"),
    GateStep("loopback_on_c", "loopback", session="C", spec="007"),
    GateStep("switch_delay_c", "block_switch", 2, session="C", spec="007"),
    GateStep("loopback_off_c", "loopback", session="C", spec="007"),
)

SPEC007_STEPS: tuple[GateStep, ...] = SPEC007_SESSION_C

ALL_STEPS: tuple[GateStep, ...] = SPEC003_STEPS + SPEC004_STEPS + SPEC007_STEPS

SESSION_DATES = {
    ("003", "A"): SESSION_A_DATE,
    ("003", "B"): SESSION_B_DATE,
    ("004", "A"): SPEC004_SESSION_A_DATE,
    ("004", "B"): SPEC004_SESSION_B_DATE,
    ("007", "C"): SPEC007_SESSION_C_DATE,
}

ROW_STEPS: dict[str, frozenset[str]] = {
    "bypass": frozenset({"bypass", "bypass_b"}),
    "loopback": frozenset({"loopback_off", "loopback_on", "loopback_off_c", "loopback_on_c"}),
    "stored_slot": frozenset({"save", "restore_slot", "save_b", "restore_slot_b"}),
    "commit": frozenset(
        {
            "save",
            "restore_slot",
            "image_noop",
            "restore_all",
            "save_b",
            "restore_slot_b",
            "restore_all_b",
        }
    ),
    "stored_image": frozenset({"image_noop", "restore_all", "restore_all_b"}),
}
"""Spec 004 write rows → the gate steps whose excerpts may back their promotion (T070)."""

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
    # spec 004 M3, session A (T082)
    "bypass": "20261118-gate-bypass.jsonl",
    "bypass_off": "20261118-gate-bypass_off.jsonl",
    "normal_switch_mod": "20261118-gate-normal_switch_mod.jsonl",
    "normal_led_colour": "20261118-gate-normal_led_colour.jsonl",
    "loopback_off": "20261118-gate-loopback_off.jsonl",
    "loopback_on": "20261118-gate-loopback_on.jsonl",
    "save": "20261118-gate-save.jsonl",
    "restore_slot": "20261118-gate-restore_slot.jsonl",
    "image_noop": "20261118-gate-image_noop.jsonl",
    "restore_all": "20261118-gate-restore_all.jsonl",
    # spec 004 M4, session B (T090)
    "bypass_b": "20261118-gate-bypass_b.jsonl",
    "bypass_off_b": "20261118-gate-bypass_off_b.jsonl",
    "save_b": "20261118-gate-save_b.jsonl",
    "restore_slot_b": "20261118-gate-restore_slot_b.jsonl",
    "restore_all_b": "20261118-gate-restore_all_b.jsonl",
    # spec 007 gate session C
    "switch_amp_c": "20261119-gate-switch_amp_c.jsonl",
    "switch_mod_c": "20261119-gate-switch_mod_c.jsonl",
    "switch_delay_c": "20261119-gate-switch_delay_c.jsonl",
    "switch_reverb_c": "20261119-gate-switch_reverb_c.jsonl",
    "led_colour_c": "20261119-gate-led_colour_c.jsonl",
    "loopback_on_c": "20261119-gate-loopback_on_c.jsonl",
    "loopback_off_c": "20261119-gate-loopback_off_c.jsonl",
}
"""Step → committed excerpt file name. Filled in each evidence commit (T055, T062, T082)."""

STEPS_BY_NAME: dict[str, GateStep] = {s.step: s for s in ALL_STEPS}
PERSISTENT_STEPS = frozenset(s.step for s in ALL_STEPS if s.persistent)


def excerpt_path(step: GateStep) -> Path:
    default = f"{SESSION_DATES[(step.spec, step.session)]}-gate-{step.step}.jsonl"
    return FW96 / RECORDED.get(step.step, default)


def committed_gate_excerpts() -> list[Path]:
    return sorted(FW96.glob("*-gate-*.jsonl"))
