# openvave documentation

openvave talks to the **M-VAVE Tank-G** guitar multi-effects pedal over Bluetooth LE: it reads
the pedal, backs up its 36 presets, changes the current sound remotely, and (behind `--unsafe`)
saves and restores stored presets. These pages explain the pedal, the command-line tool and the
Python library. They describe version **0.4.0**, tested on firmware **96**.

> Unofficial project. Not affiliated with or endorsed by M-VAVE / Cuvave. Every diagram here is an
> original drawing; no vendor photos, manual pages or app screenshots are used.

## For Tank-G owners

1. [Getting started](getting-started.md): install, connect, first commands, troubleshooting.
2. [The Tank-G explained](tank-g.md): every control and the field and byte behind it, the effect
   chain, the 36 presets, modes, bypass and loopback.
3. [Effect types](effect-types.md): how the MOD FX, DLY MIX and RVB DECAY knobs each hold three
   effect types, and how to pick one.
4. [Recipes](recipes.md): dial in a sound, switch presets, bypass, back up, save, restore.
5. [Safety](safety.md): what openvave can and cannot change, and the opt-ins that guard it.

## For developers

- [Library guide](library.md): the async `TankG` session, reading and decoding, plan vs apply,
  errors and partial results, testing without a pedal.
- [CLI reference](cli-reference.md): every command and option, exit codes, JSON schemas.
- [Runnable examples](examples/): `read_preset.py` (runs offline with `--fake`),
  `dial_in_sound.py`, `backup_and_save.py`.
- The protocol itself, byte by byte, with evidence for every claim:
  [`specs/protocol/`](../specs/protocol/) ([command layer](../specs/protocol/command-layer.md),
  [BLE GATT](../specs/protocol/ble-gatt.md), [what the official app does](../specs/protocol/app-features.md)).

## Confidence labels

You will see three words throughout openvave's output and these pages. They come from the
project's evidence rules:

| Label | Meaning |
|---|---|
| `confirmed` | Seen the same way in two independent sessions on a real pedal. |
| `observed` | Seen once, with a committed capture as evidence. |
| `hypothesis` | A reasoned guess, not yet tested on the pedal. |

Writes whose message is not `confirmed` need `--experimental`; see [Safety](safety.md).
