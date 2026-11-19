# Getting started

## Install

openvave needs Python 3.11 or newer. It installs one command, `openvave`, and the `openvave`
Python package.

```bash
uv tool install git+https://github.com/gustavolima00/openvave
```

or with pip:

```bash
pip install git+https://github.com/gustavolima00/openvave
```

From a checkout of the repository, run `uv sync` once and prefix every command with `uv run`
(`uv run openvave info`).

| Platform | Status |
|---|---|
| macOS | Verified on hardware (macOS 26, firmware 96) |
| Linux, Windows | Should work through [bleak](https://github.com/hbldh/bleak); untested on hardware |

## Before you connect

- **Close the phone app.** The Tank-G accepts one Bluetooth LE connection at a time, and the
  M-VAVE / M-effects app keeps it while it is open. Close the app or turn off Bluetooth on the
  phone.
- **macOS Bluetooth permission.** The app you run `openvave` from (Terminal, iTerm, your editor)
  needs Bluetooth access under System Settings → Privacy & Security → Bluetooth. macOS asks the
  first time. If access was denied, `openvave` exits with code 5 and a hint. A host app that
  declares no Bluetooth use at all may be stopped by macOS before openvave can print anything.
- **Power the pedal on** and keep it within a few metres.

## Finding the pedal

Every command scans for pedals advertising the name `TANK-Gv2_BLE`, connects to one, and runs the
pedal's handshake. With one pedal nearby you need no options. To see what is in range without
connecting:

```text
$ openvave scan
Scanning for 5 s…
8F3A21C4-0000-4000-8000-000000000001  TANK-Gv2_BLE  -57 dBm
1 pedal found. Select one: openvave select 8F3A21C4-0000-4000-8000-000000000001
```

`openvave scan --identify` also connects to each pedal in turn and shows its firmware (`fw 96`).
The identifier is what `info` prints on its `Address` line (`device.identifier` in `--json`). On
macOS it is a per-computer UUID, not the pedal's MAC address.

### Choosing a pedal

`openvave select` remembers a pedal as the **default**, with an optional nickname:

```bash
openvave select --name stage        # the only pedal in range
openvave select 8F3A --name home    # an identifier prefix (≥ 4 hex digits) or a full identifier
openvave select stage               # a known nickname (no scan)
openvave device                     # what is chosen, every known pedal, the file's path
openvave device --check             # scan for the default: In range: yes (-58 dBm)
openvave device rename home rehearsal
openvave forget                     # clear the default; forget NAME removes one; forget --all
```

Each pedal command then picks its pedal in this order, first present wins:

1. `--device ID|NICKNAME` on the command line;
2. the `OPENVAVE_DEVICE` environment variable (same values);
3. the default (`openvave select`);
4. the only Tank-G in range (several: exit 4).

It prints which one on stderr before connecting, e.g. `pedal: stage  8F3A21C4…  -58 dBm
(selected)`. When a pedal is chosen, openvave **never connects to another one**: if it is not
seen within `--scan-timeout`, the command exits 3 and lists the pedals it did see. Neither
`--device` nor `OPENVAVE_DEVICE` changes what is saved.

Known pedals are kept in `~/.config/openvave/devices.json` (`$XDG_CONFIG_HOME/openvave/` when set,
`%APPDATA%\openvave\` on Windows); `OPENVAVE_CONFIG` points at another file. openvave holds the
pedal only while a command runs; the default is a choice, not an open connection, so there is
nothing to disconnect.

| Option | Default | What it does |
|---|---|---|
| `--scan-timeout SECONDS` | 5 | The longest a scan waits. It stops as soon as the chosen pedal is seen (1 s after the first pedal when none is chosen). |
| `--device ID\|NICKNAME` | none | Use this pedal for one command. An identifier is connected to whatever its name. |
| `--timeout SECONDS` | 2 | How long to wait for each reply. |
| `--trace` | off | Print the hex of every frame sent and received on stderr. |

These options work before or after the command (`openvave --trace info` and `openvave info
--trace` are the same).

## Your first commands

None of these write anything to the pedal.

### `openvave info`: is it there?

```text
$ openvave info
Device     TANK-Gv2  (firmware 96)
Address    3F1A…  (TANK-Gv2_BLE, -58 dBm)
state: normal, preset 1B

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
      [0]  loopback                      on    on/off     confirmed
```

The `state:` line is the quickest summary: the pedal is in normal mode on preset 1B. Bank and slot
in the raw lines are 0-based (bank 0, slot 1 = 1B). A firmware other than 96 still works, with a
`warning:` line on stderr.

### `openvave preset dump`: what is the current sound?

```text
$ openvave preset dump
Current preset  (TANK-Gv2, firmware 96)   type 4 @ 0x10000000, 21 bytes
state: normal, preset 1B
  00: 01 00 00 01 0f 04 3c 3c 46 32 32 00 00 00 00 05
  10: 04 07 43 16 43
      [0]  amp on                        on    on/off     confirmed
      [1]  mod on                       off    on/off     confirmed
      [2]  delay on                     off    on/off     confirmed
      [3]  reverb on                     on    on/off     confirmed
      [4]  noise gate                    15    0–127      confirmed
      [5]  amp type                      #4    selector   confirmed
      [6]  gain                          60    0–127      confirmed
      [7]  treble                        60    0–127      confirmed
      [8]  middle                        70    0–127      confirmed
      [9]  bass                          50    0–127      confirmed
      [10] volume                        50    0–127      confirmed
      [11] mod fx                         0    0–127      confirmed  type: chorus 1
      [12] mod speed                      0    0–127      confirmed
      [13] delay mix                      0    0–127      confirmed  type: analog 1
      [14] delay time                     0    0–127      confirmed
      [15] reverb decay                   5    0–127      confirmed  type: room 6
      [16] reverb mix                     4    0–127      confirmed
      [17] IR cab                        #7    selector   confirmed
      [18] LED red                       67    0–255      confirmed
      [19] LED green                     22    0–255      confirmed
      [20] LED blue                      67    0–255      confirmed  LED colour #431643
```

Each line is `[byte]  field  value  range  confidence`. Knob values are the raw 0–127 numbers,
with no unit. `#4` is a stepped selector position (0–8). `type: room 6` reads a typed knob as an
effect type and a position (see [Effect types](effect-types.md)); IR cab `0` shows as `off`. Bytes
18–20 are the preset's footswitch LED colour, also shown as `#rrggbb`. The 21 bytes are explained in
[The Tank-G explained](tank-g.md).

A value outside its documented range is printed raw with `OUT OF RANGE`, never clamped. On
firmware 96 every byte of the global block, the preset and the status byte is named; a byte whose
meaning were unknown would be listed on an `unknown:` line.

### `openvave watch`: see what each control does

`watch` polls the pedal (reads only) and prints every byte that changes. Type a short label and
Enter before each step; `q` stops.

```text
$ openvave watch
Watching TANK-Gv2 (firmware 96), every 0.5 s. Type a label and Enter before each step; q to quit.
Recording to captures/private/20261117-101500-watch.jsonl
  global  00 00 01 01   browsed bank = 0, bank = 0, slot = 1, mode = normal
  preset  01 00 00 01 0f 04 3c 3c 46 32 32 00 00 00 00 05 04 07 43 16 43
  status  01
  state   normal, preset 1B
edit mode on
── label: edit mode on ──
 +3.02s  global[3]   mode              normal → edit
 +3.02s  state: edit, preset 1B
reverb decay min→max
── label: reverb decay min→max ──
 +9.51s  preset[15]  reverb decay      5 (room 6) → 64 (spring 21)
+10.02s  preset[15]  reverb decay      64 (spring 21) → 127 (cloud 40)
q
Stopped after 34.0 s: 3 changes in 67 cycles. Record: captures/private/20261117-101500-watch.jsonl
```

The lines `edit mode on`, `reverb decay min→max` and `q` are what you type. Bytes that change in
the same poll are marked `(co-moving: N)`. Pedal edits are not pushed to the computer; `watch` sees
them because it re-reads.

Options: `--interval SECONDS` (default 0.5, minimum 0.2), `--duration SECONDS`, `--record PATH`
or `--no-record`, `--json` (one JSON line per event). Records go to `captures/private/` under the
current directory, which the repository ignores; labels are stored as typed, so leave personal
names out if you plan to share one.

### Take a backup

Before you change anything, save all 36 stored presets to a file. It only reads.

```bash
openvave preset backup
```

See [Recipes → Back up](recipes.md#back-up-all-36-presets).

## When something goes wrong

| Exit | Meaning | What to try |
|---|---|---|
| 0 | Success | |
| 1 | Internal error, or a write openvave refused (the message names the reason) | Read the `error: refused (...)` line; see [Safety](safety.md). |
| 2 | Usage error (bad option or value, invalid restore file, unknown nickname, invalid configuration file) | `openvave COMMAND --help`; `openvave forget --all` resets a broken configuration file. |
| 3 | No pedal found, or the chosen pedal was not seen | Is it on? Is the phone app (or another `openvave`) connected to it? A connected pedal stops advertising. Try `--scan-timeout 10`. |
| 4 | More than one pedal and none chosen | `openvave select ID`, or `--device ID` for one command. |
| 5 | Bluetooth unavailable or permission denied | Turn Bluetooth on; grant the permission (macOS). |
| 6 | Connection lost or timed out | Move closer; try `--timeout 4`. |
| 7 | Protocol error, NAK, or backup cross-check mismatch | Re-run with `--trace` and report it. |
| 8 | A write was acknowledged but the re-read does not show it | The pedal may have been touched meanwhile; check with `preset dump`. |

`OPENVAVE_DEBUG=1` prints a Python traceback for unexpected errors.

Next: [The Tank-G explained](tank-g.md).
