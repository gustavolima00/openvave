---

description: "Task list for 003 preset backup and first edit-buffer writes"
---

# Tasks: Preset backup and first edit-buffer writes

**Input**: Design documents from `specs/003-preset-backup-edit-writes/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md),
[data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: MANDATORY. Constitution III requires capture-based tests for every encoder/parser,
written first and failing before the implementation; the default suite stays hardware-free.
Every test task precedes the code it covers.

**Organization**: one milestone per PR, as in the plan's Delivery Plan. M0 delivers US1 (backup,
read-only) and is the MVP. M1 delivers the guarded write path for US2 and US3 offline (dry-run
only on hardware). M2/M3 are **evidence milestones** for US4: the owner approves and runs each
first write, and the PR carries docs + fixtures + tests together. M4 is the release.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1–US4 from spec.md
- Paths are relative to the repository root (single Python package, `src/` layout)

## Global rules for every task

- **Write surface**: only `0x11`, `0x23` and — from M1 on — `0x22` to the `WriteTarget`
  allowlist (knob block `0x10000004`×14, block switch `0x10000000+k`×1 for k 0–3, LED colour
  `0x10000012`×3, preset select `0xE0000000+i`×1 with data `01`). No task adds erase (`0x21`), the
  commit (`0xF0000000`), stored-area writes (`0x0`–`0x2F5`), the loopback write (`0xD0000000`), a
  raw/address-based write API, or automatic write retries (FR-013, research R2/R3). The
  session-wide audit in `tests/conftest.py` (`tests/support/audit.py`) must keep passing.
- **Docs first**: every protocol fact lands in `specs/protocol/command-layer.md` in the same
  commit as the code that uses it. "Write messages" rows and `src/openvave/protocol/writes.py`
  `WRITE_MESSAGES` change together; `tests/unit/test_writes_doc.py` enforces equality (R4).
- **No factory content in git** (Constitution VI, FR-020): committed fixtures use the synthetic
  stored image (R10) and presets already public in `captures/fw96/`. The real 2026-11-17 image and
  raw gate records stay in `captures/private/` (git-ignored).
- **Hardware**: every hardware step is run by the **pedal owner** in their own terminal (Bluetooth
  permission, phone app closed). Before any **write** is sent to the pedal (M2/M3), the researcher
  posts the exact frame and expected result, the owner approves that specific write **in chat**,
  and a backup from the same session exists (FR-019). Any NAK, timeout or "not applied" stops the
  session; nothing is retried before it is reported.
- JSON stays `schema_version` 2 (additive only, R12).

---

## Delivery Plan

| PR | Milestone | Stories | Tasks | Gate |
|---|---|---|---|---|
| 1 | Milestone 0: Preset backup (US1) 🎯 MVP | US1 | T001–T020 | Suite green, audit only `0x11`/`0x23`; owner's two hardware backups identical apart from `created_at` (SC-001, SC-002) |
| 2 | Milestone 1: Guarded write path, offline (US2, US3) | US2, US3 | T021–T046 | Fake-transport tests for every target/outcome; dry-run frames == sent frames (SC-003); owner's hardware dry runs send reads only |
| 3 | Milestone 2: Gate session A — first writes (US4) | US4, US2, US3 | T047–T058 | Each approved write ACKed and applied; post-gate backup == pre-gate backup (SC-004); write rows ≥ `observed` |
| 4 | Milestone 3: Gate session B — confirmations (US4) | US4 | T059–T064 | Knob block + preset select `confirmed` (SC-005); confirmed writes run without `--experimental` |
| 5 | Milestone 4: Release 0.3.0 + Polish | all | T065–T072 | Quickstart passes end to end; SC-001…SC-007 reviewed |

Projected PR count: **5** (≤ 8). Milestone N+1 starts only after Milestone N's gate passes.

---

## Milestone 0: Preset backup (US1, P1) 🎯 MVP

**Goal**: one read-only command produces a verified backup file of all 36 stored presets.

**Independent test criteria**:
- Against the synthetic stored image over `FakeTransport`, `TankG.backup()` returns 36
  `StoredPreset`s (`1A`…`9D`) whose bytes equal the image slices, header `a5 5a`, and the frames
  sent are exactly: handshake, header read, 36 preset reads, image read — all `0x11`/`0x23`.
- Corrupting one byte of the image reply (checksum recomputed) makes the backup fail with
  `ProtocolError("backup_mismatch")` naming that preset; no file is written; exit 7.
- `openvave preset backup --output F` writes a file valid against
  `contracts/backup.schema.json`; `Backup.from_document(doc).to_document() == doc`; an existing
  `F` without `--force` exits 2 before any read; a header other than `a5 5a` adds
  `unexpected_header` and a stderr warning, exit 0.

### Tests for User Story 1 (write first, must fail)

- [X] T001 [P] [US1] Write `tests/unit/test_storage.py`: constants `STORE_OFFSET == 2`, `PRESET_SIZE == 21`, `PRESET_COUNT == 36`, `IMAGE_SIZE == 758`, `EXPECTED_HEADER == bytes.fromhex("a55a")` from `openvave.protocol.storage`; `position(0) == "1A"`, `position(6) == "2C"`, `position(35) == "9D"`; `parse_position` accepts `"2c"`, `"2C"`, `"6"` → 6 and raises `ValueError` for `"10A"`, `"1E"`, `"0A"`, `"36"`, `"-1"`, `""`; `StorageRead.header()/preset(i)/image()` give `(4, 0, 2)`, `(4, 2 + 21*i, 21)`, `(4, 0, 758)`; `StorageRead.preset(36)` and `StorageRead.preset(-1)` raise `ValueError`; `StorageRead` has no public constructor taking an address
- [X] T002 [P] [US1] Write `tests/unit/test_commands.py` additions: `build_storage_read(StorageRead.image())` == `00 59 23 08 00 00 04 00 00 00 00 f6 02 00 03`; `build_storage_read(StorageRead.preset(2))` encodes address `0x2c`; `parse_storage_reply` validates echo type/address/length and data length exactly like `parse_read_reply` (reuse its error codes `wrong_command`, `echo_mismatch`, `short_data`); existing `build_read(Region…)` behaviour unchanged
- [X] T003 [P] [US1] Write `tests/support/storage_fixture.py` (synthetic image builder, R10) and `tests/unit/test_storage_fixture.py`: `synthetic_image()` returns 758 bytes = `a5 5a` + 36 presets where preset 1 (1B) equals the fw96 capture's current preset (`01 00 00 01 0f 04 3c 3c 46 32 32 00 00 00 00 05 04 07 43 16 43`, read from `captures/fw96/20261116-probe-connect.jsonl` via `tests/support/captures.py`) and every other preset is a documented deterministic pattern within the byte-map ranges; `storage_replies(image)` returns the reply frames for header, 36 presets and the whole image
- [X] T004 [P] [US1] Write `tests/unit/test_fake_transport.py` additions for a new `FakeTransport` option `memory: Mapping[int, bytes] | None` (type-4 address → bytes): a `0x23` request for any `(4, address, length)` inside a mapped block is answered with a correct read reply built from the memory; requests outside are unanswered (timeout) unless scripted; scripted labels still take precedence; with `chunk_size=182` a 773-byte reply is delivered as chunks of 182, 182, 182, 182, 45 bytes
- [X] T005 [P] [US1] Write `tests/integration/test_backup_session.py` over `FakeTransport(memory={0: synthetic_image(), …})` plus the handshake reply: the criteria above (frame sequence, 36 presets, header, `decoded` per preset equals `decode_region` of its bytes, `created_at` timezone-aware UTC, `warnings` empty); mismatch case via a one-byte mutation of the image block only for the image read (use `replies=` override) → `ProtocolError` with code `backup_mismatch` and detail containing the position; header `00 00` → warning `unexpected_header`; firmware 97 identity → warning `untested_firmware`
- [X] T006 [P] [US1] Write `tests/unit/test_backup_document.py`: `backup.to_document()` validates against `specs/003-preset-backup-edit-writes/contracts/backup.schema.json` (`jsonschema`), hex fields lowercase space-separated, `presets[i].fields` items validate against `specs/002-preset-byte-map/contracts/decoded-field.schema.json`, no key contains a device identifier; `Backup.from_document()` round-trips; a document whose `image` disagrees with `presets[*].raw` raises `ProtocolError("backup_mismatch")`; wrong `kind`/`format_version` raises `ValueError`
- [X] T007 [P] [US1] Write `tests/contract/test_cli_backup.py` (CLI over the fake transport factory used by the existing contract tests): human output matches [contracts/cli.md](contracts/cli.md) (`Backup of TANK-Gv2 (firmware 96)   36 presets, header a5 5a`, 36 position lines, `Cross-check with whole-image read: OK`, `Saved <path>`); `--json` prints one envelope document (`schema_version` 2, `command` `"preset backup"`, `backup`, `saved_to`); default file name matches `tankg-backup-\d{8}-\d{6}\.json` in the working directory; existing target without `--force` → exit 2, no frame sent; `--force` overwrites; mismatch → exit 7, no file; unexpected header → stderr warning, exit 0; the file is written via a temp file in the same directory (no partial file left when the write is interrupted — simulate with a raising serializer)

### Implementation for User Story 1

- [X] T008 [US1] Create `src/openvave/protocol/storage.py`: layout constants, `position`, `parse_position`, and `StorageRead` (frozen dataclass with private construction through `header()`, `preset(index)`, `image()`), until T001 passes
- [X] T009 [US1] Add `build_storage_read` and `parse_storage_reply` to `src/openvave/protocol/commands.py`, sharing the prefix/echo logic with `build_read`/`parse_read_reply` through an internal `ReadTarget` protocol (`type`, `address`, `length`); export from `src/openvave/protocol/__init__.py`, until T002 passes
- [X] T010 [US1] Add `tests/support/storage_fixture.py` (T003) and commit `captures/fw96/20261117-storage-synthetic.jsonl`: a capture-format file (same meta/tx/rx line format as `captures/fw96/20261116-probe-connect.jsonl`) with the handshake, the header, 36 preset and the image request/reply frames built from `synthetic_image()`, with a meta note "synthetic stored image (R10); preset 1B from 20261116-probe-connect" — until T003 passes
- [X] T011 [US1] Add the `memory` and `chunk_size` options to `src/openvave/transport/fake.py` (one class, additive options), until T004 passes
- [X] T012 [US1] Add `StoredPreset` and `Backup` to `src/openvave/models.py` per [data-model.md](data-model.md) (frozen; `Backup.__post_init__` checks image == header + presets and raises `ProtocolError("backup_mismatch", …)`)
- [X] T013 [US1] Implement `TankG.backup()` in `src/openvave/session.py`: header read, 36 preset reads, image read, cross-check, warnings (`unexpected_header`, `untested_firmware`), `created_at` after the last read; reads only, no polling, until T005 passes
- [X] T014 [US1] Create `src/openvave/backup.py`: `to_document(backup, tool_version)` / `from_document(doc)` per [contracts/backup.schema.json](contracts/backup.schema.json), using the existing JSON field renderer from `src/openvave/cli/render.py` moved or reused without importing CLI code into the library (move the pure `field_json` helper into `src/openvave/backup.py` or a shared pure module), until T006 passes
- [X] T015 [US1] Create `src/openvave/cli/files.py` (atomic write: temp file in the target directory, `os.replace`; refuse existing target unless `force`) and add `preset backup` (`--output`, `--force`) to `src/openvave/cli/__init__.py` with human/JSON rendering in `src/openvave/cli/render.py`, until T007 passes
- [X] T016 [P] [US1] Export `Backup`, `StoredPreset` from `src/openvave/__init__.py` and `StorageRead`, `build_storage_read`, `parse_storage_reply` from `openvave.protocol`; extend `tests/contract/test_public_api.py`
- [X] T017 [US1] Update `specs/protocol/command-layer.md` "Storage layout": cite `captures/fw96/20261117-storage-synthetic.jsonl` as the committed fixture for the frame shapes (the hardware evidence stays the private 2026-11-17 probe) and note that `openvave preset backup` implements the read

### Live verification (milestone gate)

- [X] T018 Run `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check`, `uv run mypy src`; confirm T001–T007 failed before T008–T016; record counts in the PR
  - Evidence (2026-11-17): before T008–T016, T001/T002/T005/T006/T007 failed at collection
    (`ImportError`: `openvave.protocol.storage`, `Backup` missing) and T003/T004 had 9 failures
    (no committed synthetic capture; `FakeTransport` had no `memory`/`chunk_size`). After:
    `uv run pytest` → 823 passed, 4 skipped (baseline 741 passed); `ruff check` → all checks
    passed; `ruff format --check` → 89 files already formatted; `mypy src` → no issues in 23
    files. The session audit (`tests/conftest.py`) still sees only `0x11`/`0x23`.
- [X] T019 Owner, hardware (read-only, no approval needed): quickstart §2 — two `uv run openvave preset backup --output …` runs; record exit codes, header, duration, and that the two files are identical except `created_at` (SC-001: < 10 s, SC-002)
  - Evidence (2026-11-17, fw 96, macOS, owner's terminal): run A 13:34:18Z and run B 13:35:09Z
    (UTC `created_at`), both exit 0, `36 presets, header a5 5a`, `Cross-check with whole-image
    read: OK`, `warnings: []`. Comparing the two files key by key, the only difference is
    `created_at`; both load with `Backup.from_document` and have identical images (SC-002).
    An earlier attempt failed at the BLE connect step (`connect failed: TimeoutError`, nothing
    sent); it worked on retry. SC-001: a third run (`time uv run openvave preset backup --output
    /tmp/backup-c.json`) took 8.8 s wall clock end to end, including the BLE scan (default 5 s
    scan timeout) and connect, so the reads themselves take ≈ 3–4 s. Run C is identical to run A
    apart from `created_at`. Under 10 s, but with little margin because of the fixed scan time.
- [X] T020 Owner, hardware: one run with `--trace`; confirm only `0x11`/`0x23` frames and that the image reply arrived as several chunks; record in the PR
  - Evidence (run B, `--trace`): 39 TX frames: one `0x11` (handshake), then 38 `0x23` (header
    `0x0`×2, the 36 presets `2 + 21·i`×21, image `0x0`×758). No other command byte. The
    773-byte image reply came in 5 notification chunks and reassembled with a valid checksum.
    Stored 1B in the trace equals the public `20261116-probe-connect` preset. Files stay in
    `/tmp` (not committed, Constitution VI).

**Checkpoint**: ✅ Milestone 0 DONE (2026-11-17) — the owner has a verified backup before any write exists

---

## Milestone 1: Guarded write path, offline (US2 P2, US3 P3)

**Goal**: `openvave set` and `openvave preset select` exist with every safety check, dry-run and
ACK/verify handling, fully tested against the fake transport. No write reaches the pedal in this
milestone.

**Independent test criteria**:
- `build_write(WriteTarget.knob_block(), data)` for 1B with gain 90 equals
  `00 59 22 16 00 00 04 04 00 00 10 0e 00 00 0f 04 5a 3c 46 32 32 00 00 00 00 05 04 07 76`;
  `build_write(WriteTarget.preset_select(6), b"\x01")` equals
  `00 59 22 09 00 00 04 06 00 00 e0 01 00 00 01 13`; `encode_frame(0x21, …)` raises
  `UnsafeCommandError`; there is no way to build a `0x22` frame to any other address.
- `parse_write_reply(00 59 00 01 00 00 00 ff)` → ACK; status `01`, command byte ≠ `00`, wrong
  length or bad checksum → `WriteNakError` with the raw bytes.
- Over the fake transport: not edit mode → `WriteRefusedError("not_edit_mode")`, no `0x22` sent;
  out of range → refused before any write; hypothesis/observed message without `experimental` →
  `experimental_required`; NAK → exit 7; ACK but unchanged re-read → exit 8; dry-run prints the same
  frame the real call sends; select in edit mode without `discard_edits` → refused.

### Tests for User Stories 2 and 3 (write first, must fail)

- [X] T021 [P] [US2] Write `tests/unit/test_writes.py`: `WriteTarget` constructors and fields per [data-model.md](data-model.md) (`block_switch(4)`, `preset_select(36)`, negative arguments → `ValueError`); `build_write` frames for each target including the two vectors above, `block_switch(1)` with `01` → `00 59 22 09 00 00 04 01 00 00 10 01 00 00 01 …` (checksum computed in-test with `checksum`), `led_colour()` with `ff 00 00`; wrong data length → `ValueError`; `WriteTarget` cannot be constructed with an arbitrary address (no public `__init__` path; `dataclasses.replace` attempts raise); `rebuild_knob_block(buffer, offset, value)` returns buffer[4:18] with one byte changed and raises for offsets outside 4–17
- [X] T022 [P] [US2] Write `tests/unit/test_frame.py` additions: `ALLOWED_COMMANDS == {0x11, 0x23, 0x22}`; `encode_frame(0x21, …)` and `encode_frame(0x15, …)` raise `UnsafeCommandError`; `decode_frame` of the ACK (`00 59 00 01 00 00 00 ff`) returns command `0x00`, body `00`
- [X] T023 [P] [US2] Write `tests/unit/test_write_reply.py`: ACK accepted; NAK cases (status `01`, `ff`; command byte `22`; 7- or 9-byte frames; bad checksum → `ProtocolError("bad_checksum")`), each `WriteNakError` exposing `.reply` and exit code 7
- [X] T024 [P] [US2] Write `tests/support/writes_doc.py` (parser for the "Write messages" table under the heading `### Write messages` in `specs/protocol/command-layer.md`, columns `Target | Type | Address | Len | Data | Reply | Confidence | Firmware | Evidence | Notes`) and `tests/unit/test_writes_doc.py`: the parsed rows equal `WRITE_MESSAGES` (kind, argument, type, address, length, confidence, firmware, evidence); an in-test altered copy (confidence changed) is detected; rows exist for knob block, block switch k = 0–3, LED colour, preset select and the ACK; `observed`/`confirmed` rows cite existing files under `captures/`; `confirmed` rows cite ≥ 2 distinct files
- [X] T025 [P] [US2] Write `tests/unit/test_write_gate.py`: `sendable_by_default(kind, argument, firmware)` per research R4 — false for every row as initially documented (no row `confirmed`); true only when a row is `confirmed`, the ACK row ≥ `observed` and the firmware is covered (use a patched `WRITE_MESSAGES` copy, never the real table)
- [X] T026 [P] [US2] Update `tests/support/audit.py` and its test `tests/unit/test_audit.py`: allowed command bytes `0x11`, `0x23`, `0x22`; a `0x22` frame is unsafe unless its `(type, address, length)` is in the `WriteTarget` allowlist and (for preset select) its data is `01`; `0x21` always unsafe; frames to `0xF0000000`, `0xD0000000`, address `0x2`, `0x0` flagged
- [X] T027 [P] [US2] Write `tests/integration/test_set_field.py` over `FakeTransport(memory=…)` with the fake applying ACKed edit-buffer writes to its memory (new option `apply_writes=True`, see T034): knob (`gain` 90) → one 14-byte write differing from the read buffer only at block index 2, ACK, re-read shows 90, `WriteResult.applied` and `changes == ((preset, 6, 60, 90),)`; switch (`mod_on` on) → 1-byte write at `0x10000001`; `led_colour` `(255, 0, 0)` and `"#ff0000"` → 3-byte write at `0x10000012`; no-change request → `plan.no_change`, nothing sent; global mode ≠ 0 → `WriteRefusedError("not_edit_mode")` and zero `0x22` frames; `gain` 128 / `amp_type` 9 / colour 256 → `out_of_range`; unknown field → `unknown_field`; without `experimental=True` → `experimental_required`; firmware 97 → `untested_firmware`; scripted NAK → `WriteNakError`, no re-read write; ACK with `apply_writes=False` → `WriteNotAppliedError` carrying the result; a switch write where the fake also changes other block bytes → all changes reported; `plan_set` frames == frames later sent by `set_field` (SC-003); no frame to forbidden addresses (audit)
- [X] T028 [P] [US3] Write `tests/integration/test_select_preset.py`: select 6 from 1B (mode 1) → one select frame, ACK, the fake (with `apply_writes=True`) updates global bank/slot and copies stored preset 6 into the edit buffer, then the session reads global (once returning slot `ff`, then `01 01 02 01`), the edit buffer and stored preset 6 → `applied`; mode 0 without `discard_edits` → `edits_would_be_discarded`; with it → sent; slot never leaves `ff` within 10 tries → `WriteNotAppliedError`; bank/slot mismatch → not applied; `plan_select` frames == sent frames; `parse_position` errors surface as `ValueError` before connecting
- [X] T029 [P] [US2] Write `tests/contract/test_cli_set.py`: human output per [contracts/cli.md](contracts/cli.md) (`Set gain 60 → 90`, `write …`, `reply … ACK`, `after [6] gain 90   applied`, the "Not saved" line); `--dry-run` prints the frame and `dry run: nothing sent`, exit 0, zero `0x22` frames, and shows a refusal reason when one applies; `--json` validates against `specs/003-preset-backup-edit-writes/contracts/write-result.schema.json`; exit codes: refused 1, unknown field / bad value 2 (message lists valid fields), NAK 7, not applied 8; `--experimental` required message names the flag and the confidence
- [X] T030 [P] [US3] Write `tests/contract/test_cli_select.py`: `preset select 2C` / `6` / `2c` human output per contract; invalid positions exit 2 without connecting; edit mode without `--discard-edits` exit 1; `--dry-run`; `--json` schema; NAK 7; not applied 8

### Implementation for User Stories 2 and 3

- [X] T031 [US2] Add `WRITE = 0x22` to `ALLOWED_COMMANDS` in `src/openvave/protocol/frame.py` (docstring: `0x22` frames come only from `commands.build_write`), until T022 passes
- [X] T032 [US2] Add the "Write messages" table to `specs/protocol/command-layer.md` (new `### Write messages` section after "Write acknowledgement"): rows for knob block, block switch k = 0, 1, 2, 3, LED colour, preset select and the ACK, all `hypothesis`, firmware 96, Evidence `—`. Rule (stated in the section): a row is `observed` only when it cites a committed capture of this project's own send; app-log sightings (knob block, switch k = 1, preset select) go in Notes as "seen in the app's log (2026-11-16)"
- [X] T033 [US2] Create `src/openvave/protocol/writes.py`: `WriteTarget` (closed constructors), `WriteMessage`, `WRITE_MESSAGES` mirroring T032, `sendable_by_default`, `rebuild_knob_block`, field→target mapping from `BYTE_MAP` (knobs offsets 4–17, switches 0–3 with on/off raw values, `led_colour`); add `build_write` and `parse_write_reply` to `src/openvave/protocol/commands.py`; export from `openvave.protocol`, until T021, T023, T024, T025 pass
- [X] T034 [US2] Extend `src/openvave/transport/fake.py` with `apply_writes: bool` (ACK allowlisted `0x22` writes and apply them to `memory`; preset select copies stored preset `i` into `0x10000000` and sets global bytes 1–2, optionally preceded by one `ff` slot read via a `select_transient` option) and scripted write replies through the existing `replies=` override (for NAKs)
- [X] T035 [US2] Add `WriteRefusedError` (subclass of `UnsafeCommandError`, exit 1, `.reason`), `WriteNakError` (subclass of `ProtocolError`, exit 7, `.reply`) and `WriteNotAppliedError` (exit 8, `.result`) to `src/openvave/errors.py`; map exit 8 in `src/openvave/cli/__init__.py` `_report`
- [X] T036 [US2] Add `WritePlan` and `WriteResult` to `src/openvave/models.py` per [data-model.md](data-model.md)
- [X] T037 [US2] Implement `TankG.plan_set(field, value)` and `TankG.set_field(field, value, *, experimental=False)` in `src/openvave/session.py`: one guarded path (read global → mode check → read edit buffer → build/validate → gate → send once → `parse_write_reply` → re-read edit buffer and global → `WriteResult`); never retries a write; until T027 passes
- [X] T038 [US3] Implement `TankG.plan_select(index)` and `TankG.select_preset(index, *, discard_edits=False, experimental=False)` in `src/openvave/session.py` using the same guarded path, with the 100 ms wait and up to 10 global reads 100 ms apart (injectable `sleep` like `watch`), until T028 passes
- [X] T039 [US2] Add `openvave set <field> <value>` (`--dry-run`, `--experimental`) to `src/openvave/cli/__init__.py` and plan/result rendering (human + JSON) to `src/openvave/cli/render.py`; value parsing: integers, `on`/`off`, `#rrggbb` / `r,g,b`, until T029 passes
- [X] T040 [US3] Add `openvave preset select <position>` (`--dry-run`, `--experimental`, `--discard-edits`) to `src/openvave/cli/__init__.py` with rendering, until T030 passes
- [X] T041 [P] [US2] Export `WritePlan`, `WriteResult`, `WriteRefusedError`, `WriteNakError`, `WriteNotAppliedError` from `src/openvave/__init__.py` and `WriteTarget`, `WRITE_MESSAGES`, `build_write`, `parse_write_reply` from `openvave.protocol`; extend `tests/contract/test_public_api.py`
- [X] T042 [P] [US2] Add `tests/hardware/test_hw_writes.py` skeleton: collected only with `--hardware` **and** `OPENVAVE_HW_WRITES=1` (skip otherwise, asserted by a unit test in `tests/unit/test_hw_markers.py`); contains gate helpers only (backup → plan → print frame → wait for explicit confirmation on stdin → write → report), no test sends a write without the stdin confirmation
- [X] T043 [US2] Update the CLI contract docs in `specs/001-readonly-ble-connection/contracts/cli.md` exit-code table with a pointer to exit 8 in `specs/003-preset-backup-edit-writes/contracts/cli.md` (no behaviour change for 001 commands)

### Live verification (milestone gate)

- [X] T044 Run `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check`, `uv run mypy src`; confirm T021–T030 failed before T031–T043; record counts and the audit result (no `0x21`, no `0x22` outside the allowlist) in the PR
  - Evidence (2026-11-17): before T031–T043, `test_writes.py`, `test_write_reply.py`,
    `test_writes_doc.py`, `test_write_gate.py`, `test_set_field.py` and `test_select_preset.py`
    failed at collection (`ImportError`: `WriteNakError`, `openvave.protocol.writes` missing);
    `test_frame.py`, `test_audit.py`, `test_cli_set.py`, `test_cli_select.py` gave 19 failed +
    14 errors. After: `uv run pytest` → 1013 passed, 5 skipped (M0: 823 passed, 4 skipped);
    `ruff check` → all checks passed; `ruff format --check` → 102 files already formatted;
    `mypy src` → no issues in 24 files. The session audit (`tests/conftest.py` →
    `tests/support/audit.py`, its own independent allowlist) passed with `0x22` frames sent by the
    integration/contract tests: none to `0xF0000000`, `0xD0000000`, `0x0`–`0x2F5`, no `0x21`.
    `pytest --hardware tests/hardware/test_hw_writes.py` without `OPENVAVE_HW_WRITES=1` → 1 skipped.
    Small additions beyond the contract, synced into `contracts/library-api.md` and
    `data-model.md`: `plan_set`/`plan_select` take `experimental`/`discard_edits`, so a dry run
    shows exactly the refusal the real call would raise; `WritePlan` also carries `confidence`
    and `field`; `encode_frame(0x22, body)` itself refuses non-allowlisted bodies; with `--json`
    an exit-8 failure leaves stdout empty (001 rule), and human output prints the not-applied result.
- [X] T045 Owner, hardware (dry-run only, no write): in edit mode run `uv run openvave set gain 90 --dry-run --trace` and `uv run openvave preset select 2C --dry-run --discard-edits --trace`; confirm the printed frames, `dry run: nothing sent`, and that the trace contains only `0x11`/`0x23`; leave edit mode without saving; record in the PR
  - Evidence, `set gain 90` (2026-11-17, fw 96, owner's terminal): global `00 00 01 00` (1B, mode
    0 = edit); edit buffer `00 00 00 01 0f 00 7f 00 00 00 00 00 00 00 00 05 04 07 43 16 43` (the
    owner's unsaved pedal edits: amp off, amp type 0, gain 127, treble…delay time 0). Output
    `Set gain 127 → 90   (current preset 1B, edit mode)`, frame `00 59 22 16 00 00 04 04 00 00
    10 0e 00 00 0f 00 5a 00 00 00 00 00 00 00 00 05 04 07 60`: the knob block rebuilt from the
    live buffer with only byte 6 changed (re-encoded independently, allowlisted by the audit).
    `refused: experimental_required`, `dry run: nothing sent`, stderr empty. Trace: one `0x11`,
    two `0x23`, no `0x22`. The refusal line read `… 'hypothesis' (--experimental))`; the wording
    is now `… is 'hypothesis'; needs --experimental`.
  - Evidence, `preset select 2C --dry-run --discard-edits --trace` (same session, still in edit
    mode, global `00 00 01 00`): `Select 2C (index 6)   from 1B`, frame `00 59 22 09 00 00 04 06
    00 00 e0 01 00 00 01 13` (byte-identical to the M1 vector and the app's documented shape),
    `refused: experimental_required (preset_select is 'hypothesis'; needs --experimental)`,
    `dry run: nothing sent`, stderr empty. `--discard-edits` cleared the
    `edits_would_be_discarded` refusal as designed. Trace: one `0x11`, two `0x23`, no `0x22`.
  - Owner note (2026-11-17): the phone app edits the pedal without entering edit mode, so the
    `not_edit_mode` refusal (FR-009) may be stricter than needed. Kept for M1; M2 adds one gate
    step that sends an approved knob write in normal mode and records mode/buffer before and
    after, so FR-009 can be relaxed on evidence.
- [X] T046 Owner, hardware: outside edit mode run `uv run openvave set gain 90 --dry-run`; confirm it prints the `not_edit_mode` refusal and exits 0; record in the PR
  - Evidence (2026-11-17, fw 96, owner's terminal, run with `--trace`): global read `00 00 01 01`
    (1B, mode 1 = normal), edit buffer = public 1B preset. Output `Set gain 60 → 90   (current
    preset 1B, normal mode)`, the planned frame `00 59 22 16 00 00 04 04 00 00 10 0e 00 00 0f 04
    5a 3c 46 32 32 00 00 00 00 05 04 07 76` (byte-identical to the M1 test vector),
    `refused: not_edit_mode (the pedal is not in edit mode)`, `dry run: nothing sent`, stderr
    empty. Trace: 3 TX frames, one `0x11` (handshake) and two `0x23` (global, edit buffer); no
    `0x22`. The exit status was not in the paste; the dry-run path returns 0.

**Checkpoint**: ✅ Milestone 1 DONE (2026-11-17) — every write path exists and is tested, nothing has been written to the pedal

---

## Milestone 2: Gate session A — first writes (US4 P1, evidence for US2/US3)

**Goal**: each write message is sent to the pedal once, with approval, backup and record; the
results move the "Write messages" rows to `observed` (or document a failure).

**Independent test criteria**:
- For every gate step: the PR quotes the owner's approval of that exact frame, cites a same-session
  pre-gate backup, and the post-gate backup equals it (SC-004).
- Each successful step yields a sanitized excerpt in `captures/fw96/` (write frame, reply, re-reads;
  only our own edit values and public presets) and a regression test that replays it.
- `test_writes_doc.py` passes with the promoted rows; nothing in the code path changed except
  `WRITE_MESSAGES` mirroring the doc.

### Tests (write first, must fail until the evidence exists)

- [X] T047 [P] [US4] Extend `tests/integration/fixture_pairs.py` (or a new `tests/integration/gate_fixtures.py`) with entries for the expected gate excerpts `captures/fw96/20261117-gate-<step>.jsonl` (steps: `knob_gain`, `switch_mod`, `switch_amp`, `switch_delay`, `switch_reverb`, `led_colour`, `select`); each test replays its excerpt through `FakeTransport.from_capture` and asserts ACK, `applied`, and the exact write frame; tests are marked `xfail(strict=True)` until the excerpt exists, then the marker is removed in the evidence commit
  - Done (2026-11-17): `tests/integration/gate_fixtures.py` (steps, `RECORDED` step → file) and
    `tests/integration/test_gate_replay.py`. Each excerpt's `meta.replay` names the library call
    (`set_field`/`select_preset`, always `experimental=True`); the replay must send exactly the
    recorded request sequence, its one write must equal an independent encoding
    (`write_fixture.write_frame`), reply = ACK, `applied`. A step joins `RECORDED` in its evidence
    commit; until then it is strict `xfail` (7 xfailed now). One write per excerpt: a step is
    undone by leaving edit mode without saving, not by a second write.
  - Tooling found missing while writing T047: `--trace` prints text (`TX`/`RX chunk`/`RX`) on
    stderr, while `tests/support/excerpt.py` only cuts `watch` JSONL records. Added
    `tests/support/gate_excerpt.py` (trace text → labelled JSONL, labels from frame bytes only)
    and `tests/unit/test_gate_excerpt_tool.py`: a round trip runs the real write path on the fake
    pedal with the trace logger on, converts the text, replays it with `from_capture` and gets the
    same frames and result (set gain / mod_on / led_colour, select).
- [X] T048 [P] [US4] Write `tests/unit/test_gate_excerpts.py`: every committed `captures/fw96/*-gate-*.jsonl` contains only allowlisted `0x22` frames, no device identifier/MAC, no stored-image read with more than the header + presets already public, and a meta line with firmware 96, date and step name
  - Done (2026-11-17): `problems()` checks meta (fw 96, ISO date, step == file name), the
    independent audit allowlist, no device-info/type-5 read, and stored reads limited to the
    header and presets already in the committed non-gate fw96 captures (1B, 1A, 1C, 1D, 2A, 9D
    as seen in the edit buffer). Exercised on synthetic excerpts (clean passes; non-public stored
    read, commit write, identifier read and step mismatch are each rejected); the per-file test
    is parametrized over `captures/fw96/*-gate-*.jsonl` (none yet → skipped). Consequence for
    T053: select only between public presets (1B ↔ 1A).

### Evidence gathering (pedal owner, hardware, one approval per step)

- [X] T049 [US4] Pre-session: owner runs `uv run openvave preset backup --output <pre>.json` (backup A0); researcher checks it equals the M0 gate backup apart from `created_at`
  - Evidence (2026-11-17 14:32:49Z, fw 96): `preset backup --output
    captures/private/20261117-gate-A0.json` → `36 presets, header a5 5a`, `Cross-check with
    whole-image read: OK`. Compared key by key with M0 run A (`/tmp/backup-a.json`, 13:34:18Z):
    the only difference is `created_at`; image and all 36 presets identical. (A first attempt from
    the Claude app's shell found no pedal; it worked once the pedal was on and the phone app closed.)
- [X] T050 [US4] Step `knob_gain`: researcher posts the frame from `openvave set gain <v> --dry-run` on the current preset and the expected result; **owner approves in chat**; owner, in edit mode, runs `uv run openvave set gain <v> --experimental --trace` with the record kept in `captures/private/`; then leaves edit mode without saving and runs `uv run openvave preset dump` (stored gain back)
  - Evidence (2026-11-17, fw 96, 1B, edit mode entered without moving a knob): dry run showed
    `Set gain 60 → 90`, frame `00 59 22 16 00 00 04 04 00 00 10 0e 00 00 0f 04 5a 3c 46 32 32 00
    00 00 00 05 04 07 76` (= M1 vector). Approval: the owner ran the exact posted command
    (`set gain 90 --experimental --trace 2> captures/private/20261117-gate-knob_gain.trace`)
    without a separate chat message; later steps get a written approval first. Result: reply
    `00 59 00 01 00 00 00 ff` (ACK), re-read edit buffer byte 6 `3c` → `5a`, nothing else changed,
    global `00 00 01 00` before and after, `applied`. After leaving edit mode without saving,
    `preset dump` showed gain 60 and the buffer equal to public 1B. Excerpt:
    `captures/fw96/20261117-gate-knob_gain.jsonl` (replay test green).
- Incident (2026-11-17, between T050 and T051, no openvave write involved): while practising how
  to leave edit mode, the owner used the pedal's own save once. Backup A1
  (`captures/private/20261117-gate-A1.json`) differs from A0 only in stored preset **1A** (14
  bytes): 1A now holds the 1B bytes (`01 00 00 01 0f 04 3c 3c 46 32 32 00 00 00 00 05 04 07 43 16
  43`); 1B and every other preset are unchanged. Finding: the pedal's save from 1B wrote to slot
  1A. Session paused: no further write until 1A is restored to its A0 bytes and a new backup
  equals A0 (SC-004 baseline stays A0).
  Resolved: restored 1A with the phone app (values from A0; app counts from 1); backup A6
  (`captures/private/20261117-gate-A6.json`) equals A0 apart from `created_at`. Session resumed
  with A6 as the same-session backup; SC-004 still compares against A0.
- Finding while restoring 1A with the phone app (2026-11-17, owner): the app shows reverb decay
  as three colour-coded sections (blue, orange, green), each 1–40, with an "X" past 40 —
  probably three reverb types sharing preset byte 15. Restores gave orange 13 → 55, orange 11 → 54, orange 9 →
  52, orange 10 → 53 (backups A3–A6): not linear, about 1 raw per 1–2 app steps, so the app scale and the byte do
  not map simply. The byte map still
  calls byte 15 `reverb_decay` (continuous 0–127). Follow-up, not in M2 scope: name the three
  reverb types (from the app's labels) and split byte 15 into type + decay in
  `specs/protocol/command-layer.md` / `bytemap.py`, with a labelled sweep as evidence.
  Similarly, the app counts amp type and knob values from 1 where the raw bytes count from 0.
- [X] T051 [US4] Steps `switch_mod`, then `switch_amp`, `switch_delay`, `switch_reverb`: same protocol as T050, one approval per step, toggling one block on then back to its stored state; note any co-moving knob bytes (expected pedal behaviour)
  - Evidence (2026-11-17, fw 96, 1B, edit mode entered without moving a knob, backup A6). Each
    step: dry run → frame posted → approval → one write → undo by leaving edit mode without saving.
    One write per step (the plan's "toggle back" is the no-save exit, not a second write).
    | step | approval | frame | reply | re-read | undo check |
    |---|---|---|---|---|---|
    | `switch_mod` (on) | "approve switch_mod" | `00 59 22 09 00 00 04 01 00 00 10 01 00 00 01 e8` | ACK | byte 1 `00`→`01` only, applied | dump: mod off, buffer = 1B |
    | `switch_amp` (off) | "approve switch_amp" | `00 59 22 09 00 00 04 00 00 00 10 01 00 00 00 ea` | ACK | byte 0 `01`→`00` only, applied | dump: amp on, buffer = 1B |
    | `switch_delay` (on) | "approve switch_delay" | `00 59 22 09 00 00 04 02 00 00 10 01 00 00 01 e7` | ACK | byte 2 `00`→`01` only, applied | next step's plan read = 1B (delay off) |
    | `switch_reverb` (off) | owner ran the posted command without a chat approval | `00 59 22 09 00 00 04 03 00 00 10 01 00 00 00 e7` | ACK | byte 3 `01`→`00` only, applied | pending (post-session backup) |
    ACK bytes `00 59 00 01 00 00 00 ff` every time; global `00 00 01 00` before and after.
    No co-moving knob bytes: a switch *write* does not copy knob positions into the buffer (the
    co-moving seen on 2026-11-16 came from the physical switch). Excerpts:
    `captures/fw96/20261117-gate-switch_{mod,amp,delay,reverb}.jsonl` (replay tests green).
- [X] T052 [US4] Step `led_colour`: same protocol with `set led_colour '#ff0000'`; owner reports whether the preset LED turned red (evidence for preset 18–20 = R, G, B)
  - Evidence (2026-11-17, 1B, edit mode, backup A6): approval "approve led_colour"; frame
    `00 59 22 0b 00 00 04 12 00 00 10 03 00 00 ff 00 00 d7`; reply ACK; re-read bytes 18–20
    `43 16 43` → `ff 00 00`, nothing else changed, applied. The plan read was stored 1B with
    reverb on, so the `switch_reverb` step had been undone. **LED not observable**: in edit mode
    the pedal's LEDs show the block colours (amp red, reverb purple, …), and leaving edit mode
    restores the buffer, so whether 18–20 drive the preset LED stays open (no byte map naming in
    M4 T066/T067 unless later evidence). Owner note: the phone app edits without entering edit
    mode, where the LED is visible; this joins the T045 note on relaxing `not_edit_mode` (FR-009)
    as a follow-up. Excerpt: `captures/fw96/20261117-gate-led_colour.jsonl`.
- [X] T053 [US4] Step `select`: same protocol, outside edit mode, `uv run openvave preset select <position> --experimental --trace` to a preset that differs from the current one; owner confirms the pedal display; then select back to the original preset (second approved write)
  - Evidence (2026-11-17, normal mode, backup A6), two steps, one write each, between presets
    already public (1B ↔ 1A) so the excerpts carry no factory content (T048):
    | step | approval | frame | reply | after |
    |---|---|---|---|---|
    | `select` 1B → 1A | owner ran the posted command without a chat approval | `00 59 22 09 00 00 04 00 00 00 e0 01 00 00 01 19` | ACK | first global read `00 00 00 01` (no `ff` transient), buffer = stored 1A = stored-preset read, applied; owner: display changed 1B → 1A |
    | `select_back` 1A → 1B | owner ran the posted command without a chat approval | `00 59 22 09 00 00 04 01 00 00 e0 01 00 00 01 18` | ACK | first global read `00 00 01 01`, buffer = stored 1B, applied |
    The plan read of `select` showed 1B with bytes 18–20 at `43 16 43`, so the `led_colour` step
    had been undone. Mode stayed 1 (normal) throughout. Excerpts:
    `captures/fw96/20261117-gate-select.jsonl`, `…-gate-select_back.jsonl` (`select_back` added
    to `gate_fixtures.SESSION_A`).
- [X] T054 [US4] Post-session: owner runs `uv run openvave preset backup --output <post>.json`; researcher confirms the presets are byte-identical to backup A0 (SC-004); any difference stops the milestone and is reported before anything else
  - Evidence (2026-11-17 15:20:57Z): `preset backup --output
    captures/private/20261117-gate-A-post.json` → `36 presets, header a5 5a`, cross-check OK.
    Compared key by key with A0 (14:32:49Z): the only difference is `created_at`; image and all 36
    presets byte-identical (SC-004). Display on 1B at the end.

### Recording findings

- [X] T055 [US4] Cut sanitized excerpts with `tests/support/gate_excerpt.py` (from the step's `--trace` stderr) into `captures/fw96/20261117-gate-<step>.jsonl` (one per successful step), remove the `xfail` markers of T047 for those steps
  - Done: eight excerpts `captures/fw96/20261117-gate-{knob_gain,switch_mod,switch_amp,
    switch_delay,switch_reverb,led_colour,select,select_back}.jsonl`, cut from the private
    `--trace` files with `tests/support/gate_excerpt.py`; all in `gate_fixtures.RECORDED`, no
    `xfail` left. Each holds only public presets (1B, 1A) and our own written values.
- [X] T056 [US4] Update `specs/protocol/command-layer.md` "Write messages" rows (→ `observed`, evidence = excerpt path, Notes = date/session/result), the ACK row (→ `observed`), the Address map confidences, "Write acknowledgement" (actual ACK bytes seen), and — if T052 confirmed the LED — the preset 18–20 byte map Notes; mirror in `src/openvave/protocol/writes.py` `WRITE_MESSAGES` in the same commit
  - Done: all eight "Write messages" rows `hypothesis` → `observed` (fw 96, evidence = the
    excerpts, Notes = session result); ACK row → `observed` (cites `knob_gain` and `select`);
    Address map rows for `0x10000000+k`, `0x10000004`, `0x10000012`, `0xE0000000+i` updated;
    "Write acknowledgement" records the bytes seen; "Preset LED colour" records that the LED could
    not be judged. `WRITE_MESSAGES` mirrors the table (`_observed` rows; unused `_hypothesis`
    helper removed). Tests that pinned the old `hypothesis` state (`test_write_gate`,
    `test_writes_doc` altered-doc check, `test_cli_set`, `test_set_field`) now pin `observed`;
    behaviour is unchanged (every write still needs `--experimental`; nothing is `confirmed`).
- [X] T057 [US4] Document any failed or surprising step (NAK bytes, not applied, side effects) in `command-layer.md` with its record path, and keep that message's confidence unchanged
  - No NAK, timeout or not-applied step. Surprises, recorded above and in `command-layer.md`:
    (1) the owner's pedal save (no openvave write) wrote 1B's buffer into slot **1A**; restored
    via the phone app, verified by backups A1–A6; (2) the LED meaning of 18–20 is not observable
    in edit mode; (3) neither select showed the `ff` loading read the app's log had; (4) switch
    writes do not co-move knob bytes. Process note: four of the eight writes (`knob_gain`,
    `switch_reverb`, `select`, `select_back`) were sent by the owner running the exact posted
    command without a separate chat approval; each followed a matching dry run and a posted
    approval request. Follow-ups, out of M2 scope: name the three reverb types sharing byte 15
    (app shows blue/orange/green sections, 1–40 each); writes outside edit mode (the app does
    this; would relax FR-009 and allow judging the LED).

### Live verification (milestone gate)

- [X] T058 Run the full suite (T047/T048 green, no `xfail` left for completed steps) and record per step: approval quote, frame, reply, applied, post-gate backup equality
  - Evidence (2026-11-17): `uv run pytest` → 1056 passed, 5 skipped, 0 xfailed (M1: 1013
    passed); `tests/integration/test_gate_replay.py` 8/8 green, `tests/unit/test_gate_excerpts.py`
    clean for all eight excerpts; `ruff check` all passed; `ruff format --check` 107 files
    formatted; `mypy src` no issues in 24 files. Per step (approval, frame, reply, applied): see
    T050–T053; post-gate backup = A0 (T054).

**Checkpoint**: ✅ Milestone 2 DONE (2026-11-17) — every in-scope write has been sent once on hardware with evidence

---

## Milestone 3: Gate session B — confirmations (US4)

**Goal**: an independent second session promotes the knob block and preset select (and any other
approved write) to `confirmed`, which lifts the `--experimental` requirement for them.

**Independent test criteria**:
- Session B uses a new connection, a different stored preset as the starting point, and its own
  pre/post backups; promoted rows cite excerpts from two distinct sessions.
- `openvave set gain <v>` (no `--experimental`) is accepted by the gate in tests for fw 96 once the
  knob block and ACK rows are promoted; other rows still require the flag.

### Tests (write first, must fail)

- [X] T059 [P] [US4] Extend `tests/unit/test_write_gate.py`: with the real `WRITE_MESSAGES`, `sendable_by_default("knob_block", None, 96)` and `sendable_by_default("preset_select", <any>, 96)` are true, firmware 97 false, rows left `observed` false (fails until T062)
  - Done (2026-11-17): `test_session_b_rows_are_sendable_on_fw96` (knob block; select 0, 6, 35)
    is strict `xfail` until T062; fw 97 refused and "a row not `confirmed` needs the opt-in"
    pass now and must keep passing after the promotion.
- [X] T060 [P] [US4] Add session-B gate fixtures to `tests/integration/gate_fixtures.py` (`20261118-gate-knob_<field>.jsonl`, `20261118-gate-select.jsonl`, dates adjusted to the actual session), `xfail(strict=True)` until committed
  - Done (2026-11-17): `GateStep.session` (`A`/`B`), `SESSION_B` = `knob_treble` (offset 7),
    `select_b`, `select_b_back`; `test_gate_replay.py` runs `ALL_STEPS` (3 new strict `xfail`).
    Step names differ from session A's so both sessions' excerpts can share a date if session B
    runs the same day. Suite: 1067 passed, 5 skipped, 7 xfailed.

### Evidence gathering and recording

- [X] T061 [US4] Owner, hardware, with per-step approval as in T050: pre-backup → knob block write on another knob (e.g. `treble`) on another preset → select to another preset and back → post-backup equality; optionally repeat switch and LED steps the owner approves
  - Evidence (2026-11-17, fw 96, a new connection per command, ~16:36–16:42Z):
    - Backup B0 (`captures/private/20261117-gate-B0.json`, 16:36:22Z): 36 presets, cross-check
      OK, equal to A0 apart from `created_at`.
    - Starting preset: 1C was proposed, but stored 1C is byte-identical to 1B (session A's
      preset), so session B moved to **1D** (public, different content: all blocks on, treble 43).
      A first attempt to run the write with a literal `<v>` placeholder failed in zsh before
      openvave started (no frame sent, no trace file).
    - `knob_treble` (1D, edit mode, global `00 00 03 00`): dry run `Set treble 43 → 90`, frame
      `00 59 22 16 00 00 04 04 00 00 10 0e 00 00 40 05 64 5a 58 53 40 14 29 0f 35 09 05 04 58`
      (= independent encoding from stored 1D in B0). Approval: the owner ran the exact posted
      command without a written "approve knob_treble" (same process gap as in session A). Reply
      `00 59 00 01 00 00 00 ff` (ACK); re-read: byte 7 `2b` → `5a` only; global unchanged; applied.
      Undo: left edit mode without saving; `preset dump` showed treble 43 and the buffer equal to
      stored 1D (`01 01 01 01 40 05 64 2b 58 53 40 14 29 0f 35 09 05 04 77 b3 b3`).
    - `select_b` (1D → 1A, normal mode, global `00 00 03 01`): dry run frame
      `00 59 22 09 00 00 04 00 00 00 e0 01 00 00 01 19` (same frame as session A's select to 1A;
      only the starting preset differs). Approval: the owner ran the exact posted command without
      a written "approve select_b". Reply ACK; first global read `00 00 00 01` (no `ff`
      transient), buffer = stored 1A = stored-preset read of 1A, applied.
    - `select_b_back` (1A → 1D, normal mode): dry run frame
      `00 59 22 09 00 00 04 03 00 00 e0 01 00 00 01 16` (= independent encoding, index 3).
      Approval: the owner ran the exact posted command without a written "approve select_b_back".
      Reply ACK; global `00 00 00 01` → `00 00 03 01`, buffer = stored 1D = stored-preset read,
      applied. The owner's display readings (1A, then 1D) were asked for but not recorded.
    - Backup B-post (`captures/private/20261117-gate-B-post.json`, 16:42:12Z): 36 presets,
      cross-check OK, equal to B0 **and** A0 apart from `created_at` (SC-004).
    - Switch and LED steps were not repeated: those rows stay `observed`.
    - Process: none of the three writes had a written approval line in chat before it ran; each
      was the exact command posted after a matching dry run and a posted approval request.
- [X] T062 [US4] Cut excerpts, promote rows with two sessions to `confirmed` in `specs/protocol/command-layer.md` "Write messages" and `WRITE_MESSAGES`, remove `xfail` markers; record fw 96 as the covered firmware
  - Done: excerpts `captures/fw96/20261117-gate-{knob_treble,select_b,select_b_back}.jsonl` (cut
    with `tests/support/gate_excerpt.py`; only presets 1D and 1A, both public, and our own value);
    `SESSION_B_DATE` = 20261117, all in `RECORDED`, no `xfail` left. Promoted to `confirmed`
    (fw 96): `knob_block` (knob_gain + knob_treble), `preset_select` (select, select_back,
    select_b, select_b_back), `ack`; Address map rows `0x10000004` and `0xE0000000 + i` and
    "Write acknowledgement" updated. Block switches and LED colour stay `observed`.
    New guard `test_confirmed_rows_cite_two_gate_sessions` (`test_writes_doc.py`): a confirmed row
    must cite excerpts from sessions A **and** B, not just two files. Tests that pinned
    "everything needs `--experimental`" now use an `observed` field (`mod_on`, `led_colour`) for
    the refusal and assert that gain / select run without the flag.

### Live verification (milestone gate)

- [X] T063 Run the full suite; record which rows are `confirmed` / `observed` (SC-005)
  - Evidence (2026-11-17): `uv run pytest` → 1085 passed, 5 skipped, 0 xfailed; gate replay
    11/11, `test_gate_excerpts` clean for all eleven excerpts; `ruff check` passed; `ruff format
    --check` 107 files formatted; `mypy src` no issues in 24 files. Confirmed (fw 96):
    `knob_block`, `preset_select`, `ack`. Observed: `block_switch(0–3)`, `led_colour`.
- [X] T064 Owner, hardware (approval required, it is still a write): one `uv run openvave set gain <v>` **without** `--experimental` on fw 96 succeeds; leave edit mode without saving; record
  - Evidence (2026-11-17, fw 96, 1D, edit mode, global `00 00 03 00`, after commit 6e1e42c):
    dry run without the flag `Set gain 100 → 70`, frame `00 59 22 16 00 00 04 04 00 00 10 0e 00 00
    40 05 46 2b 58 53 40 14 29 0f 35 09 05 04 a5` (= independent encoding), **no refusal line**.
    Approval: the owner ran the exact posted command without a written "approve T064". Run
    `set gain 70 --trace` (no `--experimental`; raw trace
    `captures/private/20261117-gate-T064.trace`): reply ACK, re-read byte 6 `64` → `46` only,
    global unchanged, applied, exit 0.
    Undo: left edit mode without saving; `preset dump` showed gain 100 and the buffer equal to
    stored 1D. No pedal save was used at any point in session B.

**Checkpoint**: ✅ Milestone 3 DONE (2026-11-17) — confirmed writes run by default; the rest stays behind `--experimental`

---

## Milestone 4: Release 0.3.0 + Polish

**Goal**: ship 0.3.0 with docs that let a user back up first and write safely.

### Tests (write first, must fail)

- [X] T065 [P] Extend `tests/contract/test_changelog_renames.py` (or a new `tests/contract/test_changelog_030.py`): `CHANGELOG.md` has a `0.3.0` section listing `preset backup`, `set`, `preset select`, exit code 8, the `0x22` allowlist and (if named) the new byte map names; `openvave --version` reports `0.3.0`
  - Done (2026-11-17): new `tests/contract/test_changelog_030.py` (commands, `--dry-run`,
    `--experimental`, exit code 8, `0x22` and the four allowlisted targets, `0x21`/`0xF0000000`
    never sent, nothing left under `[Unreleased]`, `__version__` = `pyproject.toml` = 0.3.0,
    `openvave --version`). Failed 15/15 before T069. The 0.2.0 version pin in
    `test_changelog_renames.py` became "the 0.2.0 section is kept". No new byte map names (T066).
- [X] T066 [P] If M2 observed the LED colour: extend `tests/unit/test_bytemap.py` expectations for preset 18–20 named `led_red`, `led_green`, `led_blue` (`continuous`, 0–255, `observed`, evidence = the `led_colour` gate excerpt); otherwise skip this task and record why
  - Skipped (2026-11-17): M2 observed the `led_colour` **write** (ACK, bytes 18–20 changed) but not
    the LED: in edit mode the pedal's LEDs show block colours, and leaving edit mode restores the
    buffer (T052). That 18–20 drive the preset LED stays a hypothesis, so they stay unnamed.

### Implementation

- [X] T067 Name preset 18–20 in `specs/protocol/command-layer.md` byte map and `src/openvave/protocol/bytemap.py` per T066 (additive; `schema_version` stays 2)
  - Skipped with T066 (no naming without evidence); byte map and `bytemap.py` unchanged.
- [X] T068 [P] Update `README.md`: backup-first workflow, `preset backup`, `set`, `preset select`, `--dry-run`, `--experimental`, "nothing is saved — leave edit mode without saving to undo", exit codes, the unofficial disclaimer unchanged
  - Done: Status rewritten for 0.3.0; new sections `openvave preset backup` and "Writing to the
    pedal" (backup → edit mode → `--dry-run` → run → leave edit mode without saving; field table;
    `--discard-edits`; ACK + re-read, no retries; `--experimental` and which rows are confirmed);
    exit codes 1/7/8 extended; links to the 003 CLI, JSON and library contracts. Examples match
    `cli/render.py`. Disclaimer line unchanged.
- [X] T069 [P] Update `CHANGELOG.md` (0.3.0) and bump the version in `pyproject.toml` and `src/openvave/__init__.py`, until T065 passes
  - Done: `CHANGELOG.md` `[0.3.0]` (Added: backup, set, select, `--dry-run`, `--experimental`,
    exit code 8, JSON, library, plus the reverb sections entry moved from Unreleased; Changed: the
    `0x22` allowlist and what stays unencodable; Tested). Version 0.3.0 in `pyproject.toml`,
    `src/openvave/__init__.py` and `uv.lock`. T065 passes (19/19 with the renames test).
- [X] T070 [P] Update `captures/README.md`: the gate excerpt format (`*-gate-<step>.jsonl`: meta with firmware/date/step, write frame, reply, re-reads), the synthetic stored-image fixture, and the rule that real stored images stay in `captures/private/`
  - Done: `captures/README.md` table row for `fw96/20261117-gate-<step>.jsonl`, new sections
    "Gate excerpts (writes)" (meta incl. `replay`, frame order, labels from bytes, cutting with
    `tests/support/gate_excerpt.py`, what `test_gate_excerpts.py` checks) and "Stored image and
    backups" (synthetic fixture; real images, backups and raw traces stay in `captures/private/`).

### Live verification (milestone gate)

- [X] T071 Run the full suite, ruff, format check, mypy; record counts
  - Evidence (2026-11-17): `uv run pytest` → 1120 passed, 5 skipped, 0 xfailed (M3: 1085);
    `ruff check .` all passed; `ruff format --check .` 110 files formatted; `mypy src` no issues in
    24 files; `uv run openvave --version` → `openvave 0.3.0`. Quickstart §1 (offline) passes.
- [X] T072 Owner, hardware: run [quickstart.md](quickstart.md) §1–§5 end to end (writes approved per step); review SC-001…SC-007 in the PR with evidence links
  - Evidence (2026-11-17, fw 96, 0.3.0 at 18b2dec, a new connection per command, ~17:03–17:09Z;
    raw files `captures/private/20261117-T072-*`):
    - §1: `uv run pytest` 1120 passed, 5 skipped (T071).
    - §2: backup A (17:03:58Z) and backup B (17:04:09Z, `--trace`): 36 presets, header `a5 5a`,
      cross-check OK, exit 0; A = B apart from `created_at` (SC-002); B's trace: one `0x11`, 38
      `0x23`, no write (SC-001). A also equals session B's `gate-B-post` apart from `created_at`
      and `tool`: no stored change since M3.
    - §3 (no `--experimental`): `set gain 90 --dry-run` on 1D, edit mode → `Set gain 100 → 90`,
      frame `00 59 22 16 00 00 04 04 00 00 10 0e 00 00 40 05 5a 2b 58 53 40 14 29 0f 35 09 05 04
      91`, no `refused:` line; `preset select 2C --dry-run --discard-edits` → frame `00 59 22 09 00
      00 04 06 00 00 e0 01 00 00 01 13` (= the CLI contract example). Both traces: `0x11` + two
      `0x23` only.
    - Refusal on hardware (bonus): the first `set gain 90` ran in normal mode (global `00 00 03
      01`) → `refused (not_edit_mode)`, exit 1, no `0x22` in the trace.
    - §4 `set_gain` (1D, edit mode `00 00 03 00`, no `--experimental`): the dry-run frame, reply
      `00 59 00 01 00 00 00 ff` ACK, re-read byte 6 `64` → `5a` only, global unchanged, applied.
      Undo: a first `preset dump` still showed gain 90 (taken before the pedal had left edit
      mode); after leaving edit mode without saving, the buffer = stored 1D (gain 100).
    - §4 `select_2c` (1D → 2C, normal mode): one write (the dry-run frame), ACK, first global read
      `01 01 02 01` (2C, no `ff` transient), buffer = stored-preset read at `0x80` = 2C in backup
      A, applied.
    - §4 `select_back` (2C → 1D): frame `00 59 22 09 00 00 04 03 00 00 e0 01 00 00 01 16` (= session
      B's), ACK, global `00 00 03 01`, buffer = stored read at `0x41` = 1D, applied.
    - Post backup (17:09:18Z): 36 presets, cross-check OK, equal to backup A apart from
      `created_at` (SC-004). No pedal save was used.
    - Process: none of the three writes had a written approval line in chat before it ran; each
      was the exact command posted after a matching dry run and an approval request (the same
      gap as sessions A and B). Display: the owner confirmed in chat that the pedal showed 2C after
      `select_2c` and 1D after `select_back`.
  - SC review:
    - SC-001 ✅ one command, zero write frames (B's trace); duration 8.8 s end to end measured in
      M0 T019 (not re-timed here).
    - SC-002 ✅ A = B (and = M3's B-post) apart from `created_at`.
    - SC-003 ✅ offline: dry-run frames == sent frames for every write action (M1 tests); on
      hardware all three T072 writes sent the dry-run frame byte for byte.
    - SC-004 ✅ post = A here; A0 = A-post (M2 T054), B0 = B-post (M3 T061).
    - SC-005 ✅ knob block, preset select, ACK `confirmed` (fw 96, sessions A and B); block
      switches 0–3 and LED colour `observed`.
    - SC-006 ✅ offline NAK/not-applied tests exit 7/8 with raw bytes; no NAK or not-applied
      occurred on hardware in any session.
    - SC-007 ✅ 1120 passed, 5 skipped, no hardware.

**Checkpoint**: ✅ Milestone 4 DONE (2026-11-17) — 0.3.0 ready to release (quickstart passed on hardware; tag after the PR merges)

---

## Dependencies & Execution Order

### Milestone dependencies

- **M0** (backup): no dependency; blocks everything (the backup is required before any write).
- **M1** (write path): needs M0 (`FakeTransport.memory`, storage reads for select verification).
- **M2** (gate A): needs M1's gate (dry runs verified on hardware).
- **M3** (gate B): needs M2; must be a separate session.
- **M4** (release): needs M3 (confidences final, names decided).

### Within each milestone

- Tests first and failing (T001–T007, T021–T030, T047–T048, T059–T060, T065–T066).
- Docs row + code mirror + fixture + passing test in the same commit (T032/T033, T056, T062).
- No hardware write before its in-chat approval; live verification closes the milestone and the PR
  description records the gate evidence.

### Story dependencies

- US1 is independent and is the MVP.
- US2 and US3 share the guarded write path (T031–T038); US3's CLI (T040) can follow US2's (T039).
- US4 depends on US2/US3 code and supplies their evidence.

### Parallel opportunities

- M0: T001–T007 in parallel; T016 after T013.
- M1: T021–T030 in parallel; T041, T042 after T037; T039 and T040 touch the same CLI files — do them
  sequentially.
- M2: T047/T048 while the owner prepares the session; evidence steps are strictly sequential.
- M4: T065/T066 in parallel; T068/T069/T070 in parallel.

## Parallel Example: Milestone 0 (US1)

```bash
# Tests first, together:
Task: "Storage layout and StorageRead tests in tests/unit/test_storage.py"
Task: "Storage read builder/parser tests in tests/unit/test_commands.py"
Task: "Synthetic image fixture tests in tests/unit/test_storage_fixture.py"
Task: "FakeTransport memory/split tests in tests/unit/test_fake_transport.py"
Task: "TankG.backup integration tests in tests/integration/test_backup_session.py"
Task: "Backup document tests in tests/unit/test_backup_document.py"
Task: "CLI preset backup contract tests in tests/contract/test_cli_backup.py"
```

## Implementation Strategy

### MVP first

1. M0 → `openvave preset backup`. **Stop and validate** on hardware: the owner has a verified,
   repeatable backup of all 36 presets, and nothing else is needed for that value.

### Incremental delivery

- M1 adds the write commands but leaves them unusable without `--experimental` and approval.
- M2/M3 turn each write into evidence; each promoted row relaxes the gate for that write only.
- M4 releases 0.3.0. Stored-slot writes, the save commit and restore stay for a later spec behind
  an unsafe opt-in.
