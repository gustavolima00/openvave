# Implementation Plan: Closing the Tank-G mapping gaps (spec 007)

**Spec**: [spec.md](spec.md) · **Branch**: `claude/polish-names-pending-4f3232` · **Date**: 2026-11-19

## Status

| Story | State |
|---|---|
| US1 confirm the last writes | done (gate session C, commit `07b31c9`) |
| US2 name LED colour and loopback | done (commit `499f128`) |
| US3 IR cab 0 = off, MASTER | done (commit `499f128`) |
| US4 amp / cab names | deferred: no source yet (the manual's lists are images) |
| US5 preset copy / swap / export / import | this plan |

## Technical context

Python 3.12, bleak, existing `TankG` session, `SequencePlan` / `SequenceResult` sequence runner of
spec 004 (the only sender of persistent writes), `Backup` documents, argparse CLI. No new
dependency, no new pedal message.

## Design (US5)

Every operation is a plan built from reads, then the existing sequence runner: refusal checks,
`on_plan`, full cross-checked automatic backup, writes with ACK checks, read-back, verification.

| Operation | Plan reads | Steps (all confirmed writes) | Ends on | Verification |
|---|---|---|---|---|
| `copy SRC DST` | global, buffer, slot SRC, slot DST (+ loaded slot) | slot write DST ← SRC → read back → 300 ms → commit → 100 ms → select DST | DST | as `restore --slot` |
| `import FILE --to DST` | as copy, without SRC | slot write DST ← file bytes → … → select DST | DST | as `restore --slot` |
| `swap A B` | global, buffer, whole image | image write (current image with A and B exchanged) → 300 ms → commit → 100 ms → select the loaded preset | loaded preset | full backup read = planned image (as `restore --all`) |
| `export POS --output FILE` | slot POS | none (read-only) | — | — |

- Copy and import end on the target, like `preset save --to` and the app's "save to" (spec FR-017
  is met by saying so in the output). They refuse with `edits_would_be_discarded` when the loaded
  preset has unsaved edits (the final select discards them) unless `--discard-edits`, as
  `restore --slot`.
- Swap uses the confirmed 758-byte image write instead of the app's two slot writes: one persistent
  write, one commit, and the existing full verification; the image is the one just read, with
  only the two slots exchanged. Swapping equal slots is `no_change`; swapping a slot with itself
  is a usage error.
- Single-preset file (`kind: openvave.preset`, `format_version: 1`): `created_at`, `tool`,
  `identity` (as in a backup), `source_position`, `raw` (21 bytes hex), decoded `fields` (for
  reading only; recomputed, never trusted). Import refuses another kind / version / size before
  connecting, and another firmware unless `--experimental` (`firmware_mismatch`). A full backup
  file given to import is a usage error pointing to `preset restore`.
- `SequenceAction` gains `copy`, `import`, `swap`; `sequence-result.schema.json` lists them.
  Human output: `Copy 1A to 3C`, `Import tone.json into 2C`, `Swap 2B and 4D`, each `UNSAFE`.
- Library: `plan_copy` / `copy_preset`, `plan_import` / `import_preset`, `plan_swap` /
  `swap_presets`, `export_preset` → `PresetFile` (`to_document` / `from_document`).

## Constitution check

- I/II: no new message; docs say which confirmed writes each operation uses. Pass.
- III: tests on the fake pedal first (plans, frames, refusals, verification, failure reports).
- IV: persistent operations need `--unsafe`, take the automatic backup, support `--dry-run`, never
  retry. Export is read-only. Pass.
- V: library first, CLI exposes every operation with JSON output. Pass.
- VI: export files hold the user's own preset bytes; nothing vendor is committed. Pass.
- VII: reuses the sequence runner; no new abstraction beyond the three plan builders.
