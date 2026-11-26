# Library contract additions (feature 008, openvave 0.7.0)

Extends the [005 `library-api.md`](../../005-device-selection/contracts/library-api.md) and the
names added by specs 006 and 007. Additions only: no 0.6.0 name changes meaning (MINOR bump).
Shapes: [data-model.md](../data-model.md).

## A simulated pedal that accepts writes

```python
from openvave import FakeTransport, TankG

fake = FakeTransport.simulated("captures/fw96/20261116-probe-connect.jsonl")
async with TankG.over(fake) as pedal:
    await pedal.set_fields({"gain": 95, "delay_on": True})
    await pedal.select_preset(6)                      # 2C
    backup = await pedal.backup()                     # 36 presets, cross-checked
fake.sent                                             # every request, in order
```

```python
FakeTransport.simulated(
    path,                    # str | Path: a capture file (captures/README.md)
    *,
    image=None,              # bytes: the 758-byte stored image to start from
    faults=None,             # Mapping[str, str]: {write kind: action}, each used once
    select_transient=0,      # int: global reads showing slot ff after each select
    chunk_size=None,         # int: reply notification size (182 = ATT MTU 185)
) -> FakeTransport
```

- Starts in the recorded state (identity, global block, current preset, status byte) and holds 36
  stored presets: `image`, else the session's whole-image read, else a generated image whose
  loaded position holds the recorded preset.
- Accepts every allowlisted write and applies it to its memory; answers every read from that
  memory. A frame outside the allowlist raises `AssertionError`, as on any `FakeTransport`.
- Raises `ValueError` when the session lacks the handshake, the global read or the current-preset
  read, when the recorded state has no loaded preset, when `image` is not 758 bytes, or for an
  unknown fault kind or action.
- The returned object is a plain `FakeTransport`: `sent`, `commits`, `lose_link()` and the
  transport methods work as documented there.
- It is a model built from the protocol document, not evidence of what a pedal does.

`FakeTransport(...)` and `FakeTransport.from_capture(...)` are unchanged.

## Front panel

```python
from openvave.protocol import PANEL_CONTROLS, PanelControl, panel_control

for control in PANEL_CONTROLS:                        # 19, in panel order
    print(control.order, control.label, control.group, control.kind, control.field, control.offset)

panel_control("reverb_decay")   # PanelControl(order=3, label="RVB DECAY", group="REVERB", kind="knob", field="reverb_decay", offset=15)
panel_control("led_red")        # None
PANEL_CONTROLS[0]               # MASTER: field None, offset None
```

The order is the one of `docs/images/tankg-controls.svg`.

## Preset positions

```python
from openvave import preset_index, preset_position    # also in openvave.protocol

preset_index("2C")      # 6
preset_position(6)      # "2C"
preset_index("2c")      # ValueError (also "0A", "10A", "1E", "", "6", 6, None)
preset_position(36)     # ValueError (also -1, True, 1.0, "1")
```

## Unchanged

Every other public name, the CLI's and the MCP tools' position parsing (which also accepts lower
case and index text), all CLI and MCP output, and the JSON documents (`schema_version` 2).
