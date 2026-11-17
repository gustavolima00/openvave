# CLI contract additions: `openvave` (feature 003)

Extends [001 `cli.md`](../../001-readonly-ble-connection/contracts/cli.md) and
[002 `cli.md`](../../002-preset-byte-map/contracts/cli.md). Global options (`--device`,
`--timeout`, `--scan-timeout`, `--json`, `--trace`), stderr rules and exit codes are unchanged
unless stated. Decisions: [research.md](../research.md).

## `openvave preset backup` (read-only)

```text
openvave preset backup [--output PATH] [--force]
```

Reads the stored-image header, the 36 stored presets one by one and the whole image, cross-checks
them (R1), and writes the backup file ([`backup.schema.json`](backup.schema.json)).

- `--output PATH`: target file. Default `./tankg-backup-<YYYYmmdd-HHMMSS>.json` (local time).
- `--force`: overwrite an existing target. Without it an existing target is a usage error (exit 2)
  and nothing is read.
- Sends only `0x11` and `0x23`.

Human output (stdout):

```text
Backup of TANK-Gv2 (firmware 96)   36 presets, header a5 5a
  1A  01 00 01 01 12 05 41 37 41 37 32 00 00 0c 28 35 0f 07 ff f7 00
  …
  9D  …
Cross-check with whole-image read: OK
Saved tankg-backup-20261117-100500.json
```

- Unexpected header: the header line ends with `  UNEXPECTED (expected a5 5a)`, a warning goes to
  stderr, the file is written with `warnings: ["unexpected_header"]`, exit 0.
- Cross-check mismatch: stderr lists the differing positions, no file is written, exit 7.
- `--json`: stdout is one document: the envelope (`schema_version: 2`, `command: "preset backup"`,
  `read_at`, `device`, `identity`) plus `backup` (the file document) and `saved_to` (path).

## `openvave set <field> <value>` (edit-buffer write)

```text
openvave set <field> <value> [--dry-run] [--experimental]
```

Changes one field of the **current preset in the edit buffer**. Never saves, never touches stored
presets: leaving edit mode on the pedal without saving restores the stored preset.

Fields and values:

| Field | Value | Write |
|---|---|---|
| `noise_gate`, `gain`, `treble`, `middle`, `bass`, `volume`, `mod_fx`, `mod_speed`, `delay_mix`, `delay_time`, `reverb_decay`, `reverb_mix` | integer 0–127 | 14-byte knob block |
| `amp_type`, `ir_cab` | integer 0–8 | 14-byte knob block |
| `amp_on`, `mod_on`, `delay_on`, `reverb_on` | `on` / `off` | 1 byte at `0x10000000 + k` |
| `led_colour` | `#rrggbb` or `r,g,b` (0–255) | 3 bytes at `0x10000012` |

Field names are the byte map's machine names; unknown names are a usage error (exit 2) listing
the valid ones.

Steps: read global block → refuse unless mode = edit → read edit buffer → build the write → check
range, firmware and confidence → (dry-run stops here) → send → check ACK → re-read edit buffer
and global block → report.

- `--dry-run`: performs the reads, prints the plan, sends no write, exit 0 even if the write would
  be refused (the refusal is printed).
- `--experimental`: allows writes whose message is not yet `confirmed` in the "Write messages"
  table, or on firmware not covered by a confirmed gate. Without it such writes are refused
  (exit 1) with the message's confidence and the flag name.

Human output:

```text
Set gain 60 → 90   (current preset 1B, edit mode)
  write  00 59 22 16 00 00 04 04 00 00 10 0e 00 00 0f 04 5a 3c 46 32 32 00 00 00 00 05 04 07 76
  reply  00 59 00 01 00 00 00 ff   ACK
  after  [6] gain 90   applied
Not saved: leave edit mode on the pedal without saving to restore the stored preset.
```

Dry run replaces the `reply`/`after` lines with `dry run: nothing sent`. A switch toggle may move
other bytes (pedal copies physical knob positions); every changed byte is listed under `after`.
No change requested: `gain is already 90; nothing sent`, exit 0.

## `openvave preset select <position>`

```text
openvave preset select <position> [--dry-run] [--experimental] [--discard-edits]
```

`<position>`: `1A`–`9D` (case-insensitive) or index `0`–`35`. Invalid → usage error (exit 2).

Steps: read global block → if mode = edit, refuse unless `--discard-edits` → build the select
write (`01` to `0xE0000000 + index`) → confidence/firmware gate → (dry-run stops) → send → ACK →
wait 100 ms → read global until slot ≠ `ff` (≤ 10 tries, 100 ms apart) → read edit buffer and the
stored preset → report applied iff bank/slot match and the buffer equals the stored preset.

```text
Select 2C (index 6)   from 1B
  write  00 59 22 09 00 00 04 06 00 00 e0 01 00 00 01 13
  reply  00 59 00 01 00 00 00 ff   ACK
  now    bank 2, slot C   buffer = stored 2C   applied
```

## JSON for `set` / `preset select`

`--json` prints one document: the envelope plus `plan` and, unless dry-run or no-change, `result`
([`write-result.schema.json`](write-result.schema.json)). Refusals and errors still go to stderr
with the exit code; with `--json` the error object of 001 is printed to stdout as before.

## Exit codes (additions)

| Code | Meaning |
|---|---|
| 1 | write refused (not edit mode, out of range, untested firmware, experimental required, edits would be discarded) |
| 2 | usage: unknown field, bad value syntax, bad position, backup target exists |
| 7 | NAK (reply other than the ACK; raw bytes printed) or backup cross-check mismatch |
| 8 | **new**: write acknowledged but the re-read does not show it (not applied) |

Codes 3–6 keep their 001 meanings (no device, multiple devices, Bluetooth unavailable, connection
lost / timeout).
