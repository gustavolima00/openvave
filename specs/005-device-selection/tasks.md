---

description: "Task list for 005 finding, selecting and connecting to Tank-G pedals"
---

# Tasks: Finding, selecting and connecting to Tank-G pedals

**Input**: Design documents from `specs/005-device-selection/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md),
[data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: MANDATORY (FR-030, SC-003, SC-004, SC-006 are stated as test outcomes). Every test task
precedes the code it covers and must fail first. The default suite stays hardware-free.

**Organization**: one milestone per PR, as in the plan's Delivery Plan. M0 is the pure library
foundation. M1 delivers search and management commands (US1 and the saving half of US2/US4). M2
makes every command use the choice (US2, US3, US4). M3 is the library's long-lived connection
(US6, US5) and depends only on M0. M4 is the owner's hardware check and the release.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1–US6 from spec.md
- Paths are relative to the repository root (single Python package, `src/` layout)

## Global rules for every task

- **No new pedal message.** Nothing in `src/openvave/protocol/` changes. `scan --identify` sends
  only the confirmed `0x11` query. The session-wide audit (`tests/support/audit.py`) keeps passing
  unchanged.
- **No fallback**: with a chosen pedal (option, environment or default) nothing else is ever
  connected to; a chosen pedal that is not seen is `TargetNotFoundError`, exit 3 (FR-019).
- **No prompts**: no command reads stdin for a choice (FR-011).
- **The user's file is never touched by tests**: `tests/conftest.py` points `OPENVAVE_CONFIG` at a
  temporary file and unsets `OPENVAVE_DEVICE` for every test (R13). Library tests pass explicit
  paths.
- **Made-up identifiers only** in fixtures, docs and examples: `AA:BB:CC:DD:EE:01`…,
  `8F3A21C4-0000-4000-8000-000000000001`… (Constitution VI).
- **0.4.0 compatibility** (SC-006): stdout and exit codes of existing commands do not change;
  JSON gets added keys only (`schema_version` stays 2); `TankG.connect()` with no argument and
  `discover()` behave as before and read no configuration (FR-028).
- **No new dependency** (plan, Constitution VII). `src/openvave/devices.py` imports no Bluetooth
  code; `src/openvave/transport/ble.py` stays the only module that scans.
- **Docs with code**: contracts in `specs/005-device-selection/contracts/` are the reference; a
  deliberate deviation is noted under its task and fixed in the contract in the same commit.
  `CHANGELOG.md` [Unreleased] is updated in each milestone. `README.md` is touched only in M4
  (another session is editing it; rebase on `main` first).
- **Hardware**: run by the **pedal owner** in their own terminal (Bluetooth permission, phone app
  closed unless a step says otherwise). Reads only.
- Checks before each commit: `uv run pytest -q`, `uv run ruff check .`,
  `uv run ruff format --check .`, `uv run mypy`.

---

## Delivery Plan

| PR | Milestone | Stories | Tasks | Gate |
|---|---|---|---|---|
| 1 | Milestone 0: Known pedals and the choice rule (library) | US5 (part); basis of US2–US4 | T001–T014 | Suite green; every data-model table row is a test; no CLI behaviour change |
| 2 | Milestone 1: Search and manage 🎯 MVP | US1, US2 (saving), US3 (show), US4 | T015–T033 | Contract tests per command; no Bluetooth where the contract says none; quickstart §2 |
| 3 | Milestone 2: Every command uses the choice | US2, US3, US4 | T034–T047 | All commands × four `chosen_by`: pedal line, JSON fields, stdout identical to 0.4.0; choice matrix (SC-003, SC-004, SC-006); quickstart §3 |
| 4 | Milestone 3: Long-lived connection (library) | US6, US5 | T048–T057 | Lifecycle tests; existing suite untouched and green; quickstart §5 on the fake |
| 5 | Milestone 4: Hardware check and release 0.5.0 | all | T058–T067 | Owner's quickstart §4 passes; SC-001…SC-006 reviewed |

Projected PR count: **5** (≤ 8). Milestone N+1 starts only after Milestone N's gate passes, except
Milestone 3, which may start once Milestone 0's gate has passed.

---

## Milestone 0: Known pedals and the choice rule (library, pure)

**Goal**: the model of known pedals, its file, and the one function that chooses a pedal, usable
and tested without Bluetooth or a CLI.

**Independent test criteria**:
- `KnownDevices` operations give the results of the data-model "Operations" table, and each
  refusal raises `ConfigError` with the listed `reason`.
- A saved file validates against `contracts/devices-file.schema.json`, loads back equal, keeps
  unknown keys, and every "invalid" case of the data model raises `ConfigError(reason="invalid_file")`
  naming the path.
- `default_config_path()` follows R1 for each combination of `OPENVAVE_CONFIG`,
  `XDG_CONFIG_HOME`, platform.
- `resolve_target` returns exactly the data-model table for all seven rows.
- No existing test changes; `openvave --help` output is unchanged.

### Setup

- [X] T001 Confirm the branch is rebased on `origin/main` and that `uv run pytest -q`, `uv run ruff check .`, `uv run ruff format --check .` and `uv run mypy` are green before any change; note the baseline test count under this task
  - 2026-11-19: rebased on `origin/main` (9eaea03, docs only). Baseline: 1767 passed, 6 skipped;
    ruff check and mypy green. `ruff format --check .` (ruff 0.17.5) flags `README.md` and
    `docs/library.md`, Markdown that came from `main` with the docs work; out of scope here (README
    belongs to M4), so the format check is run on `src tests` for this milestone.
- [X] T002 Add an autouse fixture to `tests/conftest.py` that sets `OPENVAVE_CONFIG` to a file under `tmp_path` and removes `OPENVAVE_DEVICE` from the environment for every test (monkeypatch); add `tests/unit/test_conftest_isolation.py` asserting both

### Tests (write first, must fail)

- [X] T003 [P] [US5] `tests/unit/test_nickname_rules.py`: identifier shapes (MAC with `:` or `-`, UUID, case-insensitive) recognised by `is_identifier`; valid nicknames; rejected nicknames (empty, 33 chars, spaces, identifier-shaped, all-hex of length ≥ 4 such as `abcd` and `8F3A`); `beef` rejected, `stage`, `amp-2`, `a1` accepted (R3)
- [X] T004 [P] [US5] `tests/unit/test_known_devices.py`: every row of the data-model "Operations" table (select new, select known, select with nickname, nickname in use → `nickname_in_use`, bad nickname → `bad_nickname`, rename, rename unknown → `unknown_device`, `forget()` keeps devices, `forget(target)` removes and clears the default when it was it, `forget_all`, `find` by nickname and by identifier case-insensitively, `record_seen` on known and unknown); values are immutable (each operation returns a new `KnownDevices`); times come from the injected `now`
- [X] T005 [P] [US5] `tests/unit/test_devices_file.py`: missing file loads empty; save then load is equal; saved JSON validates against `specs/005-device-selection/contracts/devices-file.schema.json`; unknown top-level and per-device keys survive a rewrite; save is atomic (no partial file when the write raises, existing file intact) and creates the directory; mode is `0600` on POSIX; each invalid case (not JSON, `format_version` 2, `default` not in `devices`, duplicate identifier, duplicate nickname differing only in case, wrong field type) raises `ConfigError` with `reason == "invalid_file"` and `path` set
- [X] T006 [P] [US5] `tests/unit/test_config_path.py`: `default_config_path()` for `OPENVAVE_CONFIG` set / empty, `XDG_CONFIG_HOME` set, Windows (`sys.platform` and `APPDATA` monkeypatched), and the `~/.config/openvave/devices.json` fallback (R1)
- [X] T007 [P] [US5] `tests/unit/test_resolve_target.py`: the seven rows of the data-model `resolve_target` table, plus: option beats environment beats default; an identifier unknown to the configuration yields a `Target` with `nickname=None`; an identifier of a known pedal carries its nickname; empty environment string is unset; unknown nickname raises `ConfigError(reason="unknown_nickname")` whose message lists the known nicknames; `known=None` with an identifier works and with a nickname raises
- [X] T008 [P] [US5] `tests/unit/test_errors_005.py`: `ConfigError.exit_code == 2`; `TargetNotFoundError` is a `NoDeviceFoundError` with `exit_code == 3`, `.target` and `.seen`; its message is `<nickname> (<identifier>) not found` or `device <identifier> not found`
- [X] T009 [P] [US5] `tests/contract/test_public_api.py`: add the new exports of `contracts/library-api.md` available in this milestone (`KnownDevice`, `KnownDevices`, `Target`, `resolve_target`, `default_config_path`, `ConfigError`, `TargetNotFoundError`); `DeviceInfo("id", "name")` and `DeviceInfo("id", "name", -50)` still construct, with `nickname is None` and `chosen_by is None`

### Implementation

- [X] T010 [US5] `src/openvave/errors.py`: add `ConfigError` (exit 2; `path`, `reason`) and `TargetNotFoundError(NoDeviceFoundError)` (`target`, `seen`) (T008)
- [X] T011 [US5] `src/openvave/models.py`: add optional `nickname: str | None = None` and `chosen_by: str | None = None` to `DeviceInfo` (last fields); add `ScanEntry` per data-model.md (T009)
- [X] T012 [US5] New `src/openvave/devices.py`: `is_identifier`, `check_nickname`, frozen `KnownDevice`, frozen `KnownDevices` with `load(path=None)`, `save()`, `select`, `rename`, `forget`, `forget_all`, `find`, `record_seen`; `default_config_path()`; atomic write and file validation per R1–R3 (T003–T006)
- [X] T013 [US5] `src/openvave/devices.py`: `Target` and `resolve_target(option, environment, known)` per R5 (T007)
- [X] T014 [US5] `src/openvave/__init__.py`: export the new names and extend the module docstring's API summary; `CHANGELOG.md` [Unreleased]: library additions of this milestone (T009)

### Live verification (milestone gate)

- Suite, linters and type check green; the only changed pre-existing test file is `tests/contract/test_public_api.py`.
- `uv run openvave --help` and `uv run openvave info --help` print the same text as on `main`.

**Gate evidence (2026-11-19)**:
- `uv run pytest -q`: 1901 passed, 6 skipped (baseline 1767 + 134 new). `uv run ruff check .`:
  all checks passed. `uv run ruff format --check src tests`: 138 files formatted. `uv run mypy`:
  no issues in 26 source files.
- Changed pre-existing test files: `tests/contract/test_public_api.py` and `tests/conftest.py`
  (the latter required by T002; the fixture only sets environment variables, no test changed).
- `openvave --help` (32 lines) and `openvave info --help` (12 lines) are byte-identical to
  `origin/main` (compared by running `main`'s `src` with the same interpreter).
- CLI JSON unchanged: `render.device_json` lists its keys explicitly, so the new `DeviceInfo`
  fields do not reach any document until Milestone 2.
- Deviations: `KnownDevices` stores the default as `default_identifier` with a `default` property
  (the data model's `default: KnownDevice | None`); `KnownDevice` and `KnownDevices` carry an
  `extra` mapping for unknown file keys (R2). Identifiers in the file must be non-empty strings;
  their MAC/UUID shape is not enforced on load (an unusual identifier is unreachable by
  `--device` but harmless). `ConfigError(problem, *, reason, path)` keeps the bare text in
  `.problem`; `str()` is `<path>: <problem>`, which is what `contracts/cli.md` prints after
  `error:`. `ScanEntry` exists in `models.py` but is exported in M1 (T031), as planned.

**Checkpoint**: ✅ Milestone 0 DONE — known pedals and the choice rule exist as tested library code; no user-visible CLI change

---

## Milestone 1: Search and manage (US1 P1, US2 saving, US3 show, US4) 🎯 MVP

**Goal**: the owner can see every Tank-G in range, pick one, name it, see what is selected, switch,
rename and forget. Other commands do not use the selection yet (Milestone 2).

**Independent test criteria**:
- `openvave scan` against a fake scanner with two pedals lists both, strongest first, marks the
  default with `*` and its nickname, connects to nothing, exits 0; none → the "No Tank-G found"
  text and hint, exit 3; `--all` adds other advertisers flagged `(not a Tank-G)`; `--json`
  validates against `contracts/scan.schema.json` (also with an empty list, exit 3).
- `scan --identify` adds `fw 96` per Tank-G through the fake transport and `fw ? (<reason>)` when
  one fails, sending only the `0x11` query.
- `select` accepts a known nickname (no scan), a full identifier (scan), a unique prefix, or
  nothing (the only pedal); refuses with exit 3 / 4 / 2 as in `contracts/cli.md`, saving nothing.
- `device`, `device rename`, `forget` and `select --offline` work with a scanner factory that
  raises if used (no Bluetooth).
- Quickstart §2 passes as written.

### Tests (write first, must fail)

- [X] T015 [P] [US1] `tests/unit/test_scan.py`: add cases for `scan()` rows: ordering (Tank-G first, RSSI descending, unknown RSSI last, ties by identifier), `include_all` adds non-Tank advertisers with `tank_g=False`, `known` annotates `nickname` / `known` / `selected`, the whole timeout is used even after a pedal is seen (FR-003), `discover()` unchanged
- [X] T016 [P] [US1] `tests/integration/test_identify.py`: `identify(entries)` connects to each Tank-G entry in order through an injected transport factory, sends exactly one `0x11` query per pedal (assert the frames), fills `firmware`; a failing connection or handshake sets `identify_error` and the next pedal is still tried; non-Tank entries are skipped
- [X] T017 [P] [US1] `tests/contract/test_cli_scan.py`: human output for two pedals / one default / none / default not seen / `--all` / `--identify` exactly as in `contracts/cli.md`; `Scanning for 5 s…` on stderr only; `--json` against `scan.schema.json`; exit codes 0, 3, 5 (scanner raising `BluetoothUnavailableError`); the transport factory is never called without `--identify`
- [X] T018 [P] [US2] `tests/contract/test_cli_select_device.py`: `select` with a full identifier in range, with `--name`, with a prefix matching one / two (exit 4, list) / none (exit 3), with no argument and one / two / zero pedals, with a known nickname and a scanner that raises if used, with `--offline` (full identifier only; prefix + `--offline` → exit 2); `Was:` line when a default is replaced; previous default stays known; bad nickname and nickname in use → exit 2 and the file is byte-identical; `--json` against `device.schema.json` with `"command": "select"`
- [X] T019 [P] [US3] `tests/contract/test_cli_device.py`: `device` with no file, with no default, with a default and two known pedals (text of `contracts/cli.md`, including the "choice, not an open connection" line and the configuration path), with `OPENVAVE_DEVICE` set (override line); `--check` in range → exit 0 and `In range: yes (-58 dBm)`, not in range → exit 3, no default → exit 2; without `--check` the scanner is never used; `--json` against `device.schema.json`
- [X] T020 [P] [US4] `tests/contract/test_cli_rename_forget.py`: `device rename OLD NEW` by nickname and by identifier, unknown OLD / bad NEW / NEW in use → exit 2; `forget` clears the default and keeps the devices, with no default prints `No default pedal.` exit 0; `forget TARGET` removes it (and the default when it was it), unknown → exit 2; `forget --all` empties; on an invalid file `forget` exits 2 with the hint and `forget --all` moves it to `devices.json.invalid-<timestamp>` and leaves a valid empty file; `--json` against `device.schema.json`; none of them uses the scanner
- [X] T021 [P] [US4] `tests/contract/test_cli_invalid_config.py`: with an invalid file, `scan` still lists pedals and prints the `warning: <path>: <problem> (nicknames unavailable)` line, `device` and `select` exit 2 with `error: <path>: <problem>` and the `forget --all` hint

### Implementation

- [X] T022 [US1] `src/openvave/transport/ble.py`: add `scan(timeout=5.0, *, include_all=False, known=None, scanner_factory=None) -> list[ScanEntry]` on top of `_scan`, with the ordering rule; keep `discover()` as is (T015)
- [X] T023 [US1] `src/openvave/transport/ble.py`: add `identify(entries, *, timeout=2.0, transport_factory=None) -> list[ScanEntry]` using `TankG.over(BleakTransport(...))` for the handshake only (T016)
- [X] T024 [US1] `src/openvave/cli/__init__.py`: make the scanner injectable in `main()` next to `transport_factory` (parameter `scanner_factory`), and add the `scan` subcommand with `--all` and `--identify` (T017)
- [X] T025 [P] [US1] `src/openvave/cli/render.py`: `human_scan` and `scan_json` per `contracts/cli.md` and `scan.schema.json` (T017)
- [X] T026 [US2] `src/openvave/cli/__init__.py`: `select [TARGET] [--name NICKNAME] [--offline]` implementing R4 (nickname → identifier → prefix → none), saving only on success (T018)
- [X] T027 [US3] `src/openvave/cli/__init__.py`: `device [--check]` with an optional `rename OLD NEW` action (T019, T020)
- [X] T028 [US4] `src/openvave/cli/__init__.py`: `forget [TARGET | --all]`, including the move-aside of an invalid file (T020)
- [X] T029 [P] [US3] `src/openvave/cli/render.py`: `human_device`, `human_select`, `human_forget`, `human_rename`, `device_document` (shared JSON of `device.schema.json`) (T018–T020)
- [X] T030 [US4] `src/openvave/cli/__init__.py`: `_report` handling of `ConfigError` (`error: <path>: <problem>`, hint `openvave forget --all` for `invalid_file`, known nicknames for `unknown_nickname`) and the warning path used by `scan` (T021)
- [X] T031 [US1] `src/openvave/__init__.py`: export `scan`, `identify`, `ScanEntry`; extend `tests/contract/test_public_api.py`
- [X] T032 [US1] `CHANGELOG.md` [Unreleased]: the five commands, `OPENVAVE_CONFIG`, the file location; top-level `--help` description in `src/openvave/cli/__init__.py` mentions `scan` and `select`

### Live verification (milestone gate)

- [X] T033 [US1] Run quickstart §2 in a shell with a temporary `OPENVAVE_CONFIG` and paste the outputs under this task; confirm each matches `contracts/cli.md`

**Gate evidence (2026-11-19)**:
- `uv run pytest -q`: 1984 passed, 6 skipped (M0 gate 1901 + 83 new; the only changed pre-existing
  test files are `tests/unit/test_scan.py`, extended as T015 says, and
  `tests/contract/test_public_api.py`). `uv run ruff check .`: all checks passed.
  `uv run ruff format --check src tests`: formatted. `uv run mypy`: no issues in 27 source files.
- Contract tests per command: `tests/contract/test_cli_scan.py`, `test_cli_select_device.py`,
  `test_cli_device.py`, `test_cli_rename_forget.py`, `test_cli_invalid_config.py`. Every command
  that must not use Bluetooth runs with `forbidden_scanner` (`tests/support/scanner.py`), which
  fails the test if a scanner is built.
- T033, quickstart §2 in a shell with `OPENVAVE_CONFIG="$(mktemp -d)/devices.json"`:

  ```text
  $ openvave device
  No default pedal. Commands use the only Tank-G in range.
  Choose one: openvave scan, then openvave select ID
  Configuration: /var/folders/…/tmp.wzcILF5SO2/devices.json
  (exit 0)
  $ openvave select AA:BB:CC:DD:EE:01 --name stage --offline
  Default pedal: stage  AA:BB:CC:DD:EE:01
  Saved in /var/folders/…/tmp.wzcILF5SO2/devices.json
  $ openvave select AA:BB:CC:DD:EE:02 --name home --offline
  Default pedal: home  AA:BB:CC:DD:EE:02
  Was: stage  AA:BB:CC:DD:EE:01
  Saved in /var/folders/…/tmp.wzcILF5SO2/devices.json
  $ openvave device
  Default pedal: home  AA:BB:CC:DD:EE:02
    selected 2026-11-19 11:05
  Known pedals:
    stage  AA:BB:CC:DD:EE:01
  * home   AA:BB:CC:DD:EE:02
  Configuration: /var/folders/…/tmp.wzcILF5SO2/devices.json
  openvave connects for the length of one command; this is a choice, not an open connection.
  $ openvave select stage && openvave device rename home rehearsal && openvave forget
  Default pedal: stage  AA:BB:CC:DD:EE:01
  Was: home  AA:BB:CC:DD:EE:02
  Saved in /var/folders/…/devices.json
  Renamed home → rehearsal  AA:BB:CC:DD:EE:02
  Forgot the default (stage AA:BB:CC:DD:EE:01). It is still a known pedal; remove it with: openvave forget stage
  $ openvave device --json
  → "default": null, nicknames ["stage", "rehearsal"]; validates against contracts/device.schema.json
  $ openvave select nobody
  error: 'nobody' is not a known nickname, an identifier or a prefix of at least 4 hex digits; known nicknames: stage, rehearsal
  (exit 2)
  ```

  Each matches `contracts/cli.md`. The last step of §2, `openvave info --device nobody` → exit 2,
  is Milestone 2 behaviour (`info` resolves nicknames from T042/T045); it was not run, because in
  M1 it would start a real Bluetooth scan for the text `nobody`.
- Early hardware smoke check (2026-11-19, owner's pedal on, fw 96, phone app closed, macOS,
  temporary `OPENVAVE_CONFIG`, reads only; identifier redacted as `<UUID>`), run in the owner's
  terminal after the push. All exit 0:
  - `scan`: one row `<UUID>  TANK-Gv2_BLE  -57 dBm`, `1 pedal found. Select one: …`.
  - `scan --identify`: the same row with `fw 96` (handshake only).
  - `scan --json`: one device, `tank_g: true`, `known: false`, `default_seen: null`.
  - `select --name stage` (no TARGET, the only pedal): `Default pedal: stage  <UUID>
    (TANK-Gv2_BLE, -56 dBm)`, saved.
  - `device`: default `stage`, `selected …`, one known pedal, the choice line.
  - `device --check`: `In range: yes (-56 dBm)`.
  - `scan` again: `* stage  <UUID>  TANK-Gv2_BLE  -57 dBm`, `* = default.`
  - `info`: unchanged 0.4.0 output (firmware 96, normal, preset 1B); it does not use the default
    yet (M2).
  - `forget --all`: `Forgot 1 known pedal.`
  Timings were not captured (the script's timer did not work). The full quickstart §4 (phone app
  connected, two processes, timings for SC-002 / SC-005) stays with M4 (T058–T061).
- Deviations (contract updated where it changes what users see):
  - The four commands live in a new module, `src/openvave/cli/pedals.py` (T024, T026–T028);
    `cli/__init__.py` registers their parsers, takes `scanner_factory` in `main()` and dispatches
    them through `_run_pedal_command`, which returns their exit code with their output (needed for
    `scan` / `device --check` printing a result with exit 3).
  - Renderers are `human_select_device` (`human_select` already renders `preset select`),
    `human_forget_default` / `human_forget_one` / `human_forget_all`, plus `short_identifier`
    and `known_json`.
  - `identify(..., transport_factory)` takes an async `DeviceInfo -> Transport`; the CLI adapts
    its injected factory to it. With BLE it builds `BleakTransport(identifier)`, so bleak looks
    the address up again before connecting (a pedal that is advertising is found at once).
  - `transport/ble.py` also gains `strongest_first` (the row order) and `seek` (a scan that stops
    when an identifier is seen, used by `select ID` and `device --check`); neither is exported.
  - `scan`: the "not seen" line prints the full identifier; `No Tank-G found.` goes to stdout and
    its hint to stderr; `Scanning for N s…` only in human mode. `device` without a default still
    lists known pedals and the configuration path. `forget --all --json` adds `moved_to`.
  - `select TEXT` where TEXT is no nickname, identifier or ≥ 4-hex-digit prefix exits 2 with
    `ConfigError(reason="unknown_nickname")` listing the known nicknames, before any scan.

**Checkpoint**: ✅ Milestone 1 DONE — pedals can be searched, selected, shown, renamed and forgotten

---

## Milestone 2: Every command uses the choice (US2 P1, US3 P2, US4 P2)

**Goal**: all pedal commands pick their pedal by the one rule, never fall back, say which pedal
they used, and keep their 0.4.0 output.

**Independent test criteria**:
- For every pedal command and each of the four `chosen_by` values: the `pedal:` line is on stderr
  (absent with `--json`), JSON `device` has `nickname` and `chosen_by`, and stdout equals the
  0.4.0 output for the same fake.
- With a target, the scan stops at first sight and the grace period is not waited for.
- A target that is not seen exits 3 with the `seen:` list and both hints, for reads and writes,
  and no transport is opened.
- The choice matrix (option × environment × configuration × scan result) never connects to an
  identifier other than the expected one.
- `--device NICKNAME` and `OPENVAVE_DEVICE` work and leave the file byte-identical.

### Tests (write first, must fail)

- [ ] T034 [P] [US2] `tests/unit/test_scan.py`: `open_ble(target, scan_timeout)` with a `Target`: stops at first sight; target absent and other Tank-G pedals seen → `TargetNotFoundError` with `.seen` strongest first and Tank-G only; target absent and nothing seen → `TargetNotFoundError` with empty `.seen`; `target=None` keeps the 0.4.0 rules (one → chosen with `chosen_by="only_one_found"`, none → `NoDeviceFoundError`, several → `MultipleDevicesError`); the returned `DeviceInfo` carries `nickname` and `chosen_by`; passing a plain identifier string still works (`chosen_by="device_option"`)
- [ ] T035 [P] [US2] `tests/integration/test_choice_matrix.py`: parametrised over option (absent / identifier / known nickname / unknown nickname), environment (absent / identifier / nickname), configuration (none / default A / default A with B known / invalid file) and scan result (A only / B only / A and B / none); asserts the connected identifier or the error class and exit code from the data-model tables; asserts the transport of any other identifier is never opened (SC-004); runs once with `info` and once with `set gain=90` on a fake pedal
- [ ] T036 [P] [US3] `tests/contract/test_cli_pedal_line.py`: parametrised over **every** pedal command in `COMMANDS` (`info`, `preset dump`, `preset backup`, `preset select`, `preset reload`, `preset save --dry-run`, `preset restore --dry-run`, `set`, `set FIELD=VALUE`, `bypass on/off`, `loopback on/off`, `watch --duration`) × four `chosen_by`: stderr has exactly one `pedal:` line in the `contracts/cli.md` format (nickname first when known, UUID shortened to 8 characters + `…`, MAC in full, the right reason), none with `--json`; the test fails if a command exists in `COMMANDS` that it does not cover (SC-003)
- [ ] T037 [P] [US3] `tests/contract/test_cli_stdout_unchanged.py`: for the same commands, stdout with a default selected equals stdout with no configuration (golden comparison within the test, human mode), and exit codes are equal (SC-006); JSON documents differ only by `device.nickname` and `device.chosen_by`
- [ ] T038 [P] [US3] `tests/contract/test_cli_info_identity.py` and the JSON contract tests that validate a `device` object: assert `nickname` and `chosen_by` are present; the 001 `info.schema.json` `device` definition still validates (added keys)
- [ ] T039 [P] [US2] `tests/contract/test_cli_target_errors.py`: exit 3 text for a default not seen with and without other pedals, and for an identifier unknown to the configuration; exit 4 text with both hints and nicknames of known pedals at the end of their rows; exit 2 for `--device nobody` before any scan (scanner raises if used); invalid file → exit 2 for `info`, but `info --device <identifier>` runs with the warning; a non-Tank advertised name with `--device ID` adds `name: <name> (not a Tank-G name)` to the pedal line
- [ ] T040 [P] [US4] `tests/contract/test_cli_last_seen.py`: after a successful command on a known pedal the file's `last_name`, `last_firmware`, `last_seen_at` are updated; on an unknown pedal the file is untouched (not created); with `--device` / `OPENVAVE_DEVICE` the `default` is unchanged; a read-only configuration directory does not fail the command (FR-023, FR-026)

### Implementation

- [ ] T041 [US2] `src/openvave/transport/ble.py`: `open_ble(target: Target | str | None, scan_timeout)` per T034: stop at first sight for a target, build `TargetNotFoundError` from the scan's Tank-G rows, annotate the returned `DeviceInfo` (`nickname`, `chosen_by`); `select_device` keeps its 0.4.0 signature and behaviour for a plain identifier
- [ ] T042 [US2] `src/openvave/cli/__init__.py`: one session helper (async context manager, e.g. `_pedal(args, factory)`) that loads the configuration only when needed (R5), calls `resolve_target(args.device, os.environ.get("OPENVAVE_DEVICE"), known)`, obtains the transport from the factory, prints the pedal line, opens `TankG`, and records last-seen after the handshake (best effort); change `TransportFactory` to take `Target | str | None`
- [ ] T043 [US2] `src/openvave/cli/__init__.py` and `src/openvave/cli/watch.py`: replace every per-command `source()` closure and direct `factory(args.device, …)` call with the helper of T042, so no command can bypass the choice (T035, T036)
- [ ] T044 [P] [US3] `src/openvave/cli/render.py`: `pedal_line(device)` and `device_json` with `nickname` and `chosen_by` (T036, T038)
- [ ] T045 [US2] `src/openvave/cli/__init__.py` `_report`: `TargetNotFoundError` text with `seen:` rows and the two hints; `MultipleDevicesError` text with both hints and nicknames; `--device` help text ("identifier or nickname"); keep the existing exit-3 hint for the no-target case (T039)
- [ ] T046 [US3] `specs/001-readonly-ble-connection/contracts/info.schema.json` and the other schemas that define `device`: add the optional `nickname` and `chosen_by` properties (no change to `required`); `CHANGELOG.md` [Unreleased]: choice order, `OPENVAVE_DEVICE`, the pedal line, the JSON keys, "no fallback" behaviour

### Live verification (milestone gate)

- [ ] T047 [US2] Run quickstart §3 (Bluetooth on, no pedal needed) and paste the output and exit code under this task; run `uv run pytest tests/contract/test_cli_pedal_line.py tests/integration/test_choice_matrix.py -q` and note the number of cases

**Checkpoint**: Milestone 2 DONE — every command acts on the chosen pedal, says so, and never falls back

---

## Milestone 3: Long-lived connection in the library (US6 P3, US5 P3)

**Goal**: code built on openvave can open a connection, keep it for many operations, ask whether
it is alive and to which pedal, and close it. May start after Milestone 0.

**Independent test criteria**:
- `await pedal.open()` then N operations use one transport `open` and one handshake; `close()`
  releases the transport; closing twice is harmless.
- After a lost link, `is_connected` is false and every operation raises `ConnectionLostError`
  without writing a frame; nothing reconnects; `close()` then `open()` works again.
- `open()` on an open or lost session raises `RuntimeError`.
- `TankG.connect(KnownDevice | Target)` and `TankG.connect_selected()` reach the right pedal and
  set `pedal.device.nickname` / `chosen_by`; `connect_selected()` with no default raises
  `ConfigError`.
- Every existing `async with` test passes unmodified.

### Tests (write first, must fail)

- [ ] T048 [P] [US6] `tests/unit/test_fake_transport.py`: `FakeTransport.lose_link()` calls the registered `on_disconnect` callback, makes later `write` raise `ConnectionLostError`, and is a no-op when closed
- [ ] T049 [P] [US6] `tests/integration/test_session_lifecycle.py`: `open()` / `close()` without `async with` (one transport open, one handshake, N reads and one write on a fake); `is_connected` across closed → open → closed; `close()` twice; `open()` twice → `RuntimeError`; `lose_link()` between operations → next operation raises `ConnectionLostError` and the fake records no new frame; `lose_link()` during a pending request → that request raises as today and later ones fail fast; lost → `open()` raises `RuntimeError`; lost → `close()` → `open()` succeeds with a new source call; `identity` available after `open()`; `async with` still closes on exit and on exception
- [ ] T050 [P] [US5] `tests/integration/test_connect_forms.py`: with an injected scan (`monkeypatch` of `open_ble`), `TankG.connect()` passes `None` and reads no configuration (a `KnownDevices.load` patched to raise proves it); `TankG.connect("ID")`, `TankG.connect(known_device)`, `TankG.connect(target)` pass the expected target; `TankG.connect_selected(config_path=p)` uses the default of that file with `chosen_by="selected"` and raises `ConfigError` when there is none
- [ ] T051 [P] [US5] `tests/integration/test_library_usage.py`: add the three examples of `contracts/library-api.md` ("Known pedals", "Choosing and connecting", "Long-lived connection") as runnable tests against the fake

### Implementation

- [ ] T052 [US6] `src/openvave/transport/fake.py`: `lose_link()` (T048)
- [ ] T053 [US6] `src/openvave/session.py`: public `open()` and `close()` (moved from `__aenter__` / `_close`, which now call them), state tracking (closed / open / lost), `is_connected`, fail-fast check at the start of `_request`, `RuntimeError` on `open()` when not closed (T049)
- [ ] T054 [US5] `src/openvave/session.py`: `connect(device: str | KnownDevice | Target | None = None, …)` and `connect_selected(*, config_path=None, scan_timeout=…, timeout=…)`; the session's `device` carries `nickname` and `chosen_by` (T050)
- [ ] T055 [P] [US6] `src/openvave/session.py` and `src/openvave/__init__.py` docstrings: lifecycle, the single-connection note ("while open, the phone app and scans do not see the pedal"), no reconnect; `CHANGELOG.md` [Unreleased]: library lifecycle additions (T051)
- [ ] T056 [US6] `tests/contract/test_public_api.py`: `TankG.open`, `close`, `is_connected`, `connect_selected` are public and documented in `contracts/library-api.md`

### Live verification (milestone gate)

- [ ] T057 [US6] Run the quickstart §5 script against `FakeTransport` (replace `connect_selected()` by `TankG.over(fake)`), once to completion and once calling `fake.lose_link()` mid-loop; paste both outputs under this task

**Checkpoint**: Milestone 3 DONE — the library supports a long-lived connection with an explicit lifecycle

---

## Milestone 4: Hardware check and release 0.5.0 (all stories)

**Goal**: the owner confirms the behaviour on the real pedal, the observations are documented, and
0.5.0 is released.

**Independent test criteria**:
- Quickstart §4 passes on the owner's pedal (fw 96), reads only.
- README, contracts, CHANGELOG and version agree; `tests/contract/test_changelog_050.py` passes.
- SC-001…SC-006 each have a recorded result.

### Hardware (owner)

- [ ] T058 [US1] Owner runs quickstart §4 `scan`, `scan --identify`, `select --name stage`, `info`, `device --check`, the `--json` check; researcher pastes outputs and times under this task (SC-002: time of `info` with a default vs the 0.4.0 figure of 2.5 s; SC-005: the pedal is listed within 5 s)
- [ ] T059 [US1] Owner runs the phone-app-connected steps and the two-commands-at-once step of quickstart §4; researcher records exit codes and texts (expected: exit 3 with the "stops advertising" hint)
- [ ] T060 [US4] Owner runs `forget` then `info` (expects `(only one found)`); optional: the Bluetooth off/on observation; if a second Tank-G is available, the two-pedal steps
- [ ] T061 [US6] Owner runs the quickstart §5 script on the pedal, once to completion and once switching the pedal off mid-loop; researcher records the output
- [ ] T062 Any behaviour that differs from the contracts becomes a failing test first, then a fix, in this PR

### Documentation and release

- [ ] T063 [P] `specs/protocol/command-layer.md` (connection notes) and `specs/protocol/ble-gatt.md`: record what T058–T061 observed with date, firmware and confidence (a second openvave process does not see a connected pedal; the identifier is per computer on macOS; the Bluetooth off/on result if run)
- [ ] T064 `README.md` (after rebasing on `main`): new "Finding and choosing a pedal" section (scan, select, device, rename, forget, choice order, `OPENVAVE_DEVICE`, `OPENVAVE_CONFIG`, identifiers are per computer on macOS, "openvave holds the pedal only while a command runs; there is nothing to disconnect"); Options and Exit codes updated; Library section shows `connect_selected()` and the `open()` / `close()` lifecycle; links to the 0.5.0 contracts and schemas; "Before you connect" mentions that a connected pedal is invisible to `scan`
- [ ] T065 [P] `CHANGELOG.md`: move [Unreleased] to `[0.5.0]` with a summary paragraph; `tests/contract/test_changelog_050.py` in the style of `test_changelog_040.py` (commands, variables, library names, "no fallback", schema_version unchanged)
- [ ] T066 `pyproject.toml` version `0.5.0` (and the package description if it still says read-only); `src/openvave/__init__.py` docstring; `uv run openvave --version`
- [ ] T067 Review SC-001…SC-006 and record each result under this task; run the full quickstart once more end to end

**Checkpoint**: Milestone 4 DONE — 0.5.0 released

---

## Dependencies & Execution Order

- **Milestone 0** blocks everything.
- **Milestone 1** needs M0. **Milestone 2** needs M1 (uses `scan` rows and the `_report` paths).
- **Milestone 3** needs M0 only; `connect(Target)` (T054) uses `open_ble(target)` from T041 when M2
  is merged, otherwise T054 includes that change (note it in the PR).
- **Milestone 4** needs M1, M2 and M3.

Within a milestone: tests before the code they cover; `errors.py` / `models.py` before
`devices.py`; `transport/ble.py` before the CLI; renderers alongside their command.

### Parallel opportunities

- M0: T003–T009 together (seven test files); then T010 and T011 in parallel, T012, T013, T014.
- M1: T015–T021 together; T025 and T029 (renderers) alongside T024, T026–T028 (same CLI file:
  sequential among themselves).
- M2: T034–T040 together; T044 alongside T041; T042 → T043 → T045 sequential (one file).
- M3: T048–T051 together; T052 alongside T053.
- M3 as a whole alongside M1–M2 (different files except `src/openvave/__init__.py`,
  `tests/contract/test_public_api.py` and `CHANGELOG.md`: rebase before merge).

### Parallel example: Milestone 0 tests

```text
Task: "tests/unit/test_nickname_rules.py (T003)"
Task: "tests/unit/test_known_devices.py (T004)"
Task: "tests/unit/test_devices_file.py (T005)"
Task: "tests/unit/test_config_path.py (T006)"
Task: "tests/unit/test_resolve_target.py (T007)"
Task: "tests/unit/test_errors_005.py (T008)"
```

## Implementation Strategy

- **MVP**: Milestones 0 + 1 give the owner search, select, show, switch and forget. It is not
  worth releasing alone (the selection is not used by other commands until Milestone 2), so the
  first release is after Milestone 4; Milestones 0–2 are the minimum shippable set if Milestone 3
  slips.
- **Order**: M0 → M1 → M2, with M3 in parallel after M0, then M4.
- Stop at each checkpoint, run the gate, and record its result in this file before the next PR.

## Notes

- Story coverage: US1 → M1 (T015–T017, T022–T025); US2 → M1 (T018, T026) and M2; US3 → M1 (T019,
  T027, T029) and M2 (T036–T038, T044); US4 → M1 (T020, T021, T028, T030) and M2 (T040); US5 → M0
  and M3 (T050, T051, T054); US6 → M3.
- Deviations found while implementing are written under their task, as in spec 004's tasks file.
