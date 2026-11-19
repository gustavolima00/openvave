# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.5.0]

Finding and choosing a pedal. `openvave scan` lists every Tank-G in range without connecting,
`openvave select` makes one the default (with a nickname), `openvave device` shows the choice and
`openvave forget` clears it. Every pedal command then uses the chosen pedal, in one order
(`--device`, `OPENVAVE_DEVICE`, the default, the only one in range), says which one on a `pedal:`
line, and **never falls back** to another pedal. The library gains the same pieces
(`KnownDevices`, `resolve_target`, `scan`, `identify`) and a long-lived connection
(`TankG.open()` / `close()` / `is_connected`, `TankG.connect_selected()`). No new pedal message:
`scan --identify` sends only the confirmed handshake query. stdout and exit codes of existing
commands are unchanged, and JSON only gains keys.

### Added (library, spec 005 milestone 3): long-lived connection

- `TankG.open()` and `TankG.close()`: what `async with` does on enter and exit, for code that
  keeps one connection for many operations. `close()` is idempotent; after it, `open()` scans and
  handshakes again on the same object. `open()` on a session that is open or lost raises
  `RuntimeError`.
- `TankG.is_connected`: true between a successful `open()` and `close()` or a lost link.
- Lost link: the pending operation and every later one raise `ConnectionLostError` at once,
  without sending anything; nothing is retried or reconnected.
- `TankG.connect()` also accepts a `KnownDevice` or a `Target`; `TankG.connect_selected(*,
  config_path=None, scan_timeout=…, timeout=…)` connects to the default pedal of the known-pedals
  file (`chosen_by="selected"`) and raises `ConfigError` when there is no default. `pedal.device`
  carries `nickname` and `chosen_by`. `TankG.connect()` without an argument still reads no
  configuration.
- An operation on a session that was never opened, or is closed, still raises
  `ConnectionLostError("session is closed")` as in 0.4.0.
- `FakeTransport.lose_link()` simulates a lost link between operations.

### Changed (command line, spec 005 milestone 2): every command uses the chosen pedal

- Every pedal command (`info`, `preset dump|backup|select|reload|save|restore`, `set`,
  `bypass`, `loopback`, `watch`) chooses its pedal in one order: `--device VALUE`, then
  `OPENVAVE_DEVICE`, then the default pedal (`openvave select`), then the only Tank-G in range as
  in 0.4.0. `--device` and `OPENVAVE_DEVICE` take an identifier or a known nickname; neither
  changes the configuration. A text that is neither is exit 2 before any scan, listing the known
  nicknames.
- **No fallback**: when a pedal is chosen, the scan stops as soon as it is seen and nothing else
  is ever connected to. If it is not seen within `--scan-timeout`, the command exits 3 naming it,
  lists the Tank-G pedals it did see (`seen:`) and says how to use another one. Several pedals
  without a choice still exit 4; the message now lists them strongest first, with the nicknames
  of known pedals, and suggests `--device ID` or `openvave select ID`.
- A `pedal:` line on stderr says which pedal a command uses and why, before connecting, e.g.
  `pedal: stage  8F3A21C4…  -58 dBm  (selected)`; the reason is `(selected)`, `(--device)`,
  `(OPENVAVE_DEVICE)` or `(only one found)`. Not printed with `--json`. stdout and exit codes of
  every command are unchanged.
- JSON: the `device` object gains `nickname` (string or null) and `chosen_by`
  (`device_option`, `environment`, `selected`, `only_one_found`). `schema_version` stays 2; the
  001 `info` and `preset-dump` schemas list the two optional keys.
- An invalid configuration file makes a pedal command exit 2 with the `forget --all` hint, except
  when `--device` / `OPENVAVE_DEVICE` gives an identifier: then the command runs and warns
  `(nicknames unavailable)`.
- After a successful command on a known pedal, its `last_name`, `last_firmware` and
  `last_seen_at` are updated (best effort; a file that cannot be written does not fail the
  command). An unknown pedal leaves the file untouched.
- Library: `openvave.transport.ble.open_ble(target, scan_timeout)` takes a `Target`, an
  identifier or `None`; with a target it raises `TargetNotFoundError` instead of choosing another
  pedal. `TankG.connect()` without an argument behaves as in 0.4.0.

### Added (command line, spec 005 milestone 1)

- `openvave scan [--all] [--identify]`: lists every Tank-G in range, strongest signal first, for
  the whole `--scan-timeout`, and connects to nothing. `*` marks the default pedal and known
  pedals show their nickname; a default that is not in range gets a `not seen` line. `--all` adds
  other Bluetooth advertisers flagged `(not a Tank-G)`. `--identify` connects to each pedal in
  turn and adds its firmware (`fw 96`, or `fw ? (<reason>)`), sending only the `0x11` query.
  Exit 0 when a Tank-G is listed, 3 when none, 5 when Bluetooth is unavailable. `--json`:
  `specs/005-device-selection/contracts/scan.schema.json`.
- `openvave select [TARGET] [--name NICKNAME] [--offline]`: makes a pedal the default. TARGET is
  a known nickname (no scan), a full identifier (checked by a scan unless `--offline`) or an
  identifier prefix of at least 4 hex digits matching one pedal in range; without TARGET, the only
  pedal in range. Several candidates exit 4, none exit 3, a bad or already used nickname exit 2;
  nothing is saved unless it succeeds. Never prompts.
- `openvave device [--check]` shows the default pedal, the known pedals and the configuration
  path, without Bluetooth; `--check` scans for the default (exit 3 when not in range).
  `openvave device rename OLD NEW` changes a nickname.
- `openvave forget [TARGET | --all]` clears the default, removes one known pedal, or all of them;
  `--all` moves an invalid configuration file aside (`devices.json.invalid-<time>`).
- `OPENVAVE_CONFIG` sets the configuration file; by default
  `~/.config/openvave/devices.json` (`$XDG_CONFIG_HOME/openvave/devices.json` when set,
  `%APPDATA%\openvave\devices.json` on Windows). An invalid file makes `device`, `select` and
  `forget` exit 2 with a hint; `scan` still lists pedals with a warning.
- Library: `openvave.scan(timeout, *, include_all=False, known=None)`,
  `openvave.identify(entries)` and `openvave.ScanEntry`. `discover()` is unchanged.

### Added (library, spec 005 milestone 0)

- `openvave.KnownDevices` and `openvave.KnownDevice`: the pedals you have selected, a default
  pedal and their nicknames, kept in one JSON file (`devices.json`, `format_version` 1, schema in
  `specs/005-device-selection/contracts/devices-file.schema.json`). Every operation (`select`,
  `rename`, `forget`, `forget_all`, `find`, `record_seen`) returns a new value; `save()` writes
  the file atomically with mode `0600`. Unknown keys in the file are kept. An invalid file is
  refused, never guessed at.
- `openvave.default_config_path()`: `$OPENVAVE_CONFIG`, else
  `$XDG_CONFIG_HOME/openvave/devices.json`, else `%APPDATA%\openvave\devices.json` on Windows,
  else `~/.config/openvave/devices.json`.
- `openvave.resolve_target(option, environment, known)` and `openvave.Target`: the one rule that
  chooses a pedal (`--device`, then `OPENVAVE_DEVICE`, then the default), pure. An identifier
  (MAC or UUID shape) is used as is; anything else must be a known nickname.
- `openvave.ConfigError` (exit code 2) and `openvave.TargetNotFoundError` (a
  `NoDeviceFoundError`, exit code 3, with `.target` and `.seen`).
- `DeviceInfo` gains the optional fields `nickname` and `chosen_by` (default `None`); existing
  constructors keep working.

Nothing reads the configuration unless one of these is called: `TankG.connect()` and
`discover()` behave as in 0.4.0, and the command line does not change yet.

### Tested

- On the owner's pedal (fw 96, macOS 26), reads only: `scan`, `scan --identify`, `select`,
  `info` with the default and with `--device`, `device --check`, `forget`, a second process
  while one is connected (exit 3 with the hint), and a long-lived `open()` / `close()` session.
  Details under "Hardware check" in Milestone 4 of `specs/005-device-selection/tasks.md`. With the phone
  app connected, `scan` and `info` exit 3 with the hint. The identifier survives Bluetooth off
  and on. Switching the pedal off during a long-lived session raises `ConnectionLostError`. Not run on hardware: two pedals at once.

## [0.4.0]

Remote editing without edit mode, and the first release that can **change stored presets**:
`set` now works in normal mode, `preset reload` discards edits, `bypass` and `loopback` toggle
volatile state, and `preset save` / `preset restore` write stored presets behind `--unsafe` and
an automatic, verified backup. Every new message was first sent by openvave on the owner's pedal
(fw 96) in two gate sessions, with a backup before and after each step.

### Added

- **Several fields over one connection**: `openvave set gain=95 treble=58 reverb_decay=room:18
  delay_on=on led_colour=#2040ff --experimental`. One session reads the pedal once, sends every
  knob field in a single knob-block write (rebuilt from that read), then each block switch and the
  LED colour, and checks each write's ACK and re-read before the next. Typed knobs take
  `POSITION`, `TYPE:POSITION` or `raw:N`. The batch is refused as a whole, with nothing sent, if
  any field is; fields already set are skipped. `--dry-run` prints every frame; `--json` prints
  a `set-fields-result.schema.json` document, also when the batch stops midway. A failure
  mid-batch (NAK, lost link, re-read differs) stops without retrying and lists every field as
  applied / unknown / not applied / not sent. The `set FIELD VALUE [--type | --raw]` form is
  unchanged. Library: `TankG.plan_set_fields(changes)` / `set_fields(changes)`, new types
  `EditPlan`, `EditWrite`, `FieldEdit`, `EditResult`, `EditWriteOutcome`, and
  `OpenvaveError.edit` (the partial result on an error raised mid-batch).

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
- **Bypass**: `openvave bypass on [--discard-edits]` sends `01` to
  `0xE1000000 + i` for the loaded preset (normal mode only) and reports `applied` when the pedal
  reads slot `ff` with an all-zero buffer, then prints `Leave bypass: openvave bypass off 1B`.
  `openvave bypass off <position>` leaves bypass with the confirmed preset select, only when the
  pedal is bypassed (refusal `not_bypassed` otherwise); without a position it exits 2 and names
  the bank the pedal reports. Library: `TankG.plan_bypass_on()` / `bypass_on()` (result
  `return_index`), `plan_bypass_off(i)` / `bypass_off(i)`, `WriteTarget.bypass(i)`. The message is
  `confirmed` on fw 96 (spec 004 gate sessions A and B), so `bypass on` runs without
  `--experimental`.
- **Loopback** (experimental): `openvave loopback on|off` reads the status byte (`0xD0000000`),
  writes `01`/`00`, and reads it back; never followed by a commit; an equal value sends nothing.
  Library: `TankG.plan_loopback(on)` / `set_loopback(on)`, `WriteTarget.loopback()`. Message
  `observed`: `on` mixes the pedal's Bluetooth audio (e.g. a phone backing track) into the USB
  recording, `off` leaves it out (still heard); the flag persists across a power cycle.
- `WriteTarget.persistent` and refusal reasons `edit_mode` and `not_bypassed`. The write
  allowlist grows by the two volatile kinds above; bypass data other than `01`, an index above 35,
  loopback data other than `00`/`01` or any other length stay unencodable.
- **Save** (UNSAFE): `openvave preset save [--to POSITION] --unsafe` stores the edit
  buffer in the loaded slot (or `--to`), normal mode only, with the phone app's sequence: slot
  write to `2 + 21·i` (21 bytes), read back (a mismatch stops before the commit), 300 ms, the
  empty commit write to `0xF0000000`, 100 ms, select, then verifies stored slot, position and
  buffer. Nothing to save: `1C already holds this sound; nothing sent`. Library:
  `TankG.plan_save(to)` / `save_preset(to, unsafe=True, on_backup=…)`. The slot write and the
  commit are `confirmed` on fw 96 (gate sessions A and B).
- **Restore** (UNSAFE): `openvave preset restore FILE (--slot POSITION | --all)
  --unsafe` writes back an openvave backup file, checked before connecting
  (`openvave.backup.restore_problems`). `--slot` uses the save sequence with the file's bytes;
  `--all` writes the whole 758-byte image to `0x0` in one message (split over several Bluetooth
  writes by the transport), commits, selects the preset that was loaded and verifies with a full
  read. Lists the slots that differ; nothing differs → nothing sent. A file from another firmware
  needs `--experimental` (`firmware_mismatch`); unsaved edits need `--discard-edits`. Library:
  `TankG.plan_restore(backup, slot=i | all=True)` / `restore(...)`. The slot write, the image
  write and the commit are `confirmed` on fw 96 (gate sessions A and B).
- Both take an **automatic backup** before the first write
  (`tankg-backup-<time>-before-save|restore.json` in `--backup-dir`, never overwriting) and stop
  if it fails its cross-check or cannot be written. A failure mid-sequence prints every step
  (ACK / NAK / no reply / not sent), whether stored presets may have changed, and the recovery
  commands; nothing is retried. Exit codes as before (1 refused, 6 lost link, 7 NAK, 8 read-back
  differs). JSON: [`sequence-result.schema.json`](specs/004-remote-edit-save-restore/contracts/sequence-result.schema.json).
- New opt-in `--unsafe` (`unsafe=True`), required by every command that changes stored presets and
  never implied by `--experimental`; refusal reasons `unsafe_required` and `firmware_mismatch`.
- Three **persistent** write targets, `WriteTarget.stored_slot(i)`, `.commit()` and
  `.stored_image()` (`persistent` is true for them), rows in "Write messages" at `confirmed`
  on fw 96 (spec 004 gate sessions A and B), so save and restore run without `--experimental`;
  `--unsafe` is still required. Only `save_preset` / `restore` send them, only with
  `unsafe=True`, after the backup. Library types `SequencePlan`, `SequenceStep`,
  `SequenceResult`, `StepOutcome`; errors raised mid-sequence carry `.sequence`.
- The BLE transport splits a request longer than one Bluetooth write (`ATT MTU − 3`) into
  consecutive chunks (only the 773-byte image write needs it; observed at MTU 185: one ACK).
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

### Tested

- Spec 004 gate session A on a TANK-G v2, fw 96 (2026-11-18), each message sent once by openvave
  with a backup before and after: bypass on/off, MOD switch and LED colour in normal mode, loopback
  off/on (persists across a power cycle; on = Bluetooth audio in the USB recording), save to 1C (persists across a power cycle), restore of
  one slot, the stored-image write as a no-op and as restore all (persists across a power cycle).
  The pedal ended equal to its pre-session backup. Excerpts: `captures/fw96/20261118-gate-*.jsonl`.
- Spec 004 gate session B on the same pedal (2026-11-18, after a power cycle, a new connection per
  command, loaded preset 1A, target slot 1D): bypass on/off, save to 1D (persists across a power
  cycle), restore of 1D, and restore all (persists across a power cycle). The pedal ended equal to
  its pre-session backup B0. Bypass, stored slot, commit and stored image are now `confirmed`;
  loopback, the block switches and the LED colour stay `observed`. Excerpts:
  `captures/fw96/20261118-gate-*_b.jsonl`.

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
