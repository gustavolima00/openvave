# Feature Specification: Closing the Tank-G mapping gaps

**Feature Branch**: `claude/polish-names-pending-4f3232` (feature directory `007-mapping-gaps`)

**Created**: 2026-11-19

**Status**: Draft

**Input**: User description: "Close openvave's remaining mapping and configuration gaps on the
Tank-G (fw 96). (1) A second independent hardware gate session for the writes still `observed` —
the four block switches, the preset LED colour and the loopback flag — so they become `confirmed`
and run without --experimental. (2) Name the bytes still `unknown` in the byte map once evidence
allows: preset bytes 18–20 as the preset LED colour and the status byte as `loopback`; dump, watch
and info then show them as fields (JSON gains keys only). (3) Label IR cab position 0 as off once
heard, and name amp types / IR cabs only if the owner supplies the manual's list with evidence.
(4) Map the MASTER knob if any byte follows it. (5) Preset management with already-confirmed writes
only: copy, swap, export one preset to a file, import a file into a slot; behind --unsafe with the
automatic backup first. Out of scope: IR import, factory restore, erase, firmware update, writes to
the global block, MIDI."

**Builds on**: [`004-remote-edit-save-restore`](../004-remote-edit-save-restore/spec.md) (writes,
gate sessions, `--experimental` / `--unsafe`, the save/restore sequence and automatic backup) and
[`002-preset-byte-map`](../002-preset-byte-map/spec.md) (byte map, step fixtures, `watch`).

**Protocol source of truth**: [`specs/protocol/command-layer.md`](../protocol/command-layer.md)
(byte map, write messages, confidence) and [`specs/protocol/app-features.md`](../protocol/app-features.md).
This feature sends **no new pedal message**: every write it uses already exists in the write table.
What changes is the confidence of six rows, the names of four bytes, and new sequences built from
confirmed writes.

**Parallel work**: spec 006 (MCP server) is built in another session and does not touch the
protocol layer or the protocol docs; this spec does. Where both touch the CLI or the public API,
the later one rebases.

## Starting point (0.5.0 + the unreleased change of 2026-11-19)

| Area | Today | Gap |
|---|---|---|
| Block switches `0x10000000 + k` | `observed` (one session), need `--experimental` | a second session |
| LED colour `0x10000012` | `observed`, needs `--experimental`; meaning seen once (LED turned red) | a second session |
| Loopback `0xD0000000` | `observed`, needs `--experimental`; meaning seen once (Bluetooth audio in the USB recording) | a second session |
| Preset bytes 18–20 | `unknown` in the byte map (dump lists them as unknown) | a step fixture → name them |
| Status byte | `unknown` in the byte map, although it is the loopback flag | a status-byte fixture and fixture support for the status region → name it |
| IR cab 0 | hypothesis "cab off" (manual + app display) | heard on hardware → label `off` |
| Amp type / IR cab names | none; the manual's lists are images, the app shows numbers | the owner's transcription with evidence, or stay numbered |
| MASTER knob | not mapped; nothing known to follow it | a watch step |
| Copy / swap / export / import one preset | not available (only save the current sound and restore from a full backup) | new commands from confirmed writes |

## Clarifications

### Session 2026-11-19

- Q: Order of work? → A: P1 (docs, no hardware) is done; then the hardware gate session (this
  spec's US1–US3), then names (US4), then preset management (US5).

## User Scenarios & Testing *(mandatory)*

The owner and other Tank-G users drive the pedal from the command line or from Python. Hardware
steps are run by the owner in their own terminal; every write is posted and approved before it is
sent, with a backup before and after, as in the spec 004 gate sessions.

### User Story 1 - Switch blocks, colour presets and toggle loopback without `--experimental` (Priority: P1)

A user turns the delay block on, colours a preset's LED green, or turns loopback off with the same
plain commands that already work for knobs, preset select and bypass, without an `--experimental`
flag that suggests the operation is risky.

**Why this priority**: these are the last everyday remote controls still marked experimental; one
short hardware session closes them.

**Independent Test**: after a second, independent gate session (new connection, another preset
than spec 004 session A), `set delay_on on`, `set led_colour …` and `loopback off|on` succeed
without `--experimental` on firmware 96 and are still refused on other firmware without it.

**Acceptance Scenarios**:

1. **Given** the pedal on fw 96 in normal mode, **When** the user runs `openvave set mod_on on`
   without `--experimental`, **Then** the switch is written, the re-read shows it applied, and the
   output names the change as for a knob.
2. **Given** each of the four block switches, the LED colour and loopback, **When** their rows in
   the write table cite two independent gate sessions, **Then** the rows read `confirmed` and the
   commands run without `--experimental`.
3. **Given** a pedal reporting another firmware, **When** the user runs any of these writes without
   `--experimental`, **Then** it is refused as today (untested firmware).
4. **Given** a gate step whose write is not applied or not acknowledged, **When** the session is
   recorded, **Then** the row stays `observed` and the failure is documented.

---

### User Story 2 - Read the LED colour and loopback flag like every other field (Priority: P1)

A user running `openvave preset dump`, `info` or `watch` sees the preset's LED colour and whether
loopback is on as named fields, instead of three "unknown" preset bytes and an unknown status byte.

**Why this priority**: they are the only bytes of the read regions without a name; naming them makes
the byte map complete for fw 96.

**Independent Test**: with step fixtures for bytes 18–20 and the status byte committed, the byte map
names them, the doc/code parity test passes, and `preset dump` shows the colour (e.g. as a hex
colour) and `loopback: on|off`; JSON output only gains keys.

**Acceptance Scenarios**:

1. **Given** a preset whose bytes 18–20 are `ff 00 00`, **When** the user runs `preset dump`,
   **Then** the human output shows the LED colour as one readable value and each byte under its
   name, and the JSON carries the same values under new keys.
2. **Given** status byte `00`, **When** the user runs `info` or `preset dump`, **Then** the output
   shows loopback off; with `01`, on.
3. **Given** `watch` running while the LED colour or loopback is changed (by openvave or the app),
   **When** the next poll arrives, **Then** the change is reported under the field's name.
4. **Given** a JSON consumer of 0.5.0, **When** it reads the new output, **Then** every key it used
   is still there with the same meaning (`schema_version` changes only if a key is renamed or
   removed, which this story does not do).

---

### User Story 3 - Know what IR cab 0 and the MASTER knob do (Priority: P2)

A user sees `ir_cab` position 0 labelled `off` (once heard on hardware), and learns whether the
MASTER knob is reported anywhere.

**Why this priority**: small, but removes the two "not known" lines from the user docs; both are
checked in the same hardware session as US1–US2.

**Independent Test**: the owner sets `ir_cab 0` and hears the cabinet simulation disappear (and come
back at 1); the byte map labels position 0 `off` with the session as evidence. A `watch` step while
turning MASTER either shows a byte that follows it (then it is mapped) or nothing (then the docs say
MASTER is not reported, observed).

**Acceptance Scenarios**:

1. **Given** the owner's labelled listening step for `ir_cab` 0 vs 1, **When** it is recorded,
   **Then** `preset dump` shows `off` for raw 0 and `#1`–`#8` for the rest, at the recorded
   confidence.
2. **Given** a labelled `watch` step turning only MASTER from end to end, **When** no read byte
   changes, **Then** the docs record "MASTER is not reported over Bluetooth" as observed; **when** a
   byte changes alone, **then** it is added to the byte map as any knob.

---

### User Story 4 - See amp model and cabinet names (Priority: P3)

A user sees which amp model and which factory cabinet a preset uses by name instead of `#0`–`#8`.

**Why this priority**: useful but blocked on a source: neither the app nor the manual's text names
them. It ships only if the owner provides the manual's lists (or the vendor's desktop software's
display) and the positions are matched on hardware.

**Independent Test**: with a committed evidence record (the owner's transcription of each position's
label, with source and date), `preset dump` shows the names; without it, nothing changes.

**Acceptance Scenarios**:

1. **Given** the owner's transcription, matched position by position on the pedal, **When** it is
   recorded, **Then** the names appear in dump/watch/set output with their confidence, and the raw
   position stays available.
2. **Given** an IR cab slot that may have been replaced by a user-imported IR, **When** names are
   shown, **Then** the docs say they describe the factory IRs only.
3. **Given** a name that is a trademark of another company, **When** it is documented, **Then** it
   is used only to describe the sound character, as the vendor's manual does, with the same
   disclaimer.

---

### User Story 5 - Copy, swap, export and import single presets (Priority: P3)

A user copies preset 1A to 3C, swaps 2B and 4D, exports 1D to a file to share it, or imports a
shared file into a slot, each with one command and the same safety as `preset save` / `restore`.

**Why this priority**: the official app offers swap, share and import of single presets; openvave
covers only "save the current sound" and "restore from a full backup". All needed writes are already
confirmed.

**Independent Test**: on a fake pedal, each command plans the exact frames (dry run), refuses without
`--unsafe`, takes the automatic backup first and verifies the result by reading the slots back; on
hardware, one copy and one swap are verified and undone with `preset restore`.

**Acceptance Scenarios**:

1. **Given** `openvave preset copy 1A 3C --unsafe`, **When** it runs, **Then** it reads 1A, takes
   the automatic backup, writes 1A's bytes to 3C, commits, and verifies 3C equals 1A; the loaded
   preset is reselected so the pedal shows what it showed before (or 3C if 3C was loaded).
2. **Given** `openvave preset swap 2B 4D --unsafe`, **When** it runs, **Then** after the backup both
   slots are written with each other's bytes, committed once, and verified; if the second write
   fails, the output says which slot holds what and how to restore from the backup.
3. **Given** `openvave preset export 1D --output tone.json`, **When** it runs, **Then** it only
   reads, and writes a file holding the 21 preset bytes with firmware, source position and time; it
   never overwrites a file without `--force`.
4. **Given** `openvave preset import tone.json --to 2C --unsafe`, **When** it runs, **Then** it
   checks the file before connecting, takes the automatic backup, writes the slot, commits,
   selects 2C and verifies, exactly as `preset restore --slot`.
5. **Given** any of the four commands without `--unsafe` (copy, swap, import) or with `--dry-run`,
   **When** it runs, **Then** nothing is written and the exact frames are shown.
6. **Given** source and target are the same slot (copy) or the same pair (swap of a slot with
   itself), **When** the command runs, **Then** it is a usage error and nothing is sent.

### Edge Cases

- A gate step in US1 finds the pedal on another preset than the last command left it (the
  unexplained preset changes of spec 004): every write re-reads the state first, as today; the
  step is recorded with the observed preset.
- The status byte is written by loopback while `watch` runs in another process: impossible, the
  pedal accepts one connection; `watch` reports changes made by the pedal or after reconnecting.
- LED colour bytes outside a "colour-looking" value (any 0–255 is valid): shown as-is.
- Copy or swap involving the loaded preset while the edit buffer holds unsaved edits: refused unless
  `--discard-edits`, as `preset reload`.
- Swap when the two slots already hold identical bytes: nothing is written ("already equal").
- Import of a file from another firmware, of the wrong size, or that is not a single-preset file:
  usage error before connecting; a full backup file is pointed to `preset restore` instead.
- A user-imported IR cab: the pedal reports only the position, so names (US4) may be wrong for that
  slot; the docs say so.
- Power loss during copy/swap/import: unknown outcome, warned before the first persistent write as
  `preset save` does; the automatic backup is the way back.

## Requirements *(mandatory)*

### Functional Requirements

**Gate session and confidence (US1)**

- **FR-001**: A second gate session MUST exercise each of `block_switch(0)`–`block_switch(3)`,
  `led_colour` and `loopback` on fw 96 over a new connection, on another preset than spec 004 gate
  session A, each step approved before sending and followed by a re-read, with a full backup before
  and after the session.
- **FR-002**: Each step MUST leave a committed, sanitised excerpt of this project's own send and the
  pedal's replies; a row becomes `confirmed` only when it cites excerpts from two independent
  sessions (the rule of the write table).
- **FR-003**: Once confirmed, the writes MUST run without `--experimental` on fw 96 and MUST still
  need it on other firmware; no other safety rule changes.
- **FR-004**: The session MUST NOT send anything outside the existing write table; erase, factory
  reset, firmware update and global-block writes are never sent.

**Naming read bytes (US2, US3)**

- **FR-005**: Preset bytes 18–20 MUST be named in the byte map (the LED colour's red, green and blue
  parts) once a committed step fixture shows each changing as the colour changes, with the
  confidence that evidence supports.
- **FR-006**: The status byte MUST be named `loopback` (switch: on = `01`, off = `00`) once a committed
  status-byte step fixture exists; the fixture index and its checks MUST cover the status region.
- **FR-007**: `preset dump`, `info` and `watch` MUST show the new fields in human output (the LED
  colour also as one combined value) and JSON MUST only gain keys; existing keys keep their meaning.
- **FR-008**: `ir_cab` position 0 MUST be shown as `off` only after a recorded hardware step supports
  it; until then the docs keep it as a hypothesis and the output stays `#0`.
- **FR-009**: A labelled MASTER step MUST be recorded; its result (a byte, or "not reported") MUST be
  written in the protocol docs and user docs.
- **FR-010**: The byte map table, the code that mirrors it and the user docs MUST stay in sync, as
  enforced today.

**Names (US4)**

- **FR-011**: Amp type and IR cab names MUST come only from a committed evidence record naming the
  source (e.g. the printed manual or the vendor's desktop software), the date, and the position
  matching done on the pedal; without it the positions stay numbered.
  *Amended 2026-11-25 (owner decision):* the positions were matched against the shipped printed
  manual (the AM3 revision, corroborated by the vendor's PDF) instead of by ear on the pedal; such
  names carry the confidence `documented`. See `evidence-amp-cab-names.md`.
- **FR-012**: Named positions MUST keep the raw position visible and accepted as input; IR cab names
  MUST be documented as factory names.

**Preset management (US5)**

- **FR-013**: openvave MUST provide `preset copy SRC DST`, `preset swap A B`, `preset export POS
  --output FILE` and `preset import FILE --to POS`, and the same operations in the library.
- **FR-014**: Copy, swap and import MUST use only confirmed writes (stored slot, commit, preset
  select), MUST require `--unsafe`, MUST take the cross-checked automatic backup before the first
  write, MUST support `--dry-run` with the exact frames, and MUST verify by reading back.
- **FR-015**: Export MUST only read; the file MUST hold the 21 preset bytes and enough metadata
  (format version, firmware, source position, time) to refuse an incompatible import; it MUST NOT
  overwrite without `--force`.
- **FR-016**: Import MUST validate the file before any pedal I/O and MUST refuse firmware other than
  the pedal's unless `--experimental`, as `preset restore`.
- **FR-017**: After copy, swap or import the pedal MUST end on a defined preset (the one loaded before,
  or the target when it was the loaded one, or the import target), and the output MUST say which.
- **FR-018**: A swap MUST commit once after both slot writes; on a failure after the first write the
  output MUST say which slots changed and give the restore command.

### Out of scope

- IR file import, factory restore from vendor images, erase, firmware update, writes to the global
  block, MIDI (unchanged from spec 004).
- The phone app's `.tkg` share format (its layout is only a hypothesis from app code); a later spec
  may read it once a real file is compared.
- Names from guesswork or from other products; edit mode from the computer.
- The unexplained preset changes and the "is the commit required" question: noted if seen, not
  investigated here.

### Key Entities

- **Gate step**: one approved command in a hardware session, with its excerpt, the before/after
  backups and the observed result.
- **Byte map entry**: as in spec 002; this spec adds names to preset 18–20 and status 0, and labels
  for `ir_cab` (and amp type) positions when evidence exists.
- **Single-preset file**: 21 preset bytes plus format version, firmware, source position and time.
- **Preset operation**: copy, swap or import; a sequence of confirmed writes with backup, dry run and
  verification.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All six remaining `observed` writes are `confirmed` after one hardware session of under
  30 minutes, and none of the everyday remote controls needs `--experimental` on fw 96.
- **SC-002**: The fw 96 byte map has 0 unknown bytes in the global, preset and status regions.
- **SC-003**: A user can copy, swap, export or import a preset with one command each, and in every
  case the before-backup restores the exact previous state (verified on hardware once for copy and
  swap).
- **SC-004**: Every new or promoted claim cites committed evidence; the hardware-free test suite
  passes and replays every new excerpt.
- **SC-005**: Existing 0.5.0 JSON consumers keep working unchanged (only added keys).
- **SC-006**: The user docs list no "not known yet" item that this spec resolved; what stays unknown
  (e.g. amp names without a source) is still listed.

## Assumptions

- The owner runs the hardware steps in their own terminal (this app session cannot reach
  Bluetooth); every write is approved in chat before it is sent.
- Fw 96 is the only firmware tested; other firmware keeps needing `--experimental`.
- Byte 18–20 naming uses one byte map row per byte (red, green, blue), as every other row; the
  combined colour is a display convenience.
- The export file is openvave's own JSON format; reading the app's `.tkg` files is out of scope.
- Amp/cab names may not ship in this spec if no source is available; US4 is then deferred and the
  rest of the spec still completes.
- Spec 006 may land first; this spec then follows its conventions for any shared CLI or API surface.
