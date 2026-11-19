# Recipes

Every example below is real `openvave` 0.4.0 output on a pedal (or its test double) sitting on
preset 1B in normal mode. Hex frames are what is sent over Bluetooth; you can ignore them.

Before you start writing, take a [backup](#back-up-all-36-presets). Add `--dry-run` to any write
command to see what it would send without sending it.

- [Dial in a sound (several fields at once)](#dial-in-a-sound)
- [Change one field](#change-one-field)
- [Undo: go back to the stored preset](#undo-go-back-to-the-stored-preset)
- [Switch presets](#switch-presets)
- [Bypass](#bypass)
- [Back up all 36 presets](#back-up-all-36-presets)
- [Save the current sound to a preset (UNSAFE)](#save-the-current-sound-unsafe)
- [Restore presets from a backup (UNSAFE)](#restore-presets-from-a-backup-unsafe)
- [Copy, swap, share a preset (UNSAFE)](#copy-swap-share-a-preset-unsafe)
- [Loopback](#loopback)
- [Scripting with JSON](#scripting-with-json)

## Dial in a sound

Give `set` several `FIELD=VALUE` pairs. openvave connects once, reads the preset, and sends all
knob fields in a single write, then each block switch and the LED colour separately. Every write is
acknowledged and checked by re-reading before the next one goes out.

```text
$ openvave set gain=95 treble=58 reverb_decay=room:18 delay_on=on led_colour=#2040ff
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
Not saved. Discard: openvave preset reload   Keep: openvave preset save --unsafe
```

| Field | Value |
|---|---|
| `noise_gate`, `gain`, `treble`, `middle`, `bass`, `volume`, `mod_speed`, `delay_time`, `reverb_mix` | 0–127 |
| `mod_fx`, `delay_mix`, `reverb_decay` | `POSITION` (1–40, keep the type), `TYPE:POSITION`, or `raw:N` (0–127); see [Effect types](effect-types.md) |
| `amp_type`, `ir_cab` | 0–8 |
| `amp_on`, `mod_on`, `delay_on`, `reverb_on` | `on` / `off` |
| `led_colour` | `#rrggbb` or `r,g,b` |

- On firmware 96 every field is `confirmed` and needs no flag (block switches and the LED colour
  since spec 007 gate session C); on other firmware every write needs `--experimental`.
- **All or nothing up front.** If any field would be refused (out of range, tuner mode, bypass,
  untested firmware …), nothing is sent:

  ```text
  $ openvave set gain=200 delay_on=on
  error: gain: value out of range (0–127)
  ```

- Fields already at their value are skipped; if all are, nothing is sent
  (`gain already set; nothing sent`).
- **If something fails midway** (a NAK, a lost connection, a write the re-read does not show),
  the rest is not sent, nothing is retried, and every field is listed as `applied`, `unknown`,
  `not applied` or `not sent`. `openvave preset reload` throws away whatever was applied.

## Change one field

The `set FIELD VALUE` form does the same for one field, and is the one that takes `--type` and
`--raw` for typed knobs.

```text
$ openvave set gain 90
Set gain 60 → 90   (current preset 1B, normal mode)
  write  00 59 22 16 00 00 04 04 00 00 10 0e 00 00 0f 04 5a 3c 46 32 32 00 00 00 00 05 04 07 76
  reply  00 59 00 01 00 00 00 ff   ACK
  after  [6] gain 90   applied
Not saved. Discard: openvave preset reload   Keep: openvave preset save --unsafe
```

```bash
openvave set reverb_decay 10 --type spring
openvave set amp_type 3 --dry-run
```

Each `openvave` command makes its own Bluetooth connection, which takes a few seconds. For more
than one field, the `FIELD=VALUE` form is much faster.

`set` works in normal mode (like the phone app) and in the pedal's edit mode. It is refused in
tuner mode, while bypassed, and in any state openvave does not recognise:

```text
$ openvave set gain 90
error: refused (tuner_mode): the pedal is in tuner mode; leave the tuner on the pedal first
```

## Undo: go back to the stored preset

Edits made with `set` live in the edit buffer only. `preset reload` loads the current preset again
from its stored copy:

```text
$ openvave preset reload
Reload 1B (index 1)   discards unsaved edits
  write  00 59 22 09 00 00 04 01 00 00 e0 01 00 00 01 18
  reply  00 59 00 01 00 00 00 ff   ACK
  now    bank 1, slot B   buffer = stored 1B   applied
```

With nothing to discard it sends nothing (`Reload 1B: nothing to discard; nothing sent`). In the
pedal's edit mode it needs `--discard-edits`, because the edits made on the pedal are lost too.
Selecting any preset on the pedal has the same effect.

## Switch presets

```text
$ openvave preset select 2C
Select 2C (index 6)   from 1B
  write  00 59 22 09 00 00 04 06 00 00 e0 01 00 00 01 13
  reply  00 59 00 01 00 00 00 ff   ACK
  now    bank 2, slot C   buffer = stored 2C   applied
```

The position is `1A`–`9D` (case-insensitive) or an index 0–35 (`openvave preset select 6`).
Unsaved edits are lost. In the pedal's edit mode the command is refused unless you add
`--discard-edits`.

## Bypass

```text
$ openvave bypass on
Bypass on   (was 1B, normal mode)
  write  00 59 22 09 00 00 04 01 00 00 e1 01 00 00 01 17
  reply  00 59 00 01 00 00 00 ff   ACK
  now    bypass (slot ff, buffer all 00)   applied
Leave bypass: openvave bypass off 1B
```

```bash
openvave bypass off 1B
```

- `bypass on` works in normal mode only. With unsaved edits it needs `--discard-edits`, because
  leaving bypass reloads the stored preset.
- While bypassed, the pedal does not report which preset was loaded, so `bypass off` needs the
  position. Without one it stops and names the bank the pedal reports:

  ```text
  $ openvave bypass off
  openvave bypass off: error: a position is required: the pedal does not report the loaded slot while bypassed (it reports bank 1); e.g. openvave bypass off 1A … 1D
  ```

- `bypass off` is refused when the pedal is not bypassed; use `preset select` then.

## Back up all 36 presets

```text
$ openvave preset backup
Backup of TANK-Gv2 (firmware 96)   36 presets, header a5 5a
  1A  01 00 01 01 12 05 41 37 41 37 32 00 00 0c 28 35 0f 07 ff f7 00
  …
  9D  …
Cross-check with whole-image read: OK
Saved tankg-backup-20261117-100500.json
```

It reads the 36 presets one by one, then the whole memory image in one read, and saves only if
both agree (otherwise exit 7, no file). It only reads.

- `--output PATH` picks the file (default `./tankg-backup-<date>-<time>.json`). An existing file
  is kept unless you add `--force`.
- Two backups with no write in between are identical apart from `created_at`.
- The file is plain JSON
  ([schema](../specs/003-preset-backup-edit-writes/contracts/backup.schema.json)): each preset's
  21 bytes as hex with its decoded fields, plus the whole image.

## Save the current sound (UNSAFE)

`preset save` writes the current sound into a stored preset. It overwrites that preset, so it
needs `--unsafe`. Without it:

```text
$ openvave preset save --to 1C
error: refused (unsafe_required): preset save overwrites a stored preset; pass --unsafe (unsafe=True) to accept that
```

Check first with `--dry-run` (it does the reads, prints every frame, takes no backup, sends
nothing), then save:

```text
$ openvave preset save --to 1C --unsafe
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

What happens, in order:

1. openvave reads the pedal and lists the bytes that will change in the target slot (here, only
   the gain). Without `--to` it saves into the loaded slot.
2. It takes a **full backup** (the same reads and cross-check as `preset backup`) and writes it to
   `--backup-dir` (default: `~/.local/share/openvave/backups`, or `$OPENVAVE_BACKUP_DIR`) as `tankg-backup-<date>-<time>-before-save.json`.
   If the backup fails or cannot be written, nothing is sent. There is no way to skip it.
3. It sends the phone app's save sequence: write the slot, read it back (a mismatch stops before
   anything is committed), wait 300 ms, commit, wait 100 ms, select the slot.
4. It verifies that the stored slot holds the bytes written, the pedal is on that slot, and the
   buffer equals it.

If the slot already holds the sound, nothing is sent and no backup is taken
(`1C already holds this sound; nothing sent`). Save works in normal mode only.

If a step fails, openvave stops (nothing is ever retried), lists every step as acknowledged, NAK,
no reply or not sent, says whether stored presets may have changed, and prints the two recovery
commands: `openvave preset backup` and
`openvave preset restore <automatic backup> --all --unsafe`. The pedal may mute briefly during the
commit; that is the pedal. A power loss during the write has an unknown outcome.

## Restore presets from a backup (UNSAFE)

`preset restore FILE` writes an openvave backup file back to the pedal: one slot with
`--slot POSITION`, or all 36 with `--all`. It needs `--unsafe` and takes the same automatic backup
first (`…-before-restore.json`).

```text
$ openvave preset restore backup-a.json --all --unsafe
Restore all presets from backup-a.json   UNSAFE: overwrites stored presets
  differ: 1C (1 of 36)
Backup saved: tankg-backup-20261119-092428-before-restore.json
A power loss during the next second has an unknown outcome.
  write  00 59 22 fe 02 00 04 00 00 00 00 f6 02 00 a5 5a …(758 bytes)… 1b   ACK   (773 bytes)
  wait   300 ms
  write  00 59 22 08 00 00 04 00 00 00 f0 00 00 00 0b   ACK   (commit)
  wait   100 ms
  write  00 59 22 09 00 00 04 01 00 00 e0 01 00 00 01 18   ACK   (select 1B)
  verify 36 of 36 presets and header equal backup-a.json   restored
```

- The file is checked before connecting (format version, 36 presets of 21 bytes, positions,
  header `a5 5a`, image consistent with the presets). An invalid file exits 2.
- openvave lists the slots that differ and sends nothing when none does.
- `--slot 1C` uses the save sequence with the file's bytes for that slot. `--all` writes the whole
  758-byte image in one message, commits, selects the preset that was loaded, and compares a full
  read with the file.
- Every restore ends with a preset select, so unsaved edits need `--discard-edits`.
- A file made on another firmware needs `--experimental` as well.
- `--dry-run` prints every frame (the image in full) and takes no backup.

## Copy, swap, share a preset (UNSAFE)

```bash
openvave preset copy 2C 9D --unsafe          # 9D becomes a copy of 2C; the pedal ends on 9D
openvave preset swap 2B 4D --unsafe          # exchange two slots; the pedal stays on its preset
openvave preset export 1D --output tone.json # read-only: one preset to a file
openvave preset import tone.json --to 3A --unsafe
```

Each persistent command takes the automatic backup first, prints the exact frames with
`--dry-run`, and verifies by reading back, as `preset save` does. Copy and import use the save
sequence; swap writes the stored image once with the two slots exchanged (the `restore --all`
write). With unsaved edits on the loaded preset they need `--discard-edits` (the final select
discards them).

## Loopback

```text
$ openvave loopback off --dry-run
Loopback on → off   (status byte 0xD0000000: Bluetooth audio in the USB recording)
  write  00 59 22 09 00 00 04 00 00 00 d0 01 00 00 00 2a
  dry run: nothing sent
```

`on` mixes the pedal's Bluetooth audio (for example a phone backing track) into its USB recording;
`off` keeps it out of the recording (you still hear it). The setting survives a power cycle. If
the flag already
has the value, nothing is sent (`loopback is already on; nothing sent`).

## Scripting with JSON

Add `--json` to any command for one JSON document on stdout (nothing on stdout on failure; the
exit code tells you what happened). For example, with [jq](https://jqlang.github.io/jq/):

```bash
openvave preset dump --json | jq '.preset.fields[] | {name, value}'
openvave info --json | jq -r '.pedal_state'
openvave set gain 90 --json | jq '.result.applied'
```

Typed knobs are raw values in JSON (`reverb_decay` 53, not "spring 10"). `watch --json` prints one
JSON line per event. The schemas are listed in the [CLI reference](cli-reference.md#json-output).
