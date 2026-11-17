# Implementation Plan: Remote editing in normal mode, save, restore, bypass and loopback

**Branch**: `004-remote-edit-save-restore` | **Date**: 2026-11-17 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/004-remote-edit-save-restore/spec.md`

## Summary

Five additions to the 0.3.0 client, in order of risk. (1) **Remote editing without edit mode**:
one pure pedal-state classifier (normal, edit, tuner, bypass, unrecognised) replaces the
"edit mode only" guard; `set` works in normal mode, takes reverb decay as colour section and
position, and `preset reload` discards unsaved edits. (2) **Bypass** on/off and correct reporting
of a bypassed pedal by `info`, `preset dump` and `watch`. (3) **Save**: the first persistent
write, a fixed sequence (slot write, 300 ms, commit, 100 ms, select) run by one sequence runner
that requires `unsafe=True`, takes a full backup first, checks every ACK and reads the slot back.
(4) **Restore** one slot (same sequence) or all 36 (one 758-byte image write, commit, select) from
an openvave backup file. (5) **Loopback** on/off, experimental. The closed `WriteTarget` allowlist
grows by five kinds, three of them marked persistent; erase, the global block and the whole edit
buffer stay unencodable. Gate sessions make openvave's own first sends and promote the rows.
Decisions: [research.md](research.md).

## Technical Context

**Language/Version**: Python ≥ 3.11 (unchanged)

**Primary Dependencies**: `bleak` ≥ 0.22 (runtime, unchanged). No new runtime or dev dependency

**Storage**: backup files (003 format, `format_version` 1) are now also the input of restore;
automatic backups are written as `tankg-backup-<ts>-before-<save|restore>.json` in `--backup-dir`
(default: current directory). Gate records in `captures/private/`, sanitised excerpts in
`captures/fw96/` (no stored image, FR-037)

**Testing**: `pytest` (+ `pytest-asyncio`, `jsonschema`), hardware-free by default against
`FakeTransport`, which gains: a stored area that slot/image writes modify, a commit flag, bypass
state, the loopback byte, reassembly of chunked requests, and scripted failures per step (NAK, no
reply, link drop). Replay tests use the committed check 1–4 captures. Hardware write tests need
`--hardware` + `OPENVAVE_HW_WRITES=1`; persistent ones also `OPENVAVE_HW_UNSAFE=1` (R16)

**Target Platform**: macOS (hardware-verified); Linux/Windows best-effort (unchanged)

**Project Type**: library + CLI (single Python package)

**Performance Goals**: remote edit < 5 s including scan and connect (SC-001); save ≈ backup
(2–4 s) + 3 writes + 0.4 s of waits + verification ≈ 4–6 s; full restore ≈ two full reads + the
image write ≈ 6–10 s

**Constraints**: one request in flight; command bytes `0x11`, `0x23`, `0x22` only; `0x22` only to
the nine allowlisted target kinds; persistent targets only from the sequence runner, only with
`unsafe` and after the backup callback returned (R5, R9); no retries; no write to the global
block; a request longer than `ATT MTU − 3` is split by the transport (R11, hypothesis until gated)

**Scale/Scope**: 5 new write message kinds (bypass, loopback, stored slot, commit, stored image);
5 new CLI commands (`preset reload`, `bypass`, `preset save`, `preset restore`, `loopback`), 1
changed (`set`), 3 read commands gain a state line; 36 presets × 21 B, image 758 B

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Pre-research evaluation (2026-11-17):

- [x] **I. Protocol docs**: the five new messages are already in the address map; this feature
  adds their rows to the "Write messages" table (mirrored by `WRITE_MESSAGES`, doc↔code test),
  documents request chunking, the pedal-state rules and the section input, and updates
  `app-features.md` with every gate result, in the same PR as the code.
- [x] **II. Evidence**: rows start at `hypothesis` for openvave's own sends (R7) and cite the
  script-sent check captures in Notes; each promotion cites a committed gate excerpt, fw 96.
- [x] **III. Capture-driven tests**: replay tests from the committed check captures are written
  first and fail before the code exists; the suite stays hardware-free; any gate surprise becomes
  a regression fixture.
- [x] **IV. Device safety**: every write is a named action with dry run. Persistent writes need
  `--unsafe`, show what will be overwritten, and are always preceded by a verified backup (R9).
  `hypothesis` and `observed` messages need `--experimental` (R6). Erase, factory reset and
  firmware update are not encodable. The riskiest unknown (a 773-byte request) is first sent as a
  byte-identical no-op (R11).
- [x] **V. Library-first/CLI**: state classification, targets and section maths are pure
  `protocol/` code; sequences live in `TankG`; the CLI adds flags, file handling (via the
  `on_backup` callback) and rendering; human + JSON output for every command.
- [x] **VI. Clean-room**: restore only takes the user's own backup file; no preset content is
  shipped; gate excerpts of a full restore carry the synthetic image (R16).
- [x] **VII. Simplicity**: no new dependency. One sequence runner serves save, restore-slot and
  restore-all; bypass off and reload reuse the select path. Request chunking is the only
  transport change and sits behind the existing interface.

Result: **PASS**.

Post-design re-evaluation (after Phase 1, 2026-11-17): **PASS**. The data model keeps the write
surface closed (constructors only, `persistent` derived from the kind) and adds no exit code. JSON
stays `schema_version` 2 (one added key, one new schema for sequences); the backup format is
unchanged. One 003 guarantee is deliberately replaced: "no method sends the commit or a
stored-area write" becomes "only `save_preset` and `restore`, only with `unsafe=True`, only after
the backup" (FR-038), and the command audit enforces the new wording.

## Gate rules (apply to M3 and M4, and to any write in an earlier gate)

- The owner runs every pedal step in their own terminal; the assistant's session has no Bluetooth.
- A message openvave has not sent before is sent only after the owner approves **that exact frame**
  in chat; the approval is quoted in the gate record.
- `openvave preset backup` before the first step and after every step.
- Any NAK, lost connection or failed verification stops the session: no retry, backup, report.
- Never sent: erase (`0x21`), factory images, firmware update, global-block writes.
- Throwaway helpers go in `poc/` (git-ignored).

## Delivery Plan

Projected PR count: **6** (≤ 8, no re-scoping needed). M0–M2 are code milestones whose hardware
gates use only confirmed messages or dry runs. M3 and M4 are evidence milestones with
owner-approved writes; every new message's first send by openvave happens in M3.

| # | Milestone | Scope | Stories | Verification gate |
|---|---|---|---|---|
| M0 | Pedal state, remote edit, reload | `protocol/state.py` (`classify`), `TankG.state()` with bypass confirmation; `set` in normal and edit mode with the new refusal reasons; `SECTION_FIELDS`, `section_raw`, CLI section input; `preset reload`; `pedal_state` in `info` / `preset dump` / `watch` (human + JSON), bypass and loading reporting; replay tests from `gate-normal_knob_gain*` and `check2-bypass`; docs: state rules, section input, `set` no longer refuses normal mode | US1, US2 (reporting) | Suite green; audit unchanged (no new target). **Hardware (confirmed messages only)**: quickstart §2: backup, `set gain 90`, `set reverb_decay orange 10`, `preset reload`, backup identical (SC-001, SC-002). Read-only section check of MOD FX / DLY Mix against the app |
| M1 | Bypass and loopback (offline) | `WriteTarget.bypass(i)`, `.loopback()`; rows in the doc table and `WRITE_MESSAGES` (`hypothesis`); `bypass_on` / `bypass_off` / `set_loopback`; CLI `bypass on|off`, `loopback on|off`; `FakeTransport` bypass state and loopback byte; audit allows the two kinds | US2, US5 | Fake-transport tests: applied, refused per state, discard-edits rule, no change, NAK, not applied; check 2 capture replays frame for frame. **Hardware (dry run only)**: quickstart §3, first two commands |
| M2 | Save and restore (offline) | `WriteTarget.stored_slot(i)`, `.commit()`, `.stored_image()` with `persistent`; rows (`hypothesis`); `SequencePlan` / `SequenceResult`; the sequence runner (`unsafe`, `on_backup`, ACK per step, slot read-back before commit, waits, verification, step report on failure); `plan_save` / `save_preset`, `plan_restore` / `restore`; restore file checks; request chunking in `BleakTransport` and reassembly in `FakeTransport`; CLI `preset save`, `preset restore`, `--unsafe`, `--backup-dir`, automatic backup file; `sequence-result.schema.json`; audit: persistent frames only in save/restore tests | US3, US4 | Fake-transport tests for every path of US3/US4, including each mid-sequence failure; checks 3 and 4 captures replay frame for frame; dry-run frames equal sent frames (SC-006); no entry point sends a persistent frame without `unsafe` (SC-005). **Hardware (dry run only)**: quickstart §3, last two commands |
| M3 | Gate session A: first sends | Quickstart §4, one approved step at a time: bypass; block switch + LED colour in normal mode; loopback (with power cycle); save (changed byte, power cycle); restore slot; image write as a no-op; restore all with differences (power cycle). Optional approved observations: slot write without commit, pedal knob after a remote edit. Records private, excerpts committed, rows → `observed`; `app-features.md` and the open questions updated; MOD FX / DLY Mix sections added if M0 observed them; status byte named `loopback` if an effect was observed. If the no-op image write fails: document it, build the slot-by-slot fallback (R11) in this PR and gate that instead | US6, US2–US5 | Each step: ACKs, verification passes, backup after differs only as intended; last backup equals the first (SC-010). SC-009: all five messages ≥ `observed` |
| M4 | Gate session B: confirmations | New connection, another preset and slot: bypass, save, restore slot, restore all; block switches and LED colour if approved. Rows → `confirmed`; confirmed messages drop `--experimental` (save and restore keep `--unsafe`) | US6 | SC-009: bypass, stored slot, commit `confirmed`, each row citing two sessions; SC-003, SC-004 on hardware |
| M5 | Release 0.4.0 | README (remote editing, save, restore, bypass, safety notes), CHANGELOG (new commands, `set` in normal mode, opt-ins, the replaced 0.3.0 safety statement, FR-038), version bump, quickstart run, SC review | all | Quickstart passes end to end; SC-001…SC-011 checked |

## Project Structure

### Documentation (this feature)

```text
specs/004-remote-edit-save-restore/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   ├── cli.md                       # set (changed), preset reload, bypass, preset save/restore, loopback
│   ├── library-api.md               # state, reload, bypass, loopback, save, restore
│   └── sequence-result.schema.json  # `preset save` / `preset restore --json`
├── checklists/requirements.md
└── tasks.md             # Phase 2 output (/speckit-tasks — not created here)
```

### Source Code (repository root)

```text
specs/protocol/command-layer.md     # + 5 "Write messages" rows, pedal state rules, request chunking
specs/protocol/app-features.md      # gate results, open questions answered

captures/fw96/<date>-gate-<step>.jsonl   # openvave's own sends (M3/M4)

src/openvave/
├── models.py            # + PedalState, SequenceStep, SequencePlan, StepOutcome, SequenceResult
├── errors.py            # + refusal reasons; `.sequence` on errors raised mid-sequence
├── protocol/
│   ├── state.py         # NEW: classify(global, buffer)
│   ├── bytemap.py       # + SECTION_FIELDS, section_raw
│   └── writes.py        # + bypass, loopback, stored_slot, commit, stored_image; persistent flag; rows
├── backup.py            # + restore_problems(backup, firmware)
├── session.py           # + state(), reload_preset, bypass_on/off, set_loopback,
│                        #   plan_save/save_preset, plan_restore/restore, the sequence runner
├── transport/
│   ├── ble.py           # write(): split frames longer than MTU − 3
│   └── fake.py          # stored area, commit, bypass, loopback, chunk reassembly, scripted failures
└── cli/
    ├── __init__.py      # + preset reload, bypass, preset save, preset restore, loopback; set sections
    ├── render.py        # state line, sequence plan/result, step report, section readings
    └── files.py         # + automatic backup naming (never overwrites)

tests/
├── support/audit.py     # nine target kinds; persistent frames only where declared
├── unit/                # test_state.py, test_sections.py, test_writes.py (+ new kinds), test_restore_file.py
├── integration/         # test_set_normal_mode.py, test_bypass.py, test_loopback.py, test_save.py,
│                        # test_restore.py, test_sequence_failures.py, test_tx_chunking.py
├── contract/            # test_cli_bypass.py, test_cli_save.py, test_cli_restore.py, test_cli_loopback.py,
│                        # test_cli_reload.py, test_cli_state.py (schemas, exit codes)
└── hardware/            # gate helpers incl. the no-op image write (OPENVAVE_HW_UNSAFE=1)
```

**Structure Decision**: same single package. State classification, targets and section maths are
pure data in `protocol/`. All persistent writes go through one sequence runner in the session so
the unsafe check, the backup and the step report cannot be skipped by a new command. File
handling stays in the CLI.

## Complexity Tracking

No constitution violations and no new dependencies.

| Addition | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| Persistent targets encodable (003 had none) | The spec's purpose: save and restore | — (required); three fixed shapes, sent only by the sequence runner with `unsafe` |
| Second opt-in `--unsafe` next to `--experimental` | "stored presets change" is permanent; "message not confirmed" is temporary | One flag would either vanish once confirmed (no warning before overwriting) or stay forever (hides which messages are still unconfirmed) |
| `SequencePlan` / `SequenceResult` next to `WritePlan` / `WriteResult` | Three writes with waits and a per-step outcome | Stretching `WriteResult` to lists breaks its 0.3.0 shape and JSON schema |
| `on_backup` callback | The library must guarantee the backup exists before the first write without doing file I/O | A CLI-only backup lets a library user save with no backup; a library-written file breaks Constitution V |
| Request chunking in the BLE transport | The image write is 773 B; one Bluetooth write carries 182 B | Slot-by-slot restore avoids it and is kept as the decided fallback (R11); the owner chose the app's single write |
