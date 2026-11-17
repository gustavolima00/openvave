# Data model: Remote editing in normal mode, save, restore, bypass and loopback

Extends the [003 data model](../003-preset-backup-edit-writes/data-model.md). Decisions:
[research.md](research.md). Everything in `protocol/` is pure data and functions (no I/O).

## PedalState (`protocol/state.py`, new)

`classify(global_bytes: bytes, buffer: bytes) -> PedalState`

| Field | Type | Notes |
|---|---|---|
| `kind` | `"normal" \| "edit" \| "tuner" \| "bypass" \| "unrecognised"` | rules in R1 |
| `index` | `int \| None` | loaded preset `bank·4 + slot`; `None` in bypass and unrecognised |
| `bank` | `int \| None` | reported bank (0–8), also in bypass |
| `transient` | `bool` | set by the session / `watch` when a bypass-looking read was not confirmed by the next one (`loading`) |

Rules: `bypass` ⇔ slot = `0xff` and buffer = 21 × `00`. `normal`/`edit` need bank 0–8 and slot
0–3. Unknown mode values, slot `ff` with a non-zero buffer and an all-zero buffer with a valid slot
are `unrecognised`. Every write is
refused in `unrecognised`.

Allowed states per action:

| Action | normal | edit | tuner | bypass | unrecognised |
|---|---|---|---|---|---|
| `set` | yes | yes | no | no | no |
| `preset reload` | yes | with `discard_edits` | no | no | no |
| `preset select` (003) | yes | with `discard_edits` | as 0.3.0 | yes | no |
| `bypass on` | yes | no | no | no change | no |
| `bypass off <pos>` | "not bypassed" | no | no | yes | no |
| `preset save` | yes | no | no | no | no |
| `preset restore` | yes | no | no | no | no |
| `loopback` | yes | yes | yes | yes | no |

## Section value (`protocol/bytemap.py`)

- `SECTION_FIELDS: frozenset[str]`: fields with app sections ≥ `observed` (`{"reverb_decay"}`).
- `section_raw(section: str, position: int) -> int`: `44 · REVERB_SECTIONS.index(section) +
  position − 1`; `ValueError` for an unknown section or position outside 1–40.
- Invariant (tested): `reverb_decay_parts(section_raw(s, p)) == (s, p)` for all 120 pairs.

## WriteTarget (extended, `protocol/writes.py`)

| Kind | Constructor | Type | Address | Len | Data rule | `persistent` |
|---|---|---|---|---|---|---|
| `bypass` | `bypass(i)` | 4 | `0xE1000000 + i` | 1 | `01` | no |
| `loopback` | `loopback()` | 4 | `0xD0000000` | 1 | `00` / `01` | no |
| `stored_slot` | `stored_slot(i)` | 4 | `2 + 21·i` | 21 | 21 bytes | **yes** |
| `commit` | `commit()` | 4 | `0xF0000000` | 0 | empty | **yes** |
| `stored_image` | `stored_image()` | 4 | `0x00000000` | 758 | starts `a5 5a` | **yes** |

Plus the four 003 kinds, unchanged. `allowed_write_body` accepts exactly these shapes and data
rules. `WRITE_MESSAGES` gets one row per new kind (one row covers every `i`), mirrored from the
doc table; initial confidence `hypothesis` (R7).

## SequencePlan / SequenceStep

A persistent action is a fixed list of steps built from reads only.

| `SequenceStep` field | Type | Notes |
|---|---|---|
| `kind` | `"write" \| "wait"` | |
| `target` | `WriteTarget \| None` | for writes |
| `frame` | `bytes \| None` | the exact frame; what dry run prints |
| `seconds` | `float \| None` | for waits (0.3, 0.1) |

| `SequencePlan` field | Type | Notes |
|---|---|---|
| `action` | `"save" \| "restore_slot" \| "restore_all"` | |
| `state` | `PedalState` | as read |
| `target_index` | `int \| None` | slot written; `None` for restore-all |
| `return_index` | `int` | preset selected at the end |
| `before` / `after` | `bytes` | slot (21 B) or image (758 B): current and to be written |
| `changed_slots` | `tuple[int, ...]` | slots that differ |
| `diff` | `tuple[ByteChange, ...]` | byte-level, single-slot actions only |
| `steps` | `tuple[SequenceStep, ...]` | empty when `no_change` |
| `no_change` | `bool` | |
| `refusal` | `str \| None` | reason, evaluated with the caller's opt-ins |
| `reads` | `tuple[bytes, ...]` | frames of the reads done while planning |

Step lists: save / restore-slot = `stored_slot(i)` · wait 0.3 · `commit` · wait 0.1 ·
`preset_select(i)`. Restore-all = `stored_image` · wait 0.3 · `commit` · wait 0.1 ·
`preset_select(return_index)`.

## SequenceResult

| Field | Type | Notes |
|---|---|---|
| `plan` | `SequencePlan` | |
| `steps` | `tuple[StepOutcome, ...]` | `StepOutcome(step, status, reply)`; status `acked`, `nak`, `no_reply`, `not_sent`, `waited` |
| `stored_may_have_changed` | `bool` | true once any persistent frame was written to the transport |
| `verified` | `bool` | read-back equals what was written, pedal on `return_index`, buffer = stored preset |
| `read_back` | `bytes \| None` | slot or image as read after the sequence |
| `backup` | `Backup` | the automatic backup taken before the first write |

State transitions of a run: `planned → backed_up → slot_or_image_written → committed → selected →
verified`. A failure at any arrow stops the run; the result (attached to the raised error) shows
the last state reached.

## Backup as restore input

`Backup.from_document` (003) plus `restore_problems(backup, pedal_firmware) -> list[str]`:
`format_version` ≠ 1, header ≠ `a5 5a`, image ≠ header + presets, not 36 presets of 21 bytes,
firmware differs from the pedal's (`firmware_mismatch`, overridable with `experimental`).

## WriteRefusedError reasons (added)

`unsafe_required`, `bypassed`, `tuner_mode`, `edit_mode`, `unrecognised_state`, `not_bypassed`,
`firmware_mismatch`. Removed: `not_edit_mode` is no longer raised (kept in the type for
compatibility until 1.0).

## DeviceSnapshot (extended)

`pedal_state: PedalState` added; JSON gets a top-level `pedal_state` string (`normal`, `edit`,
`tuner`, `bypass`, `loading`, `unrecognised`).
