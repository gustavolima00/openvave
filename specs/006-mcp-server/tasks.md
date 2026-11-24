---

description: "Task list for 006 MCP server"
---

# Tasks: MCP server

**Input**: Design documents from `specs/006-mcp-server/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md),
[data-model.md](data-model.md), [contracts/tools.md](contracts/tools.md), [quickstart.md](quickstart.md)

**Tests**: MANDATORY (FR-030, SC-003, SC-004, SC-007 are test outcomes). Each test task precedes
the code it covers and must fail first. The default suite stays hardware-free.

**Organization**: one milestone per PR, as in the plan's Delivery Plan. M0 is the server skeleton
and the connection holder (US3, US1 info). M1 adds reads, pedal choice, backups and resources
(US1, US4, US6, US7, US5 backup). M2 adds volatile writes (US2). M3 adds save/restore (US5). M4 is
docs, release and the owner's hardware gate.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1–US7 from spec.md
- Paths are relative to the repository root

## Global rules for every task

- **No new pedal message, no protocol change**: nothing in `src/openvave/protocol/` or
  `specs/protocol/` changes (a parallel session edits them). The session-wide frame audit in
  `tests/conftest.py` keeps passing; save/restore tests carry `@pytest.mark.persistent_writes`.
- **Thin layer**: tools call public `TankG` / `scan` / `KnownDevices` / `openvave.backup`
  functions and the CLI's helpers (`openvave.cli.render` JSON builders, `openvave.cli`
  `parse_assignments` / `parse_field_value`, `openvave.cli.choice`, `openvave.cli.files`). A
  missing helper is added to the CLI module only if the CLI uses it too; otherwise inside
  `mcp_server/`.
- **Opt-ins per call** (`dry_run`, `experimental`, `discard_edits`, `unsafe`) are passed to the
  library unchanged; the server adds no gate except `--read-only` and elicitation.
- **stdout is MCP only**: no `print()` in `src/openvave/mcp_server/`; logging goes to stderr.
- **Library, CLI and their JSON do not change** (existing suite untouched and green).
- **The `mcp` import stays inside `openvave.mcp_server`** and is loaded only by `openvave mcp`.
- **Made-up identifiers only** in fixtures and docs (Constitution VI).
- **Docs with code**: `contracts/tools.md` is the reference; a deliberate deviation is fixed in the
  contract in the same commit. `CHANGELOG.md` [Unreleased] updated each milestone; `README.md`
  only in M4 (rebase on `main` first).
- **Hardware** steps are run by the pedal owner in their own terminal and assistant.
- Checks before each commit: `uv run pytest -q`, `uv run ruff check .`,
  `uv run ruff format --check .`, `uv run mypy`.

---

## Delivery Plan

| PR | Milestone | Stories | Tasks | Gate |
|---|---|---|---|---|
| 1 | Milestone 0: Server skeleton and connection holder 🎯 MVP | US3, US1 (info) | T001–T016 | Lifecycle tests (lazy, reuse, disconnect, idle, lost link, shutdown, lock); errors as `isError`; stdout clean; exit 2 without the extra |
| 2 | Milestone 1: Reads, pedal choice, backups, resources | US1, US4, US6, US7, US5 (backup) | T017–T033 | Parity with CLI JSON; selection matrix; changes; backup folder; resources; quickstart §2 |
| 3 | Milestone 2: Volatile writes | US2 | T034–T045 | Frames equal the CLI's; refusals before sending; dry_run; `--read-only`; annotation table (SC-003, SC-004) |
| 4 | Milestone 3: Save and restore | US5 | T046–T055 | `unsafe`; automatic backup first; elicitation accept/decline/cancel/unsupported in both modes; restore confinement |
| 5 | Milestone 4: Docs, release 0.6.0, hardware gate | all | T056–T066 | Owner's quickstart §3 on fw 96; SC-001…SC-007 reviewed |

Projected PR count: **5** (≤ 8). Milestone N+1 starts only after Milestone N's gate passes.

---

## Milestone 0: Server skeleton and connection holder (US3, US1 info) 🎯 MVP

**Goal**: `openvave mcp` starts an MCP server that holds one connection the right way and answers
`pedal_status`, `pedal_disconnect` and `pedal_info`.

**Independent test criteria**:
- Starting the server scans nothing; the first `pedal_info` opens one connection; ten more calls
  open none (SC-002).
- `pedal_disconnect` closes it (twice is harmless); the next `pedal_info` opens a new one.
- With a fake idle timer, the idle release closes the connection; the next call reopens.
- A link lost between calls → the next call opens once more and succeeds; a link lost during a call
  → that call is an error carrying the library's message, the next call reopens, nothing is resent.
- Two concurrent `pedal_info` calls never interleave requests on the fake transport.
- Any library error is a tool result with `isError: true`; the server answers the next call.
- `pedal_info`'s result equals `openvave info --json` for the same capture, plus `summary`.
- Nothing is written to stdout by tools; `openvave mcp` without the `mcp` package exits 2 with the
  install hint.

### Setup

- [X] T001 Add `[project.optional-dependencies] mcp = ["mcp>=2.3,<3"]` and `mcp>=2.3,<3` to the dev
  group in `pyproject.toml`; `uv sync`; add a mypy override only if the SDK lacks types (it ships
  `py.typed`); confirm `uv run pytest -q` still green
- [X] T002 Create package `src/openvave/mcp_server/` with `__init__.py` (docstring: the server is
  imported only by `openvave mcp`; exposes `run(options, *, transport_factory=None,
  scanner_factory=None) -> int`), empty `server.py`, `holder.py`, `errors.py`, `results.py`
- [X] T003 [P] Test harness in `tests/mcp/conftest.py`: `counting_factory` (wraps a
  `FakeTransport.from_capture(...)` source from the captures existing tests use; counts opens and
  handshakes; can be told to `lose_link()`), `ManualTimer` (injectable idle timer the test fires),
  `make_server(options, factory)` returning the `MCPServer`, and an async `client` fixture using
  `mcp.Client(server, mode="legacy")`; helper `call(client, name, args) -> (is_error, data, text)`

### Tests first (must fail)

- [X] T004 [P] [US3] `tests/mcp/test_holder.py`: lazy start; N `pedal_info` = 1 open + 1 handshake;
  `pedal_disconnect` idempotent and reopen on next call; idle release via `ManualTimer` (timer
  armed after a call, cancelled at the start of the next, `--idle-release 0` never arms); lost link
  between calls → one reopen; lost during a call → error, next call reopens, the fake records no
  repeated write; reopen attempt fails (pedal absent) → `no_device_found` error and server alive;
  concurrent calls serialised (fake records request/reply strictly alternating); shutdown closes
- [X] T005 [P] [US3] `tests/mcp/test_status.py`: `pedal_status` before connecting (`connected:
  false`, options echoed), after (pedal, `chosen_by`, firmware, `firmware_untested`, `since`),
  after an error (`last_error`); never takes the lock (answers while a slow fake call is pending)
- [X] T006 [P] [US1] `tests/mcp/test_read_tools.py::test_info_*`: `pedal_info` result equals the
  `info --json` document built by `openvave.cli.render.info_json` for the same capture (+
  `summary`); bypass/tuner captures report the state; untested-firmware capture carries the warning
- [X] T007 [P] [US3] `tests/mcp/test_errors.py`: each `OpenvaveError` subclass and `ValueError` maps
  to `isError` text `<kind>: <message>` + `hint:` (the CLI's hint) per contracts/tools.md
  §Errors; an unexpected exception → `internal` and a traceback on stderr (caplog), server alive
- [X] T008 [P] [US3] `tests/mcp/test_command.py`: `openvave mcp --help` lists the options;
  invalid `--idle-release -1` → exit 2; with `openvave.mcp_server` import made to fail
  (`monkeypatch` of `sys.modules["mcp"] = None`) → exit 2 and the install hint on stderr; options
  reach `ServerOptions`; during in-process tool calls `capsys` stdout stays empty

### Implementation

- [X] T009 [US3] `src/openvave/mcp_server/holder.py`: `ServerOptions` (frozen dataclass,
  data-model table; `default_backup_dir()` landed in `cli/mcp.py`, T014); `PedalHolder` with fields of the
  data model, `use()` async context manager (lock → cancel idle → open or reopen once → yield →
  re-arm idle), `disconnect()`, `shutdown()`, `status()`; target choice through
  `openvave.cli.choice.choose` / `annotate` / `record_seen` with a namespace carrying
  `device=session_target or options.device`; transport factory and timer injectable
- [X] T010 [US3] `src/openvave/mcp_server/errors.py`: `tool_errors()` async context manager /
  decorator mapping exceptions to `ToolError` text (kind from `WriteRefusedError.reason` or a
  class table; hint text shared with `openvave.cli._report` — extracted as `openvave.cli.error_text(err)`
  and `openvave.cli.report_lines(err) -> list[str]` used by both, CLI output unchanged);
  records `holder.last_error`
- [X] T011 [US1] `src/openvave/mcp_server/results.py`: `with_summary(document, text)`; summary =
  first line of the CLI's human output for the same result (`render.human_info` …)
- [X] T012 [US3] `src/openvave/mcp_server/server.py`: `build_server(holder, options) ->
  MCPServer` (name `openvave`, version, `instructions` = one paragraph: one connection, phone app,
  opt-ins), tools `pedal_status`, `pedal_disconnect`, `pedal_info` with annotations from
  contracts/tools.md; a module-level registry `TOOLS: dict[str, ToolSpec(writes, annotations)]`
  used by later milestones
- [X] T013 [US3] `run()` in `src/openvave/mcp_server/__init__.py`: configure stderr logging
  (`--trace` → the CLI's trace handler), build holder + server, `await server.run_stdio_async()`,
  `holder.shutdown()` in `finally`; return 0
- [X] T014 [US3] `openvave mcp` in `src/openvave/cli/__init__.py` (parser and start in the new
  `src/openvave/cli/mcp.py`, which also holds `default_backup_dir()`, so the CLI needs no MCP
  package to parse the options): subparser with the contract's
  options (`--device`, `--read-only`, `--backup-dir`, `--idle-release`, plus the global
  `--scan-timeout`, `--timeout`, `--trace`); lazy `import openvave.mcp_server` inside a
  `try/except ImportError` → exit 2 with the hint; `main(..., transport_factory=…)` passes the
  factory through
- [X] T015 [US3] `CHANGELOG.md` [Unreleased]: "Added (spec 006 milestone 0): `openvave mcp`…"

### Live verification (milestone gate)

- [X] T016 Suite, ruff, mypy green; `uv run --extra mcp openvave mcp` started by hand answers an
  MCP Inspector `tools/list` with the three tools (quickstart §2, optional if Node is absent:
  then a stdio smoke test in `tests/mcp/test_command.py` that spawns `python -m openvave mcp` with
  `mcp.Client(StdioServerParameters(...))` and lists tools); report to the owner
  - Evidence (2026-11-19): `uv run pytest -q` → 2640 passed, 6 skipped (hardware); `tests/mcp/`
    38 passed, including `test_stdio_smoke` (spawns `python -m openvave mcp`, lists the three
    tools, `pedal_status` → `connected: false`); ruff check / format, mypy (34 files) clean.
    Inspector not run (the stdio smoke test covers the same check). No pedal involved.

**Checkpoint**: Milestone 0 DONE ✅

---

## Milestone 1: Reads, pedal choice, backups, resources (US1, US4, US6, US7, US5 backup)

**Goal**: the assistant can read everything, choose a pedal, take backups and read reference data.

**Independent test criteria**:
- `preset_read` (current / global / status) equals `preset dump --json` regions for the same
  capture; typed knobs carry type and position; bypass shows state without fields.
- Selection matrix: session choice > `--device` > `OPENVAVE_DEVICE` > default > only one; chosen
  but absent → `target_not_found` with seen pedals; two and no choice → `multiple_devices`;
  selecting another pedal closes the held connection; `remember` writes the default (+ nickname)
  to `devices.json`, otherwise the file is untouched.
- `pedal_scan` lists pedals (no connection); a held pedal appears with `connected: true`.
- `pedal_changes`: first call baseline; scripted change → named field before/after; no change
  within `wait_seconds` → `changed: false`; `wait_seconds > 30` → `invalid_value`.
- `preset_backup` writes a verified file in the folder, never overwriting; `backups_list` lists it
  `restorable: true`; a corrupt file is listed with problems.
- Each resource reads without a pedal and matches the library tables.

### Tests first (must fail)

- [X] T017 [P] [US1] `tests/mcp/test_read_tools.py`: `preset_read` for each region and state vs
  `render.preset_json` / `region_json`; unknown region → `invalid_value`
- [X] T018 [P] [US4] `tests/mcp/test_pedal_choice.py`: the matrix above with the existing
  scanner/transport fakes from `tests/integration/test_choice_matrix.py`; prefix ≥ 4 hex digits,
  ambiguous prefix, unknown nickname, invalid config file (identifier still works)
- [X] T019 [P] [US6] `tests/mcp/test_changes.py`: scripted fake whose current-preset read changes
  between calls; state change (bypass) reported; poll with injected sleep; cap
- [X] T020 [P] [US5] `tests/mcp/test_backups.py`: default folder from `XDG_DATA_HOME` / HOME /
  `LOCALAPPDATA` (monkeypatched), `--backup-dir`, created 0700; backup result = `backup_json` +
  `path`; second backup in the same second gets a new name; `backups_list` newest first with
  `restore_problems`
- [X] T021 [P] [US7] `tests/mcp/test_resources.py`: `openvave://fields` has every
  `WRITABLE_FIELDS` name with syntax, range, types and `experimental` for observed targets;
  `effect-types` equals the three type tables; `byte-map` equals `BYTE_MAP`; `safety` markdown
  names `unsafe` and `experimental`

### Implementation

- [X] T022 [US1] `preset_read` tool in `server.py` (reads + `decode_region` + `state()`; sets
  `holder.baseline`)
- [X] T023 [US6] `pedal_changes` tool: reads global / current / status, `diff` per region, decode
  names; polling loop with injectable sleep, 0.5 s step, cap 30 s; updates baseline
- [X] T024 [US4] `pedal_scan` tool: `openvave.scan(timeout=options.scan_timeout)` + known
  nicknames + default marker; under the holder lock; held pedal appended `connected: true`
- [X] T025 [US4] `pedal_select` tool: nickname / full identifier / prefix resolution (reuse
  `openvave.cli.pedals` helpers where pure, else move the pure matcher into
  `openvave.devices` only if `cli.pedals` uses it too; landed as
  `openvave.cli.pedals.resolve_selection`, used by `openvave select` too); sets `holder.session_target`
  (`chosen_by="device_option"`); closes a held connection to another pedal and clears baseline /
  bypass_return; `remember` → `KnownDevices.select(...).save()` and the `select --json` document
- [X] T026 [US5] `src/openvave/mcp_server/backups.py`: `default_backup_dir()` (re-exported from
  `openvave.cli.mcp`, M0), `ensure_dir()`,
  `manual_backup_path(dir, when)` (no overwrite, `-1`, `-2` …), `resolve_backup_file(dir, name)`
  (confinement rules of research R10, raising a `ValueError` subclass mapped to `invalid_file`),
  `list_backups(dir)`
- [X] T027 [US5] `preset_backup` tool (`TankG.backup()` → `openvave.cli.files.write_json_atomic`
  with the CLI's backup document) and `backups_list` tool
- [X] T028 [US7] `src/openvave/mcp_server/resources.py` and registration in `server.py`
  (`openvave://fields`, `effect-types`, `byte-map`, `safety`)
- [X] T029 [US1] Annotations for the M1 tools in the `TOOLS` registry (contract table)
- [X] T030 `CHANGELOG.md` [Unreleased]: milestone 1 entries

### Live verification (milestone gate)

- [X] T031 Suite, ruff, mypy green
- [X] T032 Quickstart §2 with the Inspector (or the stdio smoke test): tools and resources listed,
  resources readable without a pedal
- [X] T033 Report to the owner (tools so far, what the assistant can now do)
  - Evidence (2026-11-19): `uv run pytest -q` → 2704 passed, 6 skipped (hardware);
    `tests/mcp/` 102 passed (read tools vs `preset dump` / `info` JSON, choice matrix incl.
    session > `--device` > env > default > only one, changes with injected poll sleep, backup
    folder and confinement, resources vs library tables); `test_stdio_smoke` spawns
    `python -m openvave mcp`, lists the 9 tools and 4 resources, calls `backups_list` and reads
    `openvave://fields` without a pedal. ruff check / format, mypy (36 files) clean. Nothing in
    `src/openvave/protocol/` or `specs/protocol/` changed. Inspector not run (the stdio smoke
    test covers it). No pedal involved.

**Checkpoint**: Milestone 1 DONE ✅

---

## Milestone 2: Volatile writes (US2)

**Goal**: the assistant changes the current sound, loads/reloads presets, bypasses and toggles
loopback with the CLI's opt-ins.

**Independent test criteria**:
- For each tool, the frames the fake transport receives equal what the CLI sends for the same
  arguments (`main([...], transport_factory=…)` on an identical fake).
- `pedal_set` with an observed field and no `experimental` → `experimental_required`, no frame;
  with it → applied. Unknown field / bad value / tuner / bypassed / unsaved edits without
  `discard_edits` → refused, no frame.
- `dry_run: true` on every write tool → frames in the result, none sent.
- Mid-batch failure (NAK) → error with `partial:` = the CLI's `edit_json`.
- `bypass_off` without position after `bypass_on` in the session returns to the reported one;
  without either → `invalid_value` naming the bank.
- `--read-only` → the 8 write tools are absent from `tools/list`; calling one by name fails.
- Every listed tool's annotations equal the contract table (SC-004).

### Tests first (must fail)

- [X] T034 [P] [US2] `tests/mcp/test_write_tools.py`: parity, refusals, dry_run, partial result,
  reminder text, bypass return position, loopback
- [X] T035 [P] [US2] `tests/mcp/test_annotations.py`: parse the tool table of
  `specs/006-mcp-server/contracts/tools.md` and compare with `tools/list` (names, RO/D/I,
  `openWorldHint=false`, hidden under `--read-only`)
- [X] T036 [P] [US2] `tests/mcp/test_gates.py` (SC-003): for every write tool × {no opt-in,
  `experimental`, `discard_edits`} the fake never receives a persistent write or a non-confirmed
  message without `experimental`

### Implementation

- [X] T037 [US2] Value conversion for `pedal_set.changes` (landed in the new `src/openvave/mcp_server/writes.py` with the six write tools, registered from `server.py`): JSON numbers / booleans →
  CLI text; `openvave.cli.parse_assignments` for syntax; errors → `invalid_value` /
  `unknown_field`
- [X] T038 [US2] `pedal_set` tool (`plan_set_fields` for `dry_run`, else `set_fields`; result =
  `render.edit_json` + reminder)
- [X] T039 [US2] `preset_select` (`parse_position` for `1A`–`9D` or index) and `preset_reload`
  tools (`render.write_json`)
- [X] T040 [US2] `bypass_on` (stores `holder.bypass_return`) and `bypass_off` tools
- [X] T041 [US2] `loopback` tool
- [X] T042 [US2] `--read-only`: remove `TOOLS` entries with `writes=True` after registration
- [X] T043 `CHANGELOG.md` [Unreleased]: milestone 2 entries

### Live verification (milestone gate)

- [X] T044 Suite, ruff, mypy green; frame audit unchanged
- [X] T045 Report to the owner
  - Evidence (2026-11-19): `uv run pytest -q` → 2817 passed, 18 skipped (6 hardware, 12
    gate-matrix cells for tools without `discard_edits`); session frame audit (SC-004) and
    persistent-write audit pass unchanged. `tests/mcp/test_write_tools.py`: for 10 tool calls
    the frames and the document equal `openvave … --json` on an identical fake, with and
    without `dry_run` (nothing sent); refusals (`experimental_required`, `tuner_mode`,
    `bypassed`, `edits_would_be_discarded`, `not_bypassed`, `unknown_field`, `invalid_value`)
    send no frame, and argument errors open no connection; a mid-batch NAK carries the CLI's
    `edit_json` as `partial:`; `bypass_off` returns to the position from `bypass_on`.
    `test_gates.py` (SC-003): 7 calls × 3 opt-ins × 3 states, no persistent write and nothing
    unconfirmed without `experimental`. `test_annotations.py` (SC-004): annotations equal the
    contract table; `--read-only` hides and blocks the 6 write tools (also over stdio in
    `test_command.py`). ruff check / format, mypy (37 files) clean. Nothing in
    `src/openvave/protocol/` or `specs/protocol/` changed. No pedal involved.

**Checkpoint**: Milestone 2 DONE ✅

---

## Milestone 3: Save and restore (US5)

**Goal**: persistent writes with the CLI's `--unsafe` rules, the automatic backup in the backup
folder, and the owner's confirmation through elicitation where supported.

**Independent test criteria**:
- Without `unsafe` → `unsafe_required`, no frame, no prompt, no backup file.
- `dry_run` → planned steps and frames, nothing sent, never prompts.
- With `unsafe` and a client without elicitation → backup file in the folder first, then the
  sequence; result = `render.sequence_json` + backup path.
- Client with elicitation, both `mode="legacy"` and `mode="auto"`: accept + `confirm: true` → run;
  decline, cancel, `confirm: false` → `declined_by_owner`, no frame, no backup.
- Backup write failure (read-only folder) → nothing written to the pedal.
- Restore: `file` absolute, with `/`, `..`, or a symlink leading out → `invalid_file` before
  connecting; another firmware's file without `experimental` → `firmware_mismatch`; unsaved edits
  without `discard_edits` → refused.

### Tests first (must fail)

- [X] T046 [P] [US5] `tests/mcp/test_save_restore.py` (`@pytest.mark.persistent_writes`): the
  criteria above, reusing the save/restore fakes of `tests/contract/test_cli_save.py` /
  `test_cli_restore.py`; frames equal the CLI's for the same arguments
- [X] T047 [P] [US5] `tests/mcp/test_elicitation.py`: callback variants × both client modes;
  message names position(s) and folder; capability absent → not asked

### Implementation

- [X] T048 [US5] Elicitation resolver (landed in the new `src/openvave/mcp_server/sequences.py`
  with both tools, registered from `server.py`; research R9): `Confirm` model, `ask()`
  resolver returning `Elicit(...)` or the "not asked" marker; outcome → proceed or
  `declined_by_owner`
- [X] T049 [US5] `preset_save` tool: `plan_save` for `dry_run`; else `save_preset(to, unsafe=…,
  experimental=…, on_backup=…)` with `on_backup` writing to
  `openvave.cli.files.automatic_backup_path(holder.options.backup_dir, "save", now)`
- [X] T050 [US5] `preset_restore` tool: `resolve_backup_file` + `openvave.cli.load_restore_file`
  (or `openvave.backup` loader) before taking the pedal; `plan_restore` / `restore(...)` with the
  same `on_backup`; `slot` (position or index) xor `all`
- [X] T051 [US5] Annotations (`destructiveHint=true`) and descriptions (what `unsafe` means, that a
  backup is taken first, that the owner may be asked)
- [X] T052 `CHANGELOG.md` [Unreleased]: milestone 3 entries

### Live verification (milestone gate)

- [X] T053 Suite, ruff, mypy green; persistent-frame audit passes (only marked tests send them)
- [X] T054 SC-003 test extended to save/restore
- [X] T055 Report to the owner
  - Evidence (2026-11-19): `uv run pytest -q` → 2896 passed, 24 skipped (6 hardware, 18
    gate-matrix cells for tools without `discard_edits`); the session persistent-write audit
    passes (only `tests/mcp/test_save_restore.py` and `test_elicitation.py`, both marked
    `persistent_writes`, send slot / commit / image frames). `test_save_restore.py`: save (run
    and dry run) and restore (`all`, `slot` 1C, `slot` 2) send the CLI's frames and return its
    `--json` document; without `unsafe` → `unsafe_required`, no frame, no backup file; edit
    mode, `firmware_mismatch`, `edits_would_be_discarded` refused with nothing sent; slot/all,
    bad position, absolute / separator / `..` / missing / symlink-out / corrupt files refused
    before connecting; the automatic backup (folder 0700) equals the pedal before the save; a
    read-only folder → `invalid_file`, nothing written to the pedal; a commit NAK carries
    `backup:` and `partial:`. `test_elicitation.py` (legacy and `auto` modes): accept +
    `confirm: true` runs; decline / cancel / `confirm: false` → `declined_by_owner` with no
    connection and no backup; not asked without `unsafe`, with `dry_run`, for invalid
    arguments, or without the capability; the confirmation is not a tool argument.
    `test_gates.py` (SC-003) covers save/restore × 3 opt-ins × 3 states with no persistent
    frame. ruff check / format, mypy (38 files) clean. Nothing in `src/openvave/protocol/` or
    `specs/protocol/` changed. No pedal involved.

**Checkpoint**: Milestone 3 DONE ✅

---

## Milestone 4: Docs, release 0.6.0, hardware gate (all)

**Goal**: an owner can install and configure the server from the docs and it works on their pedal.

**Independent test criteria**:
- Following `docs/mcp.md` alone, the owner configures Claude Code or Claude Desktop and asks
  "what preset is loaded?" (SC-001).
- Quickstart §3 passes on fw 96 (reads, one volatile write + reload, refusal without
  `experimental`, disconnect → phone app connects, lost link, idle release, backup).

- [X] T056 [P] `docs/mcp.md`: install (`pip install 'openvave[mcp]'`, `uv tool install
  'openvave[mcp] @ git+…'`), Claude Code (`claude mcp add openvave -- …`) and Claude Desktop
  (`claude_desktop_config.json` snippet, macOS Bluetooth permission for the app that launches it),
  options, connection behaviour (one connection, phone app, `pedal_disconnect`, idle release),
  tool table with opt-ins and annotations, elicitation, backup folder, troubleshooting
- [X] T057 [P] `docs/README.md` index, `docs/safety.md` (MCP row: same opt-ins per call,
  `--read-only`, elicitation), `docs/cli-reference.md` (`openvave mcp`)
- [X] T058 Merge `origin/main` (no rebase: a merge, so the open PR's history stays intact); `README.md`: short "AI assistants (MCP)" section linking
  `docs/mcp.md`
- [X] T059 `CHANGELOG.md` [0.6.0] from the milestone entries; version 0.6.0 in `pyproject.toml`
  and `src/openvave/__init__.py`; `tests/contract/test_changelog_060.py`
- [X] T060 Suite, ruff, mypy green
- [X] T061 Owner: quickstart §3 steps 1–9 in their own assistant and terminal (fw 96)
- [ ] T062 Owner (optional): step 10 (no-op save; elicitation decline) — not run in this gate;
  the owner checked saving in a separate test of their own (see Hardware check)
- [X] T063 Record the results under "Hardware check" below (client and version, firmware, macOS)
- [X] T064 Fix regressions found by the gate (each with a test): the gate found none. Fixed
  before it, each with a test: Codex's review of 0475c9e ([P1] restore writes the confirmed
  snapshot, also for import; [P2] backups published without replacing) and the PR #6 Codex
  rounds 1–3 (CLI backup retry, no-link folders, dangling names, slot checks before reading,
  the owner's answer final across the modern-protocol retry, link errors keep their reason)
- [X] T065 Review SC-001…SC-007 against the results (below)
- [X] T066 Report to the owner (PR #6, through the orchestrator); no push to `main`, no tag or
  release

**Checkpoint**: Milestone 4 DONE ✅

### Hardware check

Owner's run of quickstart §3, 2026-11-24, code of PR #6 at b45c0eb / 6c449b8 (server started
from the branch with `claude mcp add openvave-m4 -- uv run --directory <worktree> --extra mcp
openvave mcp --backup-dir captures/private`). Client **Claude Code 2.1.331**, started from
Terminal; **macOS 26.5.2**; pedal firmware **96**.

| Step | What | Result |
|---|---|---|
| 1 | `pedal_info` (fw 96, state, loaded preset), then `pedal_status` `connected: true` | pass |
| 2 | `preset_read` vs `openvave preset dump --json` after `pedal_disconnect` | pass |
| 3 | three more reads on one connection (`pedal_status.since` unchanged) | pass |
| 4 | `pedal_set gain=80` with `dry_run`, then for real (heard), then `preset_reload` | pass |
| 5 | `preset_save` without `unsafe` → `unsafe_required`, nothing sent (replaces the old "delay without `experimental`" check: since spec 007 no fw 96 write needs `experimental`) | pass |
| 6 | `pedal_disconnect` → the phone app connects; after closing it, the server reconnects | pass |
| 7 | pedal off between calls → error, server still answering; on again → next call works | pass |
| 8 | `--idle-release 30` → the phone app connects without closing the assistant | pass |
| 9 | `preset_backup` into `captures/private`; `backups_list` shows it `restorable` | pass |
| 10 | optional no-op save and elicitation decline | **not run** in this gate; the owner checked saving through the server in a separate test of their own; an elicitation dialog was not observed |

The owner's summary: "rodei o teste manual, e funcionou". No regression found (T064). Nothing in
this gate wrote stored presets.

**SC review (T065)**:

- SC-001 (docs to "what preset is loaded?" in < 10 min): partly evidenced. The owner configured
  Claude Code with one `claude mcp add` line (the form `docs/mcp.md` gives) and step 1 passed; the
  time and a fresh install from the docs alone were not measured. Claude Desktop not tried.
- SC-002 (reads reuse one connection): pass. Steps 1–3 on hardware; `test_holder.py` (N calls = 1
  open + 1 handshake).
- SC-003 (no stored change without `unsafe`, nothing unconfirmed without `experimental`): pass.
  Step 5 on hardware; `test_gates.py` covers every write tool × opt-ins × states.
- SC-004 (annotations, previews): pass. `test_annotations.py` against the contract table; every
  write tool's `dry_run` sends nothing (`test_write_tools.py`, `test_save_restore.py`,
  `test_preset_ops.py`); step 4's dry run on hardware.
- SC-005 (recovery after a lost link, server never exits on a pedal error): pass. Step 7 on
  hardware; `test_holder.py`, `test_errors.py`.
- SC-006 (phone app after disconnect or idle release, without restarting the assistant): pass.
  Steps 6 and 8 on hardware.
- SC-007 (server values equal the CLI's JSON): pass. Step 2 on hardware; parity tests in
  `test_read_tools.py`, `test_write_tools.py`, `test_save_restore.py`, `test_preset_ops.py`.
- Not covered by this gate: the elicitation dialog in a real client (tested in-process in both
  protocol modes, `test_elicitation.py`), Claude Desktop, Linux / Windows hardware.

---

## Dependencies & Execution Order

- M0 → M1 → M2 → M3 → M4 (each gate before the next milestone).
- Inside a milestone: setup → tests (fail) → implementation → gate. Test tasks marked [P] touch
  different files and can be written together.
- US3 (holder) blocks every pedal tool; US1 info lands with it as the MVP.

## Parallel Example: Milestone 1 tests

```text
T017 tests/mcp/test_read_tools.py
T018 tests/mcp/test_pedal_choice.py
T019 tests/mcp/test_changes.py
T020 tests/mcp/test_backups.py
T021 tests/mcp/test_resources.py
```

## Implementation Strategy

MVP = Milestone 0: an assistant can already ask what the pedal is and the connection behaves
(lazy, shared, released). Each later milestone adds a group of tools without changing earlier
ones; the server is usable after every gate.
