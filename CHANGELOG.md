# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- `openvave preset reload [--discard-edits] [--dry-run]` / `TankG.reload_preset()` /
  `TankG.plan_reload()`: discards unsaved edits by selecting the loaded preset again (the
  confirmed preset-select write) and verifies the buffer equals the stored preset. Nothing is sent
  when there is nothing to discard; edit mode needs `--discard-edits`.
- Reverb types for the decay knob, named as in the Tank-G manual: **room**, **spring**, **cloud**
  (the app's blue, orange, green sections; between two types the reverb is off).
  `openvave set reverb_decay 10 --type spring`; without `--type` the preset's current type is
  kept (refusal `type_required` when the knob sits between two types); `--raw 53` writes the raw
  byte. Library: `set_field("reverb_decay", ("spring", 10))`, `(None, 10)` to keep the type,
  `openvave.protocol.REVERB_TYPES`, `TYPED_FIELDS`, `type_raw()`, `type_parts()`. Output shows
  both readings (`5 (room 6) → 53 (spring 10)`).
- The same for MOD FX (`chorus`, `phaser`, `tremolo`) and DLY MIX (`analog`, `tape`, `dual`):
  `set mod_fx 20 --type phaser`, `set delay_mix 30 --type tape`; `preset dump` / `watch` show
  `type: chorus 1`. Their split was checked against the phone app on the pedal (15 readings, all
  fit). `openvave.protocol.MOD_FX_TYPES`, `DELAY_MIX_TYPES`.
- **Bypass** (experimental): `openvave bypass on [--discard-edits]` sends `01` to
  `0xE1000000 + i` for the loaded preset (normal mode only) and reports `applied` when the pedal
  reads slot `ff` with an all-zero buffer, then prints `Leave bypass: openvave bypass off 1B`.
  `openvave bypass off <position>` leaves bypass with the confirmed preset select, only when the
  pedal is bypassed (refusal `not_bypassed` otherwise); without a position it exits 2 and names
  the bank the pedal reports. Library: `TankG.plan_bypass_on()` / `bypass_on()` (result
  `return_index`), `plan_bypass_off(i)` / `bypass_off(i)`, `WriteTarget.bypass(i)`. The message is
  `hypothesis` (seen once from a `poc/` script, spec 004 check 2; openvave has not sent it), so
  `bypass on` needs `--experimental`.
- **Loopback** (experimental): `openvave loopback on|off` reads the status byte (`0xD0000000`),
  writes `01`/`00`, and reads it back; never followed by a commit; an equal value sends nothing.
  Library: `TankG.plan_loopback(on)` / `set_loopback(on)`, `WriteTarget.loopback()`. Message
  `hypothesis` (app code only); what loopback does on the Tank-G is not known yet.
- `WriteTarget.persistent` and refusal reasons `edit_mode` and `not_bypassed`. The write
  allowlist grows by the two volatile kinds above; bypass data other than `01`, an index above 35,
  loopback data other than `00`/`01` or any other length stay unencodable.
- **Save** (UNSAFE, experimental): `openvave preset save [--to POSITION] --unsafe` stores the edit
  buffer in the loaded slot (or `--to`), normal mode only, with the phone app's sequence: slot
  write to `2 + 21·i` (21 bytes), read back (a mismatch stops before the commit), 300 ms, the
  empty commit write to `0xF0000000`, 100 ms, select, then verifies stored slot, position and
  buffer. Nothing to save: `1C already holds this sound; nothing sent`. Library:
  `TankG.plan_save(to)` / `save_preset(to, unsafe=True, on_backup=…)`.
- **Restore** (UNSAFE, experimental): `openvave preset restore FILE (--slot POSITION | --all)
  --unsafe` writes back an openvave backup file, checked before connecting
  (`openvave.backup.restore_problems`). `--slot` uses the save sequence with the file's bytes;
  `--all` writes the whole 758-byte image to `0x0` in one message (split over several Bluetooth
  writes by the transport), commits, selects the preset that was loaded and verifies with a full
  read. Lists the slots that differ; nothing differs → nothing sent. A file from another firmware
  needs `--experimental` (`firmware_mismatch`); unsaved edits need `--discard-edits`. Library:
  `TankG.plan_restore(backup, slot=i | all=True)` / `restore(...)`.
- Both take an **automatic backup** before the first write
  (`tankg-backup-<time>-before-save|restore.json` in `--backup-dir`, never overwriting) and stop
  if it fails its cross-check or cannot be written. A failure mid-sequence prints every step
  (ACK / NAK / no reply / not sent), whether stored presets may have changed, and the recovery
  commands; nothing is retried. Exit codes as before (1 refused, 6 lost link, 7 NAK, 8 read-back
  differs). JSON: [`sequence-result.schema.json`](specs/004-remote-edit-save-restore/contracts/sequence-result.schema.json).
- New opt-in `--unsafe` (`unsafe=True`), required by every command that changes stored presets and
  never implied by `--experimental`; refusal reasons `unsafe_required` and `firmware_mismatch`.
- Three **persistent** write targets, `WriteTarget.stored_slot(i)`, `.commit()` and
  `.stored_image()` (`persistent` is true for them), rows in "Write messages" at `hypothesis`
  (spec 004 checks 3–4 were `poc/` sends). Only `save_preset` / `restore` send them, only with
  `unsafe=True`, after the backup. Library types `SequencePlan`, `SequenceStep`,
  `SequenceResult`, `StepOutcome`; errors raised mid-sequence carry `.sequence`.
- The BLE transport splits a request longer than one Bluetooth write (`ATT MTU − 3`) into
  consecutive chunks (only the 773-byte image write needs it; hypothesis until gated).
- Pedal state: `openvave.PedalState`, `openvave.protocol.classify(global, buffer)`,
  `TankG.state()` (confirms bypass with a second read 300 ms later) and
  `DeviceSnapshot.pedal_state`. `info` and `preset dump` print a `state:` line (in bypass: no
  decoded preset fields and `bank <n>, slot not reported`); `watch` prints the state in its header
  and a line when it changes (`loading` for one bypass-looking cycle, `bypass` for two). JSON adds
  a top-level `pedal_state` to `info` and `preset dump` and to `watch --json` start and change
  events; existing fields keep their meaning (`schema_version` 2).

### Changed

- **`openvave set` works in normal mode** (spec 004 check 1: the app never enters edit mode, and
  the knob block is applied in normal mode, confirmed over two connections). It is refused in
  tuner mode (`tuner_mode`), while the pedal is bypassed (`bypassed`) and in states openvave does
  not recognise (`unrecognised_state`). The refusal reason `not_edit_mode` is no longer raised.
  Block switches and `led_colour` still need `--experimental`.
- The "Not saved" line after a write now names the discard command
  (`Not saved. Discard: openvave preset reload`).
- **openvave can now change stored presets**, replacing the 0.3.0 statement that it never saves or
  overwrites one: it does so only through `preset save` and `preset restore`, only with `--unsafe`,
  and always after an automatic, verified backup. Every other write stays volatile.
- `openvave preset dump` now also reads the global block (to report the pedal state).
- Connecting is faster: the Bluetooth scan stops 1 s after the pedal is seen (or as soon as the
  `--device` identifier is seen) instead of always waiting `--scan-timeout` (5 s). A second pedal
  seen within that second still gives exit 4. `openvave.discover()` still scans the whole timeout.
  Measured before: `set gain 90` took 11 s on macOS.
- JSON write results validate against the spec 004 extension of the schema
  ([`write-result.schema.json`](specs/004-remote-edit-save-restore/contracts/write-result.schema.json)):
  commands `preset reload`, `bypass on|off`, `loopback on|off`, target kinds `bypass` and
  `loopback`, the new refusal reasons, change region `status`, and `return_index` /
  `return_position` in a `bypass on` result.
- A write refused because the pedal is bypassed now points to `openvave bypass off <position>`.

- `preset dump` and `watch` human output show reverb decay (preset byte 15) as reverb type and
  position: `type: room 6` after the field line (`off` between types), and
  `5 (room 6) → 64 (spring 21)` in watch changes. JSON is unchanged (`schema_version` 2, raw value
  only). Library: `openvave.cli.render.type_reading()`. `REVERB_SECTIONS` /
  `reverb_decay_parts` (0.3.0) still give the app's colour reading.

### Documentation

- [`specs/protocol/app-features.md`](specs/protocol/app-features.md): inventory of the official
  app's Tank-G features and the messages behind each (edit mode, save, bypass, loopback, import /
  export, factory restore), with confidence, risk and a proposed scope for spec 004.

## [0.3.0]

The first release that **writes** to the pedal, and only to the edit buffer: a full backup of the
36 stored presets, then guarded writes of one field or one preset select at a time. Nothing is
ever saved: leaving edit mode on the pedal without saving restores the stored preset. Every write
was first sent by hand on the owner's pedal (fw 96) with a backup before and after; the backups
were identical.

### Added

- `openvave preset backup [--output PATH] [--force]`: reads the stored-image header, the 36 stored
  presets one by one and the whole image, cross-checks them, and writes a versioned JSON file
  ([`backup.schema.json`](specs/003-preset-backup-edit-writes/contracts/backup.schema.json)).
  Read-only (`0x11` and `0x23` only). A cross-check mismatch writes no file and exits 7.
- `openvave set <field> <value>`: changes one field of the current preset in the edit buffer. Knobs
  and selectors (`gain`, `treble`, …, `amp_type`, `ir_cab`), block switches (`amp_on`, `mod_on`,
  `delay_on`, `reverb_on`: `on`/`off`) and `led_colour` (`#rrggbb` or `r,g,b`). Refused unless
  the pedal is in edit mode. After the write it checks the ACK and re-reads the buffer.
- `openvave preset select <position>`: selects preset `1A`–`9D` (or index 0–35). Refused in edit
  mode unless `--discard-edits` (the unsaved edits are lost). Reports applied only when the pedal
  shows the new bank and slot and the buffer equals the stored preset.
- `--dry-run` on `set` and `preset select`: does the reads, prints the exact write frame, sends
  nothing. The frame printed is the frame that would be sent.
- `--experimental`: needed for a write whose message is not yet `confirmed`, or on firmware other
  than 96. Confirmed on fw 96 (two independent hardware sessions): the knob block and preset
  select, so `set gain 90` and `preset select 2C` run without it. Still `observed` (one session):
  the four block switches and the LED colour.
- Exit code 8: the pedal acknowledged a write but the re-read does not show it (not applied).
  Exit 1 now also covers a refused write; exit 7 covers a NAK (raw reply printed). Writes are never
  retried.
- `--json` for the three commands: the 0.2.0 envelope plus `backup` / `saved_to`, or `plan` and
  `result`
  ([`write-result.schema.json`](specs/003-preset-backup-edit-writes/contracts/write-result.schema.json)).
  `schema_version` stays 2.
- Library: `TankG.backup()`, `plan_set()`, `set_field()`, `plan_select()`, `select_preset()`;
  types `Backup`, `StoredPreset`, `WritePlan`, `WriteResult`; errors `WriteRefusedError`,
  `WriteNakError`, `WriteNotAppliedError`; `openvave.protocol.StorageRead`, `WriteTarget`,
  `WRITE_MESSAGES`, `build_write`, `parse_write_reply`, `build_storage_read`,
  `parse_storage_reply`
  ([library contract](specs/003-preset-backup-edit-writes/contracts/library-api.md)).
- `openvave.protocol.reverb_decay_parts(raw)` and `REVERB_SECTIONS`: preset byte 15
  (`reverb_decay`) read the way the phone app shows it, as a colour section (blue, orange or green,
  44 raw values each; most likely the reverb type) and a position 1–40, or `X` past 40. JSON is
  unchanged (`schema_version` 2): `reverb_decay` still reports the raw 0–127 value.

### Changed

- Safety: the encoder now accepts write memory (`0x22`), but only to four targets, all in the
  edit buffer ([Write messages](specs/protocol/command-layer.md)):
  - knob block `0x10000004` × 14 (preset bytes 4–17),
  - block switch `0x10000000 + k` × 1, k = 0–3 (preset bytes 0–3),
  - LED colour `0x10000012` × 3 (preset bytes 18–20; whether they drive the LED is still a
    hypothesis, so the byte map leaves them unnamed),
  - preset select `0xE0000000 + i` × 1, data `01`, i = 0–35.

  Erase (`0x21`), the save commit (`0xF0000000`), stored-preset writes (`0x0`–`0x2F5`) and the
  loopback write (`0xD0000000`) still cannot be encoded: openvave never saves or overwrites a
  stored preset.

### Tested

- Firmware 96 on macOS 26: two backups identical; two gate sessions of writes (2026-11-17),
  eleven writes in all, each ACKed and applied, each followed by a backup equal to the first.

## [0.2.0]

Every byte of the current preset, global settings and status regions is mapped or explicitly
unknown, and a new `openvave watch` command maps the pedal one control at a time. Still
**read-only**: only the handshake query (`0x11`) and region reads (`0x23`) are ever sent.

### Breaking

- JSON output is now `schema_version` 2 (`info`, `preset dump`, `watch --json`). Two field names
  changed:

  | 0.1.0 name | 0.2.0 name | Why |
  |---|---|---|
  | `knob_unknown` | `gain` | Preset byte 6 is the gain knob (one knob at a time, two sessions) |
  | `not_in_edit_mode` | `mode` | Global byte 3 is a three-state mode selector: `0` edit, `1` normal, `2` tuner. The tuner value refutes the 0.1.0 edit-mode on/off reading |

  `value` keeps its meaning (the raw byte). For `mode`, `display` reads `edit` / `normal` /
  `tuner`.

### Added

- `openvave watch`: polls global, current preset and status (default every 0.5 s, minimum
  0.2 s) and prints each byte that changes, with the field it belongs to. Type a label and Enter
  before each step to tag the changes; `q` stops. Options `--interval`, `--duration`,
  `--record PATH`, `--no-record`, `--json` (JSON Lines,
  [`watch-event.schema.json`](specs/002-preset-byte-map/contracts/watch-event.schema.json)).
  Every session is recorded by default to `captures/private/<date>-watch.jsonl` (git-ignored)
  in the [capture format](captures/README.md).
- A byte map of all 26 bytes (global 0–3, preset 0–20, status 0), mirrored from
  [`command-layer.md`](specs/protocol/command-layer.md) and checked against it by the test suite.
  Named: browsed bank, bank, slot, mode; amp/mod/delay/reverb block on/off, noise gate, amp
  type, gain, treble, middle, bass, volume, mod fx, mod speed, delay mix, delay time, reverb
  decay, reverb mix, IR cab. Unknown: preset 18–20 and status 0.
- `preset dump` and `info` print one decoded line per named field (value, range, confidence;
  ` ?` on hypotheses, `OUT OF RANGE` when a byte leaves its documented range) and an `unknown:`
  line. On firmware other than 96 the header says `(decoded with the fw 96 map)`.
- JSON `fields[]` items gain `raw`, `mask`, `encoding`, `range`, `display`, `interpreted`,
  `out_of_range`
  ([`decoded-field.schema.json`](specs/002-preset-byte-map/contracts/decoded-field.schema.json));
  each region gains `map_firmware` and `unknown_offsets`.
- Library: `TankG.watch()`, `openvave.protocol.decode_region()` / `diff()` / `BYTE_MAP` /
  `MAP_FIRMWARE`, and the types `Encoding`, `ByteMapEntry`, `DecodedField`, `DecodedRegion`,
  `ByteChange`, `WatchStart`, `WatchChange`
  ([library contract](specs/002-preset-byte-map/contracts/library-api.md)).
- `FakeTransport` serves several replies to the same request in order (the last one repeats),
  so a recorded watch session replays as it happened.

### Changed

- Confidence: preset 0–17 and global 3 are `confirmed` (two independent sessions each), global
  0–2 `observed`. `reverb_mix` and `ir_cab`, hypotheses in 0.1.0, are confirmed.
- `ir_cab` and `amp_type` are selectors with 9 positions (0–8).

### Deprecated

- `openvave.models.KNOWN_FIELDS` and `FieldSpec`: thin aliases derived from `BYTE_MAP`, so they
  carry the 0.2.0 names. Use `openvave.protocol.BYTE_MAP` and `ByteMapEntry`. They will be
  removed before 1.0.

### Tested

- Firmware 96 on macOS 26, including `watch` on hardware (seven sessions, 2026-11-16).

## [0.1.0]

First release: a **read-only** BLE client for the M-VAVE Tank-G.

### Added

- `openvave info`: finds the pedal, runs the handshake and reads the device info, global settings,
  current preset and status regions.
- `openvave preset dump`: reads the 21-byte current preset buffer and prints it with offsets and
  confidence-labelled fields (`confirmed` / `observed` / `hypothesis`).
- `--json` output for both commands, `schema_version` 1
  ([`info`](specs/001-readonly-ble-connection/contracts/info.schema.json),
  [`preset dump`](specs/001-readonly-ble-connection/contracts/preset-dump.schema.json)).
- Global options `--device`, `--scan-timeout`, `--timeout`, `--trace` (hex of every frame on stderr).
- Exit codes 0–7 as a public contract
  ([CLI contract](specs/001-readonly-ble-connection/contracts/cli.md#exit-codes)).
- Python library: `TankG` (`connect()`, `over()`, `read()`, `snapshot()`), `discover()`, typed
  models and errors, and `FakeTransport` for testing without a pedal
  ([library contract](specs/001-readonly-ble-connection/contracts/library-api.md)).
- Safety: only the handshake query (`0x11`) and region reads (`0x23`) can be encoded; every other
  command byte raises `UnsafeCommandError`.

### Tested

- Firmware 96 on macOS 26. Other firmware versions work with a `warning:` on stderr. Linux and
  Windows are untested on hardware.
