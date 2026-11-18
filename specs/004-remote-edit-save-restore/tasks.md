---

description: "Task list for 004 remote editing in normal mode, save, restore, bypass and loopback"
---

# Tasks: Remote editing in normal mode, save, restore, bypass and loopback

**Input**: Design documents from `specs/004-remote-edit-save-restore/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md),
[data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: MANDATORY. Constitution III requires capture-based tests for every encoder/parser,
written first and failing before the implementation; the default suite stays hardware-free.
Every test task precedes the code it covers.

**Organization**: one milestone per PR, as in the plan's Delivery Plan. M0 delivers US1 (remote
edit in normal mode) plus the state reporting of US2 and is the MVP. M1 delivers bypass and
loopback (US2, US5) offline. M2 delivers save and restore (US3, US4) offline. M3 and M4 are
**evidence milestones** for US6: the owner approves and runs each first send. M5 is the release.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1–US6 from spec.md
- Paths are relative to the repository root (single Python package, `src/` layout)

## Global rules for every task

- **Write surface**: `0x11`, `0x23`, and `0x22` only to the `WriteTarget` allowlist: the four
  0.3.0 kinds plus, from M1, `bypass(i)` (`0xE1000000+i`×1, data `01`) and `loopback()`
  (`0xD0000000`×1, `00`/`01`), and from M2 the **persistent** kinds `stored_slot(i)`
  (`2+21·i`×21), `commit()` (`0xF0000000`×0) and `stored_image()` (`0x0`×758, starts `a5 5a`).
  No task adds erase (`0x21`), type 6, a write to the global block (`0x20000000`–`0x20000003`),
  the whole-edit-buffer write (`0x10000000`×21), `0x15`, a raw/address-based write API, or a write
  retry (FR-031, FR-032, R5). The session-wide audit (`tests/support/audit.py`) must keep passing.
- **Persistent writes** are sent only by the sequence runner, only with `unsafe=True`, only after
  `on_backup` returned (FR-013, FR-014, R9). No test, helper or command bypasses this.
- **Docs first**: every protocol fact lands in `specs/protocol/command-layer.md` (and
  `specs/protocol/app-features.md` for gate results) in the same commit as the code. "Write
  messages" rows and `WRITE_MESSAGES` change together (`tests/unit/test_writes_doc.py`).
- **No factory content in git** (Constitution VI, FR-037): fixtures use the synthetic stored
  image and presets already public in `captures/fw96/` (1B/1C bytes). Raw gate records and real
  backups stay in `captures/private/`.
- **Hardware**: every pedal step is run by the **pedal owner** in their own terminal (Bluetooth
  permission, phone app closed). Before openvave sends a message it has never sent, the researcher
  posts the exact frame and the expected result and the owner approves that frame **in chat**;
  `openvave preset backup` runs before the first step and after every step. Any NAK, lost
  connection or failed verification stops the session; nothing is retried before it is reported.
  Never sent: erase, factory images, firmware update, global-block writes.
- JSON stays `schema_version` 2 (additive only, R17). Throwaway scripts go in `poc/`.

---

## Delivery Plan

| PR | Milestone | Stories | Tasks | Gate |
|---|---|---|---|---|
| 1 | Milestone 0: Pedal state, remote edit, reload 🎯 MVP | US1, US2 (reporting) | T001–T022 | Suite green, audit unchanged; owner: `set` in normal mode applied, reload restores, backups identical (SC-001, SC-002) |
| 2 | Milestone 1: Bypass and loopback, offline | US2, US5 | T023–T039 | Fake-transport tests for every outcome; check 2 replays frame for frame; owner's dry runs send reads only |
| 3 | Milestone 2: Save and restore, offline | US3, US4 | T040–T067 | Every US3/US4 path and mid-sequence failure tested; checks 3–4 replay; dry-run frames == sent frames (SC-006); no persistent frame without `unsafe` (SC-005); owner's dry runs send reads only |
| 4 | Milestone 3: Gate session A, first sends | US6, US2–US5 | T068–T084 | Each approved step ACKed and verified; backups differ only as intended; last backup == first (SC-010); five rows ≥ `observed` (SC-009) |
| 5 | Milestone 4: Gate session B, confirmations | US6 | T085–T091 | Bypass, stored slot, commit `confirmed`, two sessions each (SC-009); SC-003, SC-004 on hardware |
| 6 | Milestone 5: Release 0.4.0 + Polish | all | T092–T100 | Quickstart passes end to end; SC-001…SC-011 reviewed |

Projected PR count: **6** (≤ 8). Milestone N+1 starts only after Milestone N's gate passes.

---

## Milestone 0: Pedal state, remote edit, reload (US1 P1, US2 reporting) 🎯 MVP

**Goal**: edit the current preset from the computer in normal mode, type reverb decay as the app
shows it, discard edits with one command, and see a bypassed pedal reported as bypass.

**Independent test criteria**:
- `classify` returns `normal`, `edit`, `tuner`, `bypass`, `unrecognised` for the byte patterns of
  data-model.md, and the bytes of `captures/fw96/20261117-check2-bypass.jsonl` classify as bypass.
- Replaying `captures/fw96/20261117-gate-normal_knob_gain.jsonl` through `set_field("gain", 90)`
  sends exactly the capture's frames and reports applied with mode still normal.
- `set reverb_decay 10 --type spring` plans raw 53; `set reverb_decay 20` on a room preset plans
  room 20 (raw 19); `set gain 10 --type room` and `set reverb_decay 3 --type hall` exit 2 without
  a write (amended from colour input, research R3 amendment).
- `set` in tuner or bypass exits 1 (`tuner_mode`, `bypassed`) with only reads in the trace.
- `preset reload` sends one select for the loaded index; with buffer = stored it sends nothing.
- `info` / `preset dump` on a bypassed fake print `state: bypass` and no decoded field lines;
  `watch` reports a one-cycle slot-`ff` state as `loading` and two cycles as `bypass`.

### Setup

- [X] T001 Confirm the branch `004-remote-edit-save-restore` contains the groundwork (`specs/protocol/app-features.md`, `captures/fw96/20261117-check*.jsonl`) and that `uv run pytest -q` is green before any change; note the baseline test count in this file
  - Baseline (2026-11-17, branch at `a6c6e6b`): **1156 passed, 5 skipped**. After T003–T020: 1254 passed, 5 skipped; `ruff check`, `ruff format --check`, `mypy` (strict) clean.
- [X] T002 [P] Add the committed check captures to the capture index in `captures/README.md` if missing (check 1–4 files, what each holds, that they were sent by `poc/` scripts)

### Tests for User Story 1 and state reporting (write first, must fail)

- [X] T003 [P] [US1] `tests/unit/test_state.py`: table-driven `classify(global, buffer)` cases for every row of the data-model state table, including slot `ff` + non-zero buffer and zero buffer + valid slot → `unrecognised`, unknown mode value, bank 9, and the check 2 capture bytes → `bypass`
- [X] T004 [P] [US1] `tests/unit/test_sections.py`: `section_raw` for the eight documented readings (blue 1 → 0 … green 40 → 127, orange 10 → 53), round trip with `reverb_decay_parts` for all 120 pairs, `ValueError` for unknown section and positions 0 and 41, `SECTION_FIELDS == {"reverb_decay"}`
- [X] T005 [P] [US1] `tests/unit/test_bytemap_doc.py`: extend so the doc's section table and `SECTION_FIELDS` agree (a field is listed iff its sections are ≥ `observed` in `specs/protocol/command-layer.md`)
- [X] T006 [P] [US1] `tests/integration/test_set_normal_mode.py`: replay `gate-normal_knob_gain.jsonl` and `gate-normal_knob_gain_b.jsonl` (frames equal, applied, mode stays 1); `set` in edit mode still works; refused in tuner, bypass and unrecognised states with only reads sent; block switch and LED colour in normal mode refused without `experimental`; section tuple `("orange", 10)` writes raw 53
- [X] T007 [P] [US1] `tests/integration/test_reload.py`: reload in normal mode sends one `preset_select(loaded)` and verifies buffer = stored; nothing sent when buffer = stored; edit mode needs `discard_edits`; refused in bypass, tuner, unrecognised
- [X] T008 [P] [US2] `tests/integration/test_state_session.py`: `TankG.state()` confirms bypass with a second read 300 ms later (injected `sleep`); a slot-`ff` first read followed by a normal second read returns the second state; `snapshot()` carries `pedal_state`
- [X] T009 [P] [US1] `tests/contract/test_cli_set.py`: add normal-mode output (`normal mode`, the "Not saved. Discard: … Keep: …" line), section input output with both readings, exit 2 for bad section input, exit 1 reasons `tuner_mode` / `bypassed`; `--json` plan has no `not_edit_mode`
- [X] T010 [P] [US1] `tests/contract/test_cli_reload.py`: `preset reload` human and `--json` output (valid against `write-result.schema.json`), `--dry-run`, `--discard-edits`, exit codes
- [X] T011 [P] [US2] `tests/contract/test_cli_state.py`: `info`, `preset dump` and `watch` show the `state:` line; in bypass no decoded field lines and `bank <n>, slot not reported`; JSON has top-level `pedal_state` and unchanged `fields`; `watch` `loading` vs `bypass`

### Implementation for User Story 1 and state reporting

- [X] T012 [US1] Add `PedalState` to `src/openvave/models.py` and `classify` in new `src/openvave/protocol/state.py`; export from `src/openvave/protocol/__init__.py` and `src/openvave/__init__.py` (T003)
- [X] T013 [P] [US1] Add `SECTION_FIELDS` and `section_raw` to `src/openvave/protocol/bytemap.py` and export them (T004, T005)
- [X] T014 [US1] `src/openvave/session.py`: `TankG.state()` (global + buffer, bypass confirmation, injectable `sleep`); `snapshot()` fills `pedal_state` (T008)
- [X] T015 [US1] `src/openvave/session.py` + `src/openvave/errors.py`: `plan_set` uses the state (allowed `normal`, `edit`; reasons `tuner_mode`, `bypassed`, `unrecognised_state`), accepts a `(section, position)` value for `SECTION_FIELDS`, refusal messages updated; `not_edit_mode` no longer raised (T006)
- [X] T016 [US1] `src/openvave/session.py`: `reload_preset(discard_edits=False, experimental=False)` on top of the select path, with the "nothing to discard" case (T007)
- [X] T017 [US1] `src/openvave/cli/__init__.py`: `set <field> <value> [<position>]` parsing, `preset reload` subcommand, usage errors for section input (T009, T010)
- [X] T018 [US1] `src/openvave/cli/render.py`: mode name in the `set` header, section readings in before/after, the discard/keep hint, reload output (T009, T010)
- [X] T019 [US2] `src/openvave/cli/render.py`, `src/openvave/cli/watch.py`, `src/openvave/_jsonform.py`: `state:` line, bypass rendering, `pedal_state` in JSON, `loading` vs `bypass` in `watch` (T011)
- [X] T020 [US1] Docs in the same commits: `specs/protocol/command-layer.md` (pedal-state rules, section input, "openvave 0.3.0 still refuses" sentence replaced), `specs/protocol/app-features.md` (edit-mode section), `README.md` usage of `set` in normal mode and `preset reload`, `CHANGELOG.md` [Unreleased]
  - Deviations, deliberate: (1) the "Not saved" line prints only `Discard: openvave preset reload` (edit mode: `--discard-edits`); `Keep: openvave preset save --unsafe` is added in M2 when `preset save` exists. (2) A reload refused in bypass points to `preset select <position>` until M1 adds `bypass off`. (3) `specs/004-remote-edit-save-restore/contracts/write-result.schema.json` (extended copy, planned for T036) was needed now for `preset reload` and the new refusal reasons. (4) `preset dump` now also reads the global block. (5) `watch --json` carries `pedal_state` on start/change events only; the schema has no event for the unchanged-bytes `loading` → `bypass` confirmation, which only the human output reports.

### Live verification (milestone gate)

- [X] T020a [US1] Rework after the owner's review during the gate (2026-11-17): reverb decay types named as in the Tank-G manual (room, spring, cloud; off between types) instead of the app's colours; `set reverb_decay <1-40> [--type T | --raw]`, bare position keeps the current type (`type_required` in an off zone); `TYPED_FIELDS`, `type_raw`, `type_parts`, `REVERB_TYPES`, `type_reading`; spec FR-003/FR-004, research R3 amendment, contracts, command-layer.md (manual source cited), README, CHANGELOG. Tests first (`tests/unit/test_types.py`, `test_cli_set.py`, `test_set_normal_mode.py`)
- [X] T021 [US1] Owner runs quickstart §2 on hardware (knob block is confirmed, no new message): backup, `set gain 90`, `set reverb_decay orange 10`, `preset reload`, backup; researcher compares the two backups (SC-002) and records times (SC-001) and outputs under this task
  - Run 2026-11-17 19:59–20:14 UTC, fw 96, owner's Mac, pedal on **1A** in normal mode, phone app closed. Only confirmed messages sent (knob block, preset select).
  - `preset backup --output /tmp/q-before.json`: 36 presets, header `a5 5a`, cross-check OK.
  - `set gain 90`: `Set gain 65 → 90   (current preset 1A, normal mode)`, knob block with only byte 6 changed, ACK, `after  [6] gain 90   applied`, mode stayed normal.
  - `set reverb_decay orange 10` (before T020a): `reverb_decay is already 53 (orange 10); nothing sent` (no-change path; 1A is stored at 53).
  - `preset reload`: `Reload 1A (index 0)   discards unsaved edits`, select `… e0 01 00 00 01 19`, ACK, `now    bank 1, slot A   buffer = stored 1A   applied`.
  - After T020a: `set reverb_decay 1 --type cloud`: `Set reverb_decay 53 (spring 10) → 88 (cloud 1)   (current preset 1A, normal mode)`, only byte 15 changed (`35` → `58`; gain back at `41` confirms the first reload), ACK, `applied`. `preset reload` again: applied, buffer = stored 1A.
  - `preset backup --output /tmp/q-after.json`: identical to `/tmp/q-before.json` in every key except `created_at` (36 presets, image, header) → **SC-002 passed**.
  - SC-001 (< 5 s per remote edit, scan and connect included): `time uv run openvave set gain 90` → applied, **10.98 s total** (0.24 s user, 0.13 s system): **failed**. Cause: the scan always waited the whole 5 s `--scan-timeout`.
- [X] T021a [US1] Gate fix for SC-001 (owner's choice, research R3b): `src/openvave/transport/ble.py` `_scan` stops 1 s (`SCAN_GRACE`) after the first `TANK-Gv2_BLE` or at once on `--device`; `discover()` unchanged. Tests first: `tests/unit/test_scan.py`. Docs: research R3b, 001 research R8 note, README options, CHANGELOG. Re-timed on hardware (below)
  - Re-timing after T021a (owner's Mac, 1A, normal mode): `time uv run openvave set gain 90` → applied in **2.54 s** total → **SC-001 passed**. Other runs: 4.76 s (refused, bypassed), 6.34 s (no change), 10.35 s (applied). Phase breakdown, read-only (`poc/time_phases.py`, six rounds): scan 1.3–2.3 s (pedal heard + 1 s grace), connect + settle + handshake 0.75–1.05 s, two reads 0.12 s, disconnect ≈ 0 s. `poc/time_cli.py` (real `info` in-process): `main()` returned at 3.67 s of a 3.73 s total, so no delay at exit. `uv` start-up 0.23 s warm (1.0 s cold). The slow runs are attributed to late advertising right after the previous connection (the scan varies most); `--scan-timeout` bounds it.
  - Bypass seen on hardware during the gate (pedal bypassed on the pedal after a reload): `info` printed `state: bypass (all blocks off; the pedal does not report the loaded slot)` and `bank 1, slot not reported`, global `00 00 ff 01` (= check 2); `set gain 90` and `preset reload` refused with `bypassed`, reads only; `preset select 1A` left bypass, verified (header showed `from ?`; fixed after the gate: `from bypass (bank 1)`, test in `tests/contract/test_cli_select.py`).
- [X] T022 [US1] Owner runs the read-only section check of quickstart §2 for MOD FX (byte 11) and DLY Mix (byte 13); researcher records the readings in `specs/protocol/command-layer.md` as observed or refuted (R3) and transcribes them to `captures/fw96/<date>-sections-app.jsonl` like the reverb readings
  - Run 2026-11-17, fw 96, preset 1A in normal mode, app colours mapped to the manual's types in knob order. MOD FX (byte 11): blue 1 → 0, blue 40 → 39, blue X → 41, orange 1 → 44, orange 40 → 83, orange X → 84, green 1 → 88, green 40 → 127. DLY MIX (byte 13): blue 40 → 39, blue X → 41, orange 1 → 44, orange 40 → 83, orange X → 87, green 1 → 88, green 40 → 127 (blue 1 not read). **All 15 fit** `raw // 44`, positions 1–40, off zones 40–43 / 84–87 → both splits `observed`. Moving MOD FX in the app did not switch the MOD block on. Capture `captures/fw96/20261117-knob-types-app.jsonl` (`tests/support/knob_types_fixture.py`). The owner touched noise gate and DLY MIX by hand at the MOD FX blue X step (ignored). `preset reload` afterwards: applied.
  - Pulled forward from T083 at the owner's request: `mod_fx` (chorus, phaser, tremolo) and `delay_mix` (analog, tape, dual) added to `TYPED_FIELDS` and the doc's knob-type table as `observed`, so `set mod_fx 20 --type phaser` and the `type:` readings work now. Tests: `tests/unit/test_types.py`, `test_render_type_reading.py`, `test_cli_preset_dump.py`.

**Checkpoint**: Milestone 0 DONE — remote editing works without edit mode and nothing new has been sent to the pedal ✅ (2026-11-17: T021 SC-001 2.54 s and SC-002 identical backups; T022 15/15 readings fit)

---

## Milestone 1: Bypass and loopback, offline (US2 P2, US5 P5)

**Goal**: `bypass on|off` and `loopback on|off` exist, are fully tested offline and are refused
without `--experimental`; nothing new is sent to the pedal yet.

**Independent test criteria**:
- `WriteTarget.bypass(1)` builds `00 59 22 09 00 00 04 01 00 00 e1 01 00 00 01 17`;
  `WriteTarget.loopback()` with `00` builds `00 59 22 09 00 00 04 00 00 00 d0 01 00 00 00 2a`;
  `bypass(36)`, bypass data `00` and loopback data `02` are rejected.
- Replaying `captures/fw96/20261117-check2-bypass.jsonl`: `bypass_on` then `bypass_off(1)` send
  the capture's writes and both verify.
- `bypass on` with unsaved edits is refused without `--discard-edits`; `bypass off` without a
  position exits 2; `bypass off 1B` on a pedal that is not bypassed exits 1 (`not_bypassed`).
- Both commands exit 1 (`experimental_required`) without `--experimental` while their rows are
  `hypothesis`.

### Tests for User Stories 2 and 5 (write first, must fail)

- [X] T023 [P] [US2] `tests/unit/test_writes.py`: `bypass(i)` and `loopback()` shapes, data rules, argument range, `persistent is False`, `allowed_write_body` accepts exactly these and still rejects `0xE1000000+36`, `0xD0000000`×2 and `0xD0000000` type 5
- [X] T024 [P] [US2] `tests/unit/test_writes_doc.py` + `tests/support/writes_doc.py`: the doc table has `bypass(i)` and `loopback` rows, `hypothesis`, mirrored by `WRITE_MESSAGES`
- [X] T025 [P] [US2] `tests/unit/test_fake_transport.py`: fake pedal enters bypass on the bypass write (global slot `ff`, buffer zeros), leaves it on select, and stores the loopback byte
- [X] T026 [P] [US2] `tests/integration/test_bypass.py`: check 2 replay; applied; refused per state table; `edits_would_be_discarded`; already bypassed → no change; `bypass_off` only in bypass; NAK → `WriteNakError`; ACK but not bypassed → `WriteNotAppliedError`; result carries the return index
- [X] T027 [P] [US5] `tests/integration/test_loopback.py`: read, one write, ACK, re-read; no change when equal; refused without `experimental` and in `unrecognised`; never followed by a commit frame; NAK and not-applied paths
- [X] T028 [P] [US2] `tests/contract/test_cli_bypass.py`: human and `--json` output of `bypass on` / `bypass off <pos>`, the "Leave bypass: openvave bypass off 1B" line, `--dry-run`, exit 2 for a missing position (message names the reported bank), exit codes 1/7/8
- [X] T029 [P] [US5] `tests/contract/test_cli_loopback.py`: `loopback on|off` output, `--dry-run`, no-change line, refusal without `--experimental`
- [X] T030 [P] [US2] `tests/support/audit.py` + `tests/unit/test_audit.py`: the audit accepts the two new kinds and nothing else new

### Implementation for User Stories 2 and 5

- [X] T031 [US2] `src/openvave/protocol/writes.py`: `WriteTarget.bypass(i)`, `.loopback()`, data rules in `check_write_data`, `_SHAPES`, `WriteTarget.persistent`, two `WRITE_MESSAGES` rows (`hypothesis`, check 2 in Notes) (T023, T024)
- [X] T032 [US2] `specs/protocol/command-layer.md`: the two "Write messages" rows and the allowlist sentence, in the same commit as T031
- [X] T033 [US2] `src/openvave/transport/fake.py`: bypass state and loopback byte (T025)
- [X] T034 [US2] `src/openvave/session.py`: `bypass_on(discard_edits, experimental)` and `bypass_off(index, experimental)` (select path, only in bypass); `WriteResult` gains an optional `return_index` in `src/openvave/models.py` (T026)
- [X] T035 [US5] `src/openvave/session.py`: `set_loopback(on, experimental)` (T027)
- [X] T036 [US2] `src/openvave/cli/__init__.py` + `src/openvave/cli/render.py`: `bypass on|off`, `loopback on|off` commands and output; `write-result.schema.json` consumers accept the new `command` and `target.kind` values (add them to `specs/004-remote-edit-save-restore/contracts/` as an extended copy if the 003 schema's enums reject them) (T028, T029)
- [X] T037 [US2] `tests/support/audit.py`: allow the two kinds (T030); `tests/contract/test_public_api.py` lists the new exports
- [X] T038 [US2] `README.md` and `CHANGELOG.md` [Unreleased]: bypass and loopback commands, both experimental
  - Done 2026-11-18. Suite **1418 passed, 5 skipped** (M0 end: 1254 + gate fixes); `ruff check`,
    `ruff format --check`, `mypy` (strict) clean. Decisions: (1) `bypass off` sends the confirmed
    preset select, so it needs no `--experimental`; only `bypass on` and `loopback` do. (2)
    `bypass on` in edit mode is refused as `edit_mode`, `bypass off` outside bypass as
    `not_bypassed` (normal) / `edit_mode` / `tuner_mode` / `unrecognised_state`. (3) Public plan
    methods `plan_bypass_on`, `plan_bypass_off`, `plan_loopback` (dry run and library), as for
    `set` / `select` / `reload`. (4) A loopback plan's `before` and result's `after` are the status
    byte; JSON change region `status`. (5) M0 deviation (2) closed: the `bypassed` refusal now
    points to `bypass off <position>`. (6) `bypass off` without a position connects, reads the
    state, then exits 2 naming the reported bank (`e.g. openvave bypass off 3A … 3D`).

### Live verification (milestone gate)

- [X] T039 [US2] Owner runs the first two commands of quickstart §3 with `--trace` (`bypass on --dry-run --experimental`, `loopback off --dry-run --experimental`); researcher checks the trace holds reads only and the printed frames equal the frames of the Independent test criteria; outputs recorded under this task
  - Offline rehearsal 2026-11-18 (fake pedal on 1B, normal mode, status `01`; not hardware): both
    exit 0, `dry run: nothing sent`, trace holds only `0x11` and `0x23` frames. Printed frames:
    `00 59 22 09 00 00 04 01 00 00 e1 01 00 00 01 17` (bypass 1B) and
    `00 59 22 09 00 00 04 00 00 00 d0 01 00 00 00 2a` (loopback off), equal to the Independent test
    criteria. Superseded by the hardware run below.
  - Hardware run 2026-11-18 ~13:05 UTC, fw 96, owner's Mac (Terminal panel; the owner allowed the
    researcher to run commands). Raw output: `captures/private/20261118-t039-phase{1,2}.log`.
    12 connections, 57 frames sent: 12 × `0x11`, 44 × `0x23`, **one** `0x22`, the confirmed
    `preset_select(0)`. No bypass or loopback frame was sent.
  - Phase 1, pedal found **bypassed** (global `00 00 ff 01`, buffer 21 × `00`, left over from an
    earlier session): `bypass on --dry-run --experimental` → `already bypassed; nothing sent`, exit 0
    (bypass confirmed by the second read); `loopback off --dry-run --experimental` → frame
    `… d0 01 00 00 00 2a`, `dry run: nothing sent`; `bypass off` (no position) → exit 2, `it reports
    bank 1; e.g. openvave bypass off 1A … 1D`; `bypass off 1A --dry-run` → select frame
    `… e0 01 00 00 01 19`.
  - `bypass off 1A` (real, confirmed select): ACK, `now bank 1, slot A   buffer = stored 1A
    applied`; first global re-read already `00 00 00 01` (no `ff` transient). First hardware run of
    the `bypass_off` path. `preset dump`: `state: normal, preset 1A`.
  - Phase 2, normal mode on 1A: `bypass on --dry-run --experimental` → `Bypass on   (was 1A, normal
    mode)`, frame `00 59 22 09 00 00 04 00 00 00 e1 01 00 00 01 18` (= `build_write(bypass(0))`; the
    criteria frame `… 01 17` is index 1, 1B); without `--experimental` the dry run prints
    `refused: experimental_required (bypass is 'hypothesis'; …)` and the real run exits 1, reads
    only. `loopback off --dry-run --experimental` → `Loopback on → off`, frame `… d0 01 00 00 00 2a`
    (status read `01`); `loopback off` without `--experimental` → exit 1; `loopback on --dry-run
    --experimental` → `loopback is already on; nothing sent`; `bypass off 1A` in normal mode → exit 1
    `not_bypassed`, reads only; `bypass on --dry-run --experimental --json` → `plan.target`
    `bypass` `0xe1000000`, `confidence` `hypothesis`, `refusal` null, `dry_run` true.
  - Pedal left on 1A, normal mode, buffer = stored 1A, status `01`.

**Checkpoint**: Milestone 1 DONE — bypass and loopback are implemented and tested; neither has been sent by openvave ✅ (2026-11-18: suite 1418 passed; T039 on hardware, 12 connections, only reads plus one confirmed select)

---

## Milestone 2: Save and restore, offline (US3 P3, US4 P4)

**Goal**: `preset save` and `preset restore` exist behind `--unsafe`, always back up first, report
every step, and are fully tested offline; no persistent write is sent to the pedal yet.

**Independent test criteria**:
- Replaying `captures/fw96/20261117-check4-real_save.jsonl`: `save_preset(to=2, unsafe=True,
  experimental=True, on_backup=…)` sends the capture's three writes in order with the 0.3 s and
  0.1 s waits, and verifies. `check3-noop_save` state → "nothing to save", nothing sent.
- No call path sends `stored_slot`, `commit` or `stored_image` with `unsafe=False`, with
  `on_backup` raising, or when the backup cross-check fails (the trace holds reads only).
- Each failure point (NAK on slot / commit / select, link drop after each write, slot read-back
  mismatch before the commit, final verification mismatch) raises the documented error with a
  `SequenceResult` whose steps and `stored_may_have_changed` match the contract table.
- Restore: a synthetic backup with three changed slots restores via one image write + commit +
  select and the fake's image equals the file; an identical backup sends nothing; an invalid
  file exits 2 before connecting.
- A 773-byte frame goes out as 5 chunks of ≤ 182 bytes at MTU 185, and `FakeTransport`
  reassembles them into one request.
- For every command, the frames printed by `--dry-run` equal the frames sent by the real run.

### Tests for User Stories 3 and 4 (write first, must fail)

- [X] T040 [P] [US3] `tests/unit/test_writes.py`: `stored_slot(i)` (address `2+21·i`, 21 B), `commit()` (0 B, frame `00 59 22 08 00 00 04 00 00 00 f0 00 00 00 0b`), `stored_image()` (758 B, must start `a5 5a`), `persistent is True`; rejected: slot 36, address 3, 20 or 22 bytes, commit with data, image of 757 bytes, image with another header, `0x10000000`×21, `0x20000003`×1
- [X] T041 [P] [US3] `tests/unit/test_writes_doc.py`: rows `stored_slot(i)`, `commit`, `stored_image` present, `hypothesis`, mirrored
- [X] T042 [P] [US3] `tests/unit/test_fake_transport.py`: slot and image writes change the fake's stored area, the commit sets a flag, select loads from the stored area; scripted failures per step (NAK, no reply, link drop)
- [X] T043 [P] [US4] `tests/integration/test_tx_chunking.py`: `BleakTransport` chunking logic (pure helper `split_frame(frame, mtu)`: 773 B → 182×4 + 45; ≤ limit → one chunk; order kept) and `FakeTransport` reassembly of a chunked request by the length field
- [X] T044 [P] [US3] `tests/integration/test_save.py`: check 4 replay (run 1 and the restore of run 2); `--to` another slot leaves the loaded slot unchanged and ends on the target; no change; refused in edit, tuner, bypass, unrecognised; `unsafe_required`; `experimental_required` names both opt-ins when both are missing; `on_backup` called once with a valid `Backup` before the first write; `on_backup` raising or a backup mismatch → no write
- [X] T045 [P] [US3] `tests/integration/test_sequence_failures.py`: every failure point of the Independent test criteria, asserting error class, exit-code mapping, `steps` statuses, `stored_may_have_changed`, and that no frame follows the failure (no retry)
- [X] T046 [P] [US4] `tests/unit/test_restore_file.py`: `restore_problems` for wrong `format_version`, 35 presets, a 20-byte preset, image ≠ header + presets, header `00 00`, firmware mismatch; a valid synthetic backup has none
- [X] T047 [P] [US4] `tests/integration/test_restore.py`: restore one slot (save sequence with file bytes, verified); restore all (image write, commit, select of the previously loaded preset, full read-back equals the file); nothing sent when equal; `changed_slots` listed; `discard_edits` rule; `firmware_mismatch` needs `experimental`; verification mismatch → `WriteNotAppliedError` with `mismatched_slots`
- [X] T048 [P] [US3] `tests/contract/test_cli_save.py`: human output (UNSAFE header, diff, "Backup saved", power-loss warning, step lines, verify line), `--json` valid against `contracts/sequence-result.schema.json`, `--dry-run` writes no backup file, `--backup-dir`, automatic backup never overwrites (numeric suffix), exit 1 without `--unsafe`, failure report text and exit codes 6/7/8
- [X] T049 [P] [US4] `tests/contract/test_cli_restore.py`: `--slot` / `--all` (exactly one, else exit 2), invalid file exit 2 before any connection, differ list, nothing-to-restore line, `--json`, dry run prints the full image frame
- [X] T050 [P] [US3] `tests/support/audit.py` + `tests/unit/test_audit.py`: persistent frames are allowed only in tests that declare them (marker or fixture), never elsewhere; SC-005 test enumerating every public `TankG` method and CLI command with `unsafe` absent
- [X] T051 [P] [US3] `tests/integration/test_dry_run_frames.py`: for `set`, `preset reload`, `bypass on/off`, `loopback`, `preset save`, `preset restore --slot/--all`, the plan's frames equal the frames the fake receives in the real run (SC-006)

### Implementation for User Stories 3 and 4

- [X] T052 [US3] `src/openvave/protocol/writes.py`: the three persistent constructors, data rules, `_SHAPES`, three `WRITE_MESSAGES` rows (`hypothesis`, checks 3–4 in Notes) (T040, T041)
- [X] T053 [US3] `specs/protocol/command-layer.md`: the three rows, the persistent-target rule, request chunking (hypothesis), in the same commit as T052
- [X] T054 [US3] `src/openvave/models.py`: `SequenceStep`, `SequencePlan`, `StepOutcome`, `SequenceResult`; `src/openvave/errors.py`: new refusal reasons and `.sequence` on errors raised mid-sequence
- [X] T055 [US3] `src/openvave/transport/fake.py`: writable stored area, commit flag, scripted step failures, chunked-request reassembly (T042, T043)
- [X] T056 [US4] `src/openvave/transport/ble.py`: `split_frame` and chunked `write()` using the negotiated MTU (T043)
- [X] T057 [US3] `src/openvave/session.py`: the sequence runner (opt-in checks, backup + `on_backup`, per-step ACK, slot read-back before the commit, injectable waits, select verification, final read-back, step report on every failure, no retry) (T044, T045)
- [X] T058 [US3] `src/openvave/session.py`: `plan_save(to)` / `save_preset(to, unsafe, experimental, on_backup)` (T044)
- [X] T059 [US4] `src/openvave/backup.py`: `restore_problems(backup, firmware)` (T046)
- [X] T060 [US4] `src/openvave/session.py`: `plan_restore(backup, slot|all)` / `restore(...)` with full read-back verification (T047)
- [X] T061 [US3] `src/openvave/cli/files.py`: automatic backup naming `tankg-backup-<ts>-before-<action>.json`, `--backup-dir`, never overwrite (T048)
- [X] T062 [US3] `src/openvave/cli/__init__.py` + `src/openvave/cli/render.py`: `preset save [--to]`, `--unsafe`, plan/diff/warning/step rendering, failure report with recovery commands, `--json` (T048)
- [X] T063 [US4] `src/openvave/cli/__init__.py` + `src/openvave/cli/render.py`: `preset restore <file> (--slot|--all)`, file loading and validation before connecting, differ list (T049)
- [X] T064 [US3] `tests/support/audit.py` (T050), `tests/contract/test_public_api.py` (new exports), `tests/hardware/test_hw_writes.py`: persistent hardware helpers require `--hardware`, `OPENVAVE_HW_WRITES=1` and `OPENVAVE_HW_UNSAFE=1`, including the no-op image write helper (reads the image, writes the same bytes through the sequence runner, logs every frame to `captures/private/`)
- [X] T065 [US3] `README.md` (save, restore, the two opt-ins, the backup rule, the short mute, power-loss warning) and `CHANGELOG.md` [Unreleased]; replace the 0.3.0 "never saves or overwrites a stored preset" statement wherever it appears, including `tests/contract/test_changelog_030.py` expectations if they pin current-behaviour text (FR-038)

  - Done 2026-11-18. Suite **1612 passed, 6 skipped** (M1 end: 1418); `ruff check`, `ruff format
    --check`, `mypy` (strict) clean; the session audit saw no persistent frame outside tests marked
    `persistent_writes`. Red first: 5 modules failed to import, 64 failed, 32 errors before T052.
    Decisions: (1) the opt-in order is pedal state → nothing to change (stop, exit 0, no backup,
    opt-ins not checked, as contracts/cli.md orders it) → `edits_would_be_discarded` →
    `firmware_mismatch` → `unsafe_required` → confidence gate; with both opt-ins missing the reason
    is `unsafe_required` and the message names `--experimental` too. (2) Every restore ends with a
    select, so unsaved edits need `--discard-edits` whichever slot is written (the contract said
    "if the loaded slot is among those written"; contract updated). (3) Library: optional
    `on_plan` callback on `save_preset` / `restore`, so the CLI prints the header, diff, backup
    path and power-loss warning before the first write (FR-030) without planning twice
    (library-api.md updated). (4) `restore_problems(document, firmware)` takes the JSON document,
    since a `Backup` object cannot hold most of the checked defects; the CLI calls it with
    `firmware=None` before connecting. (5) Slot read-back right after the slot ACK, then the full
    300 ms wait; restore-all has no read-back before the commit (full backup read after the
    select). (6) The real-run image line reads `…(758 bytes)… xx   ACK   (773 bytes)` (the chunk
    count depends on the MTU); the failure report's Undo line adds `--experimental` while the
    restore messages are unconfirmed. (7) M0 deviation (1) closed: the "Not saved" line now ends
    `Keep: openvave preset save --unsafe --experimental`. (8) T064's persistent hardware helper is
    its own module, `tests/hardware/test_hw_persistent.py` (`--hardware`, `OPENVAVE_HW_WRITES=1`,
    `OPENVAVE_HW_UNSAFE=1`, marker `persistent_writes`), so the volatile gate module keeps its one
    skip condition. (9) Fake pedal: `faults={kind: nak|no_reply|disconnect|corrupt|ignore}`,
    `commits`, `on_disconnect`, reassembly of split requests; the session audit records whole
    requests. (10) T043's chunking test lives in `tests/integration/test_tx_chunking.py`; the
    SC-005 test is `tests/integration/test_unsafe_entry_points.py` (not marked, so any persistent
    frame there fails the session).

### Live verification (milestone gate)

- [X] T066 [US3] Owner runs the last two commands of quickstart §3 with `--trace` (`set gain 90`, `preset save --to 1C --dry-run --unsafe --experimental`, `preset restore <backup> --all --dry-run --unsafe --experimental`, then `preset reload`); researcher checks: only reads plus the confirmed knob-block and select writes in the trace, no backup file created by the dry runs, printed frames equal the offline tests' frames; outputs recorded under this task
  - Offline rehearsal 2026-11-18 (fake pedal on 1B, normal mode; not hardware; `poc/m2_gate_rehearsal.py`):
    `set gain 90` → knob block, ACK, applied, `Keep: openvave preset save --unsafe --experimental`;
    `preset save --to 1C --dry-run --unsafe --experimental` → reads only, no file, frames
    `… 2c 00 00 00 15 00 00 01 00 00 01 0f 04 5a … b9` (= check 4's slot write), commit
    `… f0 00 00 00 0b`, select 1C `… e0 01 00 00 01 17`; `preset restore <backup> --all --dry-run
    …` with the backup of the same pedal → `pedal already matches …; nothing sent` (no frame to
    compare: nothing differs); `preset reload` → select 1B, applied. Hardware run still to do.
    **Note for the hardware run**: restore prints the image frame only when the file differs from
    the pedal; use a modified copy (`poc/modified_backup.py <backup> <copy> 1C 6 90`, one byte of
    1C changed in presets and image) for the restore dry run.
  - Hardware run 2026-11-18 14:00–14:28 UTC, fw 96, owner's Mac, pedal on **1A** in normal mode,
    phone app closed. Only confirmed messages were written: one knob block and one preset select.
    Backups `captures/private/20261118-m2-gate-before.json` (14:00:05) and `…-after.json`
    (14:27:57): **equal in every key except `created_at`**; no `tankg-backup-*-before-*` file was
    created by any dry run or refused run.
  - `set gain 90 --trace`: `Set gain 65 → 90   (current preset 1A, normal mode)`, knob block
    `… 12 05 5a 37 41 37 32 00 00 0c 28 35 0f 07 08` (only byte 6 changed), ACK, `applied`, mode
    stayed normal, `Keep: openvave preset save --unsafe --experimental` printed.
  - `preset save --to 1C --dry-run --unsafe --experimental --trace`: reads only (query, global,
    buffer, stored 1C `0x2C`); full diff of 1C vs the 1A buffer shown; frames slot write
    `00 59 22 1d 00 00 04 2c 00 00 00 15 00 00 01 00 01 01 12 05 5a 37 41 37 32 00 00 0c 28 35 0f 07
    ff f7 00 f0`, commit `… f0 00 00 00 0b`, select 1C `… e0 01 00 00 01 17`, each equal to an
    independent encoding (`tests/support/write_fixture.write_frame`); `dry run: nothing sent, no
    backup taken`.
  - `preset restore <modified copy> --all --dry-run --unsafe --experimental --trace` (copy from
    `poc/modified_backup.py`: 1C byte 6 = 90, image offset 50 the only difference): reads only,
    including the whole-image read whose 773-byte reply came in 5 notifications (4 × 182 + 45) and
    was reassembled; `differ: 1C (1 of 36)`; image frame 773 bytes, head `00 59 22 fe 02 00 04 00 00
    00 00 f6 02 00 a5 5a`, checksum `8d`, equal in length, head and checksum to an independent
    encoding of the copy's image (frame body not recorded here: it is the owner's stored image);
    then commit and `select 1A` (`… e0 01 00 00 01 19`, the loaded preset); also `refused:
    edits_would_be_discarded` (the gain-90 edit was unsaved), correct.
  - `preset reload --trace`: select 1A, ACK, `now bank 1, slot A   buffer = stored 1A   applied`
    (gain back at 65).
- [X] T067 [US3] Owner runs `preset save` and `preset restore <backup> --all` **without** `--unsafe`: both exit 1 with `unsafe_required` and the trace holds reads only
  - Amended procedure (contract order: "nothing to change" is checked before the opt-ins, so on a
    pedal that matches, both exit 0 with `nothing sent`): run `preset save` **after** `set gain 90`
    and before the reload, and `preset restore` with the modified copy above. Offline rehearsal
    2026-11-18: `preset save` (no opt-ins) → exit 1 `unsafe_required`, message also names
    `--experimental`; `preset save --experimental` → exit 1 `unsafe_required`; `preset restore
    <modified> --all` and `… --experimental` → exit 1 `unsafe_required`; all reads only (`0x11`,
    `0x23`), no backup file. The dry run with `--unsafe --experimental` printed `differ: 1C (1 of
    36)` and the full 773-byte image frame, then the commit and select 1B. Hardware run still to do.
  - Hardware run 2026-11-18 (same session): `preset save --trace` with the gain-90 edit unsaved →
    `refused (unsafe_required): preset save overwrites a stored preset; pass --unsafe … and
    --experimental …: commit, stored_slot are not confirmed …`, exit 1, reads only (query, global,
    buffer, stored 1A), no backup file. `preset restore <modified copy> --all --experimental
    --trace` with the edit still unsaved → `refused (edits_would_be_discarded)`, exit 1, reads only
    (the edit check comes first).
    After `preset reload` (no edit): the same restore command → `refused (unsafe_required): preset
    restore overwrites stored presets; pass --unsafe (unsafe=True) to accept that`, exit 1, reads
    only (query, global, buffer, whole image), no backup file. Both commands refused with
    `unsafe_required` on hardware → **T067 passed**.

**Checkpoint**: Milestone 2 DONE — every persistent path exists and is tested; openvave has not yet sent a persistent write ✅ (2026-11-18: suite 1612 passed; T066/T067 on hardware, only reads plus one confirmed knob block and one confirmed select, backups before/after equal)

---

## Milestone 3: Gate session A, first sends (US6 P1, evidence for US2–US5)

**Goal**: openvave itself sends each new message once on hardware, with approval and backups, and
the rows move to `observed`.

**Independent test criteria**:
- Every gate step has an entry under its task: approved frame (quoted approval), backups before
  and after, private record path, observed result.
- After each volatile step the backup equals the one before; after each persistent step it
  differs only in the intended bytes; the session's last backup equals backup A0.
- The committed excerpts replay green and contain no stored preset other than public 1B/1C bytes
  or the synthetic image.

### Tests (write first, must fail until the evidence exists)

- [X] T068 [P] [US6] `tests/integration/gate_fixtures.py` + `tests/integration/test_gate_replay.py`: declare session-A steps of 004 (`bypass`, `bypass_off`, `normal_switch_mod`, `normal_led_colour`, `loopback_off`, `loopback_on`, `save`, `restore_slot`, `image_noop`, `restore_all`); the replay test fails until each excerpt exists
- [X] T069 [P] [US6] `tests/unit/test_gate_excerpt_tool.py` + `tests/support/gate_excerpt.py`: the excerpt tool replaces an image-write payload and any full-image read with the synthetic image (checksums recomputed) and refuses to emit a stored preset that is not public (FR-037)
- [X] T070 [P] [US6] `tests/unit/test_writes_doc.py`: a row may be `observed` only if it cites a committed `-gate-` excerpt of 004 (already the rule; add the five new rows to the check)
  - Done 2026-11-18, offline. Suite **1632 passed, 6 skipped, 10 xfailed** (the ten session-A
    steps, strict); `ruff`, `ruff format --check`, `mypy` clean. T068: `gate_fixtures.py` declares
    `SPEC004_SESSION_A` (spec `004`, expected date `20261118`), `PERSISTENT_STEPS` and `ROW_STEPS`
    (row → steps that may back it); `test_gate_replay.py::test_gate_004_step_replays` checks the
    recorded requests, the write frames against an independent encoding (bypass `0xE1000000 + i`
    of the first global read; save = first buffer read → slot, commit `×0`, select; restore and
    `image_noop` = the excerpt's own slot/image write, then commit and select) and `applied` /
    `verified`; persistent steps carry `persistent_writes`. T069: `gate_excerpt.py` labels the new
    writes and the status read, reads the JSONL frame log of `test_hw_persistent.py`, and
    **sanitises** every edit-buffer, stored-slot and whole-image value (reads and writes) that is
    not public through one injective map to `synthetic_preset(k)` (checksums recomputed,
    notifications re-cut at their original lengths); a buffer that is public plus the step's own
    field write counts as public; `build` refuses if `leaks()` still finds a value. Rehearsal: all
    nine session-A calls run on a fake whose stored presets are private stand-ins, cut, and pass
    the gate replay with none of those bytes in the file. `test_gate_excerpts.py` now uses the
    same leak check, allows the 1-byte status read and allows persistent writes only in
    persistent steps. The no-op plan moved to `tests/support/image_noop.py`, shared by the
    hardware helper and the replay. T070: `test_spec004_rows_cite_their_gate_excerpts` (vacuous
    until T083 promotes a row). Reference for T071: `captures/private/check1-before.json` equals
    `20261118-m2-gate-after.json` in every key except `created_at`.

### Evidence gathering (pedal owner, hardware, one approval per step)

- [X] T071 [US6] Pre-session: owner runs `uv run openvave preset backup --output captures/private/<date>-gate004-A0.json`; researcher confirms it equals the backup from before check 1 (or records the difference and stops)
  - 2026-11-18 14:50:31 UTC: owner ran the backup to `captures/private/20261118-gate004-A0.json` (36 presets, header `a5 5a`, whole-image cross-check OK). Equal to `captures/private/check1-before.json` in every key except `created_at` → **A0 = reference state**.
- [X] T072 [US6] Step `bypass` then `bypass_off`: researcher posts the frames (`… e1 01 00 00 01 17`, select 1B), owner approves, runs `bypass on --experimental --trace`, listens, runs `info` (expects `state: bypass`), runs `bypass off 1B --experimental --trace`; backup; record ACK, re-reads, LEDs and sound
  - 2026-11-18, pedal on 1B in normal mode (`preset select 1B` from 1A first: confirmed select, `… e0 01 00 00 01 18`, ACK, applied).
  - `bypass on --experimental --trace` (owner ran the frames posted in chat): write `00 59 22 09 00 00 04 01 00 00 e1 01 00 00 01 17`, reply ACK `00 59 00 01 00 00 00 ff`, re-read: global slot `ff`, buffer all `00` → `applied`; printed `Leave bypass: openvave bypass off 1B`. Trace `captures/private/20261118-gate004-bypass.trace` (21 frames: query, global, buffer, stored 1B, write, global, buffer). Trial excerpt passes the gate replay, nothing sanitised, no leaks. `info` in bypass: `state: bypass (all blocks off; the pedal does not report the loaded slot)`, global `00 00 ff 01` (slot 255 flagged OUT OF RANGE, mode normal), status byte `01` (loopback baseline before T074). 
  - `bypass off 1B --experimental --trace`: two state reads (bypass confirmed twice), write `… e0 01 00 00 01 18` (confirmed select), ACK, re-read global/buffer/stored 1B → `bank 1, slot B   buffer = stored 1B   applied`. Trace `captures/private/20261118-gate004-bypass_off.trace`; trial excerpt passes the gate replay, nothing sanitised, no leaks. 
  - Backup `captures/private/20261118-gate004-A1.json` (2026-11-18T14:51:39.704019+00:00): equal to A0 in every key except `created_at` (volatile step, as expected). Approval: owner answered "Approve both frames" in chat (the bypass frame `… e1 01 00 00 01 17` and the select `… e0 01 00 00 01 18`), given **after** the owner had run both commands; recorded as a process deviation (FR-036 asks for approval before the first send). Owner's sound/LED report: pending.
  - Owner (asked after the session): during bypass the sound was **clean** and the **LEDs went off**, as in check 2.
- [X] T073 [US6] Step `normal_switch_mod` and `normal_led_colour`: in normal mode, `set mod_on on --experimental`, then `set led_colour '#ff0000' --experimental`; owner reports the block LEDs and the preset LED; `preset reload`; backup (answers "switches and LED colour in normal mode" and "does the LED colour show")
  - 2026-11-18, 1B normal mode. `set mod_on on --experimental --trace`: `Set mod_on off → on (current preset 1B, normal mode)`, write `00 59 22 09 00 00 04 01 00 00 10 01 00 00 01 e8` (= independent encoding), ACK, `[1] mod_on on   applied`, `Not saved` line printed. Trace `captures/private/20261118-gate004-normal_switch_mod.trace`. Owner: "MOD LED light up" (sound not checked with a guitar).
  - `set led_colour '#ff0000' --experimental --trace`: `#431643 → #ff0000 (current preset 1B, normal mode)`, write `00 59 22 0b 00 00 04 12 00 00 10 03 00 00 ff 00 00 d7` (= independent encoding), ACK, `[18] 255 [19] 0 [20] 0 applied`. Owner: "the led is red now" → **the LED colour shows on the pedal in normal mode** (open question answered). Trace `captures/private/20261118-gate004-normal_led_colour.trace`. Its first buffer (1B + MOD on) is public only through the MOD step's excerpt, so `public_presets` now also counts buffer values of committed gate excerpts (except the file checked).
  - `preset reload`: select 1B `… e0 01 00 00 01 18`, ACK, `buffer = stored 1B   applied`. Backup `captures/private/20261118-gate004-A2.json` (2026-11-18T14:59:50.872843+00:00): equal to A0 except `created_at`. Excerpts `captures/fw96/20261118-gate-normal_switch_mod.jsonl` and `…-normal_led_colour.jsonl` cut and replaying green. **T073 done.**
- [X] T074 [US6] Step `loopback_off` / `loopback_on`: approved frames `… d0 01 00 00 00 2a` and `… 01 29`; `loopback off --experimental`, owner listens and records a short USB take, `info`, power cycle, `info` (persistence), `loopback on --experimental`, `info`; backup; record what changed, or that nothing audible changed
  - 2026-11-18, 1B normal mode, status byte `01` before (T072 `info`). `loopback off --experimental --trace`: write `00 59 22 09 00 00 04 00 00 00 d0 01 00 00 00 2a` (the frame posted in chat; run **before** the owner's written approval, process deviation as in T072), ACK, status re-read `00` → `applied`. Trace `captures/private/20261118-gate004-loopback_off.trace`; excerpt `captures/fw96/20261118-gate-loopback_off.jsonl`. `info` after: `state: normal, preset 1B`, global `00 00 01 01`, status `00`. Device info bytes `0x14–0x15` read `43 f3` (were `00 d6` in T072's bypass `info`; meaning unknown, likely unrelated to loopback, noted only). 
  - Power cycle (first scan found no pedal while it booted), then `info`: status **`00`** — the written value survived the power cycle (it read `01` before this session, including after earlier power cycles) → the flag looks **persistent**. Pedal booted on **1A** (`00 00 00 01`), not on 1B where it was switched off. Device info `0x14–0x1F` all `00` after boot; before, `0x17–0x1F` held `01 00 00 01 0f 04 3c 3c 46` = the first 9 bytes of 1B (noted only: the type-5 block seems to mirror the last selected/written preset at runtime). 
  - `loopback on --experimental --trace` on 1A: write `00 59 22 09 00 00 04 00 00 00 d0 01 00 00 01 29`, ACK, status re-read `01` → `applied` (again run before a written approval). Trace `captures/private/20261118-gate004-loopback_on.trace`; excerpt `captures/fw96/20261118-gate-loopback_on.jsonl` (1A's buffer is already public, nothing sanitised). `info` after: `normal, preset 1A`, status `01` (= the value before the session). Device info `0x14–0x15` now `00 25` (values seen today: `00 d6`, `43 f3`, `00 00` at boot, `00 25`; varies, meaning unknown). The owner later re-ran `loopback on … --trace` by mistake: `loopback is already on; nothing sent` (reads only). That run overwrote the private trace file; the excerpt cut from the original trace (`captures/fw96/20261118-gate-loopback_on.jsonl`, with the write and ACK) is the record of the step. 
  - Backup `captures/private/20261118-gate004-A3.json`: equal to A0 except `created_at`. Only the owner's sound / USB observation is still missing.
  - Owner (asked after the session): could not say whether anything changed with loopback off, not knowing what loopback does or what to listen for. Recorded as **nothing observed**; the meaning stays open (a targeted test needs computer playback over USB while recording over USB).
  - Follow-up test the same day (after the session, owner): phone connected to the pedal as a Bluetooth audio source playing a backing track, guitar played, USB recording. Loopback **on**: the backing track is in the recording, as heard. Loopback **off** (`… d0 01 00 00 00 2a`, ACK, status `00`): the backing track is still heard but **left out of the recording**. So the status byte is the loopback flag: `01` mixes the pedal's Bluetooth audio into the USB recording. The byte is **not** renamed in `bytemap.py`: a named byte-map entry needs a step fixture pair, and the pair index covers global and preset bytes only (follow-up); the result is in the doc's Notes.
- [X] T075 [US6] Step `save`: `set gain 90`, then the approved `preset save --to 1C --unsafe --experimental --trace` (slot write to `0x2c`, commit, select 1C); owner notes the mute; power cycle; backup: only 1C byte 6 differs from A0
  - 2026-11-18. `preset select 1B` (from 1A, ACK, applied); `set gain 90` (`60 → 90`, knob block `… 0f 04 5a … 07 76`, ACK, applied, normal mode). Dry run `preset save --to 1C --dry-run --unsafe --experimental --trace`: reads only (query, global `00 00 01 01`, buffer = 1B gain 90, stored 1C = 1B gain 60); diff `[6] gain 60 → 90`; frames slot write `… 2c 00 00 00 15 00 00 01 00 00 01 0f 04 5a … 43 16 43 b9`, commit `… f0 00 00 00 0b`, select 1C `… e0 01 00 00 01 17`, each **equal to the independent encoding posted in chat beforehand**; `dry run: nothing sent, no backup taken`.
  - Approval: owner wrote "approved" in chat **before** the real save (the three frames above).
  - Real run `preset save --to 1C --unsafe --experimental --trace`: automatic backup `tankg-backup-20261118-120931-before-save.json` (written to the **current directory**, the repo root, which is not git-ignored; moved to `captures/private/` at once — follow-up: default the automatic backup to a git-ignored place or warn); power-loss warning printed; slot write ACK, 300 ms, commit ACK, 100 ms, select 1C ACK; `verify stored 1C = written bytes, pedal on 1C, buffer = stored   saved`. Frames equal the dry run. Trace `captures/private/20261118-gate004-save.trace`; excerpt `captures/fw96/20261118-gate-save.jsonl` (155 lines, 3 writes; 30 private preset values replaced by synthetic ones, 1B/1C kept), replays green. 
  - Owner: pedal went to 1C; mute not listened for (to be checked during T076). Backup `captures/private/20261118-gate004-A4.json`: differs from A0 **only** at image offset 50 (= 1C byte 6, gain) `60 → 90` and preset entry 2 (1C) → exactly the intended change. Owner confirmed the power cycle before A4 → **the saved slot persists across a power cycle**.
- [X] T076 [US6] Step `restore_slot`: approved `preset restore captures/private/<date>-gate004-A0.json --slot 1C --unsafe --experimental --trace`; `preset select 1B`; backup equals A0
  - 2026-11-18, pedal on **1A** after T075's power cycle (global `00 00 00 01`, buffer = stored 1A, no edits). Dry run `preset restore …-A0.json --slot 1C --dry-run --unsafe --experimental --trace`: reads only (query, global, buffer, stored 1C = gain 90, stored 1A for the edit check); diff `[6] gain 90 → 60`; frames slot write `… 2c … 0f 04 3c 3c 46 … 43 16 43 d7`, commit `… f0 00 00 00 0b`, select 1C `… e0 01 00 00 01 17`, each **equal to the independent encoding posted in chat beforehand**; nothing sent, no backup.
  - Owner approved in chat, then ran the real restore with `--trace`: automatic backup `tankg-backup-20261118-134251-before-restore.json` (written to the repo root again, moved to `captures/private/`; its image equals A4); slot write ACK, 300 ms, commit ACK, 100 ms, select 1C ACK, the **same three frames** as the dry run; verify "stored 1C = A0 1C, pedal on 1C, buffer = stored" → `restored`. `preset select 1B` ACK, applied. Backup `captures/private/20261118-gate004-A5.json`: image and header **equal to A0**. Excerpt `captures/fw96/20261118-gate-restore_slot.jsonl` (3 writes) replays. Owner: **a very short mute, almost unnoticed**, during the restore sequence (the commit mute, also expected for T075).
- [X] T077 [US6] Step `image_noop`: researcher posts the frame shape (773 B, 5 Bluetooth writes, payload = the image just read) and the pass criteria (one ACK after the last chunk, no stray reply, next read fine); owner approves and runs the T064 helper; backup equals A0. **If it fails**: stop, record, skip T078, do T079
  - 2026-11-18. Researcher posted the frame shape (773-byte image write `00 59 22 fe 02 00 04 00 00 00 00 f6 02 00 a5 5a …`, commit, select 1B) and pass criteria; owner approved; helper `OPENVAVE_HW_WRITES=1 OPENVAVE_HW_UNSAFE=1 OPENVAVE_HW_STEP=image_noop pytest tests/hardware/test_hw_persistent.py --hardware -s`, record `captures/private/20261118-134453-hw-image_noop.jsonl`. **Deviation**: the helper's plan selected **1A** (`… e0 01 00 00 01 19`), not the posted 1B, because its reads found the pedal on 1A (global `00 00 00 01`, buffer = stored 1A) although `preset select 1B` had reported 1B about two minutes earlier (cause asked of the owner); the owner typed `send` before the researcher compared the printed plan. Harmless (select of the already loaded preset), but from now on the printed plan is checked in chat before `send`. Result: image write → **exactly one ACK** (~0.2 s after the request, no stray reply), 300 ms, commit ACK, 100 ms, select 1A ACK; verify reads (global, buffer, header, 36 slots, whole image) all fine, image unchanged → `verified True`, test passed. Backup `captures/private/20261118-gate004-A6.json`: image and header **equal to A0**. Excerpt `captures/fw96/20261118-gate-image_noop.jsonl` (3 writes, image sanitised) replays. **The 773-byte image write is accepted; T079 not needed.**
- [X] T078 [US6] Step `restore_all`: repeat T075's save to 1C, then the approved `preset restore captures/private/<date>-gate004-A0.json --all --unsafe --experimental --trace`; power cycle; backup equals A0
  - 2026-11-18. Before it, `preset select 1B` printed "from 1B" although the T077 helper had last read and selected **1A**; together with T077's 1B→1A this is two preset changes **no command explains**. Owner: no footswitch pressed, official app shows Bluetooth not connected. Recorded as an open observation (the traces hold every global read). Mitigation kept: each persistent run re-reads state, and the printed frames were checked against the dry run.
  - Save again: `set gain 90` on 1B (`… 0f 04 5a 3c 46 … 76` ACK); dry run equal to the independent encoding (`… 2c … 0f 04 5a 3c 46 … b9`, commit `… 0b`, select 1C `… 17`); owner approved; real save `--trace 2> captures/private/20261118-gate004-restore_all-save.trace`: automatic backup `tankg-backup-20261118-135052-before-save.json` (repo root, moved to `captures/private/`; image = A0), three ACKs, verify `saved`.
  - Restore all: dry run reads (global `00 00 02 01` = 1C normal, buffer = stored 1C, whole image); differ: 1C only; image write `00 59 22 fe 02 00 04 00 00 00 00 f6 02 00 a5 5a …` 773 B ending `ab` (= the independent encoding of A0's image), commit, select 1C. **Deviation**: the owner ran the real restore before writing "approved" (dry run matched). Real restore `--trace 2> captures/private/20261118-gate004-restore_all.trace`: automatic backup `tankg-backup-20261118-135142-before-restore.json` (moved; differs from A0 only at offset 50, 1C gain 90); image write ACK (773 bytes), commit ACK, select 1C ACK; verify "36 of 36 presets and header equal A0" → `restored`. Power cycle, then backup `captures/private/20261118-gate004-A7.json`: **equal to A0 key by key apart from `created_at`** → the image write persists across a power cycle. Excerpt `captures/fw96/20261118-gate-restore_all.jsonl` (3 writes, image sanitised) replays.
- [X] T079 [US6] Not needed (T077 passed). Only if T077 failed: implement the slot-by-slot fallback of R11 (tests first in `tests/integration/test_restore.py`, then `src/openvave/session.py`, `specs/protocol/command-layer.md`, contracts updated), gate it as its own approved step, and record why the image write was dropped
- [X] T080 [US6] Optional, each its own approved step: (a) slot write to 1C **without** commit via a `poc/` script, power cycle, backup (does it persist?), restore 1C; (b) `set gain 90` in normal mode, owner turns the gain knob on the pedal, `preset dump`, `preset reload`. Record results or "not run"
  - 2026-11-18: **not run**, owner's choice after T078. "Is the commit required?" and "knob after a remote write" stay open; the library always commits, so no feature depends on them.
- [X] T081 [US6] Post-session: final backup `captures/private/<date>-gate004-A-post.json` equals A0 key by key apart from `created_at` (SC-010 for this session)
  - 2026-11-18: A7 (T078, after the power cycle) is the last read of the session, no write followed; copied to `captures/private/20261118-gate004-A-post.json`. Equal to A0 key by key apart from `created_at` (kind, format_version, tool, identity, layout, header, image, presets, warnings). **SC-010 holds for session A.**

### Recording findings

- [X] T082 [US6] Cut sanitised excerpts with the excerpt tool into `captures/fw96/<date>-gate-<step>.jsonl` for every step run; update `captures/README.md`; T068 goes green
  - 2026-11-18: ten excerpts `captures/fw96/20261118-gate-{bypass,bypass_off,normal_switch_mod,normal_led_colour,loopback_off,loopback_on,save,restore_slot,image_noop,restore_all}.jsonl`, all registered in `RECORDED`, all replay (no strict xfail left). Independent scan against A0: none of the 30 non-public stored presets appears in any excerpt. `captures/README.md`: table row for the session-A excerpts, excerpt-tool verbs and sanitising rules.
- [X] T083 [US6] `specs/protocol/command-layer.md` + `src/openvave/protocol/writes.py`: rows `bypass`, `loopback`, `stored_slot`, `commit`, `stored_image` → `observed` with their excerpts; address map and "Stored presets, switching and saving" updated; status byte named `loopback` in the byte map and `bytemap.py` only if T074 observed an effect; (MOD FX / DLY Mix types already added in M0 after T022)
  - 2026-11-18: rows `bypass`, `loopback`, `stored_slot`, `commit`, `stored_image` → `observed` in `command-layer.md` and `WRITE_MESSAGES`, each citing its session-A excerpts (checks 2–4 stay in Notes); address map, "Volatile vs persistent" (loopback persists without a commit) and "Request chunking" (one ACK for the 5-chunk request) updated. Status byte meaning observed after the session (T074 follow-up), recorded in the doc's Notes and the loopback row; not renamed in `bytemap.py` (needs a status-byte fixture pair, follow-up). Tests moved from `hypothesis` to `observed` (`test_writes_doc`, `test_write_gate`, bypass/loopback/save integration and CLI contract tests); `--experimental` is still required until session B.
- [X] T084 [US6] `specs/protocol/app-features.md`: gate results per feature, the open questions answered or still open (commit required?, mute source, knob after remote write, LED colour, loopback meaning and persistence); `CHANGELOG.md` [Unreleased] "Tested" entry
  - 2026-11-18: `app-features.md` section "Spec 004 gate session A" (results per feature; commit-required and knob-after-write still open, T080 not run; mute heard during restore; LED colour drives the preset LED in normal mode; loopback persists, meaning open; the unexplained preset changes). `CHANGELOG.md` [Unreleased]: "Tested" entry, bypass/loopback/persistent rows and chunking now `observed`.

### Live verification (milestone gate)

- Suite green with the new excerpts; `tests/unit/test_writes_doc.py` passes with five rows ≥ `observed` (SC-009, first half); T081 holds.

**Checkpoint**: ✅ Milestone 3 DONE (2026-11-18) — every new message has been sent once by openvave with evidence, and the pedal is back to backup A0

---

## Milestone 4: Gate session B, confirmations (US6)

**Goal**: a second, independent session confirms bypass, stored slot and commit (and the image
write if session A passed it), so they run without `--experimental`.

**Independent test criteria**:
- Session B uses a new connection after a power cycle, a different loaded preset and a different
  target slot than session A.
- Rows `bypass`, `stored_slot`, `commit` are `confirmed` and each cites two sessions;
  `bypass on` and `preset save --unsafe` run without `--experimental`; `preset save` without
  `--unsafe` is still refused.

### Tests (write first, must fail)

- [X] T085 [P] [US6] `tests/integration/gate_fixtures.py`: declare session-B steps (`bypass_b`, `bypass_off_b`, `save_b`, `restore_slot_b`, `restore_all_b`); `tests/integration/test_save.py` and `test_bypass.py`: with the confirmed rows, no `experimental` needed, `unsafe` still required
  - Done 2026-11-18, offline. `gate_fixtures.py`: `SPEC004_SESSION_B` (session `B`, expected date `20261118`), added to `SPEC004_STEPS`, `SESSION_DATES` and `ROW_STEPS` (`bypass_b` backs `bypass`; `save_b`/`restore_slot_b` back `stored_slot`; those plus `restore_all_b` back `commit`; `restore_all_b` backs `stored_image`). New tests, strict `xfail` while the rows are `observed`: `test_bypass.py::test_bypass_on_and_off_without_experimental_once_confirmed`, `test_save.py::test_save_runs_with_unsafe_alone_once_confirmed`, `test_restore.py::test_restore_slot_runs_with_unsafe_alone_once_confirmed`; passing now and after T090: `test_save_without_unsafe_is_refused_even_once_confirmed`, `test_restore_without_unsafe_is_refused_even_once_confirmed`. Suite **1724 passed, 6 skipped, 8 xfailed** (5 session-B replays + 3 confirmed tests); `ruff` clean.

### Evidence gathering and recording

- [X] T086 [US6] Pre-session backup B0 equals A0; pedal on a preset other than 1B whose bytes are public or, if not public, whose excerpt payloads the tool replaces (T069)
  - 2026-11-18. Answers before the session (owner, in chat): reference state = a **new backup B0** (not A0), loaded preset **1A**, target slot **1D**. Owner power-cycled the pedal, then `preset backup --output captures/private/20261118-gate004-B0.json` (36 presets, header `a5 5a`, whole-image cross-check OK). **B0 ≠ A0**: they differ only in **2C and 2D** (27 bytes), the two sounds the owner saved after session A (`tankg-backup-20261118-142241-before-save.json`, `~/openvave-backups/tankg-backup-20261118-145009-before-save.json`); every check of session B is against B0. `info` at B0: `normal, preset 2D`, status `00` (loopback off since the T074 follow-up). 1A's bytes are public (`captures/fw96`), so the loaded preset needs no sanitising; 1D's do and the tool replaces them.
- [X] T087 [US6] Steps `bypass_b` / `bypass_off_b`, each approved: as T072 on the session-B preset; backup
  - 2026-11-18, frames encoded independently, posted and approved in chat **before** sending (owner: "Power-cycled, approve"). `preset select 1A`: `… e0 01 00 00 01 19`, ACK, applied; it printed "**from 1B**" although `info` had read 2D two minutes earlier with nothing written in between (third unexplained preset change, see T078). `bypass on --experimental --trace`: `00 59 22 09 00 00 04 00 00 00 e1 01 00 00 01 18`, ACK, slot `ff`, buffer all `00` → applied; `info`: `state: bypass`. `bypass off 1A --experimental --trace`: `… e0 01 00 00 01 19`, ACK, buffer = stored 1A → applied. Traces `captures/private/20261118-gate004-bypass_b.trace`, `…-bypass_off_b.trace`; excerpts `captures/fw96/20261118-gate-bypass_b.jsonl`, `…-bypass_off_b.jsonl` (nothing sanitised), replay green. Backup `captures/private/20261118-gate004-B1.json`: equal to B0 except `created_at`.
- [X] T088 [US6] Steps `save_b` and `restore_slot_b`, each approved: change one knob, `preset save --to <other slot> --unsafe --experimental`, power cycle, backup (one byte differs), `preset restore <B0> --slot <other slot> --unsafe --experimental`, backup equals B0
  - 2026-11-18. **save_b** (approved in chat before sending: set, then save after a matching dry run): `set treble 70` on 1A (55 → 70, `… 12 05 41 46 41 37 … 12`, ACK, applied); dry run `preset save --to 1D` printed slot write `00 59 22 1d 00 00 04 41 00 00 00 15 00 00 01 00 01 01 12 05 41 46 41 37 32 00 00 0c 28 35 0f 07 ff f7 00 e5`, commit `… f0 00 00 00 0b`, select 1D `… e0 01 00 00 01 16`, each **equal to the posted encoding**. Real save `--trace`: automatic backup `tankg-backup-20261118-151807-before-save.json` (repo root again, moved to `captures/private/`; equal to B0), three ACKs, `verify stored 1D = written bytes … saved`. Owner power-cycled; backup `captures/private/20261118-gate004-B2.json` differs from B0 **only in 1D**, which now holds 1A + treble 70 (17 bytes differ because 1D's old content differed from 1A; the plan's "one byte" assumed session A's case of a target that already held a copy) → the save persists across a power cycle. Pedal booted on **1B**. Excerpt `captures/fw96/20261118-gate-save_b.jsonl` (31 non-public preset values sanitised) replays.
  - **restore_slot_b** (approved before sending): dry run `preset restore …-B0.json --slot 1D` printed `… 41 00 00 00 15 00 00 01 01 01 01 40 05 64 2b … 77 b3 b3 72`, commit, select 1D, **equal to the posted encoding**. Real restore `--trace`: automatic backup `tankg-backup-20261118-152221-before-restore.json` (moved; equal to B2), three ACKs, `verify stored 1D = … B0.json 1D … restored`. Backup `captures/private/20261118-gate004-B3.json`: **equal to B0**. Excerpt `captures/fw96/20261118-gate-restore_slot_b.jsonl` replays.
- [X] T089 [US6] Step `restore_all_b`, approved, only if the image write passed in session A: save a change, `preset restore <B0> --all --unsafe --experimental`, power cycle, backup equals B0; optional approved repeats of block switch / LED colour in normal mode and loopback
  - 2026-11-18 (approved before sending). On 1D: `set gain 90` (100 → 90, `… 40 05 5a 2b … 91`, ACK); dry run then real `preset save --unsafe --experimental --trace` to the loaded 1D (`… 41 … 40 05 5a 2b 58 53 … 7c`, commit, select 1D; frames equal the posted encoding; automatic backup `tankg-backup-20261118-153209-before-save.json`, moved), three ACKs, saved. `preset restore …-B0.json --all` dry run: `differ: 1D (1 of 36)`; its three frames (773-byte image write `00 59 22 fe 02 00 04 00 00 00 00 f6 02 00 a5 5a … 55 ff 7f 7a`, commit, select 1D) compared **byte for byte** with the independent encoding of B0's image: equal. Real restore `--trace`: automatic backup `tankg-backup-20261118-153311-before-restore.json` (moved; differs from B0 only at 1D gain 90), image write ACK (773 bytes), commit ACK, select 1D ACK, `verify 36 of 36 presets and header equal … B0.json   restored`. Owner power-cycled; backup `captures/private/20261118-gate004-B-post.json`: **equal to B0 key by key apart from `created_at`** (SC-010 for session B). Excerpt `captures/fw96/20261118-gate-restore_all_b.jsonl` (image sanitised) replays. Optional repeats (block switch / LED colour in normal mode, loopback): **not run**, so those rows stay `observed`.
- [X] T090 [US6] Excerpts committed; `specs/protocol/command-layer.md` + `src/openvave/protocol/writes.py`: promote to `confirmed` every row with two sessions; `specs/protocol/app-features.md` and `CHANGELOG.md` updated; T085 goes green
  - 2026-11-18: five excerpts `captures/fw96/20261118-gate-{bypass_b,bypass_off_b,save_b,restore_slot_b,restore_all_b}.jsonl` registered in `RECORDED`; an independent scan against B0 finds none of the 30 non-public stored presets in them. `command-layer.md` and `WRITE_MESSAGES`: `bypass`, `stored_slot`, `commit`, `stored_image` → **`confirmed`**, each citing excerpts of sessions A and B (`test_confirmed_rows_cite_two_gate_sessions` passes); `loopback`, block switches and `led_colour` stay `observed`. CLI hints follow: the normal-mode "Keep:" hint is now `openvave preset save --unsafe` (`cli/render.py` `NOT_SAVED`); the failure "Undo:" hint already drops `--experimental` when the rows are sendable. Tests updated from `observed` to `confirmed` (`test_write_gate`, `test_writes_doc`, bypass/save integration and CLI contract tests; a bypass on firmware 97 is still refused `untested_firmware`); the three T085 tests now pass. `app-features.md` "Spec 004 gate session B", `CHANGELOG.md` [Unreleased] (Bypass / Save / Restore no longer "experimental", new "Tested" entry), `captures/README.md` row for the `_b` excerpts. `ruff`, `mypy` clean.

### Live verification (milestone gate)

- [X] T091 [US6] Owner runs `bypass on`, `bypass off <pos>`, `set gain 90`, `preset save --unsafe`, `preset restore <B0> --slot <pos> --unsafe` **without** `--experimental`: all succeed; final backup equals A0 (SC-003, SC-004, SC-010)
  - 2026-11-18, on 1B (where the pedal booted), every frame posted and approved in chat before sending, persistent steps only after a matching dry run, **no `--experimental` anywhere**. `preset save` (no change yet): `1B already holds this sound; nothing sent`. `bypass on`: `… e1 01 00 00 01 17`, ACK, slot `ff`, buffer zeros → applied. `bypass off 1B`: `… e0 01 00 00 01 18`, ACK → applied. `set gain 90`: `60 → 90`, `… 0f 04 5a 3c 46 … 76`, ACK, applied; hint `Keep: openvave preset save --unsafe`. `preset save` **without `--unsafe`** (with the edit): `refused (unsafe_required) … pass --unsafe`, exit 1, reads only, `--experimental` not mentioned. `preset save --unsafe --backup-dir captures/private`: dry run equal to the posted frames, then slot `… 17 … 0f 04 5a … 43 16 43 ce`, commit, select 1B, three ACKs, saved (backup `tankg-backup-20261118-154445-before-save.json`). `preset restore …-B0.json --slot 1B --unsafe --backup-dir captures/private`: dry run equal, slot `… 17 … 0f 04 3c … 43 16 43 ec`, commit, select 1B, three ACKs, restored (backup `tankg-backup-20261118-154532-before-restore.json`). Final backup `captures/private/20261118-gate004-T091-final.json`: **equal to B0 key by key apart from `created_at`**; against A0 it differs only in 2C/2D (the owner's own sounds, kept by the owner's choice of B0 as the reference, T086). SC-003, SC-004 hold on hardware; SC-010 holds against B0.

**Checkpoint**: ✅ Milestone 4 DONE (2026-11-18) — confirmed messages run by default; save and restore still need `--unsafe` (suite 1746 passed, 6 skipped; T091 on hardware, final backup = B0)

---

## Milestone 5: Release 0.4.0 + Polish

**Goal**: docs, changelog and version match what was built and confirmed.

### Tests (write first, must fail)

- [X] T092 [P] `tests/contract/test_changelog_040.py`: the 0.4.0 entry lists the new commands, `set` in normal mode, both opt-ins, the replaced safety statement, the confidence of each new message, and "Tested: fw 96"
  - 2026-11-18: written first, 23 failing (no [0.4.0] section, version 0.3.0). Checks commands, opt-ins, new write targets, `set` in normal mode under Changed, the replaced "never saves" statement, `confirmed` on the Bypass / Save / Restore entries and `observed` on Loopback, `fw 96` under Tested, and that 0.4.0 is not left under [Unreleased].
- [X] T093 [P] `tests/contract/test_cli_version.py` (or the existing version test): `openvave --version` reports 0.4.0
  - In `test_changelog_040.py` (`test_versions_agree`, `test_cli_version`), moved there from `test_changelog_030.py`, which keeps its 0.3.0 section checks only.

### Implementation

- [X] T094 `CHANGELOG.md`: move [Unreleased] to [0.4.0] with Added / Changed / Tested; `pyproject.toml` and `src/openvave/__init__.py` version 0.4.0 (T092, T093)
  - 2026-11-18: [Unreleased] is empty, [0.4.0] has a summary paragraph, Added / Changed / Tested / Documentation; the Save and Restore entries now state `confirmed` (gate sessions A and B). Version 0.4.0 in `pyproject.toml`, `src/openvave/__init__.py`, `uv.lock`. T092/T093: 36 passed.
- [X] T095 [P] `README.md`: final usage for remote editing, reload, bypass, save, restore, loopback; the safety section (opt-ins, automatic backup, what is never sent)
  - 2026-11-18: status paragraph now 0.4.0; bypass no longer "(experimental)" (`confirmed`), loopback `observed` with its observed meaning; save/restore need `--unsafe` only on fw 96; hints match `render.py` (`Keep: openvave preset save --unsafe`); new `### Safety` section (the two opt-ins, confidence table, automatic backup, no retries, what is never sent); links to the spec 004 contracts in Options / JSON / Exit codes / Library. No sentence says openvave never saves.
- [X] T096 [P] `specs/protocol/command-layer.md` "Next steps" and `specs/protocol/app-features.md` "Recommended scope": mark what 004 closed and list what stays open
  - 2026-11-18: `command-layer.md` "Next steps": "Closed by spec 004" (normal-mode edit, reload, bypass, loopback, save, restore slot/all, pedal state) and "Still open" (loopback, block switches and LED colour `observed`; commit required? (T080a); knob after a remote write (T080b); mute source; the unexplained preset changes of T077/T078/T087; edit-mode entry; import/export, swap, factory restore; other firmware/MTUs). Two stale sentences fixed ("Pedal state": bypass `confirmed`; "Normal mode": the session-A normal-mode sends). `app-features.md` "Recommended scope": items 1–4 struck as done, item 5 pedal state, "Still open after spec 004".
- [X] T097 [P] Remove dead code and messages for `not_edit_mode`; check `src/openvave/errors.py` docstrings and `specs/004-remote-edit-save-restore/contracts/` against the final behaviour; update the contracts where the gates changed something (for example the fallback of T079)
  - 2026-11-18: `render.py` drops the `not_edit_mode` refusal text (no code raises it; the schema keeps the enum value for 0.3.0 documents, additive only). CLI help: bypass no longer "experimental, not confirmed yet"; loopback help gives the observed meaning; `set --type` lists MOD FX and DLY MIX types. `errors.py` docstrings: exit-code mapping wording, `ProtocolError` reasons `backup_mismatch`/`nak`, `WriteRefusedError` `type_required`. `contracts/cli.md`: fw 96 opt-in status, `Keep:`/`Undo:` hints without `--experimental`, `bypass off` `edit_mode` refusal, T079 note (image write is one 773-byte request split by the transport, one ACK; the R11 fallback was not needed and does not exist), loopback meaning, `type_required`. `contracts/library-api.md`: real typed-knob names (`type_raw`, `type_parts`, `TYPED_FIELDS`), `plan_set_fields`/`set_fields` and the `Edit*` types, `experimental=True` dropped from confirmed examples. Schemas checked against the code: no change needed.
- [X] T098 Run `uv run pytest -q`, the linters and type checker configured in `pyproject.toml`; fix findings
  - 2026-11-18: `uv run pytest -q` → **1767 passed, 6 skipped** (119.9 s); `ruff check` 1 finding (unused import left in `test_changelog_030.py` after moving the version tests) fixed; `ruff format --check` clean (144 files); `mypy` clean (25 source files).

### Live verification (milestone gate)

- [X] T099 Owner runs quickstart §1–§5 end to end on hardware; outputs recorded under this task; final backup equals A0
  - 2026-11-18, openvave 0.4.0, the owner's Terminal panel, logs `captures/private/20261118-T099-*.log`. Reference **B0** (owner's choice since T086; it is A0 plus the owner's own 2C/2D sounds), so "equals A0" is checked as "equals B0". No `--experimental` anywhere except `loopback`; every backup in `captures/private`.
    - **§1**: `uv run pytest -q` 1767 passed, 6 skipped (T098).
    - **Before**: `--version` → `openvave 0.4.0`; `info` → `state: normal, preset 1B`; backup `20261118-T099-0.json` equal to B0 apart from `created_at` and `tool` (0.3.0 → 0.4.0).
    - **§2**: `set gain 90` applied in **2.77 s** (SC-001), `set reverb_decay 1 --type cloud` → `5 (room 6) → 88 (cloud 1)` applied, `preset reload` applied (buffer = stored 1B); backup `T099-1` equal to `T099-0` (SC-002).
    - **§3** (`--trace`): `bypass on --dry-run` printed `… e1 01 00 00 01 17`, `loopback off --dry-run --experimental` → `loopback is already off; nothing sent`, `set gain 90` then `preset save --to 1C --dry-run --unsafe` printed slot write `… 2c … 5a … 43 16 43 b9`, commit, select 1C; `preset restore T099-0 --all --dry-run --unsafe --discard-edits` → `pedal already matches …; nothing sent`. Traced commands sent 4 × `0x11` and 12 × `0x23`, no `0x22`; no backup file created. `preset save --to 1C` without `--unsafe` → `refused (unsafe_required)`, exit 1. A restore without `--unsafe` of a file **equal** to the pedal prints "nothing sent", exit 0 (the no-change check comes first, as for save); with A0 (differs in 2C/2D) it is `refused (unsafe_required)`, exit 1, reads only. `preset reload` applied.
    - **§4/§5 volatile**: `bypass on` → ACK, slot `ff`, buffer zeros, applied; `info` → `state: bypass`; `bypass off 1B` → applied. `preset save --unsafe` with no edits → `1B already holds this sound; nothing sent`.
    - **§4/§5 persistent** (owner approved steps A–D in chat with the posted frames; each run only if the dry run printed exactly those frames): **A** `set gain 90`, `preset save --unsafe`: automatic backup `tankg-backup-20261118-175423-before-save.json` (= T099-0), slot write `… 17 … 5a … 43 16 43 ce`, commit `… f0 00 00 00 0b`, select 1B `… e0 01 00 00 01 18`, three ACKs, saved. **B** owner power-cycled; booted on 1B; backup `T099-2` differs from T099-0 only at image offset 29 (1B byte 6) `60 → 90` (SC-003). **C** `preset restore T099-0 --slot 1B --unsafe`: automatic backup `…-180112-before-restore.json`, slot write `… 3c … 43 16 43 ec`, commit, select 1B, three ACKs, restored; backup `T099-3` equal to T099-0. **D** `set gain 90`, save again (same frames, saved), then `preset restore T099-0 --all --unsafe`: dry run `differ: 1B (1 of 36)`, its 773-byte frame = header `00 59 22 fe 02 00 04 00 00 00 00 f6 02 00` + exactly T099-0's 758-byte image (= B0's image, the frame encoded independently in T089); real run: automatic backup `…-180317-before-restore.json`, image write ACK (773 bytes), commit ACK, select 1B ACK, `verify 36 of 36 presets and header equal … restored`; the three writes sent equal the dry run's byte for byte (SC-004, SC-006).
    - **Final**: owner power-cycled; `state: normal, preset 1B`; backup `captures/private/20261118-T099-final.json` **equal to T099-0 and to B0** apart from `created_at`/`tool`; against A0 it differs only in 2C/2D (SC-010 against B0). No NAK, lost link or failed check; nothing retried.
- [X] T100 Researcher reviews SC-001…SC-011 one by one with the evidence for each, recorded under this task
  - 2026-11-18, researcher review, one SC at a time:
    - **SC-001 passed**: `set gain 90` in normal mode applied in 2.54 s end to end on hardware (T021a re-timing), under 5 s.
    - **SC-002 passed**: T021 backups before/after remote edits + reload identical; repeated in T073 (A2 = A0) and every reload since.
    - **SC-003 passed**: save to 1C (T075) changed only 1C byte 6, persisted across a power cycle; save to 1D (T088, session B) changed only 1D, persisted; T091 save on 1B without `--experimental`.
    - **SC-004 passed**: restore all in T078 and T089 verified 36/36 presets and the header, and the backups after a power cycle equal the restored file (A0, B0); restoring the automatic backup returns the previous state (T076, T088 restore_slot_b, T091).
    - **SC-005 passed**: offline `tests/integration/test_unsafe_entry_points.py` (no entry point sends a persistent write without `unsafe`), the session-wide audit in `tests/conftest.py` (persistent frames only in tests marked `persistent_writes`), T067 on hardware (`unsafe_required`, reads only); every real save/restore in sessions A, B and T091 wrote its automatic backup before the first write.
    - **SC-006 passed**: `tests/integration/test_dry_run_frames.py` (every write action, plan == sent); on hardware every persistent dry run in T075–T078, T088, T089 and T091 printed exactly the frames then sent.
    - **SC-007 passed**: `tests/contract/test_cli_state.py` (`info`, `preset dump`, `watch` report bypass; one bypass-looking cycle is `loading`, two are `bypass`) and `tests/integration/test_state_session.py`, both on replayed captures; `info` showed `state: bypass` on hardware (T072, T087).
    - **SC-008 passed (offline)**: `tests/integration/test_sequence_failures.py` covers every failure point of the sequence (non-zero exit, step-by-step report, no retry); no NAK, lost link or mismatch occurred in the gate sessions, so this is not exercised on hardware.
    - **SC-009 passed**: bypass, stored slot, commit and stored image `confirmed` (two sessions each, `test_confirmed_rows_cite_two_gate_sessions`), loopback `observed` (session A); `tests/unit/test_writes_doc.py` green.
    - **SC-010 passed against B0**: session A ended equal to A0 (T081); session B, T091 and T099 ended equal to B0. B0 differs from A0 only in 2C/2D, the owner's own sounds saved between sessions (owner's choice, T086).
    - **SC-011 passed**: offline suite green without hardware (1767 passed, 6 skipped hardware tests). Independent scan of every committed or untracked non-ignored file (301 files, raw bytes, hex and spaced hex) against the 34 distinct presets of B0: only 1A(=2A), 1B(=1C), 1D and 9D appear, and each already appeared in a pre-004 capture (2026-11-16/17); the 30 non-public presets appear nowhere, so no committed file holds the stored image.

**Checkpoint**: ✅ Milestone 5 DONE (2026-11-18) — 0.4.0 ready to release (tag after the PR merges) (suite 1767 passed, 6 skipped; T099 on hardware, final backup = B0; T100 SC-001…SC-011 passed)

---

## Dependencies & Execution Order

### Milestone dependencies

- M0 → M1 → M2 → M3 → M4 → M5, each starting only after the previous gate passes.
- M1 needs M0's `PedalState` (guards) and bypass reporting. M2 needs M0's state and M1's fake
  pedal extensions. M3 needs M1 and M2 complete (it sends their messages). M4 needs M3's
  excerpts. T079 exists only if T077 fails.

### Within each milestone

- Test tasks first and failing, then implementation, then docs in the same commits, then the gate.
- `src/openvave/session.py` tasks are sequential (T014 → T015 → T016; T034 → T035; T057 → T058 →
  T060). `src/openvave/protocol/writes.py` and the doc table change together (T031 + T032,
  T052 + T053, T083, T090).

### Story dependencies

- US1 (M0) is independent and is the MVP.
- US2 reporting ships in M0; US2 commands and US5 in M1 depend on US1's state code only.
- US3 and US4 (M2) share the sequence runner; US4 depends on US3's runner (T057).
- US6 (M3, M4) depends on US2–US5 being implemented.

### Parallel opportunities

- M0: T003–T011 (tests, different files); T013 alongside T012.
- M1: T023–T030; after T031, T033 alongside T032.
- M2: T040–T051; T055, T056, T059, T061 are independent files.
- M3: T068–T070; the hardware steps are strictly sequential.
- M5: T092, T093, T095–T097.

---

## Parallel Example: Milestone 0 (US1)

```text
# Tests first, together (all different files):
T003 tests/unit/test_state.py
T004 tests/unit/test_sections.py
T006 tests/integration/test_set_normal_mode.py
T007 tests/integration/test_reload.py
T009 tests/contract/test_cli_set.py
T011 tests/contract/test_cli_state.py

# Then, in parallel:
T012 src/openvave/protocol/state.py + models.py
T013 src/openvave/protocol/bytemap.py
```

---

## Implementation Strategy

### MVP first

Milestone 0 alone is shippable: remote editing in normal mode with section input, reload, and
correct bypass reporting, using only messages that are already confirmed. Stop and validate with
the owner's hardware gate (T021, T022) before starting M1.

### Incremental delivery

1. M0: volatile editing without edit mode (no new message).
2. M1: bypass and loopback code, experimental, unsent.
3. M2: save and restore code, unsafe + experimental, unsent.
4. M3: first sends, one approved step at a time, lowest risk first; the image write as a no-op
   before any real restore; fallback decided in advance.
5. M4: confirmations; `--experimental` drops for confirmed rows, `--unsafe` stays.
6. M5: release 0.4.0.

At every point the pedal can be returned to backup A0 with a message that is at least as well
evidenced as the one being tested (select for volatile steps; the slot write of checks 3–4 for
persistent ones).
