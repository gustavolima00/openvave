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

- [ ] T023 [P] [US2] `tests/unit/test_writes.py`: `bypass(i)` and `loopback()` shapes, data rules, argument range, `persistent is False`, `allowed_write_body` accepts exactly these and still rejects `0xE1000000+36`, `0xD0000000`×2 and `0xD0000000` type 5
- [ ] T024 [P] [US2] `tests/unit/test_writes_doc.py` + `tests/support/writes_doc.py`: the doc table has `bypass(i)` and `loopback` rows, `hypothesis`, mirrored by `WRITE_MESSAGES`
- [ ] T025 [P] [US2] `tests/unit/test_fake_transport.py`: fake pedal enters bypass on the bypass write (global slot `ff`, buffer zeros), leaves it on select, and stores the loopback byte
- [ ] T026 [P] [US2] `tests/integration/test_bypass.py`: check 2 replay; applied; refused per state table; `edits_would_be_discarded`; already bypassed → no change; `bypass_off` only in bypass; NAK → `WriteNakError`; ACK but not bypassed → `WriteNotAppliedError`; result carries the return index
- [ ] T027 [P] [US5] `tests/integration/test_loopback.py`: read, one write, ACK, re-read; no change when equal; refused without `experimental` and in `unrecognised`; never followed by a commit frame; NAK and not-applied paths
- [ ] T028 [P] [US2] `tests/contract/test_cli_bypass.py`: human and `--json` output of `bypass on` / `bypass off <pos>`, the "Leave bypass: openvave bypass off 1B" line, `--dry-run`, exit 2 for a missing position (message names the reported bank), exit codes 1/7/8
- [ ] T029 [P] [US5] `tests/contract/test_cli_loopback.py`: `loopback on|off` output, `--dry-run`, no-change line, refusal without `--experimental`
- [ ] T030 [P] [US2] `tests/support/audit.py` + `tests/unit/test_audit.py`: the audit accepts the two new kinds and nothing else new

### Implementation for User Stories 2 and 5

- [ ] T031 [US2] `src/openvave/protocol/writes.py`: `WriteTarget.bypass(i)`, `.loopback()`, data rules in `check_write_data`, `_SHAPES`, `WriteTarget.persistent`, two `WRITE_MESSAGES` rows (`hypothesis`, check 2 in Notes) (T023, T024)
- [ ] T032 [US2] `specs/protocol/command-layer.md`: the two "Write messages" rows and the allowlist sentence, in the same commit as T031
- [ ] T033 [US2] `src/openvave/transport/fake.py`: bypass state and loopback byte (T025)
- [ ] T034 [US2] `src/openvave/session.py`: `bypass_on(discard_edits, experimental)` and `bypass_off(index, experimental)` (select path, only in bypass); `WriteResult` gains an optional `return_index` in `src/openvave/models.py` (T026)
- [ ] T035 [US5] `src/openvave/session.py`: `set_loopback(on, experimental)` (T027)
- [ ] T036 [US2] `src/openvave/cli/__init__.py` + `src/openvave/cli/render.py`: `bypass on|off`, `loopback on|off` commands and output; `write-result.schema.json` consumers accept the new `command` and `target.kind` values (add them to `specs/004-remote-edit-save-restore/contracts/` as an extended copy if the 003 schema's enums reject them) (T028, T029)
- [ ] T037 [US2] `tests/support/audit.py`: allow the two kinds (T030); `tests/contract/test_public_api.py` lists the new exports
- [ ] T038 [US2] `README.md` and `CHANGELOG.md` [Unreleased]: bypass and loopback commands, both experimental

### Live verification (milestone gate)

- [ ] T039 [US2] Owner runs the first two commands of quickstart §3 with `--trace` (`bypass on --dry-run --experimental`, `loopback off --dry-run --experimental`); researcher checks the trace holds reads only and the printed frames equal the frames of the Independent test criteria; outputs recorded under this task

**Checkpoint**: Milestone 1 DONE — bypass and loopback are implemented and tested; neither has been sent by openvave

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

- [ ] T040 [P] [US3] `tests/unit/test_writes.py`: `stored_slot(i)` (address `2+21·i`, 21 B), `commit()` (0 B, frame `00 59 22 08 00 00 04 00 00 00 f0 00 00 00 0b`), `stored_image()` (758 B, must start `a5 5a`), `persistent is True`; rejected: slot 36, address 3, 20 or 22 bytes, commit with data, image of 757 bytes, image with another header, `0x10000000`×21, `0x20000003`×1
- [ ] T041 [P] [US3] `tests/unit/test_writes_doc.py`: rows `stored_slot(i)`, `commit`, `stored_image` present, `hypothesis`, mirrored
- [ ] T042 [P] [US3] `tests/unit/test_fake_transport.py`: slot and image writes change the fake's stored area, the commit sets a flag, select loads from the stored area; scripted failures per step (NAK, no reply, link drop)
- [ ] T043 [P] [US4] `tests/integration/test_tx_chunking.py`: `BleakTransport` chunking logic (pure helper `split_frame(frame, mtu)`: 773 B → 182×4 + 45; ≤ limit → one chunk; order kept) and `FakeTransport` reassembly of a chunked request by the length field
- [ ] T044 [P] [US3] `tests/integration/test_save.py`: check 4 replay (run 1 and the restore of run 2); `--to` another slot leaves the loaded slot unchanged and ends on the target; no change; refused in edit, tuner, bypass, unrecognised; `unsafe_required`; `experimental_required` names both opt-ins when both are missing; `on_backup` called once with a valid `Backup` before the first write; `on_backup` raising or a backup mismatch → no write
- [ ] T045 [P] [US3] `tests/integration/test_sequence_failures.py`: every failure point of the Independent test criteria, asserting error class, exit-code mapping, `steps` statuses, `stored_may_have_changed`, and that no frame follows the failure (no retry)
- [ ] T046 [P] [US4] `tests/unit/test_restore_file.py`: `restore_problems` for wrong `format_version`, 35 presets, a 20-byte preset, image ≠ header + presets, header `00 00`, firmware mismatch; a valid synthetic backup has none
- [ ] T047 [P] [US4] `tests/integration/test_restore.py`: restore one slot (save sequence with file bytes, verified); restore all (image write, commit, select of the previously loaded preset, full read-back equals the file); nothing sent when equal; `changed_slots` listed; `discard_edits` rule; `firmware_mismatch` needs `experimental`; verification mismatch → `WriteNotAppliedError` with `mismatched_slots`
- [ ] T048 [P] [US3] `tests/contract/test_cli_save.py`: human output (UNSAFE header, diff, "Backup saved", power-loss warning, step lines, verify line), `--json` valid against `contracts/sequence-result.schema.json`, `--dry-run` writes no backup file, `--backup-dir`, automatic backup never overwrites (numeric suffix), exit 1 without `--unsafe`, failure report text and exit codes 6/7/8
- [ ] T049 [P] [US4] `tests/contract/test_cli_restore.py`: `--slot` / `--all` (exactly one, else exit 2), invalid file exit 2 before any connection, differ list, nothing-to-restore line, `--json`, dry run prints the full image frame
- [ ] T050 [P] [US3] `tests/support/audit.py` + `tests/unit/test_audit.py`: persistent frames are allowed only in tests that declare them (marker or fixture), never elsewhere; SC-005 test enumerating every public `TankG` method and CLI command with `unsafe` absent
- [ ] T051 [P] [US3] `tests/integration/test_dry_run_frames.py`: for `set`, `preset reload`, `bypass on/off`, `loopback`, `preset save`, `preset restore --slot/--all`, the plan's frames equal the frames the fake receives in the real run (SC-006)

### Implementation for User Stories 3 and 4

- [ ] T052 [US3] `src/openvave/protocol/writes.py`: the three persistent constructors, data rules, `_SHAPES`, three `WRITE_MESSAGES` rows (`hypothesis`, checks 3–4 in Notes) (T040, T041)
- [ ] T053 [US3] `specs/protocol/command-layer.md`: the three rows, the persistent-target rule, request chunking (hypothesis), in the same commit as T052
- [ ] T054 [US3] `src/openvave/models.py`: `SequenceStep`, `SequencePlan`, `StepOutcome`, `SequenceResult`; `src/openvave/errors.py`: new refusal reasons and `.sequence` on errors raised mid-sequence
- [ ] T055 [US3] `src/openvave/transport/fake.py`: writable stored area, commit flag, scripted step failures, chunked-request reassembly (T042, T043)
- [ ] T056 [US4] `src/openvave/transport/ble.py`: `split_frame` and chunked `write()` using the negotiated MTU (T043)
- [ ] T057 [US3] `src/openvave/session.py`: the sequence runner (opt-in checks, backup + `on_backup`, per-step ACK, slot read-back before the commit, injectable waits, select verification, final read-back, step report on every failure, no retry) (T044, T045)
- [ ] T058 [US3] `src/openvave/session.py`: `plan_save(to)` / `save_preset(to, unsafe, experimental, on_backup)` (T044)
- [ ] T059 [US4] `src/openvave/backup.py`: `restore_problems(backup, firmware)` (T046)
- [ ] T060 [US4] `src/openvave/session.py`: `plan_restore(backup, slot|all)` / `restore(...)` with full read-back verification (T047)
- [ ] T061 [US3] `src/openvave/cli/files.py`: automatic backup naming `tankg-backup-<ts>-before-<action>.json`, `--backup-dir`, never overwrite (T048)
- [ ] T062 [US3] `src/openvave/cli/__init__.py` + `src/openvave/cli/render.py`: `preset save [--to]`, `--unsafe`, plan/diff/warning/step rendering, failure report with recovery commands, `--json` (T048)
- [ ] T063 [US4] `src/openvave/cli/__init__.py` + `src/openvave/cli/render.py`: `preset restore <file> (--slot|--all)`, file loading and validation before connecting, differ list (T049)
- [ ] T064 [US3] `tests/support/audit.py` (T050), `tests/contract/test_public_api.py` (new exports), `tests/hardware/test_hw_writes.py`: persistent hardware helpers require `--hardware`, `OPENVAVE_HW_WRITES=1` and `OPENVAVE_HW_UNSAFE=1`, including the no-op image write helper (reads the image, writes the same bytes through the sequence runner, logs every frame to `captures/private/`)
- [ ] T065 [US3] `README.md` (save, restore, the two opt-ins, the backup rule, the short mute, power-loss warning) and `CHANGELOG.md` [Unreleased]; replace the 0.3.0 "never saves or overwrites a stored preset" statement wherever it appears, including `tests/contract/test_changelog_030.py` expectations if they pin current-behaviour text (FR-038)

### Live verification (milestone gate)

- [ ] T066 [US3] Owner runs the last two commands of quickstart §3 with `--trace` (`set gain 90`, `preset save --to 1C --dry-run --unsafe --experimental`, `preset restore <backup> --all --dry-run --unsafe --experimental`, then `preset reload`); researcher checks: only reads plus the confirmed knob-block and select writes in the trace, no backup file created by the dry runs, printed frames equal the offline tests' frames; outputs recorded under this task
- [ ] T067 [US3] Owner runs `preset save` and `preset restore <backup> --all` **without** `--unsafe`: both exit 1 with `unsafe_required` and the trace holds reads only

**Checkpoint**: Milestone 2 DONE — every persistent path exists and is tested; openvave has not yet sent a persistent write

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

- [ ] T068 [P] [US6] `tests/integration/gate_fixtures.py` + `tests/integration/test_gate_replay.py`: declare session-A steps of 004 (`bypass`, `bypass_off`, `normal_switch_mod`, `normal_led_colour`, `loopback_off`, `loopback_on`, `save`, `restore_slot`, `image_noop`, `restore_all`); the replay test fails until each excerpt exists
- [ ] T069 [P] [US6] `tests/unit/test_gate_excerpt_tool.py` + `tests/support/gate_excerpt.py`: the excerpt tool replaces an image-write payload and any full-image read with the synthetic image (checksums recomputed) and refuses to emit a stored preset that is not public (FR-037)
- [ ] T070 [P] [US6] `tests/unit/test_writes_doc.py`: a row may be `observed` only if it cites a committed `-gate-` excerpt of 004 (already the rule; add the five new rows to the check)

### Evidence gathering (pedal owner, hardware, one approval per step)

- [ ] T071 [US6] Pre-session: owner runs `uv run openvave preset backup --output captures/private/<date>-gate004-A0.json`; researcher confirms it equals the backup from before check 1 (or records the difference and stops)
- [ ] T072 [US6] Step `bypass` then `bypass_off`: researcher posts the frames (`… e1 01 00 00 01 17`, select 1B), owner approves, runs `bypass on --experimental --trace`, listens, runs `info` (expects `state: bypass`), runs `bypass off 1B --experimental --trace`; backup; record ACK, re-reads, LEDs and sound
- [ ] T073 [US6] Step `normal_switch_mod` and `normal_led_colour`: in normal mode, `set mod_on on --experimental`, then `set led_colour '#ff0000' --experimental`; owner reports the block LEDs and the preset LED; `preset reload`; backup (answers "switches and LED colour in normal mode" and "does the LED colour show")
- [ ] T074 [US6] Step `loopback_off` / `loopback_on`: approved frames `… d0 01 00 00 00 2a` and `… 01 29`; `loopback off --experimental`, owner listens and records a short USB take, `info`, power cycle, `info` (persistence), `loopback on --experimental`, `info`; backup; record what changed, or that nothing audible changed
- [ ] T075 [US6] Step `save`: `set gain 90`, then the approved `preset save --to 1C --unsafe --experimental --trace` (slot write to `0x2c`, commit, select 1C); owner notes the mute; power cycle; backup: only 1C byte 6 differs from A0
- [ ] T076 [US6] Step `restore_slot`: approved `preset restore captures/private/<date>-gate004-A0.json --slot 1C --unsafe --experimental --trace`; `preset select 1B`; backup equals A0
- [ ] T077 [US6] Step `image_noop`: researcher posts the frame shape (773 B, 5 Bluetooth writes, payload = the image just read) and the pass criteria (one ACK after the last chunk, no stray reply, next read fine); owner approves and runs the T064 helper; backup equals A0. **If it fails**: stop, record, skip T078, do T079
- [ ] T078 [US6] Step `restore_all`: repeat T075's save to 1C, then the approved `preset restore captures/private/<date>-gate004-A0.json --all --unsafe --experimental --trace`; power cycle; backup equals A0
- [ ] T079 [US6] Only if T077 failed: implement the slot-by-slot fallback of R11 (tests first in `tests/integration/test_restore.py`, then `src/openvave/session.py`, `specs/protocol/command-layer.md`, contracts updated), gate it as its own approved step, and record why the image write was dropped
- [ ] T080 [US6] Optional, each its own approved step: (a) slot write to 1C **without** commit via a `poc/` script, power cycle, backup (does it persist?), restore 1C; (b) `set gain 90` in normal mode, owner turns the gain knob on the pedal, `preset dump`, `preset reload`. Record results or "not run"
- [ ] T081 [US6] Post-session: final backup `captures/private/<date>-gate004-A-post.json` equals A0 key by key apart from `created_at` (SC-010 for this session)

### Recording findings

- [ ] T082 [US6] Cut sanitised excerpts with the excerpt tool into `captures/fw96/<date>-gate-<step>.jsonl` for every step run; update `captures/README.md`; T068 goes green
- [ ] T083 [US6] `specs/protocol/command-layer.md` + `src/openvave/protocol/writes.py`: rows `bypass`, `loopback`, `stored_slot`, `commit`, `stored_image` → `observed` with their excerpts; address map and "Stored presets, switching and saving" updated; status byte named `loopback` in the byte map and `bytemap.py` only if T074 observed an effect; (MOD FX / DLY Mix types already added in M0 after T022)
- [ ] T084 [US6] `specs/protocol/app-features.md`: gate results per feature, the open questions answered or still open (commit required?, mute source, knob after remote write, LED colour, loopback meaning and persistence); `CHANGELOG.md` [Unreleased] "Tested" entry

### Live verification (milestone gate)

- Suite green with the new excerpts; `tests/unit/test_writes_doc.py` passes with five rows ≥ `observed` (SC-009, first half); T081 holds.

**Checkpoint**: Milestone 3 DONE — every new message has been sent once by openvave with evidence, and the pedal is back to backup A0

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

- [ ] T085 [P] [US6] `tests/integration/gate_fixtures.py`: declare session-B steps (`bypass_b`, `bypass_off_b`, `save_b`, `restore_slot_b`, `restore_all_b`); `tests/integration/test_save.py` and `test_bypass.py`: with the confirmed rows, no `experimental` needed, `unsafe` still required

### Evidence gathering and recording

- [ ] T086 [US6] Pre-session backup B0 equals A0; pedal on a preset other than 1B whose bytes are public or, if not public, whose excerpt payloads the tool replaces (T069)
- [ ] T087 [US6] Steps `bypass_b` / `bypass_off_b`, each approved: as T072 on the session-B preset; backup
- [ ] T088 [US6] Steps `save_b` and `restore_slot_b`, each approved: change one knob, `preset save --to <other slot> --unsafe --experimental`, power cycle, backup (one byte differs), `preset restore <B0> --slot <other slot> --unsafe --experimental`, backup equals B0
- [ ] T089 [US6] Step `restore_all_b`, approved, only if the image write passed in session A: save a change, `preset restore <B0> --all --unsafe --experimental`, power cycle, backup equals B0; optional approved repeats of block switch / LED colour in normal mode and loopback
- [ ] T090 [US6] Excerpts committed; `specs/protocol/command-layer.md` + `src/openvave/protocol/writes.py`: promote to `confirmed` every row with two sessions; `specs/protocol/app-features.md` and `CHANGELOG.md` updated; T085 goes green

### Live verification (milestone gate)

- [ ] T091 [US6] Owner runs `bypass on`, `bypass off <pos>`, `set gain 90`, `preset save --unsafe`, `preset restore <B0> --slot <pos> --unsafe` **without** `--experimental`: all succeed; final backup equals A0 (SC-003, SC-004, SC-010)

**Checkpoint**: Milestone 4 DONE — confirmed messages run by default; save and restore still need `--unsafe`

---

## Milestone 5: Release 0.4.0 + Polish

**Goal**: docs, changelog and version match what was built and confirmed.

### Tests (write first, must fail)

- [ ] T092 [P] `tests/contract/test_changelog_040.py`: the 0.4.0 entry lists the new commands, `set` in normal mode, both opt-ins, the replaced safety statement, the confidence of each new message, and "Tested: fw 96"
- [ ] T093 [P] `tests/contract/test_cli_version.py` (or the existing version test): `openvave --version` reports 0.4.0

### Implementation

- [ ] T094 `CHANGELOG.md`: move [Unreleased] to [0.4.0] with Added / Changed / Tested; `pyproject.toml` and `src/openvave/__init__.py` version 0.4.0 (T092, T093)
- [ ] T095 [P] `README.md`: final usage for remote editing, reload, bypass, save, restore, loopback; the safety section (opt-ins, automatic backup, what is never sent)
- [ ] T096 [P] `specs/protocol/command-layer.md` "Next steps" and `specs/protocol/app-features.md` "Recommended scope": mark what 004 closed and list what stays open
- [ ] T097 [P] Remove dead code and messages for `not_edit_mode`; check `src/openvave/errors.py` docstrings and `specs/004-remote-edit-save-restore/contracts/` against the final behaviour; update the contracts where the gates changed something (for example the fallback of T079)
- [ ] T098 Run `uv run pytest -q`, the linters and type checker configured in `pyproject.toml`; fix findings

### Live verification (milestone gate)

- [ ] T099 Owner runs quickstart §1–§5 end to end on hardware; outputs recorded under this task; final backup equals A0
- [ ] T100 Researcher reviews SC-001…SC-011 one by one with the evidence for each, recorded under this task

**Checkpoint**: Milestone 5 DONE — 0.4.0 ready to release (tag after the PR merges)

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
