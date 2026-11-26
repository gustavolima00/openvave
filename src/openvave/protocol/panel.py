"""The Tank-G front panel as data: its controls, its groups and when a group is enabled (pure).

``PANEL_CONTROLS`` lists the nineteen controls printed on the panel in panel order: the fifteen
knobs left to right, then the four footswitches left to right, as in
``docs/images/tankg-controls.svg`` (whose description text ``tests/unit/test_panel.py`` reads) and
``docs/tank-g.md``. Each control names the current-preset field and byte it drives; MASTER drives
none (spec 007 gate session C: turning it changed no byte, observed). The three LED colour bytes
are not panel controls.

``PANEL_GROUPS`` lists the seven printed groups with the field, rule and confidence that say
whether the group is enabled. The rule table is mirrored in "Front panel" in
``specs/protocol/command-layer.md``; ``tests/unit/test_panel_doc.py`` fails on any difference.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ControlKind = Literal["knob", "selector", "footswitch"]
EnabledRule = Literal["switch", "nonzero"]
EnabledConfidence = Literal["confirmed", "documented"]
"""``documented``: from the vendor's own material, not checked on the pedal (as in
:mod:`openvave.protocol.names`). Not a byte-map :data:`~openvave.models.Confidence`."""

PRESET_SIZE = 21
"""Bytes of a current preset (``Region.CURRENT_PRESET.length``)."""
SWITCH_ON, SWITCH_OFF = 1, 0
"""``on_value`` and ``off_value`` of the four block switches in the byte map."""


@dataclass(frozen=True)
class PanelControl:
    """One control printed on the front panel."""

    order: int
    """Place on the panel, 0-based: knobs left to right (0–14), then footswitches (15–18)."""
    label: str
    """The text printed at the control (``"RVB DECAY"``, ``"A/REVERB"``)."""
    group: str
    """The printed group (a :attr:`PanelGroup.name`); a footswitch's is the block it switches."""
    kind: ControlKind
    """``knob`` (a continuous byte), ``selector`` (a stepped byte) or ``footswitch`` (a block
    switch byte)."""
    field: str | None
    """Byte-map name of the current-preset field it drives; ``None`` for MASTER."""
    offset: int | None
    """Preset byte of :attr:`field`; ``None`` when :attr:`field` is ``None``."""


PANEL_CONTROLS: tuple[PanelControl, ...] = (
    PanelControl(0, "MASTER", "MASTER", "knob", None, None),
    PanelControl(1, "IR CAB", "CAB", "selector", "ir_cab", 17),
    PanelControl(2, "RVB MIX", "REVERB", "knob", "reverb_mix", 16),
    PanelControl(3, "RVB DECAY", "REVERB", "knob", "reverb_decay", 15),
    PanelControl(4, "DLY TIME", "DELAY", "knob", "delay_time", 14),
    PanelControl(5, "DLY MIX", "DELAY", "knob", "delay_mix", 13),
    PanelControl(6, "MOD SPEED", "MOD", "knob", "mod_speed", 12),
    PanelControl(7, "MOD FX", "MOD", "knob", "mod_fx", 11),
    PanelControl(8, "VOLUME", "AMP", "knob", "volume", 10),
    PanelControl(9, "BASS", "AMP", "knob", "bass", 9),
    PanelControl(10, "MIDDLE", "AMP", "knob", "middle", 8),
    PanelControl(11, "TREBLE", "AMP", "knob", "treble", 7),
    PanelControl(12, "GAIN", "AMP", "knob", "gain", 6),
    PanelControl(13, "TYPE", "AMP", "selector", "amp_type", 5),
    PanelControl(14, "NOISE GATE", "GATE", "knob", "noise_gate", 4),
    PanelControl(15, "A/REVERB", "REVERB", "footswitch", "reverb_on", 3),
    PanelControl(16, "B/DELAY", "DELAY", "footswitch", "delay_on", 2),
    PanelControl(17, "C/MOD", "MOD", "footswitch", "mod_on", 1),
    PanelControl(18, "D/AMP", "AMP", "footswitch", "amp_on", 0),
)
"""The nineteen front-panel controls, in panel order (``PANEL_CONTROLS[i].order == i``)."""

_BY_FIELD = {c.field: c for c in PANEL_CONTROLS if c.field is not None}


def panel_control(field: str | None) -> PanelControl | None:
    """The control that drives ``field``, or ``None`` (LED colour bytes, global and status
    fields, unknown names, ``None``)."""
    if field is None:
        return None
    return _BY_FIELD.get(field)


@dataclass(frozen=True)
class PanelGroup:
    """One printed group of the panel and how to read whether it is enabled.

    :attr:`enabled_field`, :attr:`enabled_rule` and :attr:`enabled_confidence` are all ``None``
    for a group without an on/off notion (MASTER), and all set otherwise.
    """

    name: str
    """The printed group: ``MASTER``, ``CAB``, ``REVERB``, ``DELAY``, ``MOD``, ``AMP``,
    ``GATE``."""
    order: int
    """Panel order, 0-based, following the first control of each group."""
    enabled_field: str | None
    """The current-preset field that says whether the group is enabled (a control of this
    group)."""
    enabled_rule: EnabledRule | None
    """``switch``: enabled when the byte is the field's on value (1), not when it is the off
    value (0), unknown otherwise. ``nonzero``: enabled when the byte is not 0."""
    enabled_confidence: EnabledConfidence | None
    """Evidence level of the rule: ``confirmed``, or ``documented`` (the vendor's material
    shows it; not checked on the pedal)."""


PANEL_GROUPS: tuple[PanelGroup, ...] = (
    # No byte follows the MASTER knob (spec 007 gate session C, observed): no state to read.
    PanelGroup("MASTER", 0, None, None, None),
    # Manual; the vendor app shows 0 as OFF; heard off in spec 007 gate session C (2026-11-19).
    PanelGroup("CAB", 1, "ir_cab", "nonzero", "confirmed"),
    # Block switches: byte-map rows and the confirmed block_switch write row.
    PanelGroup("REVERB", 2, "reverb_on", "switch", "confirmed"),
    PanelGroup("DELAY", 3, "delay_on", "switch", "confirmed"),
    PanelGroup("MOD", 4, "mod_on", "switch", "confirmed"),
    PanelGroup("AMP", 5, "amp_on", "switch", "confirmed"),
    # The vendor app shows a gate of 0 as OFF; never heard as off on the pedal.
    PanelGroup("GATE", 6, "noise_gate", "nonzero", "documented"),
)
"""The seven printed groups, in panel order (``PANEL_GROUPS[i].order == i``).

GATE's rule is ``documented`` only: the vendor's phone app shows a noise gate of 0 as ``OFF``;
openvave has not checked on the pedal that 0 turns the gate off. MOD, DELAY and REVERB follow
their block switch only: the off zones between two effect types of MOD FX, DLY MIX and RVB DECAY
(not verified, see :func:`~openvave.protocol.type_parts`) are not part of the rule.
"""

_BY_NAME = {g.name: g for g in PANEL_GROUPS}


def panel_group(name: str) -> PanelGroup | None:
    """The group printed ``name`` (exact, upper case), or ``None``."""
    return _BY_NAME.get(name)


def group_enabled(group: str, preset: bytes) -> bool | None:
    """Whether ``group`` is enabled in ``preset``, the 21 bytes of a current preset
    (``RegionRead.data``).

    Returns ``True`` or ``False`` by the group's rule (:data:`PANEL_GROUPS`), or ``None`` (no
    answer) for a group without an on/off notion (MASTER), for a block switch byte that is
    neither 1 nor 0, and for every group when ``preset`` is 21 zero bytes: that is the bypass
    placeholder, not a preset, and bypass is read from :meth:`openvave.TankG.state`. Raises
    :class:`ValueError` for an unknown group name or a ``preset`` that is not 21 bytes.
    """
    entry = _BY_NAME.get(group)
    if entry is None:
        raise ValueError(f"unknown panel group {group!r} (expected one of {', '.join(_BY_NAME)})")
    if not isinstance(preset, bytes | bytearray | memoryview):
        raise ValueError(f"a current preset is {PRESET_SIZE} bytes, got {type(preset).__name__}")
    data = bytes(preset)  # a memoryview of another format is counted in bytes, not elements
    if len(data) != PRESET_SIZE:
        raise ValueError(f"a current preset is {PRESET_SIZE} bytes, got {len(data)}")
    if entry.enabled_field is None or not any(data):
        return None
    control = _BY_FIELD[entry.enabled_field]
    assert control.offset is not None
    byte = data[control.offset]
    if entry.enabled_rule == "nonzero":
        return byte != 0
    if byte == SWITCH_ON:
        return True
    if byte == SWITCH_OFF:
        return False
    return None
