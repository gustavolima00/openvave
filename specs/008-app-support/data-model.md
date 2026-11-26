# Data model: spec 008

No persistent data and no JSON document changes. Four in-memory shapes.

## PanelControl (`openvave.protocol.panel`, frozen dataclass)

| Field | Type | Meaning | Rules |
|---|---|---|---|
| `order` | `int` | place on the front panel, 0-based: knobs left to right (0–14), then footswitches left to right (15–18) | unique; `PANEL_CONTROLS[i].order == i` |
| `label` | `str` | the text printed at the control (`"RVB DECAY"`, `"A/REVERB"`) | non-empty, as in `docs/tank-g.md` |
| `group` | `str` | the printed group: `MASTER`, `CAB`, `REVERB`, `DELAY`, `MOD`, `AMP`, `GATE` | a footswitch's group is the block it switches |
| `kind` | `"knob"`, `"selector"` or `"footswitch"` | what the control is | agrees with the byte-map encoding of `field`: `CONTINUOUS` → knob, `SELECTOR` → selector, `SWITCH` → footswitch |
| `field` | `str` or `None` | byte-map name of the current-preset field it drives | `None` only for MASTER; otherwise a `CURRENT_PRESET` entry of `BYTE_MAP` |
| `offset` | `int` or `None` | preset byte of that field | `None` iff `field` is `None`; equals the byte-map entry's offset |

`PANEL_CONTROLS: tuple[PanelControl, ...]` holds the 19 rows of research R5.
`panel_control(field)` returns the row whose `field` equals the argument, else `None` (LED colour
bytes, global and status fields, unknown names, `None`).

Relationship: every `CURRENT_PRESET` byte-map entry with encoding `CONTINUOUS`, `SELECTOR` or
`SWITCH`, except `led_red`, `led_green` and `led_blue`, has exactly one `PanelControl`; MASTER is
the only `PanelControl` without an entry.

## PanelGroup (`openvave.protocol.panel`, frozen dataclass)

| Field | Type | Meaning | Rules |
|---|---|---|---|
| `name` | `str` | the printed group: `MASTER`, `CAB`, `REVERB`, `DELAY`, `MOD`, `AMP`, `GATE` | unique; every `PanelControl.group` is one of them |
| `order` | `int` | panel order of the group, 0-based | `PANEL_GROUPS[i].order == i`; follows the first control of each group |
| `enabled_field` | `str` or `None` | the current-preset field that says whether the group is enabled | a control of this group; `None` for MASTER |
| `enabled_rule` | `"switch"`, `"nonzero"` or `None` | `switch`: enabled when the byte is the field's on value; `nonzero`: enabled when the byte is not 0 | `None` iff `enabled_field` is `None` |
| `enabled_confidence` | `"confirmed"`, `"documented"` or `None` | evidence level of the rule | `None` iff `enabled_field` is `None`; GATE is `documented`, the other five `confirmed` |

`PANEL_GROUPS` holds the seven rows of research R11. `panel_group(name)` returns the row or
`None`.

`group_enabled(group, preset) -> bool | None`:

| Input | Result |
|---|---|
| `preset` is 21 zero bytes (the bypass placeholder) | `None` for every group |
| group without a rule (MASTER) | `None` |
| `switch` rule, byte = on value / off value / anything else | `True` / `False` / `None` |
| `nonzero` rule | `byte != 0` |
| unknown group name, or `preset` not 21 bytes | `ValueError` |

## Preset position

| Form | Values | Conversion |
|---|---|---|
| text | exactly `"1A"`…`"9D"`: one digit 1–9, one upper-case letter A–D | `preset_index(text)` = 4 × (digit − 1) + letter index |
| index | exactly the `int` values 0–35 (`bool` excluded) | `preset_position(index)` = `f"{index // 4 + 1}{'ABCD'[index % 4]}"` |

Any other value raises `ValueError` in both directions. For every index,
`preset_position(i) == PedalState(kind="normal", index=i, bank=i // 4).position`.

## Simulated pedal (a configured `FakeTransport`)

Built by `FakeTransport.simulated(path, …)`. Starting state (research R2, R3):

| Part | Address (type 4) | Size | Source |
|---|---|---|---|
| stored image | `0x00000000` | 758 B | `image` argument, else the recorded whole-image read, else generated |
| edit buffer (current preset) | `0x10000000` | 21 B | first recorded read (required) |
| global block | `0x20000000` | 4 B | first recorded read (required) |
| status byte (loopback) | `0xD0000000` | 1 B | first recorded read, else `00` |
| identity | — | — | recorded handshake reply (required) |
| device information | type 5 | 32 B | recorded reply, when present |

State transitions are those of `FakeTransport(apply_writes=True)` and are not changed by this
feature:

| Write | Effect on memory |
|---|---|
| knob block, block switch, LED colour | changes the edit buffer |
| preset select `i` | copies stored preset `i` into the edit buffer; global = bank, bank, slot; edit mode → normal |
| bypass | global slot `ff`, edit buffer zeroed; the next select leaves bypass |
| loopback | status byte |
| stored slot, stored image | changes the stored image |
| commit | counted in `commits` |

Fault options: `faults={kind: action}` with kind in `knob_block`, `block_switch`, `led_colour`,
`preset_select`, `bypass`, `loopback`, `stored_slot`, `commit`, `stored_image` and action in
`nak`, `no_reply`, `disconnect`, `corrupt`, `ignore`; each is used once.
