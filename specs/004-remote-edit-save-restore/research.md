# Research: Remote editing in normal mode, save, restore, bypass and loopback

All decisions below resolve the Technical Context; no NEEDS CLARIFICATION remains. Protocol facts
come from [`command-layer.md`](../protocol/command-layer.md) and
[`app-features.md`](../protocol/app-features.md), with the confidence stated there. Decisions of
003 ([research.md](../003-preset-backup-edit-writes/research.md)) stand unless changed here.

## R1 — Pedal state

- **Decision**: one pure function classifies the pedal from the global block (4 B) and the edit
  buffer (21 B):

  | State | Rule |
  |---|---|
  | `bypass` | slot = `ff` and the buffer is 21 × `00` |
  | `normal` | mode = 1, slot 0–3, bank 0–8 |
  | `edit` | mode = 0, slot 0–3, bank 0–8 |
  | `tuner` | mode = 2 |
  | `unrecognised` | anything else: slot `ff` with a non-zero buffer, an all-zero buffer with a valid slot (spec Edge Cases), an unknown mode value, bank or slot out of range |

  A single classification cannot tell bypass from the one-cycle loading transient (same bytes), so
  the session confirms `bypass` with a second read of both regions 300 ms later; if the second
  read differs, the state is taken from the second read. `watch` already polls: one cycle is
  reported as `loading`, two consecutive cycles as `bypass`.
- **Rationale**: every guard in this feature ("refused in bypass", "save only in normal mode")
  needs the same answer; check 2 showed the bypass bytes held for at least 2 s, the 2026-11-16
  transient lasted one 0.5 s cycle.
- **Alternatives**: treat slot `ff` alone as bypass (wrong during a load); a longer confirmation
  window (slows every command for no evidence that loads take longer).

## R2 — `set` outside edit mode

- **Decision**: `plan_set` accepts states `normal` and `edit`; refusal reasons `tuner_mode`,
  `bypassed`, `unrecognised_state` replace `not_edit_mode`. The sequence (read, one write, ACK,
  re-read) and the confidence gate are unchanged, so the knob block runs without
  `--experimental` in normal mode (confirmed there, check 1) and the block switches and LED colour
  still need it (observed, edit mode only).
- **Rationale**: check 1, confirmed over two connections; the app never checks the mode.
- **Alternatives**: a `--normal-mode` flag (keeps a restriction hardware has refuted); separate
  confidence per mode in the write-messages table (one more column for a difference only two rows
  have: recorded in Notes instead, and both are covered by gate session A).

## R3 — Section input

- **Decision**: `protocol/bytemap.py` gains `SECTION_FIELDS`, the set of fields whose app sections
  are at least `observed` (today `reverb_decay` only), and `section_raw(section, position)` =
  `44 · index(section) + position − 1` for position 1–40, the inverse of the existing
  `reverb_decay_parts`. The CLI takes `set <field> <value> [<position>]`: one argument is the raw
  value as today, two are colour and position. Colour names are the documented ones (`blue`,
  `orange`, `green`), case-insensitive. The raw values the app shows as `X` are reachable only as
  raw numbers.
- **Rationale**: matches what the user reads in the app; a single source (the doc table, already
  checked against the code by `test_bytemap_doc.py`).
- **Alternatives**: `orange:10` or `orange10` syntax (less like the app's wording); accepting
  `x` (four raw values per section, no observed mapping of which `X` is which).
- **MOD FX and DLY Mix**: a read-only check in the M0 gate (owner sets a position in the app,
  closes it, runs `preset dump`; the same method as the reverb-decay readings). If the readings fit
  `raw // 44`, both fields are added to the doc and to `SECTION_FIELDS` as `observed` in M3's docs
  change; if not, they stay raw-only and the result is documented.

## R4 — Reload (discard unsaved edits)

- **Decision**: `openvave preset reload` / `TankG.reload_preset()`: read the state, then run the
  existing select path for the loaded index (confirmed message). Refused in `bypass` (the slot is
  unknown: use `bypass off <position>`), `tuner` and `unrecognised`; in `edit` it needs
  `--discard-edits` as select does. Sent even when the buffer already equals the stored preset?
  No: "nothing to discard", nothing sent.
- **Rationale**: a named action for FR-005 that reuses the one select path and its verification.
- **Alternatives**: telling users to type `preset select <same>` (they must first find the
  position); a host-side undo stack (state between runs, YAGNI).

## R5 — Closed write surface, extended

- **Decision**: `WriteTarget` gains five constructors, each fixing type 4, address and length:

  | Constructor | Address | Len | Data | Class |
  |---|---|---|---|---|
  | `bypass(i)`, i 0–35 | `0xE1000000 + i` | 1 | `01` only | volatile |
  | `loopback()` | `0xD0000000` | 1 | `00` or `01` | volatile |
  | `stored_slot(i)`, i 0–35 | `2 + 21·i` | 21 | any 21 bytes | **persistent** |
  | `commit()` | `0xF0000000` | 0 | empty | **persistent** |
  | `stored_image()` | `0x00000000` | 758 | must start `a5 5a` | **persistent** |

  `WriteTarget.persistent` is derived from the kind. `encode_frame` still refuses every `0x22`
  body outside the allowlist, so erase (`0x21`), type 6, the global block, the whole edit buffer
  (`0x10000000` × 21), any stored address that is not a slot start, and any other length stay
  unencodable. The session has one extra rule: a persistent target is sent only from the
  save/restore sequence runner, and that runner refuses without `unsafe=True`. The test-suite
  audit lists the frames each test may send; persistent frames are allowed only in the save and
  restore tests.
- **Rationale**: same enumerable surface as 003 (Constitution IV); the dangerous subset is a
  property of the target, not of the caller's goodwill.
- **Alternatives**: a second "unsafe encoder" module (two allowlists to keep in sync); a generic
  stored-area write with address checks at the call site (one wrong offset corrupts two presets).

## R6 — Opt-ins

- **Decision**: two independent booleans on the guarded path. `unsafe`: required whenever the
  planned sequence contains a persistent target; never implied by `experimental`. `experimental`:
  required when **any** message of the sequence is not `sendable_by_default` (003 R4: row
  `confirmed`, ACK ≥ `observed`, firmware listed). Refusal reasons `unsafe_required`,
  `experimental_required`, `untested_firmware`; when both are missing the refusal names both.
- **Rationale**: `--unsafe` says "I accept that stored presets change" and stays forever;
  `--experimental` says "this message is not confirmed yet" and disappears as gates promote rows.
- **Alternatives**: `--unsafe` alone (hides that the image write is a hypothesis); a typed
  confirmation prompt (not scriptable; the CLI is text I/O, Constitution V).

## R7 — Write messages table

- **Decision**: the "Write messages" table gets five rows: `bypass(i)`, `stored_slot(i)`,
  `commit`, `stored_image`, `loopback`, all **`hypothesis`** at the start of this feature. The
  table's rule (003 R4) counts only openvave's own sends; checks 2–4 were sent by `poc/` scripts
  and are cited in Notes, like the app-log sightings were. Consequence: until gate session A,
  bypass, save, restore and loopback all need `--experimental`.
- **Rationale**: keeps one rule for the table; the scripts' captures remain the fixtures for the
  offline replay tests and the evidence in the address map (already `observed` there).
- **Alternatives**: start the rows at `observed` citing the check captures (bends the table's
  rule; the first openvave send would then not need a gate step, against FR-036).

## R8 — Save sequence

- **Decision**: `plan_save(to=None)` reads state, buffer and the target slot and returns a
  `SequencePlan`: steps `slot_write(i, buffer)` → wait 300 ms → `commit` → wait 100 ms →
  `select(i)`, plus the byte diff slot → buffer. `save_preset` executes the same plan: each
  write's ACK is checked before the next step; then the 003 select verification (global until slot
  ≠ `ff`, buffer) and a read of slot `i`. Saved iff slot = bytes written, bank/slot = target and
  buffer = slot. Allowed in state `normal` only; `no_change` when buffer = slot.
- **Rationale**: exactly the sequence of checks 3 and 4 (and the app's); timing not tuned because
  nothing shows what is safe to shorten.
- **Alternatives**: skipping the select (the app always selects; whether the pedal's RAM copy and
  buffer stay coherent without it is unknown); reading the slot back before the commit and
  stopping on mismatch (kept: it is an extra read, done between the slot ACK and the 300 ms wait's
  end, as check 4's script did; a mismatch stops before the commit).

## R9 — Automatic backup

- **Decision**: the sequence runner takes the full 003 backup itself (same connection), then
  calls a required `on_backup(backup)` callback and only continues when it returns. The CLI's
  callback writes `tankg-backup-<YYYYmmdd-HHMMSS>-before-<save|restore>.json` (directory:
  `--backup-dir`, default the current directory) with the existing atomic writer; a name clash
  gets a numeric suffix, never an overwrite. Any exception from the backup or the callback aborts
  before the first write. Dry run takes no backup. There is no flag to skip it.
- **Rationale**: Constitution IV says the CLI "MUST offer" a backup; for the first persistent
  writes the project ships, making it unconditional costs 2–4 s and removes a way to lose data.
  A callback keeps file I/O out of the library (Constitution V).
- **Alternatives**: library writes the file (I/O in the library); `--no-backup` (owner did not ask
  for it; can be added later without breaking anything).

## R10 — Restore

- **Decision**: `Backup.from_document` (existing, validates the invariants) plus restore-only
  checks: `format_version` 1, header `a5 5a`, image = header + 36 presets, file firmware = pedal
  firmware (else `experimental` needed). An invalid file is a usage error (exit 2) before any
  connection. `plan_restore(backup, slot=i)` = the save sequence with the file's bytes for slot
  `i`, in state `normal` only, like save. `plan_restore(backup, all=True)` =
  `stored_image(file image)` → wait 300 ms → `commit` → wait 100 ms → `select(previously loaded
  i)`; verification = a full backup read compared with the file. The diff (slots that differ) is
  computed from the automatic backup; no difference → `no_change`. Restoring the loaded slot, or
  all, with buffer ≠ stored preset needs `discard_edits`.
- **Rationale**: the file's `image` hex is the exact 758 bytes (003 R7 foresaw this). The owner
  chose the app's single image write for the full restore (2026-11-17).
- **Alternatives**: the app's whole-edit-buffer write after an import (one more hypothesis
  message; the confirmed select reloads the same bytes); restoring a slot into another position
  (out of scope).

## R11 — Sending a frame longer than one Bluetooth write

- **Decision**: the BLE transport splits a frame longer than `ATT MTU − 3` (182 B on macOS at MTU
  185, 244 B at the app's 247) into consecutive write-without-response chunks, in order, with no
  delay added; `FakeTransport` reassembles them the way it already splits long replies. Only the
  image write (773 B = 5 chunks at MTU 185) needs it; every other request is at most 36 B. This is
  a **hypothesis**: the pedal reassembling a split request has never been seen (only replies have
  been reassembled, and how the app splits its 773-byte import is not known beyond "one command").
- **Gate design that makes it safe to find out**: the first image write ever sent carries the
  image **just read from the pedal** (a byte-identical no-op, like check 3). If the pedal only
  takes part of it, the part it writes equals what is already there. The step is judged by: one
  ACK after the last chunk, no stray replies, the next read works, backup identical. Only then is
  an image with differences sent.
- **Fallback** (decided now, built only if the gate fails): full restore as up to 36 slot writes
  (each `observed`), 300 ms, one commit, select; slots equal to the file are skipped. Several slot
  writes before one commit is what the app's swap does (hypothesis for more than two).
- **Alternatives**: write-with-response / long write (`ae41` is write-without-response only);
  shipping only the slot-by-slot path (the owner preferred the app's way; kept as the fallback).

## R12 — Bypass

- **Decision**: `openvave bypass on` / `TankG.bypass_on()`: state must be `normal`; if buffer ≠
  stored preset, needs `discard_edits`; one write `bypass(loaded i)`; verified by the R1 bypass
  rule on a re-read; the result carries the position to return to and the CLI prints
  `openvave bypass off <position>`. `openvave bypass off <position>` / `TankG.bypass_off(i)` =
  the select path, allowed only in state `bypass` (in `normal` it says "not bypassed" and points to
  `preset select`). Bypass on when already bypassed: "no change".
- **Rationale**: check 2. The pedal reports bank but not slot while bypassed, and the tool keeps
  no state between runs, so the position is an argument.
- **Alternatives**: a state file remembering the position (stale as soon as a footswitch is
  pressed); guessing slot A of the reported bank (wrong three times out of four).

## R13 — Reporting bypass in read commands

- **Decision**: `DeviceSnapshot` gains `pedal_state` (R1). Human output of `info` and `preset
  dump`: a line `state: bypass (all blocks off; the pedal does not report the loaded slot)`, the
  raw buffer bytes, and no decoded field lines. `watch`: a `state` change line. JSON: an added
  top-level `pedal_state` string; `fields` are still listed (they describe the buffer bytes) and
  `schema_version` stays 2. `preset dump` and `info` do the R1 second read only when the first
  one looks like bypass.
- **Rationale**: FR-011; additive JSON keeps 0.3.0 consumers working.
- **Alternatives**: emptying `fields` in bypass (changes the meaning of an existing key).

## R14 — Loopback

- **Decision**: `openvave loopback on|off` / `TankG.set_loopback(on)`: read status byte, no change
  if equal, one write `loopback()` with `01`/`00`, ACK, re-read. Any pedal state except
  `unrecognised`. Always `--experimental` in this feature unless both gate sessions confirm it.
  The byte map's status row is named `loopback` (switch, on = 1, off = 0) only when gate session A
  observes an effect; naming is additive.
- **Rationale**: FR-026/027; the app writes it alone, without a commit.
- **Gate**: read; off; owner listens and records over USB; read; power cycle; read (persistence);
  on; read. If the pedal misbehaves with it off, the step that turns it back on is already
  approved in the same gate step.

## R15 — Sequence result and failures

- **Decision**: a multi-write action returns a `SequenceResult`: ordered `steps`, each
  `{kind, frame, status}` with status `acked` / `nak` / `no_reply` / `not_sent`, plus `verified`,
  `stored_may_have_changed` (true once a persistent write was sent, whatever its reply),
  `backup` and the diff. Errors reuse the 003 classes and carry the partial result:
  `WriteNakError` (exit 7), `ConnectionLostError` / `RequestTimeoutError` (exit 6),
  `WriteNotAppliedError` (exit 8, verification mismatch). New `WriteRefusedError` reasons:
  `unsafe_required`, `bypassed`, `tuner_mode`, `edit_mode`, `unrecognised_state`,
  `not_bypassed`, `firmware_mismatch`. No new exit code. Nothing is retried; the CLI prints the
  steps, the automatic backup's path and the two recovery commands (`preset backup`, `preset
  restore <automatic backup> --all`).
- **Rationale**: FR-031; a user who lost the link after a slot write must know exactly where the
  sequence stopped.

## R16 — Fixtures and tests

- **Decision**: offline replay tests use the committed check captures (`check2-bypass`,
  `check3-noop_save`, `check4-real_save`, `check4-verify_restore`, `gate-normal_knob_gain*`),
  which hold only public preset 1B/1C bytes. Restore-all uses the synthetic image of
  `tests/support/storage_fixture.py`. Gate excerpts of openvave's own sends are added in M3/M4 with
  the existing excerpt tool; a full-restore excerpt keeps the frames' headers and replaces the
  image payload with the synthetic image (Constitution VI) — the private record keeps the real
  one. Hardware tests: writes still need `--hardware` and `OPENVAVE_HW_WRITES=1`; persistent ones
  also `OPENVAVE_HW_UNSAFE=1`.

## R17 — Versioning

- **Decision**: release 0.4.0 (additive). `schema_version` stays 2; backup `format_version` stays
  1. New JSON: `sequence-result.schema.json` for save / restore; bypass, loopback and reload reuse
  `write-result.schema.json`. Behaviour change listed in the changelog: `set` no longer refuses
  normal mode; reason `not_edit_mode` is no longer raised.
