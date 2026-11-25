# Tasks: spec 007 mapping gaps

## Milestone 1: Gate session C (US1, US3) ✅

- [X] T001 Runbook with independently encoded frames (`gate-session-c.md`)
- [X] T002 Owner runs session C (2026-11-19); backups C0 = C1
- [X] T003 Excerpts `captures/fw96/20261119-gate-*_c.jsonl`, registered as session C; six rows
  `confirmed`; docs, CHANGELOG

## Milestone 2: Names (US2, US3) ✅

- [X] T010 Fixture index accepts gate excerpts and the status region
- [X] T011 `led_red` / `led_green` / `led_blue`, `loopback`, `ir_cab` 0 = `off`; `LED colour #rrggbb`
- [X] T012 MASTER documented as not reported; docs, CHANGELOG

## Milestone 3: Preset management (US5) ✅

### Tests first

- [X] T020 `tests/integration/test_preset_ops.py`: copy, import, swap plans (frames, refusals,
  no_change, edits pending), sequences on the fake pedal (backup first, verification), export
  document round trip
- [X] T021 `tests/contract/test_cli_preset_ops.py`: `preset copy|swap|export|import` human and
  JSON output, dry run, `--unsafe` required, usage errors (same slot, bad file, backup file given
  to import), schema validation

### Implementation

- [X] T022 `PresetFile` + document functions (`src/openvave/backup.py`), export in `TankG`
- [X] T023 `plan_copy` / `copy_preset`, `plan_import` / `import_preset`, `plan_swap` /
  `swap_presets` in `TankG`, `SequenceAction` values, schema enum
- [X] T024 CLI commands and rendering
- [X] T025 Docs (`cli-reference`, `recipes`, `safety`, `library`, README), CHANGELOG

### Hardware check

- [X] T026 Owner: export 1A; copy 1A → a spare slot; swap two slots; restore from the automatic
  backup; final backup equals the first
  - 2026-11-19, runbook and result in `gate-session-d.md`: export, copy 1A → 9D, swap 9C ↔ 9D,
    import → 9D, restore all from D0, select 1B; every frame matched the independent encoding
    before it was sent; D1 = D0.

## Milestone 4: Amp and cab names (US4)

### Research

- [X] T030 Find the manual's amp and IR cab lists; evidence record
  `evidence-amp-cab-names.md` (FR-011): S1, the 2024 manual (Manuals+ copy, archived) and S3, the
  vendor's 2026 "NEW PRESET" card, name different models; position numbering derived
  (amp slot *k* = raw *k* − 1, cab slot *k* = raw *k*); no images committed
- [ ] T031 Owner, hardware (read-only, nothing saved): match the positions on the pedal by ear,
  as in the evidence record's "Position matching" procedure; record which list fits each
  position, firmware and date in the evidence record

### Tests first (the owner asked on 2026-11-25 to build with the manual's names before T031)

- [X] T032 `tests/unit/test_names.py`, `tests/unit/test_names_doc.py`,
  `tests/unit/test_render_names.py`: one names table (`src/openvave/protocol/names.py`, both
  vendor lists + a per-position choice), every chosen name a `hypothesis`, IR cab names factory
  names, cab 0 keeps `off`, the doc table and the evidence record match the data; expected texts
  built from the table, so switching lists is a data change
- [X] T033 Contract tests: `preset dump` human and JSON (`position_name`), `watch` human and JSON
  (`position_name_old` / `_new`), `set` human and JSON (`position_name_before` / `_after`, raw
  input), MCP `preset_read`, `pedal_changes` and `openvave://byte-map`; schemas validate,
  `schema_version` stays 2

### Implementation

- [X] T034 `src/openvave/protocol/names.py`; rendering (`render.py`, `_jsonform.py`), MCP results
  and resources; `specs/protocol/command-layer.md` "Amp type and IR cab names" (byte-map rows 5
  and 17 unchanged: the byte stays `confirmed`, the names carry their own confidence)
- [X] T035 Docs (`docs/effect-types.md`, `docs/tank-g.md`, `docs/cli-reference.md`,
  `docs/mcp.md`) with the trademark note; CHANGELOG [Unreleased]

### Live verification

- [ ] T036 Owner: `uv run openvave preset dump` on two presets shows the names next to `#n`

**Checkpoint**: Milestone 4 done when T031 is recorded and `NAME_CHOICE` follows it. Until then
the PR stays a draft: the names are built and shown as `hypothesis` ("manual, not yet matched on
fw 96"), and FR-011 keeps them from shipping in a release.
