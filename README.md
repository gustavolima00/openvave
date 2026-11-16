# openvave

Open-source, reverse-engineered protocol and client library for the **M-VAVE Tank-G** multi-effects pedal (Bluetooth / USB).

> Unofficial project. Not affiliated with or endorsed by M-VAVE / Cuvave.

## Goals

- Document the Tank-G communication protocol (BLE GATT services, MIDI/SysEx messages, USB).
- Read and write presets, effect blocks, parameters and global settings.
- Stream / control audio over Bluetooth where the hardware allows it.
- Provide a reusable library + CLI that other projects can build on.

## Status

Version 0.2.0 is **read-only**: it identifies a connected pedal, reads its state over BLE and
decodes every byte of the current preset and global settings that is understood (all but 4 of
26). It can only send the handshake query (`0x11`) and region reads (`0x23`); nothing that writes to
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
      [0]  browsed bank                   0    0–8        observed
      [1]  bank                           0    0–8        observed
      [2]  slot                           1    0–3        observed
      [3]  mode                      normal    selector   confirmed
Status        type 4 @ 0xD0000000, 1 byte     [meaning: unknown]
  00: 01
      unknown: 0
```

Bank and slot are 0-based: bank 0, slot 1 is preset 1B on the pedal.

### `openvave preset dump`

Prints the 21-byte buffer of the preset that is currently loaded. The pedal is read every time;
nothing is cached.

```text
$ openvave preset dump
Current preset  (TANK-Gv2, firmware 96)   type 4 @ 0x10000000, 21 bytes
  00: 01 00 00 01 0f 04 3c 3c 46 32 32 00 00 00 00 05
  10: 04 07 43 16 43
      [0]  amp on                        on    on/off     confirmed
      [1]  mod on                       off    on/off     confirmed
      [2]  delay on                     off    on/off     confirmed
      [3]  reverb on                     on    on/off     confirmed
      [4]  noise gate                    15    0–127      confirmed
      [5]  amp type                      #4    selector   confirmed
      [6]  gain                          60    0–127      confirmed
      …
      [15] reverb decay                   5    0–127      confirmed
      [16] reverb mix                     4    0–127      confirmed
      [17] IR cab                        #7    selector   confirmed
      unknown: 18 19 20
```

Each decoded line shows `[offset]`, the field, its value, the documented range and how sure we
are about it:

- `confirmed`: seen the same way in two independent sessions on the pedal.
- `observed`: seen once, with a committed capture as evidence.
- `hypothesis`: a guess not yet tested; the line ends with ` ?`.

A value outside the documented range is shown raw with `OUT OF RANGE` (it is never clamped).
`unknown:` lists the bytes whose meaning is not known yet. On firmware other than 96 the header
says `(decoded with the fw 96 map)`. The byte map and its evidence are in
[`command-layer.md`](specs/protocol/command-layer.md).

### `openvave watch`

Watches the pedal while you use it and prints every byte that changes. It is how the byte map
was built: move one control, see which byte moves.

```text
$ openvave watch
Watching TANK-Gv2 (firmware 96), every 0.5 s. Type a label and Enter before each step; q to quit.
Recording to captures/private/20261117-101500-watch.jsonl
  global  00 00 01 01   browsed bank = 0, bank = 0, slot = 1, mode = normal
  preset  01 00 00 01 0f 04 3c 3c 46 32 32 00 00 00 00 05 04 07 43 16 43
  status  01
edit mode on
── label: edit mode on ──
 +3.02s  global[3]   mode              normal → edit
reverb decay min→max
── label: reverb decay min→max ──
 +9.51s  preset[15]  reverb decay         5 → 64
+10.02s  preset[15]  reverb decay        64 → 127
q
Stopped after 34.0 s: 3 changes in 3 cycles. Record: captures/private/20261117-101500-watch.jsonl
```

- **Labels**: type a short description and Enter before each step. It is attached to every
  change until the next label. `q` or `quit` stops (so do Ctrl-C and `--duration SECONDS`).
- Bytes that change in the same poll are marked `(co-moving: N)`.
- Only reads are sent, every `--interval` seconds (default 0.5, minimum 0.2). Changing knobs in
  edit mode and leaving without saving keeps the stored preset as it was.
- **Records**: each session is written, line by line, to
  `captures/private/<date>-watch.jsonl` (or `--record PATH`; `--no-record` for none).
  `captures/private/` is git-ignored: records stay on your machine. Labels are stored as typed,
  so keep personal names out of them if you plan to share an excerpt.
- `--json` prints JSON Lines, one event per line
  ([schema](specs/002-preset-byte-map/contracts/watch-event.schema.json)).

### Options

`--json`, `--device ID`, `--scan-timeout SECONDS` (default 5), `--timeout SECONDS` (default 2)
and `--trace` (hex of every frame on stderr) work on every command, before or after it. The full
list is in [the CLI contract](specs/001-readonly-ble-connection/contracts/cli.md) and
[its 0.2.0 additions](specs/002-preset-byte-map/contracts/cli.md).

### JSON output

With `--json`, stdout carries exactly one JSON document on success and nothing on failure
(`watch --json` is the exception: one JSON line per event).
Schemas: [`info`](specs/001-readonly-ble-connection/contracts/info.schema.json),
[`preset dump`](specs/001-readonly-ble-connection/contracts/preset-dump.schema.json), and each
decoded field [`fields[]`](specs/002-preset-byte-map/contracts/decoded-field.schema.json). Bytes
are lowercase, space-separated hex.

Every document has `"schema_version": 2` (0.2.0 renamed two fields; see the
[CHANGELOG](CHANGELOG.md)). New fields (for example newly understood bytes in
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
from openvave.protocol import decode_region


async def main() -> None:
    async with TankG.connect() as pedal:
        print(pedal.identity.name, pedal.identity.firmware)
        preset = await pedal.read(Region.CURRENT_PRESET)
        for field in decode_region(preset, pedal.identity.firmware).fields:
            print(field.entry.name, field.display, field.entry.confidence)


asyncio.run(main())
```

`TankG.watch()` yields the same events as `openvave watch`. See the library contracts
([0.1.0](specs/001-readonly-ble-connection/contracts/library-api.md),
[0.2.0 additions](specs/002-preset-byte-map/contracts/library-api.md)), including how to test
against `FakeTransport` without a pedal.

## Development

```bash
uv sync
uv run pytest                          # hardware-free
uv run pytest --hardware tests/hardware  # needs a Tank-G nearby
```

## License

MIT — see [LICENSE](LICENSE).
