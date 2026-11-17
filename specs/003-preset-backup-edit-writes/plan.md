# Implementation Plan: Preset backup and first edit-buffer writes

**Branch**: `claude/protocol-preset-storage-bf8bea` (feature directory `003-preset-backup-edit-writes`) |
**Date**: 2026-11-17 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/003-preset-backup-edit-writes/spec.md`

## Summary

Three additions to the 0.2.0 client, in order of risk. (1) A read-only **preset backup**: a closed
set of storage reads (header, stored preset `i`, whole image) next to the existing `Region` enum,
a `TankG.backup()` that reads the header and the 36 presets one by one and cross-checks them
against one whole-image read, and `openvave preset backup` writing a versioned JSON file. (2) The
first **writes**, limited to the volatile edit buffer and the preset-select register: command
`0x22` becomes encodable only through a closed `WriteTarget` allowlist (knob block, 4 block
switches, LED colour, preset select), and every write goes through one guarded path that checks
mode, range, firmware and the message's confidence, supports dry-run, checks the ACK and re-reads
to verify. `openvave set <field> <value>` and `openvave preset select <pos>` expose it. Erase
(`0x21`), the commit (`0xF0000000`), stored-area writes and the loopback write stay unencodable.
(3) **Gated hardware sessions** in which the owner approves and runs each first write; the records
promote each write message in a new, doc-mirrored "Write messages" table. Decisions:
[research.md](research.md).

## Technical Context

**Language/Version**: Python ≥ 3.11 (unchanged)

**Primary Dependencies**: `bleak` ≥ 0.22 (runtime, unchanged). No new runtime or dev dependency

**Storage**: backup files are JSON documents at a user-chosen path (default
`./tankg-backup-<YYYYmmdd-HHMMSS>.json`, R7); gate records are JSONL in `captures/private/`,
sanitized excerpts in `captures/fw96/` (no full stored image, FR-020)

**Testing**: `pytest` (+ `pytest-asyncio`, `jsonschema`). Hardware-free by default: backup and
writes run against `FakeTransport` with a synthetic stored image and scripted ACK/NAK replies.
Hardware tests stay opt-in (`--hardware`) and the write ones additionally need an explicit
environment flag (R11)

**Target Platform**: macOS (hardware-verified); Linux/Windows best-effort (unchanged)

**Project Type**: library + CLI (single Python package)

**Performance Goals**: backup ≈ 39 reads at 40–90 ms each plus one 773-byte reply ≈ 2–4 s
(SC-001: < 10 s). A write action = 2–3 reads + 1 write ≈ 0.3 s

**Constraints**: one request in flight; command bytes `0x11`, `0x23`, `0x22` only, and `0x22`
only to allowlisted address/length pairs (FR-013); no write without edit mode (except preset
select), range check, firmware check and confidence gate (FR-009/010/014/015); no polling beyond
post-write verification (R9)

**Scale/Scope**: 36 stored presets × 21 B; 4 write message kinds (knob block, block switch ×4,
LED colour, preset select); 2 new CLI commands + 1 subcommand

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Pre-research evaluation (2026-11-17):

- [x] **I. Protocol docs**: every message is already described in `command-layer.md`; this feature
  adds a machine-checkable "Write messages" table there (target, frame, reply, confidence,
  evidence) mirrored by `WRITE_MESSAGES` in code and enforced by a doc↔code test, like the byte
  map (R4). Docs and code change in the same PR.
- [x] **II. Evidence**: storage reads cite the 2026-11-17 probe (private) and a committed
  synthetic-plus-public fixture; each write row cites the gate record that promoted it, firmware
  96 / app 3.9.2314 provenance kept (FR-019).
- [x] **III. Capture-driven tests**: fixtures first: storage-read and ACK/NAK frames from real
  records (sanitized), plus synthetic image bytes; tests fail before the code exists. Suite stays
  hardware-free.
- [x] **IV. Device safety**: writes are separately named (`set`, `preset select`), have dry-run,
  and the CLI takes a backup step before the first write of each gate (FR-019). `hypothesis`
  messages need `--experimental` (FR-014). Stored-area writes, commit, erase and loopback are not
  encodable at all (R2). Writes are volatile edit-buffer changes; "leave edit mode without
  saving" restores the preset.
- [x] **V. Library-first/CLI**: `TankG.backup()`, `TankG.set_field()`, `TankG.select_preset()` in
  the library; the protocol layer stays pure (builders/parsers only). CLI adds file writing,
  confirmation flags and rendering; human + JSON output.
- [x] **VI. Clean-room**: no vendor code or strings; the full stored image (likely factory
  content) is never committed — fixtures use synthetic bytes plus presets already public (R10).
- [x] **VII. Simplicity**: no new dependency. One guarded write path for all targets. The
  storage reads reuse the read parser through a small `ReadTarget` value instead of widening the
  `Region` enum.

Result: **PASS**.

Post-design re-evaluation (after Phase 1, 2026-11-17): **PASS**. The data model keeps encoding
pure and closed (`StorageRead`, `WriteTarget` constructors validate everything). The contracts add
one subcommand (`preset backup`), two commands (`set`, `preset select`), one exit code (8, write
not applied, R8) and a backup file schema; existing JSON stays `schema_version` 2 (additive only,
R12). The 001 guarantee "only `0x11`/`0x23`" is deliberately narrowed: `0x22` is allowed only for
the allowlisted targets, and the command audit test is updated to check that allowlist (R2).

## Delivery Plan

Projected PR count: **5** (≤ 8, no re-scoping needed). M0 and M1 are code milestones whose
hardware gates are read-only or dry-run. M2 and M3 are evidence milestones with owner-approved
writes. Each write's first send happens only in M2.

| # | Milestone | Scope | Stories | Verification gate |
|---|---|---|---|---|
| M0 | Preset backup (read-only) | `StorageRead` targets (header, preset `i`, image), read builder/parser for them, `TankG.backup()` with cross-check, `Backup` model, backup file writer (atomic, `--force`), `openvave preset backup` (human + JSON), `backup.schema.json`. Synthetic stored-image fixture + `FakeTransport` support for multi-notification image replies. `command-layer.md`: storage rows cite the committed fixture | US1 | Suite green; audit still only `0x11`/`0x23`. **Hardware (read-only, no approval needed)**: owner runs `preset backup` twice → files identical apart from timestamp, 36 presets, header `a5 5a` (SC-001, SC-002) |
| M1 | Guarded write path (offline) | `WRITE` in the frame codec behind `WriteTarget` allowlist; `parse_write_reply` (ACK/NAK); `WRITE_MESSAGES` table + "Write messages" doc table + doc↔code test; `TankG.plan_*`/`set_field`/`select_preset` (mode/range/firmware/confidence checks, dry-run, ACK, verify); `WriteResult`; CLI `set`, `preset select`, `--dry-run`, `--experimental`, `--discard-edits`; exit 8; updated command audit (0x22 only to allowlisted targets, never `0x21`) | US2, US3 | Fake-transport tests for every target, ACK, NAK, not-applied, refusals (not edit mode, range, firmware, hypothesis). Dry-run frames equal sent frames (SC-003). **Hardware (dry-run only)**: owner runs `set gain 90 --dry-run` and `preset select 2C --dry-run`; trace shows reads only |
| M2 | Gate session A: first writes | Per gate step: fresh backup → researcher states frame + expected result → owner approves in chat → owner runs → leaves edit mode without saving → backup again. Steps: knob block (gain), block switch k = 1 then 0, 2, 3, LED colour, preset select. Records in `captures/private/`, sanitized excerpts in `captures/fw96/`, regression fixtures, "Write messages" rows → `observed`; ACK row → `observed` | US4, US2, US3 | Every step: ACK received, re-read shows the value, post-gate backup == pre-gate backup (SC-004). Any NAK/unexpected result stops the session and is documented |
| M3 | Gate session B: confirmations | Independent session (new connection, other preset): repeat knob block and preset select (and any other write the owner approves). Promote to `confirmed`; confirmed messages no longer need `--experimental`. Firmware gate records fw 96 as covered | US4 | SC-005: knob block + preset select `confirmed`, all others ≥ `observed`; each promoted row cites two sessions |
| M4 | Release 0.3.0 | README usage (backup, set, select, safety notes), CHANGELOG (new commands, exit 8, `0x22` allowlist), byte map rows 18–20 named `led_red/green/blue` if M2 observed them (additive), quickstart run, SC review | all | Quickstart passes end to end on hardware; SC-001…SC-007 checked |

## Project Structure

### Documentation (this feature)

```text
specs/003-preset-backup-edit-writes/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   ├── cli.md                    # `preset backup`, `set`, `preset select`, exit 8
│   ├── library-api.md            # StorageRead, WriteTarget, TankG.backup/set_field/select_preset
│   ├── backup.schema.json        # backup file / `preset backup --json`
│   └── write-result.schema.json  # `set --json` / `preset select --json`
├── checklists/requirements.md
└── tasks.md             # Phase 2 output (/speckit-tasks — not created here)
```

### Source Code (repository root)

```text
specs/protocol/command-layer.md     # + "Write messages" table (R4), storage evidence, gate results

captures/fw96/
├── 20261117-storage-synthetic.jsonl   # synthetic image + public presets (M0)
└── <date>-gate-<step>.jsonl           # sanitized gate excerpts (M2/M3)

src/openvave/
├── models.py            # + StorageRead, Backup, StoredPreset, WriteTarget, WritePlan, WriteResult
├── errors.py            # + WriteRefusedError (1), WriteNakError (7), WriteNotAppliedError (8)
├── protocol/
│   ├── frame.py         # WRITE = 0x22 encodable only via commands.build_write
│   ├── commands.py      # + build_storage_read, parse_storage_reply, build_write, parse_write_reply
│   ├── storage.py       # NEW: layout constants (offset 2, 21 B × 36, header a5 5a), positions
│   └── writes.py        # NEW: WRITE_MESSAGES table (pure data), target allowlist, knob-block rebuild
├── backup.py            # NEW: Backup ↔ JSON document (no I/O beyond the caller's file handle)
├── session.py           # + backup(), plan_set/set_field, plan_select/select_preset
├── transport/fake.py    # + scripted write replies (ACK/NAK) and buffer state for verify tests
└── cli/
    ├── __init__.py      # + `preset backup`, `set`, `preset select`
    ├── render.py        # backup summary, write plan/result lines, JSON
    └── files.py         # NEW: atomic backup file write, no-overwrite rule

tests/
├── support/audit.py         # 0x22 allowed only to allowlisted targets; 0x21 never
├── support/writes_doc.py    # parse the "Write messages" table
├── unit/                    # test_storage.py, test_writes.py, test_write_reply.py, test_backup_doc.py, test_writes_doc.py
├── integration/             # test_backup_session.py, test_set_field.py, test_select_preset.py
├── contract/                # test_cli_backup.py, test_cli_set.py, test_cli_select.py (schemas)
└── hardware/                # test_hw_backup.py (opt-in); write tests need OPENVAVE_HW_WRITES=1
```

**Structure Decision**: same single package. Storage layout and write allowlist are pure data in
`protocol/` (reusable without I/O, Constitution V/VII). All writes go through one session method
so the safety checks cannot be skipped by a new command. File handling stays in the CLI.

## Complexity Tracking

No constitution violations and no new dependencies.

| Addition | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| `0x22` encodable (001 had only `0x11`/`0x23`) | The spec's purpose: first writes | — (required); limited to a closed target allowlist so the risk surface stays enumerable |
| Doc↔code test for the "Write messages" table | Confidence gates sending (FR-014); it must not drift from the docs | Hard-coding confidence in code lets a doc promotion and the code disagree silently |
| `ReadTarget` value shared by `Region` and `StorageRead` | Storage reads need 38 address/length pairs; the parser must stay shared | Adding 38 enum members bloats `Region` and its JSON; a raw address API breaks the closed-set rule |
| New exit code 8 | Spec distinguishes "ACK but not applied" from NAK/protocol error (US2 scenario 7) | Reusing 7 hides whether the pedal rejected the frame or silently ignored it |
