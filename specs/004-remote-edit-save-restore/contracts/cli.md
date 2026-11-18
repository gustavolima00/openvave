# CLI contract additions: `openvave` (feature 004)

Extends [003 `cli.md`](../../003-preset-backup-edit-writes/contracts/cli.md). Global options,
stderr rules and exit codes are unchanged unless stated. Decisions: [research.md](../research.md).

Two opt-ins, independent (R6):

- `--unsafe`: required by every command that changes **stored** presets (`preset save`,
  `preset restore`). Without it: exit 1, reason `unsafe_required`.
- `--experimental`: required when any message the command sends is not `confirmed` in the "Write
  messages" table, or on firmware other than 96 (as in 0.3.0).

`--dry-run` on every command below: does the reads, prints the plan and the exact frames, sends no
write, takes no backup file, exit 0 even if the real run would be refused (the refusal is printed).

## `openvave set <field> <value> [--type TYPE | --raw]` (changed)

- Works in **normal** and edit mode. Refused (exit 1) in tuner mode (`tuner_mode`), in bypass
  (`bypassed`) and in an unrecognised state (`unrecognised_state`). `not_edit_mode` is gone.
- Typed input (research R3 amendment): `set reverb_decay <1-40> --type <room|spring|cloud>`
  (case-insensitive). Without `--type`, the position is taken in the preset's current type
  (refused, exit 1 `type_required`, when the knob sits between two types); `--raw <0-127>` writes
  the raw byte. Other fields take one raw value as before. `--type` / `--raw` on a field without
  an observed type split, an unknown type, `--type` with `--raw`, or a
  position outside 1–40: usage error (exit 2) listing what is accepted.

```text
Set reverb_decay 5 (room 6) → 53 (spring 10)   (current preset 1B, normal mode)
  write  00 59 22 16 00 00 04 04 00 00 10 0e 00 00 0f 04 3c 3c 46 32 32 00 00 00 00 35 04 07 64
  reply  00 59 00 01 00 00 00 ff   ACK
  after  [15] reverb_decay 53 (spring 10)   applied
Not saved. Discard: openvave preset reload   Keep: openvave preset save --unsafe --experimental
```

## `openvave preset reload`

```text
openvave preset reload [--discard-edits] [--dry-run]
```

Discards unsaved edits by selecting the loaded preset again (R4). Buffer already equal to the
stored preset: `nothing to discard; nothing sent`, exit 0. In edit mode it needs
`--discard-edits`; refused in bypass (hint: `bypass off <position>`), tuner and unrecognised
states. Output and JSON as `preset select`.

## `openvave bypass on | off <position>`

```text
openvave bypass on  [--discard-edits] [--dry-run] [--experimental]
openvave bypass off <position> [--dry-run] [--experimental]
```

- `on`: pedal must be in normal mode with a loaded preset. If the buffer differs from the stored
  preset, refused (`edits_would_be_discarded`) unless `--discard-edits`. Sends `01` to
  `0xE1000000 + i` for the loaded `i`. Applied iff a re-read shows slot `ff` and an all-zero
  buffer. Already bypassed: `already bypassed; nothing sent`.
- `off <position>`: `1A`–`9D` or `0`–`35`, required (the pedal does not report the slot while
  bypassed; missing → exit 2 with the reported bank). Runs the select path. If the pedal is not
  bypassed: refused (`not_bypassed`), pointing to `preset select`.

```text
Bypass on   (was 1B, normal mode)
  write  00 59 22 09 00 00 04 01 00 00 e1 01 00 00 01 17
  reply  00 59 00 01 00 00 00 ff   ACK
  now    bypass (slot ff, buffer all 00)   applied
Leave bypass: openvave bypass off 1B
```

## `openvave preset save` (persistent)

```text
openvave preset save [--to <position>] --unsafe [--experimental] [--dry-run] [--backup-dir DIR]
```

Stores the current edit buffer in the loaded slot, or in `--to`. Normal mode only (refused in
edit, tuner, bypass, unrecognised). Steps: read state, buffer and target slot → no change? stop →
opt-in and confidence checks → full backup to
`DIR/tankg-backup-<YYYYmmdd-HHMMSS>-before-save.json` (default `DIR` = current directory; never
overwrites; failure → nothing written to the pedal) → slot write → read slot back (mismatch: stop
before the commit) → 300 ms → commit → 100 ms → select → verify (slot, position, buffer).

```text
Save current sound to 1C (index 2)   UNSAFE: overwrites a stored preset
  [6] gain 60 → 90
Backup saved: ./tankg-backup-20261118-101500-before-save.json
A power loss during the next second has an unknown outcome.
  write  00 59 22 1d 00 00 04 2c 00 00 00 15 00 00 01 00 00 01 0f 04 5a 3c 46 32 32 00 00 00 00 05 04 07 43 16 43 b9   ACK
  wait   300 ms
  write  00 59 22 08 00 00 04 00 00 00 f0 00 00 00 0b   ACK   (commit)
  wait   100 ms
  write  00 59 22 09 00 00 04 02 00 00 e0 01 00 00 01 17   ACK   (select 1C)
  verify stored 1C = written bytes, pedal on 1C, buffer = stored   saved
```

(Example: public preset 1B's bytes with gain 90, saved to 1C at address `0x2c`.)

Buffer equal to the slot: `1C already holds this sound; nothing sent`, exit 0, no backup.

## `openvave preset restore <file>` (persistent)

```text
openvave preset restore <file> (--slot <position> | --all) --unsafe [--experimental]
                        [--discard-edits] [--dry-run] [--backup-dir DIR]
```

`<file>`: an openvave backup (`format_version` 1). Validated before connecting; an invalid file is
a usage error (exit 2) naming the problem. A file from another firmware version is refused
(`firmware_mismatch`) unless `--experimental`.

- `--slot POS`: restores that position from the file to the same position (save sequence with the
  file's bytes).
- `--all`: writes the file's 758-byte image in one message, commits, then selects the preset that
  was loaded. Verified by a full read compared with the file.
- Lists the slots that differ first. None differs: `pedal already matches <file>; nothing sent`.
- If the loaded preset has unsaved edits: needs `--discard-edits` (M2: every restore ends with a
  select, which discards them, so this applies whichever slot is written).
- Automatic backup as for save (`…-before-restore.json`).

```text
Restore all presets from backup-a.json   UNSAFE: overwrites stored presets
  differ: 1C 3B 9D (3 of 36)
Backup saved: ./tankg-backup-20261118-102000-before-restore.json
  write  00 59 22 fe 02 00 04 00 00 00 00 f6 02 00 a5 5a …(758 bytes)… xx   ACK   (773 bytes)
  wait   300 ms
  write  00 59 22 08 00 00 04 00 00 00 f0 00 00 00 0b   ACK   (commit)
  wait   100 ms
  write  …   ACK   (select 1B)
  verify 36 of 36 presets and header equal backup-a.json   restored
```

Dry run prints the image frame in full.

## `openvave loopback on | off`

```text
openvave loopback (on | off) [--dry-run] [--experimental]
```

Reads the flag (`0xD0000000` × 1), writes `01` / `00` there, checks the ACK, re-reads. Never
followed by a commit. Equal value: `loopback is already off; nothing sent`. Needs `--experimental`
until the message is confirmed. Off: `00 59 22 09 00 00 04 00 00 00 d0 01 00 00 00 2a`.

## `info`, `preset dump`, `watch` (changed output)

- New line `state: normal | edit | tuner | bypass | unrecognised` (`watch`: also `loading` for a
  one-cycle transient, and a change line when the state changes).
- In bypass: the raw buffer is printed, decoded field lines are not, and the position line reads
  `bank <n>, slot not reported`.
- JSON: added top-level `pedal_state`; everything else unchanged (`schema_version` 2).

## Failure report of a multi-step command

On a NAK, a lost connection, a timeout or a failed verification, stderr lists every step:

```text
error: no reply to the commit (connection lost)
  slot write 1C   ACK
  commit          no reply
  select 1C       not sent
Stored presets may have changed. Nothing was retried.
Check:   openvave preset backup
Undo:    openvave preset restore ./tankg-backup-20261118-101500-before-save.json --all --unsafe --experimental
```

(`--experimental` is printed while the restore messages are not `confirmed`.)

With `--json` the same information is in `result.steps`, `result.stored_may_have_changed` and
`backup_saved_to` ([`sequence-result.schema.json`](sequence-result.schema.json)).

## Exit codes (no new code)

| Code | Added meanings |
|---|---|
| 1 | refused: `unsafe_required`, `bypassed`, `tuner_mode`, `edit_mode`, `unrecognised_state`, `not_bypassed`, `firmware_mismatch` (plus the 0.3.0 reasons) |
| 2 | usage: bad typed input, missing `bypass off` position, invalid backup file, both or neither of `--slot` / `--all` |
| 6 | connection lost / timeout, also mid-sequence (step report printed) |
| 7 | NAK, also mid-sequence; automatic backup failed its cross-check (nothing written) |
| 8 | acknowledged but verification failed (bypass not shown, slot or image read-back differs) |
