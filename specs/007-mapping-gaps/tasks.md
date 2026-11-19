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

## Deferred

- US4 amp / cab names: needs the owner's transcription of the manual's lists or the vendor
  desktop software's display, matched position by position.
