# openvave

Open-source, reverse-engineered protocol and client library for the **M-VAVE Tank-G** multi-effects pedal (Bluetooth / USB).

> Unofficial project. Not affiliated with or endorsed by M-VAVE / Cuvave.

## Goals

- Document the Tank-G communication protocol (BLE GATT services, MIDI/SysEx messages, USB).
- Read and write presets, effect blocks, parameters and global settings.
- Stream / control audio over Bluetooth where the hardware allows it.
- Provide a reusable library + CLI that other projects can build on.

## Status

Version 0.1.0 is **read-only**: it identifies a connected pedal and reads its state over BLE.
It can only send the handshake query (`0x11`) and region reads (`0x23`); nothing that writes to
the pedal exists in the code. Protocol notes live in [`specs/protocol/`](specs/protocol/); feature
specs are driven by [Spec Kit](https://github.com/github/spec-kit).

| Platform | Status |
|---|---|
| macOS | Verified on hardware (macOS 26, firmware 96) |
| Linux, Windows | Should work through [bleak](https://github.com/hbldh/bleak); untested on hardware |

Tested firmware: **96**. Other versions still work but print a `warning:` line on stderr.

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
  one BLE connection at a time, and the app holds it.
- **macOS**: the app you run `openvave` from (Terminal, iTerm, your IDE) needs Bluetooth permission
  under System Settings → Privacy & Security → Bluetooth. macOS asks the first time; if you denied
  it, `openvave` exits with code 5 and a hint. A host app with no Bluetooth usage description at all
  may be stopped by macOS before `openvave` can report anything.

## Usage

### `openvave info`

Identifies the pedal and reads its device info, global settings and status:

```text
$ openvave info
Device     TANK-Gv2  (firmware 96)
Address    3F1A…  (TANK-Gv2_BLE, -58 dBm)

Device info   type 5 @ 0xD0000000, 32 bytes   [meaning: unknown]
  00: 0a 30 39 36 00 00 00 00 00 00 00 00 00 00 00 00
  10: 00 00 00 b7 43 f3 00 00 00 00 00 00 00 00 00 00
Global        type 4 @ 0x20000000, 4 bytes    [meaning: unknown]
  00: 00 00 01 01
      [3] not in edit mode = 1   (observed)
Status        type 4 @ 0xD0000000, 1 byte     [meaning: unknown]
  00: 01
```

### `openvave preset dump`

Prints the 21-byte buffer of the preset that is currently loaded. The pedal is read every time;
nothing is cached.

```text
$ openvave preset dump
Current preset  (TANK-Gv2, firmware 96)   type 4 @ 0x10000000, 21 bytes
  00: 01 00 00 01 0f 04 3c 3c 46 32 32 00 00 00 00 05
  10: 04 07 43 16 43
      [6] knob (which one: unknown) = 60   (observed)
      [16] reverb mix? = 4   (hypothesis)
      [17] IR cab? = 7   (hypothesis)
```

Field labels carry a confidence level (`confirmed`, `observed`, `hypothesis`). Bytes without a
label are not understood yet.

### Options

`--json`, `--device ID`, `--scan-timeout SECONDS` (default 5), `--timeout SECONDS` (default 2)
and `--trace` (hex of every frame on stderr) work on every command, before or after it. The full
list is in [the CLI contract](specs/001-readonly-ble-connection/contracts/cli.md).

### JSON output

With `--json`, stdout carries exactly one JSON document on success and nothing on failure.
Schemas: [`info`](specs/001-readonly-ble-connection/contracts/info.schema.json),
[`preset dump`](specs/001-readonly-ble-connection/contracts/preset-dump.schema.json). Bytes are
lowercase, space-separated hex.

Every document has `"schema_version": 1`. New fields (for example newly understood bytes in
`fields`) may be added without changing it; removing or renaming a field, or changing its type,
bumps `schema_version`.

### Exit codes

`0` success · `1` internal error · `2` usage error · `3` no pedal found · `4` more than one pedal
(use `--device`) · `5` Bluetooth unavailable or permission denied · `6` connection lost or timed
out · `7` protocol error. Details in the
[CLI contract](specs/001-readonly-ble-connection/contracts/cli.md#exit-codes).

### Library

```python
import asyncio
from openvave import Region, TankG


async def main() -> None:
    async with TankG.connect() as pedal:
        print(pedal.identity.name, pedal.identity.firmware)
        preset = await pedal.read(Region.CURRENT_PRESET)
        print(preset.data.hex(" "))


asyncio.run(main())
```

See [the library contract](specs/001-readonly-ble-connection/contracts/library-api.md), including
how to test against `FakeTransport` without a pedal.

## Development

```bash
uv sync
uv run pytest                          # hardware-free
uv run pytest --hardware tests/hardware  # needs a Tank-G nearby
```

## License

MIT — see [LICENSE](LICENSE).
