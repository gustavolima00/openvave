"""``sendable_by_default``: the confidence and firmware gate (T025, FR-014/015, research R4)."""

from __future__ import annotations

import dataclasses

import pytest

from openvave.protocol.writes import (
    WRITE_MESSAGES,
    WriteMessage,
    message_for,
    sendable_by_default,
)

TARGETS = [
    ("knob_block", None),
    ("block_switch", 0),
    ("block_switch", 1),
    ("block_switch", 2),
    ("block_switch", 3),
    ("led_colour", None),
    ("preset_select", 6),
]


def test_confidence_after_gate_session_b() -> None:
    # session A (2026-11-17) made every row observed; session B confirmed these three (SC-005)
    confidence = {(m.kind, m.argument): m.confidence for m in WRITE_MESSAGES}
    assert confidence == {
        ("knob_block", None): "confirmed",
        ("block_switch", 0): "observed",
        ("block_switch", 1): "observed",
        ("block_switch", 2): "observed",
        ("block_switch", 3): "observed",
        ("led_colour", None): "observed",
        ("preset_select", None): "confirmed",
        ("bypass", None): "confirmed",  # spec 004 gate sessions A and B (T090)
        ("loopback", None): "observed",  # spec 004 session A only
        ("stored_slot", None): "confirmed",  # persistent: still needs --unsafe
        ("commit", None): "confirmed",
        ("stored_image", None): "confirmed",
        ("ack", None): "confirmed",
    }


@pytest.mark.parametrize(
    ("kind", "argument"),
    [("bypass", 1), ("bypass", 35), ("stored_slot", 2), ("commit", None), ("stored_image", None)],
)
def test_spec004_confirmed_rows_are_sendable_on_fw96(kind: str, argument: int | None) -> None:
    # spec 004 T090: confirmed by gate sessions A and B; persistence is gated by --unsafe elsewhere
    assert sendable_by_default(kind, argument, 96) is True
    assert sendable_by_default(kind, argument, 97) is False


def test_loopback_still_needs_the_opt_in() -> None:
    assert sendable_by_default("loopback", None, 96) is False


@pytest.mark.parametrize(
    ("kind", "argument"), [("block_switch", k) for k in range(4)] + [("led_colour", None)]
)
def test_observed_rows_still_need_the_opt_in(kind: str, argument: int | None) -> None:
    assert sendable_by_default(kind, argument, 96) is False


CONFIRMED_IN_B = [("knob_block", None), *(("preset_select", i) for i in (0, 6, 35))]


@pytest.mark.parametrize(("kind", "argument"), CONFIRMED_IN_B)
def test_session_b_rows_are_sendable_on_fw96(kind: str, argument: int | None) -> None:
    # T059: knob block and preset select are confirmed by two sessions, the ACK row too
    assert sendable_by_default(kind, argument, 96) is True


@pytest.mark.parametrize(("kind", "argument"), CONFIRMED_IN_B)
def test_session_b_rows_are_not_sendable_on_other_firmware(kind: str, argument: int | None) -> None:
    assert sendable_by_default(kind, argument, 97) is False


@pytest.mark.parametrize(("kind", "argument"), TARGETS)
def test_rows_left_observed_need_the_opt_in(kind: str, argument: int | None) -> None:
    row = message_for(kind, argument)
    if row.confidence != "confirmed":
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
        sendable_by_default("erase", None, 96)
    with pytest.raises(KeyError):
        sendable_by_default("block_switch", 4, 96)
