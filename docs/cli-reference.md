# CLI reference

`openvave COMMAND --help` prints the same information. The formal contracts are in the specs:
[0.1.0](../specs/001-readonly-ble-connection/contracts/cli.md),
[0.2.0](../specs/002-preset-byte-map/contracts/cli.md),
[0.3.0](../specs/003-preset-backup-edit-writes/contracts/cli.md),
[0.4.0](../specs/004-remote-edit-save-restore/contracts/cli.md),
[0.5.0](../specs/005-device-selection/contracts/cli.md) and
[0.6.0](../specs/006-mcp-server/contracts/tools.md) (`openvave mcp`) additions.

## Commands

| Command | Writes? | What it does |
|---|---|---|
| [`scan`](#scan) | no | list every Tank-G in range; connects to nothing (unless `--identify`) |
| [`select`](#select) | no | make a pedal the default, with a nickname |
| [`device`](#device) | no | show the default and known pedals; `rename` a nickname |
| [`forget`](#forget) | no | clear the default, or remove known pedals |
| [`info`](#info) | no | identify the pedal; device info, global block, status |
| [`preset dump`](#preset-dump) | no | the 21-byte current preset, decoded |
| [`watch`](#watch) | no | poll and print every byte that changes |
| [`preset backup`](#preset-backup) | no | save all 36 stored presets to a verified JSON file |
| [`preset export`](#preset-export) | no | save one stored preset to a JSON preset file |
| [`set`](#set) | volatile | change fields of the current preset |
| [`preset reload`](#preset-reload) | volatile | discard unsaved edits |
| [`preset select`](#preset-select) | volatile | load a stored preset |
| [`bypass on` / `bypass off`](#bypass) | volatile | bypass the pedal / leave bypass |
| [`loopback on` / `off`](#loopback) | kept across power-off | Bluetooth audio in the USB recording |
| [`preset save`](#preset-save) | **persistent** | store the current sound in a slot (`--unsafe`) |
| [`preset restore`](#preset-restore) | **persistent** | write back a backup file (`--unsafe`) |
| [`preset copy`](#preset-copy) | **persistent** | copy one stored preset to another slot (`--unsafe`) |
| [`preset swap`](#preset-swap) | **persistent** | exchange two stored presets (`--unsafe`) |
| [`preset import`](#preset-import) | **persistent** | write a preset file into a slot (`--unsafe`) |
| [`mcp`](#mcp) | per tool | run an MCP server for AI assistants (needs the `mcp` extra) |

`openvave --version` prints the version.

## Options on every command

These go before or after the command.

| Option | Default | |
|---|---|---|
| `--json` | off | one JSON document on stdout (see [JSON output](#json-output)) |
| `--device ID\|NICKNAME` | none | use this pedal: an identifier (connected to whatever its name) or a known nickname |
| `--scan-timeout SECONDS` | 5 | longest scan; it stops as soon as the chosen pedal is seen (1 s after the first pedal when none is chosen) |
| `--timeout SECONDS` | 2 | per-request timeout |
| `--trace` | off | hex of every frame on stderr |

Environment: `OPENVAVE_DEVICE` (same values as `--device`; empty = unset) and `OPENVAVE_CONFIG`
(path of the known-pedals file; default `~/.config/openvave/devices.json`).

### Which pedal

Every pedal command uses, first present wins: `--device`, `OPENVAVE_DEVICE`, the default
(`openvave select`), the only Tank-G in range. It prints `pedal: <nickname>  <id>…  <rssi> dBm
(<reason>)` on stderr before connecting (not with `--json`); the reason is `(--device)`,
`(OPENVAVE_DEVICE)`, `(selected)` or `(only one found)`. A chosen pedal that is not seen is exit
3, never a fallback to another pedal; the message lists the Tank-G pedals it did see. In `--json`
the `device` object carries `nickname` and `chosen_by`.

## Options on write commands

| Option | On | |
|---|---|---|
| `--dry-run` | every write command | do the reads, print the frame(s), send nothing (save/restore: no backup) |
| `--experimental` | every write command | allow messages not yet `confirmed`, and untested firmware |
| `--discard-edits` | `preset select`, `preset reload`, `bypass on`, `preset restore`, `copy`, `swap`, `import` | go ahead although unsaved edits are lost |
| `--unsafe` | `preset save`, `restore`, `copy`, `swap`, `import` | required: accept that stored presets are overwritten |
| `--backup-dir DIR` | `preset save`, `restore`, `copy`, `swap`, `import` | where the automatic backup goes (default `$OPENVAVE_BACKUP_DIR`, else `$XDG_DATA_HOME/openvave/backups`, `%LOCALAPPDATA%\openvave\backups` on Windows, or `~/.local/share/openvave/backups`; created if missing; never overwrites) |

Positions are `1A`–`9D` (case-insensitive) or an index `0`–`35`.

## scan

```text
openvave scan [--all] [--identify]
```

Scans for the whole `--scan-timeout` and lists every Tank-G, strongest signal first. `*` marks the
default pedal; known pedals show their nickname; a default that is not in range gets a `not seen`
line. `--all` adds other Bluetooth advertisers, flagged `(not a Tank-G)`. `--identify` connects to
each pedal in turn and adds its firmware, sending only the handshake query. Exit 0 when a Tank-G
is listed, 3 when none. A pedal connected to the phone app or another program does not advertise
and is not listed. `--json`:
[`scan.schema.json`](../specs/005-device-selection/contracts/scan.schema.json).

## select

```text
openvave select [TARGET] [--name NICKNAME] [--offline]
```

Makes a pedal the default. TARGET is a known nickname (no scan), a full identifier (checked by a
scan unless `--offline`) or an identifier prefix of at least 4 hex digits matching one pedal in
range; without TARGET, the only pedal in range. Several candidates: exit 4; none: exit 3; a bad
or already used nickname: exit 2. Nothing is saved unless it succeeds. Never prompts.

## device

```text
openvave device [--check]
openvave device rename OLD NEW
```

Shows the default pedal, every known pedal and the configuration file's path, without Bluetooth.
`--check` scans for the default and adds `In range: yes (-58 dBm)` (exit 3 when not in range, 2
when there is no default). `rename` changes a nickname. `--json`:
[`device.schema.json`](../specs/005-device-selection/contracts/device.schema.json).

## forget

```text
openvave forget [TARGET | --all]
```

Without TARGET, clears the default (the pedal stays known). With TARGET (nickname or identifier),
removes that pedal. `--all` removes every known pedal and moves an invalid configuration file
aside (`devices.json.invalid-<time>`). No Bluetooth.

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
| `amp_on`, `mod_on`, `delay_on`, `reverb_on` | `on` / `off` | |
| `led_colour` | `#rrggbb` or `r,g,b` | |

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
openvave loopback {on,off} [--dry-run] [--experimental]
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

## preset copy

```text
openvave preset copy SOURCE TARGET --unsafe [--discard-edits] [--backup-dir DIR] [--dry-run]
                     [--experimental]
```

Writes `SOURCE`'s stored bytes to `TARGET` with the save sequence (slot write, read back, commit,
select `TARGET`, verify). The pedal ends on `TARGET`. Automatic backup first
(`…-before-copy.json`). Equal slots: nothing sent. `SOURCE` = `TARGET` is a usage error.

## preset swap

```text
openvave preset swap FIRST SECOND --unsafe [--discard-edits] [--backup-dir DIR] [--dry-run]
                     [--experimental]
```

Writes the stored image with the two slots exchanged in one message (the `restore --all` write),
commits, selects the preset that was loaded and verifies with a full read. Automatic backup first
(`…-before-swap.json`). Slots holding the same sound: nothing sent.

## preset export

```text
openvave preset export POSITION [--output PATH] [--force]
```

Reads one stored preset and writes a preset file (`kind: openvave.preset`, the 21 bytes, firmware,
source position, decoded fields for reading). Read-only. Default file
`./tankg-preset-<POS>-<date>-<time>.json`; never overwrites without `--force`.

## preset import

```text
openvave preset import FILE --to POSITION --unsafe [--discard-edits] [--backup-dir DIR]
                       [--dry-run] [--experimental]
```

Writes a preset file's 21 bytes into `POSITION` with the save sequence and selects it. The file is
checked before connecting (a full backup file is refused with a hint to use `preset restore`); a
file from another firmware needs `--experimental`. Automatic backup first (`…-before-import.json`).

## mcp

```text
openvave mcp [--device ID|NICKNAME] [--read-only] [--backup-dir DIR]
             [--idle-release SECONDS] [--scan-timeout S] [--timeout S] [--trace]
```

Runs a [Model Context Protocol](https://modelcontextprotocol.io) server on stdin/stdout for an AI
assistant (Claude Code, Claude Desktop …), which starts it; you do not run it by hand. Needs the
optional extra: `pip install 'openvave[mcp] @ git+https://github.com/gustavolima00/openvave'`.
Every command above is a tool, with `--dry-run`, `--experimental`, `--discard-edits` and
`--unsafe` as per-call arguments. Setup, tools and troubleshooting: [MCP guide](mcp.md).

| Option | Default | |
|---|---|---|
| `--read-only` | off | list no tool that writes to the pedal |
| `--backup-dir DIR` | as `preset save` | the folder for backups and exports, and the only one restore and import read from |
| `--idle-release SECONDS` | 300 | release the pedal after this many seconds without a pedal tool; `0` never |

It connects on the first pedal tool, keeps that one connection between tools, and releases it
after `--idle-release`, on the `pedal_disconnect` tool or at exit, so the phone app can connect.
stdout carries only MCP messages; warnings and `--trace` go to stderr. Exit codes: 0 when the
assistant closes it, 2 on a usage error or without the `mcp` extra (`error: the MCP server needs
the 'mcp' extra: pip install 'openvave[mcp]'`). Pedal errors never stop it: each is the failing
tool's error.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | success (also "nothing to do; nothing sent") |
| 1 | internal error, or a write refused before sending: tuner mode, bypassed or unrecognised state, edit mode (`bypass on`, `preset save`, `preset restore`), not bypassed (`bypass off`), out of range, untested firmware, `--experimental` or `--unsafe` needed, backup from another firmware, edits would be discarded |
| 2 | usage error, including an unknown nickname, a bad or duplicate nickname, an invalid configuration file, `device --check` with no default, `bypass off` without a position, an invalid restore file, `--slot` and `--all` both or neither, an existing `--output` file without `--force` |
| 3 | no pedal found; the chosen pedal was not seen; `scan` / `select` found no Tank-G; `device --check` not in range |
| 4 | more than one pedal and none chosen (use `openvave select` or `--device`); `select` with several candidates |
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
| `scan` | [`scan.schema.json`](../specs/005-device-selection/contracts/scan.schema.json) |
| `select`, `device`, `forget` | [`device.schema.json`](../specs/005-device-selection/contracts/device.schema.json) |
| `preset backup` (and the backup file) | [`backup.schema.json`](../specs/003-preset-backup-edit-writes/contracts/backup.schema.json) |
| `set FIELD VALUE`, `preset select`, `preset reload`, `bypass`, `loopback` | [`write-result.schema.json`](../specs/004-remote-edit-save-restore/contracts/write-result.schema.json) |
| `set FIELD=VALUE ...` (also when a batch stops midway) | [`set-fields-result.schema.json`](../specs/004-remote-edit-save-restore/contracts/set-fields-result.schema.json) |
| `preset save`, `restore`, `copy`, `swap`, `import` (also when a sequence stops midway) | [`sequence-result.schema.json`](../specs/004-remote-edit-save-restore/contracts/sequence-result.schema.json) |

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
