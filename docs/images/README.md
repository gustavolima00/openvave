# Images

Every image here is an original drawing made for openvave and released under the project's MIT
license. `tankg-controls.svg` is traced from the owner's own pedal (panel order and labels, LED
colours); the others are schematic.

| File | Shows | Used in |
|---|---|---|
| `tankg-controls.svg` | the front panel in panel order, LED colours, each knob's field and preset byte, footswitches | [tank-g.md](../tank-g.md) |
| `signal-chain.svg` | the six blocks in the app's order, with their bytes | [tank-g.md](../tank-g.md) |
| `preset-grid.svg` | presets 1A–9D and their indexes 0–35 | [tank-g.md](../tank-g.md) |
| `typed-knob-sweep.svg` | how MOD FX, DLY MIX and RVB DECAY split 0–127 into three types | [effect-types.md](../effect-types.md) |

The description text (`<desc>`) of `tankg-controls.svg` is checked against the panel data
(`openvave.protocol.PANEL_CONTROLS`) by `tests/unit/test_panel.py`: change both together.

Rules (from the project [constitution](../../.specify/memory/constitution.md)): no vendor artwork,
product photos, manual pages or app screenshots. Photos you took yourself of your own pedal are
welcome; strip location metadata (EXIF GPS) and anything identifying (serial-number stickers)
before adding them.
