# openvave

Open-source, reverse-engineered protocol and client library for the **M-VAVE Tank-G** multi-effects pedal (Bluetooth / USB).

> Unofficial project. Not affiliated with or endorsed by M-VAVE / Cuvave.

## Goals

- Document the Tank-G communication protocol (BLE GATT services, MIDI/SysEx messages, USB).
- Read and write presets, effect blocks, parameters and global settings.
- Stream / control audio over Bluetooth where the hardware allows it.
- Provide a reusable library + CLI that other projects can build on.

## Status

Version 0.3.0 identifies a connected pedal, decodes every byte of the current preset and global
settings that is understood (all but 4 of 26), **backs up** the 36 stored presets, and makes its
first **writes**: one field of the current preset in the edit buffer, or a preset select. The
development version adds `preset save` and `preset restore`: openvave changes stored presets
**only** through those two commands, only with `--unsafe`, and always after an automatic, verified
backup; every other write is volatile. Every write openvave can send is listed, with its evidence, under "Write messages" in
[`command-layer.md`](specs/protocol/command-layer.md); nothing else can be encoded. Protocol notes
live in [`specs/protocol/`](specs/protocol/); feature specs are driven by
[Spec Kit](https://github.com/github/spec-kit).

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

### `openvave preset backup`

Take a backup before you write anything. It reads the 36 stored presets one by one and the whole
stored image, checks that both agree, and saves a JSON file
([schema](specs/003-preset-backup-edit-writes/contracts/backup.schema.json)). It only reads.

```text
$ openvave preset backup
Backup of TANK-Gv2 (firmware 96)   36 presets, header a5 5a
  1A  01 00 01 01 12 05 41 37 41 37 32 00 00 0c 28 35 0f 07 ff f7 00
  …
  9D  …
Cross-check with whole-image read: OK
Saved tankg-backup-20261117-100500.json
```

`--output PATH` picks the file (default `./tankg-backup-<date>-<time>.json`); an existing file is
kept unless you add `--force`. If the two reads disagree, no file is written and the exit code is
7. Two backups with no write in between are identical apart from `created_at`. The file is your
record of every stored preset, and `openvave preset restore` can write it back (below).

### Writing to the pedal: `openvave set`, `openvave preset reload`, `openvave preset select`

Backup first, then:

1. Leave the pedal in **normal mode** (as the phone app does) or put it in edit mode; both work.
   Writes are refused in tuner mode, while the pedal is bypassed, and in any state openvave does
   not recognise.
2. Check the write with `--dry-run`: it reads the pedal, prints the exact frame, and sends nothing.
3. Run the same command without `--dry-run`.
4. To undo, run **`openvave preset reload`**: it loads the current preset again from its stored
   copy. These writes are not saved; to keep the sound, save it on the pedal, in the phone app or
   with `openvave preset save --unsafe` (below).

```text
$ openvave set gain 90
Set gain 60 → 90   (current preset 1B, normal mode)
  write  00 59 22 16 00 00 04 04 00 00 10 0e 00 00 0f 04 5a 3c 46 32 32 00 00 00 00 05 04 07 76
  reply  00 59 00 01 00 00 00 ff   ACK
  after  [6] gain 90   applied
Not saved. Discard: openvave preset reload   Keep: openvave preset save --unsafe --experimental
```

The reverb decay knob runs through three reverb types, **room**, **spring** and **cloud** (as the
Tank-G manual names them; between two types the reverb is off). Give a position 1–40 inside a
type:

```text
$ openvave set reverb_decay 10 --type spring
Set reverb_decay 5 (room 6) → 53 (spring 10)   (current preset 1B, normal mode)
  write  00 59 22 16 00 00 04 04 00 00 10 0e 00 00 0f 04 3c 3c 46 32 32 00 00 00 00 35 04 07 64
  reply  00 59 00 01 00 00 00 ff   ACK
  after  [15] reverb_decay 53 (spring 10)   applied
Not saved. Discard: openvave preset reload   Keep: openvave preset save --unsafe --experimental
```

Without `--type` the preset keeps its current type (`set reverb_decay 20` on a room preset is
room 20); `--raw 53` writes the raw byte 0–127. `preset dump` and `watch` show the same reading
(`type: room 6`, `5 (room 6) → 64 (spring 21)`, `off` between types).

MOD FX and DLY MIX work the same way, with the manual's names: `set mod_fx 20 --type phaser`
(chorus, phaser, tremolo) and `set delay_mix 30 --type tape` (analog, tape, dual).

#### Several fields over one connection

Each `openvave set` connects, reads, writes and disconnects, which takes seconds per field on a
real pedal. To dial in a whole sound, give several `FIELD=VALUE` pairs to one `set`:

```text
$ openvave set gain=95 treble=58 reverb_decay=room:18 delay_on=on led_colour=#2040ff --experimental
Set 5 fields   (current preset 1B, normal mode)
  gain          60 → 95
  treble        60 → 58
  reverb_decay  5 (room 6) → 17 (room 18)
  delay_on      off → on
  led_colour    #431643 → #2040ff
  write  00 59 22 16 00 00 04 04 00 00 10 0e 00 00 0f 04 5f 3a 46 32 32 00 00 00 00 11 04 07 67   knob_block: gain, treble, reverb_decay
  reply  00 59 00 01 00 00 00 ff   ACK   applied
  write  00 59 22 09 00 00 04 02 00 00 10 01 00 00 01 e7   block_switch 2: delay_on
  reply  00 59 00 01 00 00 00 ff   ACK   applied
  write  00 59 22 0b 00 00 04 12 00 00 10 03 00 00 20 40 ff 77   led_colour: led_colour
  reply  00 59 00 01 00 00 00 ff   ACK   applied
  after  [2] delay_on on
         [6] gain 95
         [7] treble 58
         [15] reverb_decay 17 (room 18)
         [18] 32
         [19] 64
         [20] 255
Not saved. Discard: openvave preset reload   Keep: openvave preset save --unsafe --experimental
```

- All knob fields travel in **one** knob-block write, rebuilt from the edit-buffer read just
  before it; each block switch and the LED colour get their own write. Every write is
  acknowledged and checked by a re-read before the next one goes out.
- Typed knobs take `POSITION` (keep the current type), `TYPE:POSITION` (`reverb_decay=room:18`)
  or `raw:N` (`reverb_decay=raw:53`). Fields already at their value are skipped.
- The whole batch is refused, with nothing sent, if any field would be refused (out of range,
  `--experimental` missing for the block switches or the LED colour, tuner mode, bypass …).
  `--dry-run` prints every frame and the refusal; `--json` prints one document
  (`set-fields-result.schema.json`).
- If something fails mid-batch (NAK, lost connection, a write the re-read does not show), the
  rest is not sent, nothing is retried, and openvave lists each field as `applied`, `unknown`,
  `not applied` or `not sent`; `openvave preset reload` discards what was applied.
- The library call is `await pedal.set_fields({"gain": 95, "reverb_decay": ("room", 18),
  "delay_on": True}, experimental=True)` (`plan_set_fields` for the plan only).

```text
$ openvave preset reload
Reload 1B (index 1)   discards unsaved edits
  write  00 59 22 09 00 00 04 01 00 00 e0 01 00 00 01 18
  reply  00 59 00 01 00 00 00 ff   ACK
  now    bank 1, slot B   buffer = stored 1B   applied
```

`preset reload` sends nothing when there is nothing to discard. In edit mode it needs
`--discard-edits` (the pedal's own unsaved edits are lost too).

`set <field> <value>` changes one field of the current preset (`set field=value ...` several):

| Field | Value |
|---|---|
| `noise_gate`, `gain`, `treble`, `middle`, `bass`, `volume`, `mod_fx`, `mod_speed`, `delay_mix`, `delay_time`, `reverb_decay`, `reverb_mix` | 0–127 |
| `amp_type`, `ir_cab` | 0–8 |
| `amp_on`, `mod_on`, `delay_on`, `reverb_on` | `on` / `off` |
| `led_colour` | `#rrggbb` or `r,g,b` |

`preset select <position>` loads preset `1A`–`9D` (or index 0–35). In edit mode it is refused,
because the unsaved edits would be lost; `--discard-edits` selects anyway.

```text
$ openvave preset select 2C
Select 2C (index 6)   from 1B
  write  00 59 22 09 00 00 04 06 00 00 e0 01 00 00 01 13
  reply  00 59 00 01 00 00 00 ff   ACK
  now    bank 2, slot C   buffer = stored 2C   applied
```

Every write is checked: after the pedal's ACK, openvave reads the pedal again and reports
`applied` only if the change is there. A NAK (exit 7) or a write that did not apply (exit 8) is
reported with the raw bytes and is never retried.

**`--experimental`.** A write runs by default only when its message is `confirmed` (seen the same
way in two independent sessions on the pedal) and the firmware is 96. Today that is the knob
block (every knob and selector) and preset select. The block switches and `led_colour` are
`observed` (one session) and need `--experimental`, as does any write on other firmware. Whether
`led_colour` changes the preset's LED has not been seen yet: the bytes it writes are documented as
a hypothesis.

### Bypass and loopback (experimental): `openvave bypass`, `openvave loopback`

`bypass on` turns the whole pedal off (clean sound, LEDs off), as the app's BYPASS button does;
`bypass off <position>` leaves bypass by selecting that preset. While bypassed the pedal does not
report which slot was loaded, so `bypass on` prints the command to come back, and `bypass off`
needs the position. Both messages are not confirmed on the pedal by openvave yet, so `bypass on`
needs `--experimental` (`bypass off` is the confirmed preset select). `bypass on` works in normal
mode only; with unsaved edits it needs `--discard-edits`.

```text
$ openvave bypass on --experimental
Bypass on   (was 1B, normal mode)
  write  00 59 22 09 00 00 04 01 00 00 e1 01 00 00 01 17
  reply  00 59 00 01 00 00 00 ff   ACK
  now    bypass (slot ff, buffer all 00)   applied
Leave bypass: openvave bypass off 1B
```

`loopback on|off` switches the status byte the app calls Loopback (`0xD0000000`, `01` in every
session so far). What it does on the Tank-G, and whether it survives a power cycle, is not known
yet, so it needs `--experimental`. It reads the flag, writes one byte, reads it back, and is never
followed by a commit; an equal value sends nothing (`loopback is already on; nothing sent`).

Neither command saves anything. Both support `--dry-run`, `--json` and `--trace`.

### Saving and restoring stored presets (UNSAFE): `openvave preset save`, `openvave preset restore`

These are the only commands that change **stored** presets. Both need `--unsafe` ("I accept that a
stored preset is overwritten"), and while their messages are not yet confirmed by this project's
own gate sessions they also need `--experimental`. Before the first write each one takes a full
backup (the same reads and cross-check as `preset backup`) and saves it as
`tankg-backup-<date>-<time>-before-save.json` (or `-before-restore`) in `--backup-dir` (default:
the current directory; an existing file is never overwritten). If the backup fails, nothing is
written. There is no option to skip it.

`preset save [--to POSITION]` stores the current sound (the edit buffer) in the loaded slot, or in
`--to`. Normal mode only. The sequence is the phone app's: slot write, read the slot back (a
mismatch stops before the commit), 300 ms, commit, 100 ms, select, verify.

```text
$ openvave preset save --to 1C --unsafe --experimental
Save current sound to 1C (index 2)   UNSAFE: overwrites a stored preset
  [6] gain 60 → 90
Backup saved: tankg-backup-20261118-101500-before-save.json
A power loss during the next second has an unknown outcome.
  write  00 59 22 1d 00 00 04 2c 00 00 00 15 00 00 01 00 00 01 0f 04 5a 3c 46 32 32 00 00 00 00 05 04 07 43 16 43 b9   ACK
  wait   300 ms
  write  00 59 22 08 00 00 04 00 00 00 f0 00 00 00 0b   ACK   (commit)
  wait   100 ms
  write  00 59 22 09 00 00 04 02 00 00 e0 01 00 00 01 17   ACK   (select 1C)
  verify stored 1C = written bytes, pedal on 1C, buffer = stored   saved
```

`preset restore FILE (--slot POSITION | --all)` writes back an openvave backup file. The file is
checked before connecting (format version, 36 presets of 21 bytes, positions, header `a5 5a`,
image = header + presets); a file from another firmware needs `--experimental`. It lists the slots
that differ and sends nothing when none does. `--slot` uses the save sequence with the file's
bytes; `--all` writes the whole 758-byte image in one message, commits, selects the preset that
was loaded and compares a full read with the file. Every restore ends with a select, so unsaved
edits need `--discard-edits`.

The mute you may hear during the commit comes from the pedal. A power loss during the write has an
unknown outcome. Nothing is ever retried: if a step fails, the command lists every step
(acknowledged, no reply, not sent), says whether stored presets may have changed, and prints the
two recovery commands (`openvave preset backup`, `openvave preset restore <automatic backup>
--all --unsafe`). `--dry-run` prints every frame (the image in full) and takes no backup.

### Options

`--json`, `--device ID`, `--scan-timeout SECONDS` (default 5: the most a scan waits; it stops 1 s
after the pedal is seen, or at once with `--device`), `--timeout SECONDS` (default 2)
and `--trace` (hex of every frame on stderr) work on every command, before or after it. The full
list is in [the CLI contract](specs/001-readonly-ble-connection/contracts/cli.md) and its
[0.2.0](specs/002-preset-byte-map/contracts/cli.md) and
[0.3.0](specs/003-preset-backup-edit-writes/contracts/cli.md) additions.

### JSON output

With `--json`, stdout carries exactly one JSON document on success and nothing on failure
(`watch --json` is the exception: one JSON line per event).
Schemas: [`info`](specs/001-readonly-ble-connection/contracts/info.schema.json),
[`preset dump`](specs/001-readonly-ble-connection/contracts/preset-dump.schema.json), each
decoded field [`fields[]`](specs/002-preset-byte-map/contracts/decoded-field.schema.json),
[`preset backup`](specs/003-preset-backup-edit-writes/contracts/backup.schema.json) and the
[`set` / `preset select` / `preset reload` / `bypass` / `loopback` result](specs/004-remote-edit-save-restore/contracts/write-result.schema.json)
and the [`preset save` / `preset restore` result](specs/004-remote-edit-save-restore/contracts/sequence-result.schema.json)
(a save or restore that stops mid-sequence still prints its document, with every step's status).
`info` and `preset dump` add a top-level `pedal_state` (`normal`, `edit`, `tuner`, `bypass`,
`loading`, `unrecognised`), and so do `watch --json` start and change events. Bytes
are lowercase, space-separated hex.

Every document has `"schema_version": 2` (0.2.0 renamed two fields; see the
[CHANGELOG](CHANGELOG.md)). New fields (for example newly understood bytes in
`fields`) may be added without changing it; removing or renaming a field, or changing its type,
bumps `schema_version`.

### Exit codes

`0` success · `1` internal error, or a write refused (tuner mode, bypassed or unrecognised pedal
state, edit mode for `bypass on`, `preset save` or `preset restore`, not bypassed for `bypass
off`, out of range, untested firmware, `--experimental` or `--unsafe` needed, backup from another
firmware, edits would be discarded) · `2` usage error (also `bypass off` without a position, an
invalid restore file, `--slot` and `--all` both or neither) · `3` no pedal
found · `4` more than one pedal (use `--device`) · `5` Bluetooth unavailable or permission denied ·
`6` connection lost or timed out · `7` protocol error, NAK or backup cross-check mismatch · `8`
write acknowledged but not applied. Details in the
[CLI contract](specs/001-readonly-ble-connection/contracts/cli.md#exit-codes) and its
[0.3.0 additions](specs/003-preset-backup-edit-writes/contracts/cli.md#exit-codes-additions).

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

`TankG.watch()` yields the same events as `openvave watch`; `backup()`, `plan_set()` /
`set_field()`, `plan_select()` / `select_preset()`, `plan_reload()` / `reload_preset()`,
`plan_bypass_on()` / `bypass_on()` (its result's `return_index` is the preset to return to),
`plan_bypass_off(i)` / `bypass_off(i)`, `plan_loopback(on)` / `set_loopback(on)`, `plan_save()` /
`save_preset()` and `plan_restore(backup, slot=i | all=True)` / `restore()` do what the matching
commands do (writes take `experimental=True` where the CLI needs `--experimental`; save and restore
take `unsafe=True` and a required `on_backup` callback that receives the automatic backup before
the first write). See the
library contracts ([0.1.0](specs/001-readonly-ble-connection/contracts/library-api.md),
[0.2.0](specs/002-preset-byte-map/contracts/library-api.md) and
[0.3.0](specs/003-preset-backup-edit-writes/contracts/library-api.md) additions), including how to
test against `FakeTransport` without a pedal.

## Development

```bash
uv sync
uv run pytest                          # hardware-free
uv run pytest --hardware tests/hardware  # needs a Tank-G nearby
```

## License

MIT — see [LICENSE](LICENSE).
