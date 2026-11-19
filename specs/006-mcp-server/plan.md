# Implementation Plan: MCP server

**Branch**: `claude/spec-006-mcp-server-1da712` | **Date**: 2026-11-19 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/006-mcp-server/spec.md`

## Summary

`openvave mcp` runs an MCP server over stdio so an AI assistant can do everything the CLI does
with a Tank-G. It is a thin front end over the public library, like the CLI: every tool calls an
existing `TankG` operation (or `scan` / `KnownDevices`), passes the CLI's opt-ins as per-call
arguments (`dry_run`, `experimental`, `discard_edits`, `unsafe`), and returns the CLI's `--json`
document for the same operation. A `PedalHolder` keeps one long-lived connection (spec 005
`open` / `close` / `is_connected`): lazy, serialised by a lock, released after 5 idle minutes or on
`pedal_disconnect`, reopened once on the next call after a lost link, never resending a write.
Save and restore additionally ask the owner through MCP elicitation when the client supports it.
Backups live in one per-user folder; restore reads only from it. Resources expose the writable
fields, effect types, byte map and safety rules. No protocol change. SDK: official `mcp` 2.x as
the optional extra `openvave[mcp]`. Decisions: [research.md](research.md).

## Technical Context

**Language/Version**: Python ≥ 3.11 (unchanged)

**Primary Dependencies**: `bleak` ≥ 0.22 (runtime, unchanged). New **optional** extra
`mcp = ["mcp>=2.3,<3"]` (official MCP Python SDK; pulls pydantic, anyio, httpx, starlette,
uvicorn…); also added to the dev group so the suite tests the server (R1)

**Storage**: none new. Reads/writes the 0.5.0 `devices.json` through `KnownDevices`; backup files
in `--backup-dir` (default `$XDG_DATA_HOME/openvave/backups` / `~/.local/share/openvave/backups`
/ `%LOCALAPPDATA%\openvave\backups`), never overwritten (R10)

**Testing**: `pytest` + `pytest-asyncio`, hardware-free. `tests/mcp/` drives the server in-process
with `mcp.Client(server)` (modes `legacy` and `auto` for elicitation) over `FakeTransport`
captures and the existing scripted fakes; injectable transport factory, scanner factory and idle
timer; `jsonschema` checks results against the existing CLI schemas. Hardware gate by the owner
(quickstart §3)

**Target Platform**: as the library (macOS verified; Linux/Windows best effort). Clients: any MCP
client that launches stdio servers (Claude Desktop, Claude Code, MCP Inspector)

**Project Type**: library + CLI (single Python package) gaining a third front end

**Performance Goals**: first pedal call = scan + handshake (≈ 2–6 s, as the CLI); later calls
reuse the connection (SC-002); `pedal_status`, resources and `backups_list` answer without
Bluetooth; `pedal_changes` waits at most 30 s

**Constraints**: no new pedal message or write target; nothing the CLI cannot send; stdout only
MCP; one pedal call at a time; no in-call reconnect or resend after a lost link; library and CLI
behaviour and JSON unchanged; `pip install openvave` without the extra unchanged

**Scale/Scope**: 1 new CLI command (`openvave mcp`, 7 options), 17 tools, 4 resources, 1 new
subpackage (~5 modules), no new public library names

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Pre-research evaluation (2026-11-19):

- [x] **I. Protocol docs**: no message is added or changed; `specs/protocol/` is not touched
  (also keeps clear of the parallel polish session).
- [x] **II. Evidence**: no new protocol claim. The hardware gate records client, firmware and
  results in `tasks.md`.
- [x] **III. Capture-driven tests**: no codec change. Tools are tested against `FakeTransport`
  captures already in `tests/`; expected values come from the CLI's JSON for the same capture;
  tests written first per milestone; suite stays hardware-free.
- [x] **IV. Device safety**: every write keeps the library's gates (`experimental`, `unsafe`,
  `discard_edits`), its dry-run (`dry_run`), its verification and, for save/restore, the automatic
  verified backup; tools carry `destructiveHint` / `readOnlyHint`; save/restore also ask the owner
  via elicitation where supported; `--read-only` hides every write; restore reads only the backup
  folder; a lost link never triggers a resend.
- [x] **V. Library-first/CLI**: the server uses only public library calls plus the CLI's
  rendering/parsing helpers; it is started from the CLI (`openvave mcp`); results are JSON (the
  CLI's documents) with a human `summary`. MINOR bump (0.6.0), nothing breaks.
- [x] **VI. Clean-room**: no vendor material; test fixtures are the existing sanitized captures.
- [x] **VII. Simplicity**: one optional dependency (justified below); transport interface
  unchanged; the holder is a small wrapper around the existing session lifecycle.

Result: **PASS**.

Post-design re-evaluation (after Phase 1, 2026-11-19): **PASS**. The design reuses the CLI's
JSON builders and value parser instead of re-implementing them (SC-007), keeps `chosen_by` in the
existing enum (a session choice reports as `device_option`, R12), and adds no public library name.
One SDK constraint shaped the elicitation design (R9: resolver-based, works in both protocol modes).

## Delivery Plan

Projected PR count: **5** (≤ 8). M0–M3 are hardware-free; M4 holds the owner's hardware gate and
the release. Each milestone is one commit series on this branch, stopping at its gate for the
owner's review, as in specs 004–005.

| # | Milestone | Scope | Stories | Verification gate |
|---|---|---|---|---|
| M0 | Server skeleton and connection holder | `pyproject` extra + dev dep; `openvave mcp` (options, exit 2 without the extra, stderr logging, clean shutdown); `mcp_server/holder.py` (`PedalHolder`: target choice reusing `cli.choice`, lazy open, lock, reuse, one reopen after lost link, idle release with injectable timer, disconnect, shutdown); `mcp_server/errors.py` (library error → tool error with kind/hint/partial); `server.py` with `pedal_status`, `pedal_disconnect`, `pedal_info`; test harness (in-process client, counting factory) | US3, US1 (info) | Suite green: lazy (no scan at start), N reads = 1 open + 1 handshake, disconnect idempotent and next call reopens, idle release fires and next call reopens, lost link between calls → one reopen, lost during a call → error and no resend, shutdown closes, concurrent calls serialised, errors are `isError` and the server keeps serving, nothing on stdout; `openvave mcp` without `mcp` → exit 2 |
| M1 | Reads, pedal choice, backups, resources | `preset_read` (current / global / status), `pedal_changes`, `pedal_scan`, `pedal_select` (session / remember / nickname / prefix), `preset_backup`, `backups_list`, `mcp_server/backups.py` (folder, names, confinement); resources `fields`, `effect-types`, `byte-map`, `safety`; annotations for these tools | US1, US4, US6, US7, US5 (backup) | Results equal the CLI's `--json` for the same capture (schemas validate); selection matrix (session > `--device` > env > default > only one; no fallback; switching pedal closes the old connection; `remember` writes `devices.json`); changes baseline/diff/wait cap; backup file in folder, never overwritten; resources match library tables; quickstart §2 with the Inspector |
| M2 | Volatile writes | `pedal_set`, `preset_select`, `preset_reload`, `bypass_on`, `bypass_off` (return position remembered), `loopback`; `dry_run`, `experimental`, `discard_edits`; `--read-only` removes write tools; annotation table test over all tools | US2 | Frames sent equal the CLI's for the same arguments (captured `FakeTransport` writes); every refusal before sending (opt-ins, state, unknown field, bad value); `dry_run` sends nothing; partial batch result on mid-batch failure; read-only hides the 8 write tools; SC-003/SC-004 tests |
| M3 | Save and restore | `preset_save`, `preset_restore` with `unsafe`, automatic backup in the folder, restore file confinement and checks, elicitation resolver (legacy and auto modes; accept / decline / cancel / unsupported) | US5 | Without `unsafe` nothing sent; dry_run sends nothing and never prompts; backup written before the first write and failure stops; declined / cancelled → nothing sent; sequence result equals the CLI's; restore refuses absolute paths, `..`, links out of the folder |
| M4 | Docs, release 0.6.0, hardware gate | `docs/mcp.md` (install, Claude Desktop and Claude Code snippets, `--read-only`, connection behaviour, tools/opt-ins/annotations table, elicitation, backups, troubleshooting), README section, `docs/README.md` index, `docs/safety.md` row, `cli-reference.md`, CHANGELOG 0.6.0, version bump, `test_changelog_060`; owner runs quickstart §3 | all | Owner's gate passes on fw 96 and is recorded in `tasks.md`; SC-001…SC-007 reviewed; rebase on `main` without conflict with the polish session |

## Project Structure

### Documentation (this feature)

```text
specs/006-mcp-server/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── tools.md         # command, options, tools, annotations, resources, errors
├── checklists/requirements.md
└── tasks.md             # Phase 2 output (/speckit-tasks — not created here)
```

### Source Code (repository root)

```text
pyproject.toml                       # + [project.optional-dependencies] mcp; dev group + mcp

src/openvave/
├── cli/__init__.py                  # + `mcp` subcommand: parses options, imports the server lazily
└── mcp_server/                      # NEW, imported only by `openvave mcp` (needs the extra)
    ├── __init__.py                  # run(options, *, transport_factory=None, scanner_factory=None)
    ├── server.py                    # build_server(holder, options) -> MCPServer: tools, resources
    ├── holder.py                    # ServerOptions, PedalHolder (choice, lock, lifecycle, idle)
    ├── errors.py                    # tool_errors(): OpenvaveError/ValueError -> ToolError text
    ├── results.py                   # thin wrappers over cli.render JSON builders + summary
    ├── backups.py                   # default folder, names, confinement, listing
    └── resources.py                 # fields / effect types / byte map / safety documents

tests/
├── conftest.py                      # (existing) OPENVAVE_CONFIG → tmp
└── mcp/                             # NEW
    ├── conftest.py                  # server+client fixtures, counting factory, fake timer
    ├── test_command.py              # openvave mcp options, missing extra, stdout clean
    ├── test_holder.py               # lifecycle, lock, idle, lost link
    ├── test_read_tools.py           # info, preset_read, changes, parity with CLI JSON
    ├── test_pedal_choice.py         # scan, select, matrix
    ├── test_backups.py              # backup, list, confinement
    ├── test_resources.py
    ├── test_write_tools.py          # set, select, reload, bypass, loopback, read-only
    ├── test_annotations.py          # registry vs contract table
    └── test_save_restore.py         # unsafe, auto backup, elicitation

docs/mcp.md                          # NEW (M4); README, docs/README.md, safety.md, cli-reference.md
```

**Structure Decision**: one new subpackage beside `cli/`, imported only when the server runs, so
the core package keeps working without the extra. It depends on the library and on `cli`'s
rendering/parsing/choice helpers (shared front-end code); the library never imports it.

## Complexity Tracking

| Addition | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| Optional dependency `mcp` (2.x) and its tree | Speaking MCP correctly (initialize/discover, tools, annotations, resources, elicitation in both protocol modes) | Hand-written JSON-RPC re-implements a moving protocol; the low-level SDK API is more code for the same dependency; making it a hard dependency would force ~28 packages on library users |
| `PedalHolder` (lock + idle timer) | One BLE connection shared by concurrent tool calls; let the phone app take the pedal back (clarification 2) | Connect per call (CLI style) pays a scan + handshake every call; holding forever locks the phone app out |
| Elicitation resolver | Owner confirmation for persistent writes where clients support it (clarification 3) | `ctx.elicit()` in the tool body fails in the 2.x modern protocol mode (R9) |
| Front end importing `openvave.cli` helpers | Identical JSON and value syntax to the CLI (SC-007) without moving 1 400 lines the parallel session also edits | Re-implementing the JSON builders would drift from the CLI schemas |
