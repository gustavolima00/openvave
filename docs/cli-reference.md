# CLI reference

`openvave COMMAND --help` prints the same information. The formal contracts are in the specs:
[0.1.0](../specs/001-readonly-ble-connection/contracts/cli.md),
[0.2.0](../specs/002-preset-byte-map/contracts/cli.md),
[0.3.0](../specs/003-preset-backup-edit-writes/contracts/cli.md) and
[0.4.0](../specs/004-remote-edit-save-restore/contracts/cli.md) additions.

## Commands

| Command | Writes? | What it does |
|---|---|---|
| [`info`](#info) | no | identify the pedal; device info, global block, status |
| [`preset dump`](#preset-dump) | no | the 21-byte current preset, decoded |
| [`watch`](#watch) | no | poll and print every byte that changes |
| [`preset backup`](#preset-backup) | no | save all 36 stored presets to a verified JSON file |
| [`set`](#set) | volatile | change fields of the current preset |
| [`preset reload`](#preset-reload) | volatile | discard unsaved edits |
| [`preset select`](#preset-select) | volatile | load a stored preset |
| [`bypass on` / `bypass off`](#bypass) | volatile | bypass the pedal / leave bypass |
| [`loopback on` / `off`](#loopback) | kept across power-off | Bluetooth audio in the USB recording (experimental) |
| [`preset save`](#preset-save) | **persistent** | store the current sound in a slot (`--unsafe`) |
| [`preset restore`](#preset-restore) | **persistent** | write back a backup file (`--unsafe`) |

`openvave --version` prints the version.

## Options on every command

These go before or after the command.

| Option | Default | |
|---|---|---|
| `--json` | off | one JSON document on stdout (see [JSON output](#json-output)) |
| `--device ID` | none | connect to this platform identifier; skips the name filter |
| `--scan-timeout SECONDS` | 5 | longest scan; it stops 1 s after the pedal is seen (at once with `--device`) |
| `--timeout SECONDS` | 2 | per-request timeout |
| `--trace` | off | hex of every frame on stderr |

## Options on write commands

| Option | On | |
|---|---|---|
| `--dry-run` | every write command | do the reads, print the frame(s), send nothing (save/restore: no backup) |
| `--experimental` | every write command | allow messages not yet `confirmed`, and untested firmware |
| `--discard-edits` | `preset select`, `preset reload`, `bypass on`, `preset restore` | go ahead although unsaved edits are lost |
| `--unsafe` | `preset save`, `preset restore` | required: accept that stored presets are overwritten |
| `--backup-dir DIR` | `preset save`, `preset restore` | where the automatic backup goes (default `.`; never overwrites) |

Positions are `1A`–`9D` (case-insensitive) or an index `0`–`35`.

## info

```text
openvave info
```

Device name and firmware, address, pedal state, then the device-info (32 bytes), global (4) and
status (1) regions, raw and decoded.

## preset dump

```text
openvave preset dump
```

The current preset (edit buffer), raw and decoded, plus the pedal state. Reads the pedal every
time; nothing is cached.

## watch

```text
openvave watch [--interval SECONDS] [--duration SECONDS] [--record PATH | --no-record]
```

| Option | Default | |
|---|---|---|
| `--interval SECONDS` | 0.5 | time between polls (minimum 0.2) |
| `--duration SECONDS` | none | stop after this long |
| `--record PATH` | `captures/private/<date>-<time>-watch.jsonl` | session record (JSON Lines) |
| `--no-record` | | write no record |

Type a label and Enter before each step; `q`, `quit` or Ctrl-C stops. Only reads are sent.

## preset backup

```text
openvave preset backup [--output PATH] [--force]
```

| Option | Default | |
|---|---|---|
| `--output PATH` | `./tankg-backup-<date>-<time>.json` | the backup file |
| `--force` | off | overwrite an existing file |

A cross-check mismatch writes no file and exits 7.

## set

```text
openvave set FIELD VALUE [--type TYPE | --raw] [--dry-run] [--experimental]
openvave set FIELD=VALUE [FIELD=VALUE ...] [--dry-run] [--experimental]
```

| Field | `VALUE` | Needs |
|---|---|---|
| `noise_gate`, `gain`, `treble`, `middle`, `bass`, `volume`, `mod_speed`, `delay_time`, `reverb_mix` | 0–127 | |
| `mod_fx`, `delay_mix`, `reverb_decay` | position 1–40 (keep type); with `--type TYPE`; or raw 0–127 with `--raw`. In `FIELD=VALUE` form: `POSITION`, `TYPE:POSITION`, `raw:N` | |
| `amp_type`, `ir_cab` | 0–8 | |
| `amp_on`, `mod_on`, `delay_on`, `reverb_on` | `on` / `off` | `--experimental` |
| `led_colour` | `#rrggbb` or `r,g,b` | `--experimental` |

Types: `mod_fx` chorus, phaser, tremolo; `delay_mix` analog, tape, dual; `reverb_decay` room,
spring, cloud ([Effect types](effect-types.md)). Works in normal and edit mode; refused in tuner
mode, bypass and unrecognised states. Not saved.

## preset reload

```text
openvave preset reload [--discard-edits] [--dry-run] [--experimental]
```

Selects the loaded preset again, so the buffer equals the stored copy. Sends nothing when there is
nothing to discard. In edit mode needs `--discard-edits`.

## preset select

```text
openvave preset select POSITION [--discard-edits] [--dry-run] [--experimental]
```

Loads stored preset `POSITION`. In edit mode needs `--discard-edits`.

## bypass

```text
openvave bypass on [--discard-edits] [--dry-run] [--experimental]
openvave bypass off POSITION [--dry-run] [--experimental]
```

`on`: normal mode only; prints the `bypass off` command to come back. `off`: only when bypassed;
the position is required (exit 2 without it).

## loopback

```text
openvave loopback {on,off} --experimental [--dry-run]
```

Reads the status byte, writes `01` / `00`, reads it back. Equal value: nothing sent.

## preset save

```text
openvave preset save [--to POSITION] --unsafe [--backup-dir DIR] [--dry-run] [--experimental]
```

Stores the edit buffer in the loaded slot, or in `--to`. Normal mode only. Automatic backup
(`tankg-backup-<date>-<time>-before-save.json`), then slot write, read back, 300 ms, commit,
100 ms, select, verify. Nothing to save: nothing sent, no backup.

## preset restore

```text
openvave preset restore FILE (--slot POSITION | --all) --unsafe [--discard-edits]
                        [--backup-dir DIR] [--dry-run] [--experimental]
```

`FILE` is an openvave backup (`format_version` 1), checked before connecting. `--slot` restores one
position with the save sequence; `--all` writes the 758-byte image, commits, selects the preset
that was loaded and verifies with a full read. Automatic backup first (`…-before-restore.json`). A
file from another firmware needs `--experimental`.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | success (also "nothing to do; nothing sent") |
| 1 | internal error, or a write refused before sending: tuner mode, bypassed or unrecognised state, edit mode (`bypass on`, `preset save`, `preset restore`), not bypassed (`bypass off`), out of range, untested firmware, `--experimental` or `--unsafe` needed, backup from another firmware, edits would be discarded |
| 2 | usage error, including `bypass off` without a position, an invalid restore file, `--slot` and `--all` both or neither, an existing `--output` file without `--force` |
| 3 | no pedal found |
| 4 | more than one pedal (use `--device`) |
| 5 | Bluetooth unavailable or permission denied |
| 6 | connection lost or timed out |
| 7 | protocol error, NAK, or backup cross-check mismatch |
| 8 | write acknowledged but not applied |

## JSON output

With `--json`, stdout carries exactly one JSON document on success and nothing on failure
(`watch --json` prints one JSON line per event instead). Bytes are lowercase, space-separated
hex. Every document has `"schema_version": 2`; new fields may be added without changing it, while
removing, renaming or retyping a field bumps it.

| Command | Schema |
|---|---|
| `info` | [`info.schema.json`](../specs/001-readonly-ble-connection/contracts/info.schema.json) |
| `preset dump` | [`preset-dump.schema.json`](../specs/001-readonly-ble-connection/contracts/preset-dump.schema.json) |
| each item of `fields[]` | [`decoded-field.schema.json`](../specs/002-preset-byte-map/contracts/decoded-field.schema.json) |
| `watch --json` | [`watch-event.schema.json`](../specs/002-preset-byte-map/contracts/watch-event.schema.json) |
| `preset backup` (and the backup file) | [`backup.schema.json`](../specs/003-preset-backup-edit-writes/contracts/backup.schema.json) |
| `set FIELD VALUE`, `preset select`, `preset reload`, `bypass`, `loopback` | [`write-result.schema.json`](../specs/004-remote-edit-save-restore/contracts/write-result.schema.json) |
| `set FIELD=VALUE ...` (also when a batch stops midway) | [`set-fields-result.schema.json`](../specs/004-remote-edit-save-restore/contracts/set-fields-result.schema.json) |
| `preset save`, `preset restore` (also when a sequence stops midway) | [`sequence-result.schema.json`](../specs/004-remote-edit-save-restore/contracts/sequence-result.schema.json) |

`info`, `preset dump` and the `watch --json` start and change events carry a top-level
`pedal_state` (`normal`, `edit`, `tuner`, `bypass`, `loading`, `unrecognised`). Typed knobs are
raw values in JSON.

Abbreviated `openvave set gain 90 --json`:

```json
{
  "schema_version": 2,
  "command": "set",
  "plan": {
    "action": "set gain",
    "target": {"kind": "knob_block", "type": 4, "address": "0x10000004", "length": 14, "argument": null},
    "frame": "00 59 22 16 00 00 04 04 00 00 10 0e 00 00 0f 04 5a 3c 46 32 32 00 00 00 00 05 04 07 76",
    "no_change": false,
    "refusal": null,
    "dry_run": false,
    "confidence": "confirmed"
  },
  "result": {
    "ack": true,
    "changes": [{"region": "preset", "offset": 6, "before": 60, "after": 90, "name": "gain"}],
    "applied": true
  }
}
```
