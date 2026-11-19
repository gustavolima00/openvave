# openvave

Open-source, reverse-engineered protocol and client library for the **M-VAVE Tank-G** multi-effects pedal (Bluetooth / USB).

> Unofficial project. Not affiliated with or endorsed by M-VAVE / Cuvave.

## Goals

- Document the Tank-G communication protocol (BLE GATT services, MIDI/SysEx messages, USB).
- Read and write presets, effect blocks, parameters and global settings.
- Stream / control audio over Bluetooth where the hardware allows it.
- Provide a reusable library + CLI that other projects can build on.

## Status

Version 0.5.0 finds and remembers pedals (`scan`, `select`, `device`, `forget`) and never connects
to a pedal you did not choose. It identifies a connected pedal, decodes every byte of the current preset and global
settings that is understood (all but 4 of 26) and **backs up** the 36 stored presets. It edits the
current preset **remotely in normal mode**, as the phone app does (one field, or several over one
connection), discards those edits with `preset reload`, selects presets, switches **bypass** and
**loopback**, and is the first release that can **change stored presets**:
`preset save` and `preset restore`. openvave changes stored presets **only** through those two
commands, only with `--unsafe`, and always after an automatic, verified backup; every other write
is volatile (see [Safety](docs/safety.md)). Every write openvave can send is listed, with its
evidence, under "Write messages" in [`command-layer.md`](specs/protocol/command-layer.md); nothing
else can be encoded. Protocol notes live in [`specs/protocol/`](specs/protocol/); feature specs are
driven by [Spec Kit](https://github.com/github/spec-kit).

| Platform | Status |
|---|---|
| macOS | Verified on hardware (macOS 26, firmware 96) |
| Linux, Windows | Should work through [bleak](https://github.com/hbldh/bleak); untested on hardware |

Tested firmware: **96**. Other versions still work but print a `warning:` line on stderr, and every
write on them needs `--experimental`.

## Documentation

**[docs/](docs/README.md)** explains the pedal, the CLI and the library:

- [Getting started](docs/getting-started.md): install, connect, first commands, exit codes.
- [The Tank-G explained](docs/tank-g.md): every control mapped to its field and preset byte, the
  effect chain, the 36 presets, modes, bypass, loopback.
- [Effect types](docs/effect-types.md): chorus/phaser/tremolo, analog/tape/dual and
  room/spring/cloud on the MOD FX, DLY MIX and RVB DECAY knobs.
- [Recipes](docs/recipes.md): dial in a sound, switch presets, bypass, back up, save, restore.
- [Safety](docs/safety.md) · [Library guide](docs/library.md) ·
  [CLI reference](docs/cli-reference.md) · [Examples](docs/examples/)

## Install

Requires Python 3.11 or newer.

```bash
uv tool install git+https://github.com/gustavolima00/openvave
```

or, with pip:

```bash
pip install git+https://github.com/gustavolima00/openvave
```

From a checkout, `uv sync` then prefix the commands below with `uv run`.

### Before you connect

- **Close the M-VAVE / M-effects phone app** (or turn off Bluetooth on the phone). The pedal accepts
  one BLE connection at a time, and the app holds it. A connected pedal also stops advertising, so
  `openvave scan` does not list it (the same holds while another `openvave` command is connected).
- **macOS**: the app you run `openvave` from (Terminal, iTerm, your IDE) needs Bluetooth permission
  under System Settings → Privacy & Security → Bluetooth. macOS asks the first time; if you denied
  it, `openvave` exits with code 5 and a hint.

## Finding and choosing a pedal

```bash
openvave scan                     # every Tank-G in range, strongest first; connects to nothing
openvave scan --identify          # ...and each one's firmware (handshake only)
openvave select --name stage      # make the only pedal in range the default, nicknamed "stage"
openvave select 8F3A              # or pick one by identifier prefix (≥ 4 hex digits) or nickname
openvave device                   # the default, the known pedals, the configuration file
openvave device --check           # is the default in range?
openvave device rename stage live
openvave forget                   # clear the default (forget NAME removes one, --all every one)
```

Every pedal command chooses its pedal in this order: `--device ID|NICKNAME`, then the
`OPENVAVE_DEVICE` environment variable, then the default (`openvave select`), then the only Tank-G
in range. It says which one on stderr (`pedal: stage  8F3A21C4…  -58 dBm  (selected)`) and
**never falls back**: if the chosen pedal is not seen it exits 3 and lists what it did see.
Known pedals live in `~/.config/openvave/devices.json` (`$XDG_CONFIG_HOME`, `%APPDATA%` on
Windows; `OPENVAVE_CONFIG` sets another path). On macOS the identifier is a per-computer UUID,
not the pedal's MAC address, so a selection does not carry over to another computer.

openvave holds the pedal only while a command runs; there is nothing to disconnect. Details:
[Getting started](docs/getting-started.md#finding-the-pedal), and the 0.5.0
[CLI contract](specs/005-device-selection/contracts/cli.md) with its
[`scan`](specs/005-device-selection/contracts/scan.schema.json),
[`device`](specs/005-device-selection/contracts/device.schema.json) and
[configuration file](specs/005-device-selection/contracts/devices-file.schema.json) schemas.

## Quick tour

```bash
openvave info                     # identify the pedal: firmware, mode, loaded preset
openvave preset dump              # the current sound, byte by byte, decoded
openvave watch                    # move a control on the pedal, see which byte moves
openvave preset backup            # all 36 stored presets to a verified JSON file (read-only)

openvave set gain=95 treble=58 reverb_decay=spring:10   # change the current sound (not saved)
openvave preset reload            # ...and throw those changes away
openvave preset select 2C         # load another preset
openvave bypass on                # clean sound; it prints the command to come back

openvave preset save --to 1C --unsafe   # store the current sound (automatic backup first)
```

```text
$ openvave set gain 90
Set gain 60 → 90   (current preset 1B, normal mode)
  write  00 59 22 16 00 00 04 04 00 00 10 0e 00 00 0f 04 5a 3c 46 32 32 00 00 00 00 05 04 07 76
  reply  00 59 00 01 00 00 00 ff   ACK
  after  [6] gain 90   applied
Not saved. Discard: openvave preset reload   Keep: openvave preset save --unsafe
```

Every write command takes `--dry-run` (print the frame, send nothing). Messages not yet
`confirmed` need `--experimental`; anything that overwrites stored presets needs `--unsafe`. Add
`--json` to any command for machine-readable output. Details: [Recipes](docs/recipes.md),
[CLI reference](docs/cli-reference.md).

## Library

```python
import asyncio
from openvave import Region, TankG
from openvave.protocol import decode_region


async def main() -> None:
    async with TankG.connect() as pedal:
        print(pedal.identity.name, pedal.identity.firmware)
        preset = await pedal.read(Region.CURRENT_PRESET)
        for field in decode_region(preset, pedal.identity.firmware).fields:
            print(field.entry.name, field.display, field.entry.confidence)
        await pedal.set_fields({"gain": 95, "reverb_decay": ("spring", 10)})  # not saved


asyncio.run(main())
```

To keep one connection for many operations, open and close it yourself; `connect_selected()`
uses the pedal chosen with `openvave select`:

```python
pedal = TankG.connect_selected()
await pedal.open()
try:
    while pedal.is_connected:  # False once the link is lost
        print((await pedal.state()).kind)
        await asyncio.sleep(1)
finally:
    await pedal.close()  # idempotent; open() reconnects
```

A lost link makes every later operation raise `ConnectionLostError`; nothing is retried or
reconnected for you. See the [library guide](docs/library.md) and the 0.5.0
[library contract](specs/005-device-selection/contracts/library-api.md), including how to test against `FakeTransport` without a
pedal.

## Development

```bash
uv sync
uv run pytest                          # hardware-free
uv run pytest --hardware tests/hardware  # needs a Tank-G nearby
```

## License

MIT — see [LICENSE](LICENSE).
