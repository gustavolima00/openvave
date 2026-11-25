"""Amp type and IR cab names (spec 007 US4): one data table, its sources and its rules."""

from __future__ import annotations

import pytest

from openvave.protocol import BYTE_MAP
from openvave.protocol.names import (
    NAME_CHOICE,
    NAME_SOURCES,
    NAMED_FIELDS,
    POSITION_NAMES,
    position_name,
    source_list,
)

ENTRIES = {e.name: e for e in BYTE_MAP if e.name is not None}


def test_named_fields_are_the_two_selectors() -> None:
    assert NAMED_FIELDS == ("amp_type", "ir_cab")
    for field in NAMED_FIELDS:
        entry = ENTRIES[field]
        assert entry.encoding.value == "selector"
        assert (entry.min, entry.max) == (0, 8)
        assert len(NAME_CHOICE[field]) == 9


@pytest.mark.parametrize("source", sorted(NAME_SOURCES))
def test_every_source_lists_nine_positions_and_cab_zero_is_off(source: str) -> None:
    assert len(source_list(source, "amp_type")) == 9
    assert all(item is not None for item in source_list(source, "amp_type"))
    cabs = source_list(source, "ir_cab")
    assert len(cabs) == 9
    assert cabs[0] is None
    assert all(item is not None for item in cabs[1:])


def test_names_follow_the_choice_table() -> None:
    for field in NAMED_FIELDS:
        for raw, choice in enumerate(NAME_CHOICE[field]):
            name = position_name(field, raw)
            if choice is None:
                assert name is None
                continue
            source, confidence = choice
            item = source_list(source, field)[raw]
            assert item is not None
            assert name is not None
            assert (name.name, name.detail) == item
            assert (name.source, name.confidence) == (source, confidence)
            assert name.raw == raw and name.field == field


def test_names_are_documented_not_observed() -> None:
    """Spec 007 T031 (owner decision 2026-11-25): matched against the printed manual shipped
    with the pedal, not on the pedal, so ``documented`` and never ``observed`` / ``confirmed``."""
    for names in POSITION_NAMES.values():
        for name in names.values():
            assert name.confidence == "documented"
            assert name.source == "manual-am3"


def test_both_manual_revisions_print_the_same_cab_table() -> None:
    assert source_list("manual-am3", "ir_cab") == source_list("manual-2024", "ir_cab")
    assert source_list("manual-am3", "amp_type") != source_list("manual-2024", "amp_type")


def test_cab_names_are_factory_names_and_amp_names_are_not() -> None:
    assert all(n.factory for n in POSITION_NAMES["ir_cab"].values())
    assert not any(n.factory for n in POSITION_NAMES["amp_type"].values())


def test_cab_off_keeps_its_byte_map_label() -> None:
    assert position_name("ir_cab", 0) is None
    assert ENTRIES["ir_cab"].labels == {0: "off"}


def test_other_fields_and_out_of_range_have_no_name() -> None:
    assert position_name("gain", 4) is None
    assert position_name(None, 4) is None
    assert position_name("amp_type", 9) is None
    assert position_name("amp_type", 255) is None


def test_cab_text_carries_the_speaker_layout() -> None:
    for name in POSITION_NAMES["ir_cab"].values():
        assert name.text == f"{name.name} {name.detail}"
    for name in POSITION_NAMES["amp_type"].values():
        assert name.text == name.name
        assert name.detail in ("clean", "overdrive", "distortion")
