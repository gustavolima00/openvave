"""``sendable_by_default``: the confidence and firmware gate (T025, FR-014/015, research R4)."""

from __future__ import annotations

import dataclasses

import pytest

from openvave.protocol.writes import WRITE_MESSAGES, WriteMessage, sendable_by_default

TARGETS = [
    ("knob_block", None),
    ("block_switch", 0),
    ("block_switch", 1),
    ("block_switch", 2),
    ("block_switch", 3),
    ("led_colour", None),
    ("preset_select", 6),
]


@pytest.mark.parametrize(("kind", "argument"), TARGETS)
def test_nothing_is_sendable_after_gate_session_a(kind: str, argument: int | None) -> None:
    # session A (2026-11-17) promoted every row to observed; confirmed needs session B
    assert all(m.confidence == "observed" for m in WRITE_MESSAGES)
    assert sendable_by_default(kind, argument, 96) is False


def promoted(knob: str, ack: str, firmware: frozenset[int] = frozenset({96})) -> list[WriteMessage]:
    out = []
    for m in WRITE_MESSAGES:
        if m.kind == "knob_block":
            m = dataclasses.replace(m, confidence=knob, firmware=firmware)
        elif m.kind == "ack":
            m = dataclasses.replace(m, confidence=ack)
        out.append(m)
    return out


def test_confirmed_row_with_observed_ack_is_sendable() -> None:
    table = promoted("confirmed", "observed")
    assert sendable_by_default("knob_block", None, 96, messages=table) is True
    assert sendable_by_default("led_colour", None, 96, messages=table) is False


def test_observed_row_is_not_sendable() -> None:
    table = promoted("observed", "confirmed")
    assert sendable_by_default("knob_block", None, 96, messages=table) is False


def test_hypothesis_ack_blocks_everything() -> None:
    table = promoted("confirmed", "hypothesis")
    assert sendable_by_default("knob_block", None, 96, messages=table) is False


def test_uncovered_firmware_is_not_sendable() -> None:
    table = promoted("confirmed", "confirmed")
    assert sendable_by_default("knob_block", None, 97, messages=table) is False
    table = promoted("confirmed", "confirmed", frozenset({96, 97}))
    assert sendable_by_default("knob_block", None, 97, messages=table) is True


def test_preset_select_row_covers_every_index() -> None:
    table = [
        dataclasses.replace(m, confidence="confirmed") if m.kind in ("preset_select", "ack") else m
        for m in WRITE_MESSAGES
    ]
    for i in (0, 6, 35):
        assert sendable_by_default("preset_select", i, 96, messages=table) is True


def test_unknown_kind_raises() -> None:
    with pytest.raises(KeyError):
        sendable_by_default("commit", None, 96)
    with pytest.raises(KeyError):
        sendable_by_default("block_switch", 4, 96)
