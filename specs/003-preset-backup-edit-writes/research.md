# Research: Preset backup and first edit-buffer writes

All decisions below resolve the Technical Context; no NEEDS CLARIFICATION remains. Protocol facts
come from [`command-layer.md`](../protocol/command-layer.md) (confidence as stated there).

## R1 — Backup read strategy

- **Decision**: read the header (`0x0` × 2), then the 36 presets one by one (`2 + 21·i` × 21), then
  the whole image (`0x0` × 758); the backup is valid only if bytes 2–757 of the image equal the 36
  single reads and bytes 0–1 equal the header read. The file stores the image bytes and the
  per-preset data.
- **Rationale**: both paths were confirmed on 2026-11-17. Single reads fit one notification (the
  proven path); the image read exercises multi-notification reassembly and gives an independent
  copy, so a lost or corrupted notification cannot pass silently (spec edge case).
- **Alternatives**: image read only (fast, but a single path, no cross-check); single reads only
  (no independent copy); reading twice and comparing (doubles time without a different path).

## R2 — Closed write surface

- **Decision**: `0x22` joins `ALLOWED_COMMANDS`, but `encode_frame(WRITE, …)` is only reachable
  from `build_write(target, data)`, and `WriteTarget` can only be constructed by
  `knob_block()`, `block_switch(k)` (k 0–3), `led_colour()` and `preset_select(i)` (i 0–35). Each
  fixes type 4, address and length; `build_write` rejects data of another length. `0x21`,
  addresses `0x00000000–0x000002F5`, `0xF0000000` and `0xD0000000` writes have no constructor and
  `encode_frame` refuses `0x21`. The test-suite audit accepts `0x22` frames only when
  `(type, address, length)` is in the allowlist.
- **Rationale**: keeps the risk surface enumerable and auditable (Constitution IV, FR-013).
- **Alternatives**: a generic `write(address, data)` with a denylist (one forgotten address is a
  brick risk); a separate "unsafe" encoder now (YAGNI; that is the later spec).

## R3 — Write acknowledgement

- **Decision**: `parse_write_reply(frame)`: decode the frame (checksum/length as usual); accepted
  iff frame length is 8, command byte (offset 2) is `0x00` and the status byte (offset 6) is
  `0x00`. Otherwise `WriteNakError` carrying the raw reply. A timeout is `RequestTimeoutError`
  (exit 6), never retried automatically for writes (a retry could double-apply a non-idempotent
  future write; for edit-buffer writes it is harmless but the rule is kept simple).
- **Rationale**: matches the app's check; unknown status codes are reported raw (spec FR-011).
- **Alternatives**: retry on timeout like the app (hides lost replies during gates).

## R4 — Write messages table and confidence gate

- **Decision**: add a table "Write messages" to `command-layer.md` with columns
  `Target | Type | Address | Len | Data | Reply | Confidence | Firmware | Evidence | Notes`, one row per
  target kind (knob block; block switch k = 0, 1, 2, 3 as four rows; LED colour; preset select) plus
  one row for the ACK. `protocol/writes.py` mirrors it as `WRITE_MESSAGES`; a test parses the doc
  table and compares (same approach as the byte map, `tests/support/bytemap_doc.py`). A write is
  sent without `--experimental` only if its row is `confirmed` **and** the ACK row is at least
  `observed` **and** the pedal's firmware is in the row's firmware set.
- **Rationale**: Constitution IV ("hypothesis messages MUST NOT be sent by default"), extended
  conservatively to `observed` (app-log-only evidence is not our own replay). Promotion in the docs
  then automatically relaxes the gate once code mirrors it.
- **Alternatives**: gate only on `hypothesis` (would let app-log-only `observed` rows send by
  default before we ever replayed them); a hard-coded set (drifts from docs).

Initial rows (before M2): every write row and the ACK row are `hypothesis`. A row becomes
`observed` only when it cites a committed capture of this project's own send; the app-log
sightings (knob block, switch k = 1, preset select) are recorded in Notes, not as evidence,
because the log has no raw bytes. Before M3 every write therefore needs `--experimental`.

## R5 — Where writes live in the library

- **Decision**: methods on `TankG`: `plan_set(field, value)` / `set_field(field, value, *,
  experimental=False)` and `plan_select(index)` / `select_preset(index, *, discard_edits=False,
  experimental=False)`. `plan_*` performs the safe reads (global, edit buffer) and returns a
  `WritePlan` (all frames: reads done, write to send) without writing; `set_field` /
  `select_preset` = plan + checks + send + ACK + verify. CLI `--dry-run` calls `plan_*` and prints.
- **Rationale**: one session, one lock, one guarded path; dry-run shows exactly the frames the real
  call would send because the real call executes the same plan (SC-003).
- **Alternatives**: a separate `TankGWriter` class (duplicates connection handling); pure offline
  dry-run (cannot build the knob block or check mode without reading).

## R6 — Field-to-target mapping

- **Decision**: knob fields (byte map offsets 4–17: `noise_gate` … `ir_cab`) → knob block, rebuilt
  from the freshly read edit buffer with only that byte changed. Switch fields (`amp_on`, `mod_on`,
  `delay_on`, `reverb_on`) → `block_switch(offset)`, value from the row's on/off raw values. LED
  colour → `led_colour()` with 3 bytes (accepts `#rrggbb` or `r,g,b`). Values validated against the
  byte map range (0–127, selectors 0–8, colour 0–255 each). Setting a value equal to the current one
  → "no change", nothing sent.
- **Rationale**: mirrors how the app writes; keeps one source for ranges (the byte map).
- **Alternatives**: 1-byte writes at `0x10000004 + n` (never seen in the app: unverified address
  granularity).

## R7 — Backup file

- **Decision**: JSON, `kind: "openvave.preset-backup"`, `format_version: 1`, `created_at` (UTC
  ISO-8601), `tool` (`openvave <version>`), `identity` (name, firmware, raw hex; no device
  identifier/MAC), `layout` (offset 2, size 21, count 36), `header` (hex), `image` (hex, 758 B),
  `presets[]` (`index`, `position` e.g. `"1A"`, `bank` 1–9, `slot` `"A"`–`"D"`, `raw` hex,
  `fields` as in `preset dump --json`, `unknown_offsets`), `warnings[]`. Default path
  `./tankg-backup-<YYYYmmdd-HHMMSS>.json`; written to a temp file in the same directory and
  renamed; existing target refused unless `--force`. `--json` prints the same document inside the
  usual envelope.
- **Rationale**: human-inspectable, diffable, complete enough for a later restore (image hex is the
  exact bytes), no personal identifiers (Constitution VI for anything a user shares).
- **Alternatives**: raw 758-byte `.bin` (not self-describing; can be added later from `image`);
  the app's export format (unknown, vendor-specific).

## R8 — Errors and exit codes

- **Decision**: `WriteRefusedError` (exit 1; subclass of `UnsafeCommandError`; reasons:
  `not_edit_mode`, `out_of_range`, `untested_firmware`, `experimental_required`,
  `edits_would_be_discarded`, `unknown_field`); `WriteNakError` (exit 7; subclass of
  `ProtocolError`); `WriteNotAppliedError` (exit 8, new); backup cross-check mismatch →
  `ProtocolError("backup_mismatch")` (exit 7); existing backup file → usage error (exit 2).
- **Rationale**: keeps 001's code meanings; adds one code for the new, distinct outcome.

## R9 — Verification after writes and select

- **Decision**: after an ACKed edit write, re-read `CURRENT_PRESET` once (and `GLOBAL` to detect a
  mode change); applied iff the targeted bytes equal the requested values; every changed byte is
  reported. After select: wait 100 ms (as the app), then read `GLOBAL` up to 10 times, 100 ms
  apart, until slot ≠ `0xFF`; applied iff bank/slot equal the target and `CURRENT_PRESET` equals a
  fresh single read of stored preset `i` (when not in edit mode).
- **Rationale**: the pedal never pushes; the transient loading state was observed once.
- **Alternatives**: no verify (spec requires it); continuous polling (out of scope).

## R10 — Fixtures

- **Decision**: a synthetic stored image: header `a5 5a`; presets built from the public fw96 1B
  bytes and simple synthetic patterns (`index`-dependent values, all within ranges); the
  `FakeTransport` serves it at the storage addresses, splitting the image reply at 182 B like the
  real capture. ACK/NAK frames and post-write buffers come from sanitized M2/M3 gate excerpts
  (they contain only our own edit values and public presets). The real 2026-11-17 image stays in
  `captures/private/`.
- **Rationale**: Constitution III (real frames where they carry protocol facts) and VI (no factory
  preset content).

## R11 — Hardware tests

- **Decision**: `tests/hardware/test_hw_backup.py` (opt-in with `--hardware`, read-only). Write
  hardware tests exist only as gate helpers and require both `--hardware` and
  `OPENVAVE_HW_WRITES=1`; they are never collected in CI.
- **Rationale**: Constitution III/IV; prevents an accidental write from a broad `pytest --hardware`.

## R12 — Versioning

- **Decision**: release 0.3.0 (additive API and commands). Existing `info`/`preset dump` JSON is
  unchanged, so `schema_version` stays 2; new commands' JSON uses the same envelope with
  `schema_version` 2. Naming byte map rows 18–20 in M4 is additive (an unknown offset becomes a
  named field) and is listed in the CHANGELOG.
- **Rationale**: semver (Constitution V); 002 bumped only for renames.
