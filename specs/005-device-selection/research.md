# Research: Finding, selecting and connecting to Tank-G pedals

All decisions below resolve the Technical Context; no NEEDS CLARIFICATION remains. Facts about the
pedal come from [`ble-gatt.md`](../protocol/ble-gatt.md) and
[`command-layer.md`](../protocol/command-layer.md) with the confidence stated there. No decision
here adds a pedal message.

## R1 — Where the known pedals are stored

- **Decision**: one JSON file, `devices.json`, found in this order:
  1. `$OPENVAVE_CONFIG` (a file path; empty means unset);
  2. `$XDG_CONFIG_HOME/openvave/devices.json` when `XDG_CONFIG_HOME` is set;
  3. Windows: `%APPDATA%\openvave\devices.json`;
  4. otherwise `~/.config/openvave/devices.json` (macOS and Linux).

  Written atomically (temporary file in the same directory, then replace), directory created on
  first save, file mode `0600` where the platform has modes. Missing file = nothing known. The
  path is printed by `openvave device` and by `select`.
- **Rationale**: no new dependency (Constitution VII); JSON is read and written by the standard
  library and is already the project's file format (backups, schemas). `~/.config` on macOS is
  where command-line tools are expected to keep settings and keeps one path to document for two
  platforms.
- **Alternatives**: `platformdirs` (a dependency for one path); TOML (the standard library reads
  it but cannot write it); `~/Library/Application Support/openvave` on macOS (correct for apps,
  unusual for CLIs, a third path to document); a file per project directory (the pedal belongs to
  the user, not to a directory).

## R2 — File format

- **Decision**: `{"format_version": 1, "default": "<identifier>" | null, "devices": [...]}`; each
  device: `identifier`, `nickname` (string or null), `added_at`, `selected_at` (null until first
  selected), `last_name`, `last_firmware` (null until seen), `last_seen_at`. Times are UTC ISO 8601.
  Unknown keys are kept on rewrite. A file with another `format_version`, invalid JSON, a
  `default` that is not in `devices`, duplicate identifiers or duplicate nicknames is **invalid**:
  loading raises a configuration error (exit 2 in the CLI) that names the path and the problem.
  `forget --all` forgets every known pedal; on an invalid file it moves the file to
  `devices.json.invalid-<timestamp>` and starts empty (plain `forget` on an invalid file exits 2
  and says so).
  Schema: [`contracts/devices-file.schema.json`](contracts/devices-file.schema.json).
- **Rationale**: FR-012/FR-014; a versioned format can grow; refusing an invalid file is safer than
  guessing which pedal to write to (spec Edge Cases).
- **Alternatives**: silently ignoring an invalid file (a command could then pick the only pedal in
  range, which may not be the one the owner selected).

## R3 — Identifiers and nicknames

- **Decision**: an **identifier** is what the platform reports: a MAC (`AA:BB:CC:DD:EE:FF`) on
  Linux and Windows, a UUID (`8-4-4-4-12` hex) on macOS. A string is treated as an identifier when
  it has one of those two shapes; anything else given to `--device` / `OPENVAVE_DEVICE` is a
  nickname and must be known (else exit 2 before scanning, FR-018). Both are compared
  case-insensitively and stored as the platform reported them. Nicknames match
  `[A-Za-z0-9_-]{1,32}` and must not have an identifier's shape or be all hex digits of length ≥ 4
  (so a nickname can never be mistaken for an identifier prefix, R4).
- **Rationale**: FR-015, FR-016; the two shapes cannot collide with the nickname alphabet once
  all-hex nicknames are excluded.
- **Alternatives**: a `name:` / `id:` prefix syntax (more typing for no gain); resolving nicknames
  inside `TankG.connect` (would read the user's configuration implicitly, against FR-028).

## R4 — What `select` accepts

- **Decision**: `openvave select [TARGET]` where TARGET is, tried in this order: a known nickname
  (no scan needed); a full identifier (scan until seen, unless `--offline`); an identifier prefix
  of ≥ 4 hex characters (full scan, must match exactly one Tank-G in range, else exit 4 listing
  the matches or exit 3). No TARGET: a scan as commands do today; exactly one Tank-G is selected,
  several → exit 4, none → exit 3. **Row numbers are not accepted** (spec amended).
- **Rationale**: rows are ordered by signal strength, which changes between the scan the owner
  read and the scan `select` runs; a row number could silently select the other pedal. A prefix is
  as short to type and stable.
- **Alternatives**: row numbers with a cached last scan (hidden state, stale after seconds);
  interactive pick (FR-011 forbids prompts).

## R5 — Choosing the pedal for a command

- **Decision**: one pure function, `resolve_target(option, environment, known) → Target | None`,
  applied before any Bluetooth use:

  | Order | Source | `chosen_by` |
  |---|---|---|
  | 1 | `--device VALUE` | `device_option` |
  | 2 | `OPENVAVE_DEVICE` (non-empty) | `environment` |
  | 3 | the default in the configuration | `selected` |
  | 4 | none: the only Tank-G in range | `only_one_found` |

  For 1–2 the value is an identifier (used as is, annotated with its nickname if known) or a known
  nickname. With a target, the scan stops when that identifier is seen and nothing else is
  connected to (FR-017). When it is not seen within `--scan-timeout`, a new
  `TargetNotFoundError` (subclass of `NoDeviceFoundError`, exit 3) carries the target and the
  Tank-G pedals that were seen; the CLI lists them with the hints (FR-019). Without a target the
  0.4.0 rules apply unchanged, including the 1 s grace and exit 4. The configuration is loaded
  only when it is needed: `--device` or `OPENVAVE_DEVICE` with an identifier never fails on an
  invalid file (the nickname annotation is skipped with a warning).
- **Rationale**: FR-016 to FR-020 as one table-tested function (FR-030, SC-004).
- **Alternatives**: resolving inside the transport (mixes file I/O into `transport/ble.py`).

## R6 — Scanning for the search

- **Decision**: `openvave scan` uses the existing full-time scan (`discover`, no early stop) and
  sorts Tank-G pedals by signal strength, strongest first, unknown strength last, ties by
  identifier. `--all` lists every advertiser; those whose name is not `TANK-Gv2_BLE` are flagged
  `tank_g: false`. The library gains `scan(timeout, *, include_all=False)` returning the same rows;
  `discover(timeout)` stays as it is.
- **Rationale**: FR-001 to FR-004; the scan code already records every advertiser.
- **Alternatives**: filtering by the BLE-MIDI service UUID as well (other MIDI gear advertises it;
  the name is the confirmed discriminator).

## R7 — Firmware in the search (`--identify`)

- **Decision**: off by default. With `--identify`, after the scan each listed Tank-G is connected
  in turn (strongest first), the confirmed `0x11` handshake runs, the connection closes, and the
  row gains `firmware`. A failure adds `identify_error` (the error's message) to that row and the
  search continues; the exit code still depends only on whether a Tank-G was listed. Known pedals
  get their `last_firmware` updated.
- **Rationale**: FR-005; about 1–2 s per pedal and it takes the pedal's only connection for that
  time, so it must be asked for.
- **Alternatives**: always identify (slow, and surprising for a command described as "sends
  nothing"); never (the owner asked for firmware where cheap; opt-in is the cheap form).

## R8 — Telling the user which pedal

- **Decision**: one stderr line per pedal command in human mode, printed when the pedal has been
  chosen and before connecting:

  ```text
  pedal: stage  8F3A21C4…  -58 dBm  (selected)
  pedal: 8F3A21C4…  -61 dBm  (only one found)
  pedal: home  AA:BB:CC:DD:EE:FF  -70 dBm  (--device)   name: SOMETHING-ELSE (not a Tank-G name)
  ```

  UUIDs are shortened to their first 8 characters plus `…`; MACs are shown in full. With `--json`
  the line is not printed; the `device` object gains `nickname` and `chosen_by`. `DeviceInfo` gains
  the optional fields `nickname` and `chosen_by` (default `None`), so existing constructors and
  JSON consumers keep working; `schema_version` stays 2 (added keys only).
- **Rationale**: FR-021, SC-003, SC-006 (stdout unchanged).
- **Alternatives**: the line on stdout (breaks 0.4.0 output); a header inside each renderer (17
  renderers to change instead of one hook).

## R9 — Updating "last seen"

- **Decision**: after a successful handshake to a **known** pedal, the CLI rewrites its
  `last_name`, `last_firmware` and `last_seen_at`. Best effort: any failure to write is logged at
  debug level and ignored. The library does not do this on its own; it offers
  `KnownDevices.record_seen(...)`.
- **Rationale**: FR-023, FR-028.

## R10 — Long-lived connection in the library

- **Decision**: `TankG` gains `await pedal.open()` and `await pedal.close()` (what `async with`
  already does on enter and exit; close is idempotent), `pedal.is_connected`, and `pedal.device`
  with `nickname` / `chosen_by`. When the transport reports a lost link, the session records it:
  the pending request fails as today, **every later operation raises `ConnectionLostError` at
  once**, and `is_connected` is false. Nothing reconnects. After `close()`, `open()` may be called
  again on the same object (it scans and handshakes again). Opening an already open session raises
  `RuntimeError`. `TankG.connect_selected(config_path=None, …)` builds a session to the default
  pedal; `TankG.connect(device)` also accepts a `KnownDevice`.
- **Rationale**: FR-031a, User Story 6; the session already holds one transport for any number of
  operations, so this is an explicit lifecycle and a lost-link flag, not a new mechanism.
- **Alternatives**: automatic reconnect (hides a pedal that was switched off or taken by the phone
  app, and could resend a write: the project never retries writes); a connection pool or daemon
  (out of scope by clarification).

## R11 — Command names

- **Decision**: top-level `scan`, `select`, `forget`, and `device` (show; `device rename OLD NEW`
  for nicknames). `select TARGET --name NEW` on a known pedal also renames it.
- **Rationale**: the names the owner approved in the spec; `device` is the noun for "what am I
  pointing at". `rename` sits under `device` because a bare `openvave rename` does not say what is
  renamed.
- **Alternatives**: everything under `device` (`device select`, `device forget`): longer for the
  two most used commands. `preset select` keeps its name; the two `select`s act on different
  nouns and the help texts say so.

## R12 — Exit codes and errors

- **Decision**: no new exit code.

  | Situation | Exit | Error |
  |---|---|---|
  | Target (any source) not seen | 3 | `TargetNotFoundError` (new, subclass of `NoDeviceFoundError`) |
  | No Tank-G in range | 3 | `NoDeviceFoundError` |
  | Several Tank-G, no target | 4 | `MultipleDevicesError` |
  | Unknown nickname; bad nickname; nickname in use; invalid configuration file | 2 | `ConfigError` (new, `exit_code = 2`) |
  | `scan` with at least one Tank-G | 0 | — |

- **Rationale**: FR-008; scripts that test for 3 or 4 keep working.

## R13 — Privacy and fixtures

- **Decision**: the file holds device identifiers and nicknames only; it lives outside the
  repository and nothing reads it in tests (every test passes a temporary path; the test suite
  sets `OPENVAVE_CONFIG` to a temporary file for CLI tests so the developer's own file is never
  touched). Fixtures and docs use made-up identifiers (`AA:BB:CC:DD:EE:01`,
  `8F3A21C4-0000-4000-8000-000000000001`).
- **Rationale**: Constitution VI (no MAC addresses committed), "Secrets & privacy".

## R14 — Hardware verification

- **Decision**: reads only, run by the owner (quickstart §4): `scan`; `scan --identify`; `select`;
  `info` with the acting-on line; `device --check`; the same with the phone app connected (expect
  exit 3 and the hint); two `openvave watch`/`info` at once (expect exit 3 for the second);
  `forget`. With one pedal, multi-pedal behaviour is covered by the fake scanner only; if a second
  Tank-G is available the owner repeats §4 with both. Anything observed (for example whether the
  macOS identifier survives a Bluetooth off/on) is recorded in `command-layer.md` with its
  confidence.
- **Rationale**: SC-005; Constitution II for the connection notes.
