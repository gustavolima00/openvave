# Implementation Plan: Preset and global byte map (read-only decoding)

**Branch**: `claude/spec-002-tankg-mapping-b8c3d9` (feature directory `002-preset-byte-map`) |
**Date**: 2026-11-16 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/002-preset-byte-map/spec.md`

## Summary

Extend the 001 read-only client in three ways. (1) A **byte map**: one data table in the
protocol layer, mirrored row for row from a machine-checkable table in
`specs/protocol/command-layer.md`, which describes every byte of the current preset (21 B), the
global block (4 B) and the status byte (1 B). Each row has its encoding, range, control and
confidence. A pure **decoder** applies the map to region bytes. (2) An explicit, read-only
**`openvave watch`** command that polls those three regions over one connection, prints
per-byte changes with the owner's stdin labels, and saves a session record in the existing
capture format under `captures/private/`, so sanitized excerpts become test fixtures directly.
(3) The **mapping campaign** itself, carried out by the pedal owner with `watch`, which fills
the map, the protocol docs and the fixtures. `preset dump` / `info` render decoded fields
additively, and the JSON schema version is bumped once, at release. No new command byte or
address: the 001 allowlist (`0x11`, `0x23`; four regions) stays the only thing that can be
encoded. Decisions: [research.md](research.md).

## Technical Context

**Language/Version**: Python ≥ 3.11 (unchanged from 001)

**Primary Dependencies**: `bleak` ≥ 0.22 (runtime, unchanged). No new runtime or dev dependency
(R11)

**Storage**: session records are JSONL files in `captures/private/` (git-ignored); sanitized
excerpts are committed under `captures/fw96/` (R5)

**Testing**: `pytest` (+ `pytest-asyncio`, `jsonschema`). The default suite is hardware-free;
`watch` runs against a `FakeTransport` that replays a sequence of replies (R9). Hardware
checks are opt-in (`--hardware`)

**Target Platform**: macOS (hardware-verified); Linux/Windows best-effort (unchanged)

**Project Type**: library + CLI (single Python package)

**Performance Goals**: `watch` completes one poll cycle (3 reads) well within the 0.5 s default
interval. Observed reply latency is 40–90 ms, so a cycle takes about 0.15–0.3 s (R4)

**Constraints**: only `0x11`/`0x23` encodable and only the four 001 regions readable (FR-002,
FR-019); one request in flight; `--interval` ≥ 0.2 s; `watch` is the only command that polls
(clarification Q1)

**Scale/Scope**: 26 mapped bytes; ~10–20 front-panel controls (exact inventory comes from the
owner in M2); ≥ 5 stored presets compared; session records up to tens of MB per hour (R5)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Pre-research evaluation (2026-11-16):

- [x] **I. Protocol docs**: the byte map lives in `command-layer.md` first. The code table must
  match it, enforced by a test that parses the doc table (R1). Every finding PR updates the doc
  and the code together. The docs record findings, not procedure (FR-008).
- [x] **II. Evidence**: each `observed` row cites a sanitized single-control fixture (FR-009).
  `confirmed` needs a second independent session (FR-010, clarification Q2). Firmware is
  recorded in every record's meta line.
- [x] **III. Capture-driven tests**: decoder tests use before/after fixture pairs cut from real
  `watch` records (FR-020, R6), written before the map row exists. The suite stays
  hardware-free.
- [x] **IV. Device safety**: no new command byte, region or address. `watch` reuses
  `TankG.read` over the closed `Region` enum (R3). The owner leaves edit mode without saving,
  so stored presets are untouched. Dry-run/backup N/A (no writes).
- [x] **V. Library-first/CLI**: the decoder is a pure function in `openvave.protocol` and
  `TankG.watch()` is a library async iterator. The CLI adds stdin labels, rendering and the
  record file. Human + JSON (JSON Lines for the streaming `watch`, R7).
- [x] **VI. Clean-room**: the map names controls in our own words. No factory preset content
  or vendor names are committed. Session records stay private, and only excerpts of
  preset/global/status bytes (no identifiers) are committed (R5).
- [x] **VII. Simplicity**: no new dependency. One map table, one decoder, one watch iterator.
  The `FakeTransport` gains ordered replay of repeated requests (an additive option) instead of
  a second fake.

Result: **PASS** (no unjustified violations).

Post-design re-evaluation (after Phase 1, 2026-11-16): **PASS**. The data model keeps decoding
I/O-free and keyed only by the existing `Region` enum. The contracts add one CLI command
(`watch`) and additive JSON fields. The schema version bump (1 → 2) is planned once, at the
release milestone (R8), as 001 FR-016a requires. Polling is narrowed to `watch`, as the spec
clarification allows; 001's no-polling guarantee still holds for `info` and `preset dump` and
for the `TankG` methods other than `watch()`.

## Delivery Plan

Projected PR count: **5** (≤ 8, no re-scoping needed). M0 and M1 are code-only and
hardware-free apart from their gates. M2 and M3 are evidence milestones: the owner runs
`watch` and the PR carries doc + map + fixtures + tests together.

| # | Milestone | Scope | Stories | Verification gate |
|---|---|---|---|---|
| M0 | Byte map model & decoder | `ByteMapEntry` / encodings, `protocol/bytemap.py` (26-byte table, existing knowledge, unknown rows explicit), pure `decode_region()`. Normalise the `command-layer.md` table to the R1 column format, plus the doc↔code consistency test. Renderers use the decoder (human + additive JSON fields: `raw`, `mask`, `encoding`, `range`, `display`, `out_of_range`, `map_firmware`). Schemas updated additively | US3 (base) | Suite green. The decoder on the fw96 capture reproduces today's 5 known fields. The doc table parses and matches code. All 001 contract tests still pass with `schema_version` 1 |
| M1 | `openvave watch` | `FakeTransport` ordered replay. `TankG.watch(interval)` → `WatchEvent`s (snapshot, change). CLI `watch`: stdin labels, human lines, `--json` JSON Lines, `--record PATH` (default `captures/private/<date>-<time>-watch.jsonl`), `--interval`, `--duration`, Ctrl-C / `q` to stop. `watch-event.schema.json`. Record = capture format + `label`/`change` events | US1 | Fake-transport tests (changes, co-moving bytes, labels, interrupted session keeps the record). Command audit still only `0x11`/`0x23`. **Hardware**: the owner sweeps reverb decay only and sees only `preset[15]` change; this second session promotes byte 15 to `confirmed` |
| M2 | Mapping campaign: front panel | Owner's control inventory (in `command-layer.md`, our own names). One-control-at-a-time steps for every control. Isolate preset 16/17 and identify preset 6. Sanitized single-step fixtures under `captures/fw96/`. Map rows + fixture-pair tests. Unknown rows annotated with the controls tried | US2, US3 | SC-001, SC-003, SC-004 hold. The doc↔code test passes. Each `observed` row cites its fixture |
| M3 | Preset comparison, status byte, confirmations | Read ≥ 5 stored presets selected on the pedal (no host write) and record the per-preset values of each byte that differs. Status byte vs preset index (base, range). Global bytes 0–2. Second sessions to promote rows to `confirmed` | US4, US2 | SC-002, SC-008 hold. Status byte documented or explicitly unknown. Each promoted row cites two sessions |
| M4 | Release 0.2.0 | Rename provisional field names (`knob_unknown`, `not_in_edit_mode` → final names). `schema_version` 2 + CHANGELOG list of renames. README usage for `watch` and decoded output. Full quickstart run. SC-005 / SC-007 review | US3 | `preset dump` on hardware matches the knob positions the owner sets (SC-005). A reviewer decodes the fw96 fixture from the doc alone (SC-007). Quickstart passes |

M2 may produce more evidence than one PR can review comfortably. If so, it is split by control
group (amp/drive, modulation/delay, reverb/cab, switches) without changing the gates; the
projected total stays ≤ 8.

## Project Structure

### Documentation (this feature)

```text
specs/002-preset-byte-map/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   ├── cli.md                     # `watch` command; decoded-field rendering in `info` / `preset dump`
│   ├── library-api.md             # additions: decode_region, BYTE_MAP, TankG.watch, WatchEvent
│   ├── decoded-field.schema.json  # one decoded field (shared by info / preset dump)
│   ├── watch-event.schema.json    # one JSON Lines event of `openvave watch --json`
│   └── session-record.md          # record file = capture format + label/change events
├── checklists/requirements.md
└── tasks.md             # Phase 2 output (/speckit-tasks — not created here)
```

### Source Code (repository root)

```text
specs/protocol/command-layer.md     # byte map table (R1 format), control inventory, findings

captures/
├── README.md                       # + watch record events, excerpt/sanitization rules
└── fw96/
    ├── 20261116-probe-connect.jsonl
    └── <date>-step-<control>.jsonl # sanitized single-step excerpts (M2/M3)

src/openvave/
├── models.py            # FieldSpec/KNOWN_FIELDS replaced by ByteMapEntry, DecodedField,
│                        # DecodedRegion, WatchEvent (KNOWN_FIELDS kept as a thin alias until M4)
├── protocol/
│   ├── bytemap.py       # NEW: BYTE_MAP table (pure data) + MAP_FIRMWARE
│   └── decode.py        # NEW: decode_region(region, data, firmware) → DecodedRegion; diff()
├── session.py           # + TankG.watch(interval, regions) async iterator
├── transport/fake.py    # + ordered replay of repeated requests
└── cli/
    ├── __init__.py      # + `watch` subcommand
    ├── render.py        # decoded fields (human + JSON), watch lines
    └── watch.py         # NEW: stdin label reader, record writer, stop handling

tests/
├── support/bytemap_doc.py   # parse the command-layer.md byte map table
├── unit/                    # test_bytemap.py, test_decode.py, test_bytemap_doc.py, test_fake_sequence.py
├── integration/             # test_watch_session.py, test_fixture_pairs.py (one per mapped field)
├── contract/                # test_cli_watch.py, schemas for decoded fields / watch events
└── hardware/                # test_hw_watch.py (opt-in)
```

**Structure Decision**: same single package. The map is pure data in `protocol/` (reusable
without I/O, Constitution V/VII). Decoding is a pure function, so recorded bytes decode
offline (FR-013). `watch` splits into a library iterator (polling + change detection) and CLI
concerns (stdin, files, rendering) in `cli/watch.py`.

## Complexity Tracking

No constitution violations and no new dependencies.

| Addition | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| Polling in `TankG.watch()` (001 had none) | Spec clarification Q1: the mapping session must be a supported, tested command | Keeping polling in throwaway tooling leaves no tested path for the evidence the constitution requires |
| Doc↔code consistency test parsing Markdown | Constitution I: the docs are the source of truth; the code table must not drift | Generating code from the doc at build time adds a build step; a hand-kept table without a check will drift |
| `FakeTransport` ordered replay option | `watch` tests need the same request answered with changing data | A second fake class duplicates the reply/split/drop logic |
