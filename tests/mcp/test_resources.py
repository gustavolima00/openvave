"""Reference resources, readable without a pedal (spec 006 US7, FR-027)."""

from __future__ import annotations

import json
from pathlib import Path

from openvave.protocol import BYTE_MAP, DELAY_MIX_TYPES, MOD_FX_TYPES, REVERB_TYPES
from openvave.protocol.writes import WRITABLE_FIELDS
from tests.mcp.conftest import CountingFactory, open_harness, options

URIS = {
    "openvave://fields": "application/json",
    "openvave://effect-types": "application/json",
    "openvave://byte-map": "application/json",
    "openvave://safety": "text/markdown",
}


async def test_resources_are_listed(tmp_path: Path) -> None:
    async with open_harness(options(tmp_path), CountingFactory()) as h:
        listed = await h.client.list_resources()
    found = {str(r.uri): r.mime_type for r in listed.resources}
    assert found == URIS
    assert all(r.description for r in listed.resources)


async def test_fields(tmp_path: Path) -> None:
    factory = CountingFactory()
    async with open_harness(options(tmp_path), factory) as h:
        mime, text = await h.resource("openvave://fields")
    assert mime == "application/json"
    document = json.loads(text)
    fields = {f["name"]: f for f in document["fields"]}
    assert list(fields) == list(WRITABLE_FIELDS)
    for f in fields.values():
        assert f["syntax"]
        assert f["kind"] in ("knob", "selector", "typed knob", "block switch", "LED")
        assert isinstance(f["experimental"], bool)
    assert fields["gain"]["kind"] == "knob"
    assert fields["gain"]["range"] == {"min": 0, "max": 127}
    assert fields["gain"]["experimental"] is False
    assert fields["amp_type"]["kind"] == "selector"
    assert fields["amp_type"]["range"] == {"min": 0, "max": 8}
    assert fields["amp_on"]["kind"] == "block switch"
    assert fields["amp_on"]["syntax"] == "on | off"
    assert fields["amp_on"]["experimental"] is True  # block switches are only observed
    assert fields["led_colour"]["kind"] == "LED"
    assert fields["led_colour"]["experimental"] is True
    reverb = fields["reverb_decay"]
    assert reverb["kind"] == "typed knob"
    assert reverb["types"] == list(REVERB_TYPES)
    assert reverb["positions"] == {"min": 1, "max": 40}
    assert "TYPE:POSITION" in reverb["syntax"] and "raw:N" in reverb["syntax"]
    assert "experimental" in document["notes"]
    assert factory.calls == 0


async def test_effect_types(tmp_path: Path) -> None:
    async with open_harness(options(tmp_path), CountingFactory()) as h:
        _, text = await h.resource("openvave://effect-types")
    document = json.loads(text)
    assert {k: v["types"] for k, v in document["fields"].items()} == {
        "mod_fx": list(MOD_FX_TYPES),
        "delay_mix": list(DELAY_MIX_TYPES),
        "reverb_decay": list(REVERB_TYPES),
    }
    room = document["fields"]["reverb_decay"]["raw_ranges"][0]
    assert room == {"type": "room", "min": 0, "max": 39, "positions": {"min": 1, "max": 40}}
    spring = document["fields"]["reverb_decay"]["raw_ranges"][1]
    assert (spring["min"], spring["max"]) == (44, 83)


async def test_byte_map(tmp_path: Path) -> None:
    async with open_harness(options(tmp_path), CountingFactory()) as h:
        _, text = await h.resource("openvave://byte-map")
    document = json.loads(text)
    entries = [e for region in document["regions"].values() for e in region]
    assert len(entries) == len(BYTE_MAP)
    gain = next(e for e in document["regions"]["current_preset"] if e["name"] == "gain")
    assert gain == {
        "offset": 6,
        "name": "gain",
        "label": "gain",
        "encoding": "continuous",
        "range": {"min": 0, "max": 127},
        "confidence": "confirmed",
    }
    assert document["map_firmware"] == 96


async def test_safety(tmp_path: Path) -> None:
    async with open_harness(options(tmp_path), CountingFactory()) as h:
        mime, text = await h.resource("openvave://safety")
    assert mime == "text/markdown"
    for word in ("unsafe", "experimental", "dry_run", "discard_edits", "pedal_disconnect"):
        assert word in text
