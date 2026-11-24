---

description: "Task list for 002 preset and global byte map (read-only decoding)"
---

# Tasks: Preset and global byte map (read-only decoding)

**Input**: Design documents from `specs/002-preset-byte-map/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md),
[data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: MANDATORY. Constitution III requires capture-based tests for every decoder/parser,
written first and failing before the implementation. Spec FR-020/FR-021 require one real
before/after fixture pair per mapped field and a hardware-free default suite. Every test task
precedes the code it covers.

**Organization**: one milestone per PR, as in the plan's Delivery Plan. M0 (decoder) is the
foundation. M1 delivers US1 (`watch`). M2/M3 are **evidence milestones**: the pedal owner runs
`watch` on hardware, and the PR carries docs + map rows + fixtures + tests together (US2, with
US3 output growing additively, and US4). M4 is the release.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1–US4 from spec.md
- Paths are relative to the repository root (single Python package, `src/` layout)

## Global rules for every task

- Only command bytes `0x11` and `0x23` and only the four 001 `Region`s may be used (FR-002,
  FR-019). No task adds a write, erase, raw-send or address-based read. The session-wide
  SC-004 audit in `tests/conftest.py` must keep passing.
- Fixtures come only from `captures/` via `tests/support/captures.py`. Changed-data sequences
  before the first real `watch` record exists are built with documented mutations in
  `tests/support/mutations.py` (checksum recomputed), never typed by hand.
- **Docs first**: a byte map row lands in `specs/protocol/command-layer.md` and
  `src/openvave/protocol/bytemap.py` in the same commit. `tests/unit/test_bytemap_doc.py`
  enforces equality (research R1).
- Docs record findings, not procedure (FR-008). Raw records stay in `captures/private/`
  (git-ignored). Committed excerpts follow [contracts/session-record.md](contracts/session-record.md).
- Hardware steps are done by the **pedal owner** in their own terminal (Bluetooth permission,
  phone app disconnected). Agent sessions launched from the desktop app are killed by macOS TCC
  on Bluetooth access.
- JSON stays `schema_version` 1 and additive until M4 (research R8).

---

## Delivery Plan

| PR | Milestone | Stories | Tasks | Gate |
|---|---|---|---|---|
| 1 | Milestone 0: Byte map model & decoder | US3 (base) | T001–T016 | Suite green; decoder reproduces today's 5 fields from the fw96 capture; doc table parses and equals `BYTE_MAP` |
| 2 | Milestone 1: `openvave watch` (US1) 🎯 MVP | US1 | T017–T034 | Fake-transport watch tests green; owner's reverb-decay-only session shows only `preset[15]` → byte 15 `confirmed` |
| 3 | Milestone 2: Front-panel mapping campaign (US2, US3) | US2, US3 | T035–T046 | SC-001, SC-003, SC-004; every `observed` row cites a single-step fixture |
| 4 | Milestone 3: Preset comparison, status byte, confirmations (US4, US2) | US4, US2 | T047–T056 | SC-002, SC-008; status byte documented or explicitly unknown |
| 5 | Milestone 4: Release 0.2.0 (US3) + Polish | US3 | T057–T066 | SC-005, SC-007 on hardware/review; quickstart passes; `schema_version` 2 |

Projected PR count: **5** (≤ 8). If M2 is too large to review, it splits by control group
(amp/drive · modulation/delay · reverb/cab · switches), and the total stays ≤ 8. Milestone N+1
starts only after Milestone N's gate passes.

---

## Milestone 0: Byte map model & decoder (Foundational, US3 base)

**Goal**: a single, doc-checked byte map covering all 26 bytes and a pure decoder. `preset dump`
and `info` render decoded fields from it, with additive JSON.

**Independent test criteria**:
- `decode_region` on the fw96 capture's preset reply yields exactly `knob_unknown=60 (observed)`,
  `reverb_decay=5 (observed)`, `reverb_mix=4 (hypothesis)`, `ir_cab=#7 (hypothesis)`, and
  `unknown_offsets` = the other 17 offsets. On the global reply it yields
  `not_in_edit_mode=on (observed)` and unknown 0–2. On status it yields unknown 0.
- `BYTE_MAP` covers all 26 offsets with no overlap, and equals the parsed `command-layer.md`
  table.
- Every existing 001 contract test passes unchanged. The new JSON keys validate against
  `decoded-field.schema.json`.

### Tests for the foundation (write first, must fail)

- [X] T001 [P] Write `tests/unit/test_bytemap.py`: for `GLOBAL`, `CURRENT_PRESET`, `STATUS`, every offset `0…length−1` is covered (26 in total); whole-byte entries never share an offset; `flag` entries on one offset have disjoint non-zero masks; `(region, name)` unique among named entries; `name is None` iff `encoding == UNKNOWN`; `continuous`/`selector`/`index` have `min ≤ max`; `switch` has `on_value != off_value`; `observed` entries have ≥ 1 evidence path that exists under `captures/`; `confirmed` entries cite paths from ≥ 2 distinct files; `DEVICE_INFO` has no entries; `MAP_FIRMWARE == 96`
- [X] T002 [P] Write `tests/unit/test_decode.py` with the fw96 capture reads (via `tests/support/captures.py`): the criteria above; `display` per encoding (`"60"`, `"on"`/`"off"`, `"#7"`, raw hex `"0x0f"` never emitted for named fields); `flag` value = `raw & mask`; an out-of-range byte (preset 15 set to `0x80` via a mutation helper) → `out_of_range` True, `display` shows the raw value, no clamping; `decode_region(read, firmware=97)` → same fields, `firmware_untested` True, `map_firmware` 96; `DEVICE_INFO` read → no fields, 32 unknown offsets; `diff(before, after)` returns one `ByteChange` per differing offset in offset order, with `field` set for named bytes and `None` for unknown ones, and an empty tuple for identical reads
- [X] T003 [P] Write `tests/support/bytemap_doc.py` (parser) and `tests/unit/test_bytemap_doc.py`: locate the table under the heading `### Preset / global byte map` in `specs/protocol/command-layer.md`; parse rows with columns `Region | Offset | Mask | Name | Encoding | Range | Control | Confidence | Firmware | Evidence | Notes`; assert the set of `(region, offset, mask, name, encoding, min, max, confidence, firmware, evidence)` equals the one derived from `BYTE_MAP`; a deliberately altered copy of the table (in-test string edit) makes the comparison fail with a message naming the differing row
- [X] T004 [P] Extend `tests/contract/test_cli_preset_dump.py` and `tests/contract/test_cli_info_regions.py`: human `preset dump` prints one line per named field in the format of [contracts/cli.md](contracts/cli.md) (`[15] reverb decay … 5 … 0–127 … observed`), hypothesis rows end with ` ?`, then `unknown: 0 1 2 3 4 5 7 8 9 10 11 12 13 14 18 19 20`; `info` shows decoded lines under Global and Status only; every `fields[]` item validates against `specs/002-preset-byte-map/contracts/decoded-field.schema.json`; each region has `map_firmware` 96 and `unknown_offsets`; `schema_version` still 1; with a fw-97 identity the region headers end with `(decoded with the fw 96 map)`
- [X] T005 [P] Write `tests/unit/test_mutations.py` cases for a new helper `with_region_data(frame, offset, value)` in `tests/support/mutations.py`: it rewrites one data byte of a read reply and recomputes the checksum, the result decodes with `decode_frame`, and an offset beyond the data raises `ValueError`

### Implementation

- [X] T006 Rewrite the table in `specs/protocol/command-layer.md` "Preset / global byte map (in progress)" to the R1 columns: one row per offset for preset 0–20, global 0–3 and status 0 (26 rows). Keep today's knowledge (preset 6/15/16/17, global 3) with its confidence and evidence (`captures/fw96/20261116-probe-connect.jsonl` plus the dated notes). Every other row has Encoding `unknown`, Name `—`, and its fw96 value in Notes. Keep the edit-mode experiment and refutation note below the table
- [X] T007 Add `Encoding`, `ByteMapEntry`, `DecodedField`, `DecodedRegion`, `ByteChange` to `src/openvave/models.py` per [data-model.md](data-model.md). Replace `FieldSpec`/`KNOWN_FIELDS` with deprecated aliases derived from `BYTE_MAP` (same names and labels as 001 so existing callers keep working)
- [X] T008 Create `src/openvave/protocol/bytemap.py`: `MAP_FIRMWARE = 96` and `BYTE_MAP: tuple[ByteMapEntry, ...]` mirroring T006 row for row, until T001 and T003 pass
- [X] T009 Create `src/openvave/protocol/decode.py`: pure `decode_region(read, firmware) -> DecodedRegion` and `diff(before, after) -> tuple[ByteChange, ...]`, no I/O and no logging. Export both plus `BYTE_MAP`, `MAP_FIRMWARE` from `src/openvave/protocol/__init__.py`, until T002 passes
- [X] T010 Add `with_region_data` to `tests/support/mutations.py` until T005 passes
- [X] T011 Update `src/openvave/cli/render.py`: `field_lines`/`region_json` use `decode_region` (human columns, ` ?` for hypothesis, `OUT OF RANGE`, `unknown:` line, fw-96-map note; JSON keys `raw`, `mask`, `encoding`, `range`, `display`, `interpreted`, `out_of_range`, region `map_firmware`, `unknown_offsets`), until T004 passes
- [X] T012 [P] In `tests/contract/test_cli_info_regions.py` and `tests/contract/test_cli_preset_dump.py` (which load the 001 schemas from `specs/001-readonly-ble-connection/contracts/`), also validate every `fields[]` item against `specs/002-preset-byte-map/contracts/decoded-field.schema.json`; leave the 001 schema files unchanged (additive keys are already allowed by `additionalProperties: true`)
- [X] T013 [P] Export the new public types from `src/openvave/__init__.py` and extend `tests/contract/test_public_api.py` with `Encoding`, `ByteMapEntry`, `DecodedField`, `DecodedRegion`, `ByteChange`

### Live verification (milestone gate)

- [X] T014 Run `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check`, `uv run mypy src`; record counts in the PR
  - Evidence (2026-11-16): pytest 539 passed, 3 skipped (hardware); ruff check clean; 67 files formatted; mypy strict: no issues in 18 source files. Tests T001–T005 were run first and failed (3 collection errors + 19 failures) before T006–T013
- [X] T015 Run quickstart §2 (offline decode) and paste the output in the PR
  - Evidence: `[('knob_unknown', '60', 'observed'), ('reverb_decay', '5', 'observed'), ('reverb_mix', '4', 'hypothesis'), ('ir_cab', '#7', 'hypothesis')]`
- [X] T016 Owner, hardware (optional for this gate): `uv run openvave preset dump` shows the decoded lines with the same values as the hex; record in the PR
  - Not run: needs the pedal owner's terminal (Bluetooth permission). The same render path is covered over the fw96 capture by `tests/contract/test_cli_preset_dump.py::test_human_block`
  - Closed 2026-11-24 with later evidence: spec 003 T050 (2026-11-17, fw 96, owner's terminal) ran `preset dump` on hardware and it showed gain 60 (hex `3c`) with the buffer equal to the public 1B bytes; spec 004 T022 (2026-11-17) read MOD FX and DLY MIX positions with `preset dump` (`captures/fw96/20261117-knob-types-app.jsonl`)

**Checkpoint**: Milestone 0 DONE ✅ (2026-11-16; optional hardware check T016 left to the owner)

---

## Milestone 1: `openvave watch`, map one control per step (US1, P1) 🎯 MVP

**Goal**: an explicit, read-only `openvave watch` that polls global/preset/status, prints and
records per-byte changes with stdin labels, and stops cleanly. The library exposes
`TankG.watch()`.

**Independent test criteria**:
- Over a `FakeTransport` replaying a sequence where only preset byte 15 changes (5 → 64 → 127),
  `TankG.watch(sleep=no_sleep, cycles=4)` yields one `WatchStart`, then two `WatchChange`s,
  each with exactly one `ByteChange` at `(CURRENT_PRESET, 15)`. Only `0x11`/`0x23` frames are
  sent, and the frames of each cycle are global → preset → status.
- A cycle where preset 16 and 17 change together → one `WatchChange` with two changes. The CLI
  prints `(co-moving: 2)`.
- CLI with stdin `"reverb decay min→max\n"` then `"q\n"`: the record file has `meta`, the
  handshake, `tx`/`rx` per cycle, one `label`, `change` events tagged with that label, and a
  `stop` with reason `quit`. Exit 0.
- A connection lost mid-watch → exit 6. The record ends with `stop` reason `connection_lost`
  and holds every event seen before.

### Tests for User Story 1 (write first, must fail)

- [X] T017 [P] [US1] Write `tests/unit/test_fake_sequence.py`: a `FakeTransport` built from a capture with several `rx` lines for the same label serves them in order and then repeats the last; `from_capture` on the 001 capture behaves exactly as before (one reply per label); `split`/`drop`/`disconnect_after` still apply per request
- [X] T018 [P] [US1] Extend `tests/unit/test_captures.py` for `load_capture` on a file with repeated labels: `rx_all(label)` returns all replies in order, and `tx(label)`/`rx(label)` keep returning the first for compatibility
- [X] T019 [P] [US1] Write `tests/integration/test_watch_session.py` over `FakeTransport` built with `with_region_data` sequences from the fw96 capture: the criteria above; `interval < 0.2` → `ValueError`; `regions` containing `DEVICE_INFO` → `ValueError`; the default regions are global, preset, status, and device info is never read during watch; with an injected `sleep` that records its arguments, an overrunning cycle triggers no sleep and no overlap (one request in flight); `ConnectionLostError` propagates out of the iterator and the transport is closed on leaving `async with`
- [X] T020 [P] [US1] Write `tests/contract/test_cli_watch.py` calling `openvave.cli.main(["watch", ...], transport_factory=..., stdin=io.StringIO(...), clock=...)`: human output lines per [contracts/cli.md](contracts/cli.md) (start block, `── label: … ──`, `+N.NNs  preset[15]  reverb decay  5 → 64`, co-moving marker, final summary); `--json` emits JSON Lines, each validating `specs/002-preset-byte-map/contracts/watch-event.schema.json`, first `start`, last `stop`; `--duration 1` with empty stdin → `stop` reason `duration`, exit 0; `q` and `quit` stop; EOF on stdin does not stop; `--interval 0.1` → exit 2; `--record captures/fw96/x.jsonl` → exit 2 (outside `captures/private/`); `--no-record` writes no file; injected `ConnectionLostError` → exit 6 with `stop` reason `connection_lost`; the "not in edit mode" hint is printed once to stderr when a label was typed, global[3] = 1, and 30 s (fake clock) pass without a preset change
- [X] T021 [P] [US1] Write `tests/contract/test_watch_record.py`: the record written in T020 scenarios is valid JSONL in the `captures/README.md` format plus `label`/`change`/`stop` per [contracts/session-record.md](contracts/session-record.md); `meta.tool` starts with `openvave watch`; each line is flushed (the file is readable while the session is still running: read it from inside the fake transport callback after the first change); a contiguous excerpt (meta + handshake + two cycles) loads with `FakeTransport.from_capture` and replays to the same `WatchChange`

### Implementation for User Story 1

- [X] T022 [US1] Add ordered replay to `src/openvave/transport/fake.py` (`replies` per label become a list; `from_capture` collects repeated `rx`; the last reply repeats) until T017 passes; update the class docstring
- [X] T023 [US1] Add `rx_all(label)` and repeated-label support to `tests/support/captures.py` until T018 passes
- [X] T024 [US1] Add `WatchStart`, `WatchChange` (and `WatchEvent` union) to `src/openvave/models.py`; implement `TankG.watch(interval=0.5, *, regions=(GLOBAL, CURRENT_PRESET, STATUS), cycles=None, sleep=asyncio.sleep)` in `src/openvave/session.py` using `read()`, `decode_region` and `diff`, with monotonic `t` and the cycle start scheduling of research R4, until T019 passes. Update the module docstring: `watch()` is the only polling API
- [X] T025 [US1] Create `src/openvave/cli/watch.py`: stdin label reader (thread via `asyncio.to_thread(readline)`, `q`/`quit` → stop, EOF → stop reading only), record writer (capture-format JSONL, flush per event, default path `captures/private/<YYYYMMDD-HHMMSS>-watch.jsonl`, parents created, rejects paths under a `captures/` folder outside `captures/private/`), SIGINT → stop reason `interrupt`, `--duration`, edit-mode hint. The writer gets `tx`/`rx`/`rx-chunk` events through a hook on the session's trace calls (no change to what is sent)
- [X] T026 [US1] Wire the `watch` subcommand into `src/openvave/cli/__init__.py` (`--interval`, `--duration`, `--record`, `--no-record`, plus global options; `main()` gains injectable `stdin` and `clock` for tests) and add watch renderers to `src/openvave/cli/render.py` (human lines + JSON Lines events), until T020 and T021 pass
- [X] T027 [P] [US1] Export `WatchStart`, `WatchChange` from `src/openvave/__init__.py` and extend `tests/contract/test_public_api.py`
- [X] T028 [P] [US1] Document the `label`, `change` and `stop` events and the excerpt rules in `captures/README.md`, per [contracts/session-record.md](contracts/session-record.md)
- [X] T029 [P] [US1] Write `tests/hardware/test_hw_watch.py` (`@pytest.mark.hardware`): `TankG.connect()` then `watch(cycles=3)` yields a `WatchStart` with all three regions decoded and sends only `0x23` reads after the handshake

### Live verification (milestone gate)

Pedal owner, macOS, fw 96, phone app disconnected:

- [X] T030 [US1] Run `uv run pytest`, ruff, format and mypy; record counts in the PR
  - Evidence (2026-11-16): pytest 603 passed, 4 skipped (hardware); ruff check clean; 74 files formatted; mypy strict: no issues in 19 source files. Tests T017–T021 + T027 were run first and failed (39 failures + 2 collection errors) before T022–T026. The 49 watch tests passed 6 runs in a row (no flakiness). Smoke run of the real CLI (real clock, piped stdin, fake pedal sweeping preset[15]): label + 4 `preset[15]` change lines, `q` → exit 0, record complete with `stop` reason `quit`; `--record captures/fw96/x.jsonl` → exit 2; `--duration 1.2 --json < /dev/null` → `stop` reason `duration`, exit 0
  - Implementation notes: labels are read on a daemon thread instead of `asyncio.to_thread` (research R10), so a `readline` blocked on a terminal never delays exit; the CLI prints and records times from its own (injectable) clock; `--duration` and the edit-mode hint are checked between cycles and by a 50 ms ticker
- [X] T031 [US1] Owner runs quickstart §4: `uv run openvave watch`, labels `edit mode on` → enter edit mode; `reverb decay min→max` → turn **only** reverb decay fully down then fully up; `leave edit mode` → leave without saving; `q`. Expected: `global[3]` on → off → on, and only `preset[15]` lines reaching `0` and `127`. Record the terminal output in the PR
  - Evidence (2026-11-16 18:25, owner, macOS, fw 96, the desktop app's terminal panel; Bluetooth worked there): session 2 record `captures/private/20261116-182515-watch.jsonl` (979 s, 1943 cycles, 235 changes, stopped with Ctrl-C → `stop` reason `interrupt`). Entering edit mode: `global[3] 1 → 0` (+448.8 s). Reverb decay alone, swept twice: only `preset[15]` lines, `5 → 43 → 37 → 0 → 60 → 127` and `127 → … → 0 → … → 127`. Leaving edit mode without saving: `global[3] 0 → 1` and every preset byte reverted in the same cycle (+733.8 s)
  - Deviation: no stdin labels reached this record (the owner typed them in the chat box, not into the panel). Steps are identified by the owner's report afterwards plus timing. Labels worked in the panel in the later sessions (18:41 onwards)
- [X] T032 [US1] Cut the reverb-decay step from that record into `captures/fw96/<date>-step-reverb_decay.jsonl` (excerpt rules; label text reviewed), and add a replay test to `tests/integration/test_watch_session.py` that reproduces the same `WatchChange`s from the excerpt
  - Evidence: `captures/fw96/20261116-step-reverb_decay.jsonl` = cycles 936–942 of session 2 (meta + handshake + 7 cycles, 5 `change` lines, no label text to review), cut with `tests/support/excerpt.py`. `test_reverb_decay_excerpt_replays_to_the_recorded_changes` replays it to the same changes, only `(preset, 15)`, reaching 0 and 127
- [X] T033 [US1] Promote preset 15 to `confirmed` in `specs/protocol/command-layer.md` and `src/openvave/protocol/bytemap.py`, citing both sessions (2026-11-16 note + the new excerpt) per FR-010; doc↔code test green
  - Evidence: preset 15 is `confirmed` in both files, citing the probe capture and the step excerpt; doc↔code, bytemap and contract tests green
- [X] T034 [US1] Owner runs `uv run openvave watch --json --duration 10 < /dev/null` and `uv run pytest --hardware tests/hardware/test_hw_watch.py`; record the results in the PR
  - Evidence (2026-11-16 19:16, owner, fw 96): `watch --json --duration 10 < /dev/null` printed `start` (all three regions decoded) then `stop` reason `duration`, exit 0. `pytest --hardware tests/hardware/test_hw_watch.py`: 1 passed in 7.25 s. Found on the way: `--duration` counted from the tool's start, so scanning and connecting (~6 s) ate into it; it now counts from the first poll (`test_duration_counts_from_the_first_poll_not_from_connecting`)
  - Hardware also exercised the stop paths: Ctrl-C → `stop` reason `interrupt` (4 sessions); a link drop with the tuner on (session 18:46) → `stop` reason `connection_lost`, `error: the pedal disconnected`, exit 6

**Checkpoint**: Milestone 1 DONE (MVP: the mapping tool works on hardware) ✅ — gate passed on hardware 2026-11-16 (T031–T034)

---

## Milestone 2: Front-panel mapping campaign (US2 P1, US3 P2)

**Goal**: every front-panel control exercised one at a time. The byte map, protocol docs and
fixtures are updated with confidence, and `preset dump` decodes everything found.

**Independent test criteria**:
- `command-layer.md` has a "Control inventory" table listing every control, each with a result
  (mapped offsets or "no change" + date).
- Preset bytes 4–17 are each named at `observed` or better, or documented as unchanged by
  every control tried (SC-003).
- For every named field, `tests/integration/test_fixture_pairs.py` shows that decoding the
  excerpt's "after" read vs its "before" read changes exactly that field (SC-004).

### Tests (write first per field, must fail until its map row exists)

- [X] T035 [P] [US2] Create `tests/integration/test_fixture_pairs.py` and its index `tests/integration/fixture_pairs.py` (field name → excerpt path, before/after cycle selection, expected extremes for min→max sweeps). Parametrise over the index and assert: `diff` names only that field, and for continuous sweeps the values reach the documented `min` and `max`. Seed it with the M1 reverb-decay excerpt
  - `tests/integration/fixture_pairs.py` indexes 23 pairs over 21 committed excerpts; single steps assert every cycle-to-cycle change is on the field's byte, nothing else moves, the exact (min, max) reached, and no value out of range; preset-selection excerpts assert the (browsed bank, bank, slot) sequence
- [X] T036 [P] [US2] Extend `tests/unit/test_bytemap.py` with a check that every `observed`/`confirmed` named entry appears in the fixture-pair index (no row without its pair, FR-009/FR-020)
  - plus: confirmed rows need two sessions and a pair; written first, failed (19 failures) until the rows existed

### Evidence gathering (pedal owner, hardware)

- [X] T037 [US2] Owner lists every physical control (knobs as printed, selector knobs, footswitches, buttons, modes) and whether it needs edit mode. Record it as the "Control inventory" table in `specs/protocol/command-layer.md`, using our own descriptive words (research R13)
  - Control inventory table in `command-layer.md` (21 controls, from the owner's report and the sessions)
- [X] T038 [US2] Owner runs `uv run openvave watch` and works through the inventory: for each control, type a label, enter edit mode where needed, move **only that control** (continuous: full down then full up; selector: step through every position; switch: toggle on/off/on), then leave edit mode without saving. Isolate reverb mix and IR cab in separate steps (preset 16/17), and identify the knob behind preset 6. Records stay in `captures/private/`
  - Owner, 2026-11-16 18:25–18:50: six sessions (knobs one at a time; preset walk 9A–9D, 1A–1D, 2A, 2B; block switches; edit mode; tuner). Raw records in `captures/private/` of the worktree and copied to the main checkout's `captures/private/`
- [X] T039 [US2] Researcher reviews the records step by step: for each step, list the changed offsets, old → new values, extremes, and co-moving bytes. Steps with co-moving bytes or no change are noted, and repeated if the cause is unclear (owner re-runs T038 for those controls)
  - Reviewed per step with the change lists; steps with co-moving bytes (first block off-switch copies the knob positions; preset loads) are excluded from single-step fixtures and explained in "Watch session findings"

### Recording findings (one commit per control or control group)

- [X] T040 [US2] For each isolated finding, cut an excerpt `captures/fw96/<date>-step-<field>.jsonl` (excerpt rules, label text reviewed) and add it to the fixture-pair index. Run `tests/integration/test_fixture_pairs.py`: it fails for the new field
  - 21 excerpts `captures/fw96/20261116-step-*.jsonl`, cut with `tests/support/excerpt.py`; label text reviewed (only "test …" step labels)
- [X] T041 [US2] Add or update the row in `specs/protocol/command-layer.md` (R1 columns, `observed`, evidence path, range seen, linked control) and the matching `ByteMapEntry` in `src/openvave/protocol/bytemap.py` in the same commit. Fixture-pair, bytemap and doc tests green. Use neutral names for anything still `hypothesis` (research R8)
  - 26 rows; preset 0–17 and global 0–3 named; doc↔code test green
- [X] T042 [US2] Update the existing hypotheses in docs and map: preset 16 and 17 resolved (renamed or confirmed at `observed`), preset 6 given its real name (keep `knob_unknown` as the JSON name until M4 and list the rename for the CHANGELOG), and global 3 kept or refined. Refuted claims are noted under the table, not deleted (US2 scenario 4)
  - preset 16/17 isolated → observed; preset 6 = gain (JSON `knob_unknown` until M4); global 3 refined to a mode selector 0 edit / 1 normal / 2 tuner (JSON `not_in_edit_mode` until M4), confirmed. Renames for the 0.2.0 CHANGELOG: `knob_unknown` → `gain`, `not_in_edit_mode` → `mode`
- [X] T043 [US2] For every control with "no change", fill its inventory row with the session date. For every byte still unknown in 4–17, write the controls tried in its Notes (FR-007, SC-003)
  - every inventory control mapped; open ranges listed in the rows' Notes and in "Not yet known"
- [X] T044 [P] [US3] Extend `tests/contract/test_cli_preset_dump.py` expectations for the newly named fields on the fw96 capture (decoded names, values and confidence match the doc table)
  - `preset dump` / `info` / `watch` contract expectations updated to the full map (value column widened to 6 so `normal` fits)

### Live verification (milestone gate)

- [X] T045 [US2] Run the full hardware-free suite, ruff, format and mypy; record counts. Check SC-001 (every inventory control has a result), SC-003 (bytes 4–17 attributed) and SC-004 (fixture-pair test count = number of named fields); list them in the PR
  - Evidence (2026-11-16): pytest 682 passed, 4 skipped; ruff, format, mypy clean. SC-001: all 21 inventory controls have a result. SC-003: preset 4–17 all named at observed or better. SC-004: 23 fixture pairs, every observed/confirmed field indexed (test-enforced)
- [X] T046 [US3] Owner: `uv run openvave preset dump` in edit mode with three continuous knobs set to min and then max; decoded values show the documented range ends. Record in the PR
  - Evidence (2026-11-16 19:17, labelled session): every one of the 12 continuous knobs swept alone to `0` and `127`, decoded by the same `decode_region` path `preset dump` uses (values shown in range, none out of range); 12 excerpts `*-1917.jsonl` with exact (0, 127) asserted by the fixture-pair test

**Checkpoint**: Milestone 2 DONE ✅ (2026-11-16)

---

## Milestone 3: Preset comparison, status byte, confirmations (US4 P3, US2)

**Goal**: bytes that differ per preset are recorded (≥ 5 stored presets), the status byte and
global 0–2 are explained or explicitly unknown, and rows reproduced in a second session are
promoted to `confirmed`.

**Independent test criteria**:
- The status byte's relation to the selected preset (base, range seen) is documented, or it is
  explicitly unknown with the values seen per preset.
- `command-layer.md` lists, for each byte that differs between the ≥ 5 compared presets but
  never moved with a control, its value per preset (FR-011a, SC-008).
- Every `confirmed` row cites excerpts from two distinct sessions (FR-010), and
  `tests/unit/test_bytemap.py` passes.

### Tests (write first, must fail)

- [X] T047 [P] [US4] Add the preset-switch excerpt(s) to the fixture-pair index with the expected status change (from T049), and a test in `tests/integration/test_fixture_pairs.py` that the decoded status `index` field equals the expected preset number for each switch step
  - Adapted: the status byte does not track the preset (always `01`), so the index test checks global browsed bank / bank / slot over the preset-walk excerpts instead (`test_preset_selection_moves_bank_and_slot`)
- [X] T048 [P] [US2] Add a test in `tests/unit/test_bytemap.py` that every byte listed as "differs per preset" in the doc's preset comparison table is either a named entry or an `unknown` entry whose Notes contain its per-preset values (parsed via `tests/support/bytemap_doc.py`)
  - `test_per_preset_bytes_are_named_or_documented` parses the "Preset comparison (fw 96)" table (10 presets)

### Evidence gathering (pedal owner, hardware)

- [X] T049 [US4] Owner runs `uv run openvave watch`, labels each step, and selects at least 5 different stored presets on the pedal one at a time (no edit mode, no saving). Also enter and leave edit mode once on two of them (global 3, status)
  - Preset walk 9A–9D, 1A–1D, 2A (18:41, unlabelled, order from the owner's report; confirmed by global 0–2) and 2B (18:43); edit mode entered/left on 2A (18:43) and 1B (18:47)
- [X] T050 [US2] Owner runs a **second, independent** `watch` session (new connection, a different stored preset than in M2) repeating the single-control steps for the fields that should become `confirmed` (at least: reverb mix, IR cab, the preset 6 knob, and every other `observed` field the owner can repeat)
  - Evidence: session 19:17 (new connection, labelled) repeated all 12 knobs, both selectors (counted: 9 positions each, 0–8) and the 4 block switches; each step moved only its byte. The mode byte already had two sessions (18:43, 18:47)

### Recording findings

- [X] T051 [US4] Document the status byte in `specs/protocol/command-layer.md` and `src/openvave/protocol/bytemap.py` (`index` encoding with base and range seen, or `unknown` with per-preset values); excerpt `captures/fw96/<date>-step-preset_switch.jsonl`; T047 green
  - status documented as unknown with values seen (`01` everywhere); no index excerpt possible
- [X] T052 [US2] Add a "Preset comparison (fw 96)" table to `specs/protocol/command-layer.md`: one column per compared preset (identified by position only, no personal names), one row per byte that differs; update the Notes of the matching rows, and document global bytes 0–2 (named or unknown with values seen); T048 green
  - "Preset comparison (fw 96)" table: 10 presets × 19 differing bytes; global 0–2 named
- [X] T053 [US2] Promote every row reproduced in T050 to `confirmed` in the doc and the map, citing both session excerpts; add the second-session excerpts to `captures/fw96/`; bytemap/doc tests green
  - Evidence: preset 0–17 and global 3 are `confirmed`, each citing excerpts from two sessions (test-enforced); amp type and IR cab ranges set to 0–8. Global 0–2 stay `observed` (one preset walk)
- [X] T054 [US2] Update "Next steps" in `specs/protocol/command-layer.md`: what remains unknown and the questions for the write spec (e.g. app-only settings, stored-preset reads)

### Live verification (milestone gate)

- [X] T055 [US2] Run the full suite, ruff, format and mypy. Check SC-002 (26 rows, none missing) and SC-008 (≥ 5 presets compared, differing bytes covered); list them in the PR
  - Evidence: 26 rows, none missing (SC-002, test-enforced); 10 presets compared, every differing byte named or noted (SC-008, test-enforced)
- [X] T056 [US4] Owner: `uv run openvave info` on two different presets shows the decoded status value matching the selected preset (if mapped); record in the PR
  - Not applicable as written: the status byte does not follow the selected preset. `info` shows bank and slot instead (global 1–2)
  - Superseded (2026-11-24): the status byte is the loopback flag (spec 004 T074, named `loopback` in spec 007 Milestone 2), so there is nothing per preset to check

**Checkpoint**: Milestone 3 DONE ✅ (2026-11-16; T056 not applicable: the status byte does not follow the preset)

---

## Milestone 4: Release 0.2.0 (US3) + Polish

**Goal**: final field names, `schema_version` 2, docs and changelog, and the end-to-end checks.

**Independent test criteria**:
- `preset dump --json` has `schema_version` 2 and the final names. The CHANGELOG lists every
  rename/refutation old → new.
- A reviewer decodes the fw96 preset bytes from `command-layer.md` alone and gets the same values
  as `preset dump` (SC-007).

### Tests (write first, must fail)

- [X] T057 [P] [US3] Update `tests/contract/test_cli_preset_dump.py`, `tests/contract/test_cli_info_regions.py` and `tests/contract/test_cli_watch.py` to expect `schema_version` 2 and the final field names (no `knob_unknown`, no `not_in_edit_mode` if renamed)
  - Written first with T058; 18 failures before T059–T060 (commit 138f52a)
- [X] T058 [P] [US3] Add `tests/contract/test_changelog_renames.py`: every name present in 0.1.0's `KNOWN_FIELDS` that is absent from `BYTE_MAP` appears in the CHANGELOG 0.2.0 rename table
  - `KNOWN_FIELDS_0_1_0` frozen from the 0.1.0 source (`not_in_edit_mode`, `knob_unknown`, `reverb_decay`, `reverb_mix`, `ir_cab`); also checks every renamed name exists in `BYTE_MAP` and `__version__` is 0.2.0

### Implementation

- [X] T059 [US3] Apply the final names in `src/openvave/protocol/bytemap.py` and `specs/protocol/command-layer.md`; bump `SCHEMA_VERSION` to 2 in `src/openvave/cli/render.py`; update the `$id`/`const` of `specs/002-preset-byte-map/contracts/watch-event.schema.json`, `decoded-field.schema.json` and the 001 schemas' `schema_version` to 2; until T057 passes
  - `knob_unknown` → `gain`, `not_in_edit_mode` → `mode` in the doc table and `BYTE_MAP` (same commit); `SCHEMA_VERSION = 2`; the four schemas have `const: 2` and `$id` `…:v2`; the watch hint follows `mode`
- [X] T060 [US3] Write `CHANGELOG.md` 0.2.0: decoder, `watch`, new JSON keys, rename/refutation table, deprecated `KNOWN_FIELDS`/`FieldSpec` aliases; bump `version` in `pyproject.toml` to 0.2.0; until T058 passes
  - CHANGELOG 0.2.0 (Breaking / Added / Changed / Deprecated / Tested, rename table with why); `pyproject.toml`, `__version__` and `uv.lock` at 0.2.0
- [X] T061 [P] Update `README.md`: `openvave watch` usage (labels, `q`, record location and privacy), decoded `preset dump` example, confidence levels explained
  - README: decoded `info`/`preset dump` output (generated from the fw96 capture), confidence levels, `openvave watch` (labels, `q`, records in git-ignored `captures/private/`), `schema_version` 2, library snippet with `decode_region`
- [X] T062 [P] Update `specs/001-readonly-ble-connection/contracts/cli.md` with a pointer to the 002 additions, and record in `specs/002-preset-byte-map/contracts/cli.md` that `watch --json` is the JSON Lines exception
  - 001 `cli.md` gets a 0.2.0 pointer note; 002 `cli.md` records the JSON Lines exception and the past-tense schema bump
- [X] T063 Code cleanup: remove dead code paths from the 001 field rendering; ruff/mypy clean
  - No dead code found (every render/decode function and constant is referenced); `KNOWN_FIELDS`/`FieldSpec` stay as the documented deprecated aliases; the watch hint attribute renamed `outside_edit_mode`. ruff/mypy clean

### Live verification (milestone gate)

- [X] T064 Run the full quickstart ([quickstart.md](quickstart.md) §1–§6); record the results in the PR
  - Evidence (2026-11-16): §1 pytest 741 passed, 4 skipped (hardware); ruff check clean; 79 files formatted; mypy strict: no issues in 19 source files. §2: 18 fields, all `confirmed`, `gain 60`, `reverb_decay 5`, `reverb_mix 4`, `ir_cab #7` (quickstart expectation updated). §3/§4 over the fw96 capture through the real CLI (fake transport): `preset dump --json` and `info --json` have `schema_version` 2 and `gain`/`mode` (`mode` displays `normal`); `watch --json --duration 1 --no-record < /dev/null` → `start`, `stop` reason `duration`, exit 0; `openvave --version` → 0.2.0; README library snippet runs. §5/§6 are enforced by the fixture-pair, bytemap and doc tests (SC-001–SC-004, SC-008). §3/§4 on hardware: not run in this session (owner)
- [ ] T065 [US3] Owner: SC-005. Set every `observed`/`confirmed` continuous knob to min, then max, in edit mode; `uv run openvave preset dump` shows the range ends. Record in the PR
  - Not run in this session: needs the owner at the pedal. Prior evidence: session 19:17 (T046) swept all 12 continuous knobs alone to `0` and `127`, decoded by the same `decode_region` path `preset dump` uses, and the fixture-pair test asserts those exact extremes
  - Still open (2026-11-24): later hardware sessions ran `preset dump` at range ends only for MOD FX and DLY MIX (raw 0 and 127, spec 004 T022); the other ten knobs were not dumped at both ends
- [X] T066 [US3] SC-007 review: someone who did not write the decoder decodes `01 00 00 01 0f 04 3c 3c 46 32 32 00 00 00 00 05 04 07 43 16 43` using only `specs/protocol/command-layer.md`, and the result matches `preset dump` on the fw96 capture; record in the PR
  - Evidence (2026-11-16): a separate agent that never opened `src/` or `tests/` decoded the preset buffer from `command-layer.md` alone. All 21 preset bytes matched `preset dump` on the fw96 capture: 18 named values (`amp_on` on … `ir_cab` 7) and 18–20 unknown. Global: bank, browsed bank and mode matched. It misread slot as `0`; the doc says `fw96: 0x01`, as `info` shows. Gap it found: the doc gave no display rules, so selectors appeared as `4`/`7` instead of `#4`/`#7`. Fixed by adding a "Decoding a byte" list (display per encoding, out of range, unknown) under the column legend

**Checkpoint**: Milestone 4 DONE ✅ (2026-11-16; owner hardware check T065 left open, prior evidence in T046)

---

## Dependencies & Execution Order

### Milestone dependencies

- **M0** (decoder): blocks everything. M1's watch output and every later map row use it.
- **M1** (`watch`): needs M0. Blocks M2/M3, which gather evidence with `watch`.
- **M2** (front panel): needs M1's gate (tool verified on hardware, byte 15 confirmed).
- **M3** (presets, status, confirmations): needs M2. Second sessions confirm M2's rows.
- **M4** (release): needs M3. Renames are collected from M2/M3.

### Within each milestone

- Tests first and failing (T001–T005, T017–T021, T035–T036, T047–T048, T057–T058).
- Docs row + map entry + fixture + passing test in the same commit (M2/M3).
- Live verification closes the milestone; the PR description records the gate evidence.

### Parallel opportunities

- M0: T001–T005 in parallel (different files); T012, T013 in parallel after T009.
- M1: T017–T021 in parallel; T027–T029 in parallel after T024.
- M2/M3: while the owner gathers evidence (T038, T049/T050), the researcher can prepare the
  fixture-pair index (T035/T036, T047/T048). Recording findings per control group can go in
  parallel commits if they touch different rows, though they share `command-layer.md` and
  `bytemap.py`, so merge carefully.
- M4: T057/T058 and T061/T062 in parallel.

## Parallel Example: Milestone 1 (US1)

```bash
# Tests first, together:
Task: "FakeTransport ordered replay tests in tests/unit/test_fake_sequence.py"
Task: "Repeated-label capture loader tests in tests/unit/test_captures.py"
Task: "TankG.watch integration tests in tests/integration/test_watch_session.py"
Task: "CLI watch contract tests in tests/contract/test_cli_watch.py"
Task: "Session record contract tests in tests/contract/test_watch_record.py"
```

## Implementation Strategy

### MVP first

1. M0 → decoder and doc-checked map (no hardware needed).
2. M1 → `openvave watch`. **Stop and validate** on hardware with the reverb decay sweep: the
   owner now has a supported mapping tool, and byte 15 is the first `confirmed` field.

### Incremental delivery

- M2 and M3 deliver value per control: each merged commit adds one decoded field to
  `preset dump` (additive JSON, no schema bump).
- M4 consolidates names once, so scripts face a single breaking change (`schema_version` 2).
