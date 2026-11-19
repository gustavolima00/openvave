# Implementation Plan: Finding, selecting and connecting to Tank-G pedals

**Branch**: `claude/spec-005-device-selection-170117` | **Date**: 2026-11-19 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/005-device-selection/spec.md`

## Summary

Four additions to the 0.4.0 client, none of which sends a new pedal message. (1) **Known pedals**:
a per-user JSON file holding the pedals the owner selected, their nicknames and which one is the
default, behind a small pure model (`KnownDevices`). (2) **Search and manage**: `openvave scan`
(full scan, no connection, optional `--identify`), `select`, `device`, `device rename`, `forget`.
(3) **One choice rule for every command**: `--device` → `OPENVAVE_DEVICE` → default → the only
pedal in range, as one pure function; a chosen pedal that is not seen is exit 3 with what was
seen, never a fallback; every command prints a `pedal:` line on stderr and adds `nickname` and
`chosen_by` to its JSON `device`. (4) **Long-lived connection in the library**: explicit
`open()` / `close()`, `is_connected`, a lost-link state that fails fast and never reconnects. The
CLI keeps one connection per command. Decisions: [research.md](research.md).

## Technical Context

**Language/Version**: Python ≥ 3.11 (unchanged)

**Primary Dependencies**: `bleak` ≥ 0.22 (runtime, unchanged). No new runtime or dev dependency
(the configuration path is computed by hand, research R1)

**Storage**: one per-user file, `devices.json` (`format_version` 1), at `$OPENVAVE_CONFIG`, else
`$XDG_CONFIG_HOME/openvave/`, else `%APPDATA%\openvave\` on Windows, else `~/.config/openvave/`;
atomic writes, mode `0600`. Never committed; tests always use a temporary path (R13)

**Testing**: `pytest` (+ `pytest-asyncio`, `jsonschema`), hardware-free. Pure tests for
`KnownDevices` and `resolve_target` (table from data-model.md); scan and choice tests with the
existing `scanner_factory` fake; CLI contract tests through `main(argv, transport_factory=…)` with
`OPENVAVE_CONFIG` pointed at a temporary file by an autouse fixture; lifecycle tests with
`FakeTransport` (+ a `lose_link()` hook). Hardware checks are reads only (quickstart §4)

**Target Platform**: macOS (hardware-verified); Linux/Windows best-effort (unchanged). Identifier
shapes of both families are handled (MAC, CoreBluetooth UUID)

**Project Type**: library + CLI (single Python package)

**Performance Goals**: `scan` ends at `--scan-timeout` (default 5 s); a command with a chosen
pedal in range ends its scan at first sight (no 1 s grace: SC-002); `--identify` adds about
1–2 s per pedal; configuration commands without `--check` use no Bluetooth and return at once

**Constraints**: no new pedal message; `--identify` sends only the confirmed `0x11` query; no
interactive prompt; no fallback to another pedal when a chosen one is absent; the library reads
the configuration only when asked (FR-028); stdout and exit codes of 0.4.0 commands unchanged
(SC-006); `schema_version` stays 2

**Scale/Scope**: 5 new CLI commands (`scan`, `select`, `device`, `device rename`, `forget`), 1
changed global option (`--device` takes nicknames), 2 environment variables, 1 stderr line on every
pedal command, 3 new JSON schemas, about 10 new public library names; a handful of known
pedals per user

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Pre-research evaluation (2026-11-19):

- [x] **I. Protocol docs**: no new message. The connection notes in `command-layer.md` /
  `ble-gatt.md` gain what this feature relies on or observes (identifier per computer, the pedal
  not advertising while connected as seen from a second openvave process), in the same PR as the
  hardware check (M4).
- [x] **II. Evidence**: new notes carry a confidence level and the date/firmware of the owner's
  run; platform behaviour not observed on the pedal (macOS identifier change) is stated as such.
- [x] **III. Capture-driven tests**: no codec changes. All selection rules are pure and
  table-tested first; the suite stays hardware-free and never loads a BLE backend.
- [x] **IV. Device safety**: no write is added. The feature narrows where writes can go: with a
  chosen pedal nothing else is connected to, an absent chosen pedal is a refusal, an invalid
  configuration stops the command, and every command names its pedal. `--identify` is opt-in and
  sends only the confirmed handshake.
- [x] **V. Library-first/CLI**: `KnownDevices`, `resolve_target`, `scan` and the session lifecycle
  are library code with no CLI imports; the CLI adds argument parsing, the stderr line and
  rendering; human and JSON output for every new command. MINOR bump, no breaking change.
- [x] **VI. Clean-room**: fixtures and docs use made-up identifiers; the user's file stays on
  their machine and is never read by tests.
- [x] **VII. Simplicity**: no new dependency; the transport interface is unchanged (scan and
  target handling stay in `transport/ble.py` and a new pure module); the long-lived connection is
  the existing session with an explicit lifecycle.

Result: **PASS**.

Post-design re-evaluation (after Phase 1, 2026-11-19): **PASS**. The design adds two error
classes on existing exit codes, two optional `DeviceInfo` fields and three schemas; nothing in
`protocol/` changes. One spec detail was amended during planning: `select` takes a unique
identifier prefix instead of a row number (R4), because row order can change between scans.

## Delivery Plan

Projected PR count: **5** (≤ 8, no re-scoping needed). M0–M3 are hardware-free. M3 depends only on
M0 and can be built in parallel with M1–M2. No milestone sends a write.

| # | Milestone | Scope | Stories | Verification gate |
|---|---|---|---|---|
| M0 | Known pedals and the choice rule (library, pure) | `devices.py`: `KnownDevice`, `KnownDevices` (load/save/select/rename/forget/find/record_seen), `default_config_path`, nickname and identifier shape rules, `Target`, `resolve_target`; `errors.py`: `ConfigError`, `TargetNotFoundError`; `DeviceInfo.nickname` / `.chosen_by`; `devices-file.schema.json`; public exports | US5 (part), basis of US2–US4 | Suite green: every row of the data-model tables (operations, invalid files, `resolve_target`) as a test; saved files validate against the schema; atomic save and `0600` checked; `test_public_api` updated. No CLI behaviour changes |
| M1 | Search and manage (CLI) | `transport/ble.py`: `scan()` rows with `include_all`, ordering; `identify()`; CLI `scan [--all] [--identify]`, `select [TARGET] [--name] [--offline]` (nickname / identifier / prefix / none), `device [--check]`, `device rename`, `forget [TARGET \| --all]`; renderers and `scan.schema.json`, `device.schema.json`; autouse test fixture for `OPENVAVE_CONFIG` | US1, US2 (saving), US4 (switch, rename, forget), US3 (show) | Contract tests per command: human text, JSON against schema, exit codes 0/2/3/4/5, nothing saved on refusal, no Bluetooth for `device` / `forget` / `rename` / `select NICKNAME` / `--offline`; `scan` connects to nothing (fake asserts no `open`) unless `--identify`. Quickstart §2 passes |
| M2 | Every command uses the choice | One CLI session helper replacing the per-command `source()` closures: resolves the target, runs the scan (stop at first sight with a target; 0.4.0 rules without), raises `TargetNotFoundError` with what was seen, prints the `pedal:` line, records last-seen after the handshake; `--device NICKNAME`, `OPENVAVE_DEVICE`; `_report` texts for exit 3 / 4 with both hints; `device_json` adds `nickname`, `chosen_by` (001 `device` definition documented as extended) | US2 (use), US3, US4 (override) | Parametrised contract test over **all** pedal commands × the four `chosen_by` values: stderr line present, JSON fields present, stdout identical to 0.4.0 golden output (SC-003, SC-006). Choice matrix test (option × environment × configuration × scan result) asserts the connected identifier and that writes never reach another pedal (SC-004). Invalid configuration: exit 2, or warning with an explicit identifier. Quickstart §3 |
| M3 | Long-lived connection (library) | `TankG.open()` / `close()` public, `is_connected`, lost state (fail fast, no reconnect), reopen after close, `RuntimeError` on double open; `TankG.connect` accepts `KnownDevice` / `Target`; `TankG.connect_selected()`; `FakeTransport.lose_link()`; library contract examples as tests | US6, US5 | Lifecycle tests: one `open` and one handshake for N operations; lost link between and during operations; close idempotent; reopen rescans; `async with` behaviour unchanged (existing suite untouched and green). Quickstart §5 against the fake |
| M4 | Hardware check and release 0.5.0 | Owner runs quickstart §4 (reads only); observations into `command-layer.md` / `ble-gatt.md` with confidence; README (search, select, show, switch, forget, choice order, per-computer identifiers, "nothing to disconnect", long-lived connection in the library), CLI/library contract links, CHANGELOG, version 0.5.0, `test_changelog_050` | all | Quickstart passes end to end on the owner's pedal; SC-001…SC-006 reviewed; README merged without conflict with the parallel docs work (rebase on `main` first) |

## Project Structure

### Documentation (this feature)

```text
specs/005-device-selection/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   ├── cli.md                      # choice order, pedal line, scan, select, device, forget
│   ├── library-api.md              # scan, KnownDevices, resolve_target, connect forms, lifecycle
│   ├── devices-file.schema.json    # the per-user configuration file
│   ├── scan.schema.json            # `scan --json`
│   └── device.schema.json          # `device` / `select` / `forget` / `device rename --json`
├── checklists/requirements.md
└── tasks.md             # Phase 2 output (/speckit-tasks — not created here)
```

### Source Code (repository root)

```text
specs/protocol/command-layer.md     # connection notes: observations from quickstart §4 (M4)
specs/protocol/ble-gatt.md          # identifier per computer (M4)

src/openvave/
├── devices.py           # NEW (pure + file I/O): KnownDevice, KnownDevices, default_config_path,
│                        #   Target, resolve_target, identifier/nickname shape rules
├── models.py            # DeviceInfo + nickname, chosen_by; + ScanEntry
├── errors.py            # + ConfigError (exit 2), TargetNotFoundError (exit 3)
├── session.py           # open()/close()/is_connected, lost state; connect(KnownDevice | Target),
│                        #   connect_selected()
├── transport/
│   ├── ble.py           # scan() rows (+ include_all), identify(), open_ble(target) raising
│   │                    #   TargetNotFoundError with the Tank-G pedals seen
│   └── fake.py          # + lose_link()
├── __init__.py          # + new exports
└── cli/
    ├── __init__.py      # + scan, select, device, device rename, forget; session helper used by
    │                    #   every pedal command (choice, pedal line, last seen); --device NICKNAME
    └── render.py        # scan table, device/select/forget texts and JSON, pedal line,
                         #   device_json + nickname, chosen_by

tests/
├── conftest.py          # autouse: OPENVAVE_CONFIG → tmp file, OPENVAVE_DEVICE unset
├── unit/                # test_known_devices.py, test_resolve_target.py, test_config_path.py,
│                        #   test_scan.py (+ rows, ordering, include_all)
├── integration/         # test_choice_matrix.py, test_session_lifecycle.py, test_identify.py
└── contract/            # test_cli_scan.py, test_cli_select.py (device), test_cli_device.py,
                         #   test_cli_forget.py, test_cli_pedal_line.py, test_public_api.py (+),
                         #   test_changelog_050.py
```

**Structure Decision**: same single package. Everything about known pedals and the choice rule
lives in one new module, `devices.py`, with no Bluetooth import, so it is table-testable and usable
by scripts. `transport/ble.py` stays the only module that scans. The CLI gets one session helper so
that the choice, the `pedal:` line and the last-seen update cannot be forgotten by a future
command.

## Complexity Tracking

No constitution violations and no new dependencies.

| Addition | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| A per-user configuration file (the project's first persistent state) | The feature's purpose: remember which pedal | Environment variable only: nothing to show, switch or forget, and no nicknames |
| A list of known pedals instead of one entry | Owner's decision (clarification 3): switch by nickname | One entry loses the nickname on every switch |
| `Target` next to `DeviceInfo` | A choice exists before any scan (no name, no signal strength yet) and carries its reason | Reusing `DeviceInfo` with empty fields blurs "chosen" and "found" and breaks its meaning for 0.4.0 users |
| `TargetNotFoundError` subclass | The message must name the target and list what was seen (FR-019) | A plain `NoDeviceFoundError` cannot carry the candidates; a new exit code would break scripts |
| Explicit `open()` / `close()` on `TankG` | Long-lived use from code that cannot wrap its lifetime in one `async with` (clarification 1) | `AsyncExitStack` in user code works but hides the supported lifecycle and the lost-link state |
