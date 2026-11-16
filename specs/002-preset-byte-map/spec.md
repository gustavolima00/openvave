# Feature Specification: Preset and global byte map (read-only decoding)

**Feature Branch**: `claude/spec-002-tankg-mapping-b8c3d9` (feature directory `002-preset-byte-map`)

**Created**: 2026-11-16

**Status**: Draft

**Input**: User description: "Decode the Tank-G's current preset (21 B, type 4 @ 0x10000000),
global block (4 B @ 0x20000000) and status byte (1 B @ 0xD0000000) into named parameters (effect
modules on/off, knob values, selectors), each with range and confidence level; discover the byte
map empirically and read-only by polling while the pedal owner moves one control at a time;
document the map in specs/protocol/command-layer.md; expose decoded fields from library and CLI
while keeping unknown bytes visible as raw. No writes or erase."

**Builds on**: [`001-readonly-ble-connection`](../001-readonly-ble-connection/spec.md) (transport,
framing, handshake, the four confirmed reads, `info` / `preset dump`, JSON `fields` array with
per-field confidence, `schema_version`).

## Clarifications

### Session 2026-11-16

- Q: Is the mapping session a shipped CLI command or throwaway tooling? → A: Ship an explicit, read-only `openvave watch` command with stdin labels and a saved session record in `captures/private/`; only `watch` polls.
- Q: What promotes a read-only decoding to `confirmed`? → A: The same single-control result reproduced in a second, independent session (new connection, preferably a different stored preset); one session gives at most `observed`.
- Q: What is the completion bar for the mapping? → A: Every front-panel control tried one at a time, plus the buffer compared across several (≥5) stored presets selected on the pedal; app-only settings are out of scope.

**Protocol source of truth**: [`specs/protocol/command-layer.md`](../protocol/command-layer.md),
section "Preset / global byte map (in progress)". This feature turns that table into a complete,
evidence-backed map and makes the library decode it.

## Starting point (fw 96, 2026-11-16)

| Region | Offset | Current knowledge | Confidence |
|---|---|---|---|
| preset | 6 | one knob, 0–127, which one unknown | observed |
| preset | 15 | reverb decay, 0–127 | observed |
| preset | 16 | reverb mix, 0–127 | hypothesis (moved together with byte 17) |
| preset | 17 | IR cab selector, small index | hypothesis (moved together with byte 16) |
| global | 3 | edit-mode flag (1 normal, 0 in edit mode) | observed |
| preset | 0–3, 5, 7–14, 18–20 | unknown (bytes 4–17 are the block the app rewrites on knob moves) | — |
| global | 0–2 | unknown | — |
| status | 0 | unknown (hypothesis: current preset index) | hypothesis |

Known behaviour that shapes the workflow: knobs only act in edit mode; leaving edit mode without
saving restores the preset buffer; the pedal never pushes changes, so the host must re-read.

## User Scenarios & Testing *(mandatory)*

Actors:

- **Pedal owner** — has the physical Tank-G, enters edit mode, moves controls, switches presets,
  and runs commands in their own terminal (the host needs Bluetooth permission; the phone app
  must be disconnected because the pedal stops advertising while a central is connected).
- **Researcher** — reads the session record, draws conclusions, and updates the protocol docs
  and decoder. Can be the same person as the pedal owner, or an assistant working from the
  owner's notes.
- **Library / CLI user** — anyone who later reads a preset and wants named values.

### User Story 1 - Map one control per step (Priority: P1)

The pedal owner runs `openvave watch` against the connected pedal. The session reads the three
regions (preset, global, status) repeatedly and, whenever any byte changes, records which region,
offset, old value and new value changed, together with a short label the owner typed describing
what they just did (for example "edit mode on", "gain knob min → max", "delay footswitch off").
The owner works through an inventory of the pedal's physical controls, moving exactly one control
per step and sweeping continuous knobs from minimum to maximum so the range can be seen. The
session record is saved locally for the researcher.

**Why this priority**: Every other story depends on evidence. Without a disciplined one-control
-per-step record, no byte can be promoted beyond `hypothesis` (the byte 16/17 ambiguity shows
what happens when two controls move together).

**Independent Test**: With recorded reads replayed through a fake transport, the session reports
exactly the offsets that differ between consecutive reads, attaches the active label to each
change, and writes a record whose entries can be reloaded and compared. On hardware: the owner
turns only the reverb decay knob and the record shows only preset byte 15 changing.

**Acceptance Scenarios**:

1. **Given** a connected pedal in edit mode and a running session, **When** the owner turns a
   single knob from minimum to maximum, **Then** the record shows the changed offset(s), the
   minimum and maximum value seen, and the owner's label, and no other offset is reported.
2. **Given** a running session, **When** two offsets change between two consecutive reads,
   **Then** both are reported in the same step, so the researcher can see the change was not
   isolated.
3. **Given** a running session, **When** nothing changes for a while, **Then** nothing is
   recorded beyond optional heartbeats, and the session keeps only read-only traffic on the wire.
4. **Given** the session ends (owner quits, connection drops), **Then** everything recorded so far
   is already saved and the pedal is disconnected cleanly.
5. **Given** the session record, **Then** it is stored only under the private captures folder and
   contains no device MAC, serial number or personal preset names unless sanitized.

---

### User Story 2 - Record findings with confidence in the protocol docs (Priority: P1)

After a mapping session, the researcher updates the byte map in `command-layer.md`: one row per
region/offset (or bit, if a byte turns out to pack several flags) with a name, value range,
encoding (continuous 0–127, on/off, selector index, bit field), the control it corresponds to,
confidence level, firmware version and a pointer to the sanitized evidence. Bytes that never
changed during any session stay listed as unknown, with a note of what was tried. Only the
findings go into the docs, not the procedure or tooling used to obtain them.

**Why this priority**: The documented protocol is the product (Constitution I). The decoder in
Story 3 may only decode what the docs say.

**Independent Test**: A reviewer can take any row in the map and find (a) its confidence level,
(b) the firmware version, and (c) a committed sanitized fixture or annotated hex that shows the
change; every one of the 26 bytes (21 preset + 4 global + 1 status) appears in the map, either
named or explicitly unknown.

**Acceptance Scenarios**:

1. **Given** a session where only one control moved and one offset changed, **When** the
   researcher records it, **Then** the row is `observed` and cites the sanitized evidence.
2. **Given** a byte whose meaning was inferred from two controls moving together (today: preset
   16 and 17), **When** it is recorded, **Then** it stays `hypothesis` until a one-control-at-a
   -time step isolates it.
3. **Given** a single-control finding reproduced in a second, independent session (FR-010),
   **When** it is recorded, **Then** the row says `confirmed` and cites both sessions.
4. **Given** a finding contradicts an earlier row (as the "edited/unsaved" flag was refuted),
   **When** it is recorded, **Then** the old claim is corrected and the refutation is noted, not
   silently overwritten.

---

### User Story 3 - Read decoded preset and global values (Priority: P2)

A user runs `openvave preset dump` (and `openvave info`) and sees, next to the raw bytes, every
mapped parameter with its name, value, range and confidence — for example "reverb decay = 5
(0–127, observed)", "delay = on (observed)", "IR cab = 7 (selector, hypothesis)". Unknown bytes
are still printed as raw hex with their offset and marked unknown. With `--json`, scripts get the
same decoded fields plus the raw hex, in a documented, versioned format. Library users get the
same decoded values as structured data without parsing text.

**Why this priority**: This is the user-visible payoff, but it is only as good as the map behind
it, so it follows Stories 1–2. It is useful as soon as a handful of bytes are mapped, and grows
additively as the map grows.

**Independent Test**: Feeding the committed fw-96 preset reply
(`01 00 00 01 0f 04 3c 3c 46 32 32 00 00 00 00 05 04 07 43 16 43`) through a fake transport
produces decoded fields whose names, values and confidence levels match the map in
`command-layer.md` row for row, and the raw hex is unchanged.

**Acceptance Scenarios**:

1. **Given** the recorded preset reply, **When** the user runs `openvave preset dump`, **Then**
   every byte the map names is shown with name, value, range and confidence, and every other byte
   is shown as unknown raw hex.
2. **Given** `--json`, **When** `preset dump` or `info` runs, **Then** the output contains the raw
   hex of each region and one decoded entry per mapped field, each with offset, size (or bit
   mask), name, value, range/encoding and confidence; previous fields keep their names.
3. **Given** a value outside the documented range for a field (e.g. a continuous knob byte
   above 127), **When** it is decoded, **Then** the output shows the raw value and flags it as
   out of range instead of clamping or hiding it.
4. **Given** a pedal reporting a firmware other than 96, **When** values are decoded, **Then**
   decoded fields are still shown but marked as decoded with the fw-96 map (consistent with the
   001 `firmware_untested` flag).

---

### User Story 4 - Interpret the status byte and edit state (Priority: P3)

The owner switches between presets on the pedal (footswitches / preset selection) and enters and
leaves edit mode while a session runs, so the researcher can tell whether the status byte is the
current preset index, how it relates to the 36 stored presets, and whether any global byte tracks
something besides edit mode (e.g. a global volume or bank). The decoded output then shows "current
preset = N" and "edit mode = on/off" when those are at least `observed`.

**Why this priority**: Useful context for every later spec (selecting and writing presets), but
not required to decode a preset's parameters.

**Independent Test**: With replayed reads recorded while switching presets, the session record
shows the status byte (and/or preset bytes) changing in step with each preset change, and the
decoder reports the mapped index.

**Acceptance Scenarios**:

1. **Given** a running session, **When** the owner steps through several presets one at a time,
   **Then** each step is recorded with the label, and the status byte value per preset is visible.
2. **Given** the status byte is shown to track the preset index across at least the presets the
   owner stepped through, **When** it is documented, **Then** its numbering base (0- or 1-based)
   and observed range are recorded.

---

### Edge Cases

- A control changes more than one byte (e.g. a selector that also resets a dependent value, or a
  module switch that changes a parameter): all changed offsets are recorded under one step; the
  map must be able to express a control that touches several bytes and a byte that packs several
  controls (bit fields).
- A control changes nothing in the three regions (e.g. a knob that only acts outside edit mode, a
  global setting stored elsewhere, a footswitch that only sends MIDI): recorded as "no change",
  and the control is listed as unmapped in the docs with what was tried.
- Knob movement faster than the read interval: intermediate values are missed; only min/max and
  final values are required, not every step.
- Owner forgets to enter edit mode: no preset bytes change; global byte 3 still reads 1, which the
  session can point out.
- Leaving edit mode without saving restores the buffer: the session records the revert as its
  own step; it must not be mistaken for a new control.
- Saving a preset on the pedal (a pedal-side action, not a host write) changes stored memory the
  tool cannot see in these regions; the session may record a change, but no write is issued.
- Connection drops mid-session (phone app grabs the pedal, Bluetooth off, out of range): the
  session stops with the 001 error codes and keeps what was recorded.
- Device-info bytes 20–21 vary between reads (likely stale bytes from the previous reply): the
  device-info block is outside this feature's map and must not be polled as if its changes meant
  anything.
- A byte's value differs between presets but never changes with any front-panel control (e.g.
  module type selected only from the app): stays unknown, with its per-preset values noted.

## Requirements *(mandatory)*

### Functional Requirements

**Mapping session (discovery workflow)**

- **FR-001**: The CLI MUST provide an explicit, read-only `openvave watch` command that
  repeatedly reads the preset, global and status regions and reports, per change, the region,
  offset, old and new value, time, and the owner's current free-text label (typed on stdin while
  it runs). It saves a session record under `captures/private/`. Polling happens only while the
  user runs `watch`; `info` and `preset dump` keep 001's no-polling behaviour (001 FR-012 is
  narrowed accordingly, not removed). The library MUST expose the same capability (Constitution V).
- **FR-002**: The mapping session MUST use only the query (`0x11`) and read (`0x23`) commands and
  only the regions already confirmed in 001 (FR-008); no write, erase, MIDI or arbitrary-address
  command may be sent.
- **FR-003**: The read interval MUST be bounded so a knob sweep's minimum and maximum are captured
  (assumed: at least 2 reads per second) and MUST NOT exceed the pedal's request/response pace
  (one request in flight at a time).
- **FR-004**: Every change MUST be saved as soon as it is seen, so an interrupted session loses
  nothing already observed; session records MUST be written only under `captures/private/`.
- **FR-005**: The session MUST make "two or more offsets changed in one step" visible, so
  co-moving bytes are never attributed to one control by accident.

**Byte map documentation**

- **FR-006**: `command-layer.md` MUST contain a byte map covering all 26 bytes (preset 0–20,
  global 0–3, status 0); each row gives region, offset (and bit mask where a byte packs several
  fields), name, encoding (continuous, on/off, selector index, bit field, unknown), value range,
  the pedal control it corresponds to, confidence, firmware version, and evidence pointer.
- **FR-007**: Bytes with no identified meaning MUST remain in the map as `unknown`, with the
  values seen and the controls tried; they MUST NOT be named by guess.
- **FR-008**: The docs MUST record findings only (what the bytes mean and how the pedal behaves),
  not the exploration tooling or procedure (Constitution I/VI).
- **FR-009**: Each `observed` row MUST be backed by a sanitized fixture or annotated hex committed
  under `captures/` showing a step in which only that control moved.
- **FR-010**: A row MAY be promoted to `confirmed` only when the same single-control step gives
  the same result (same offset(s), same encoding, consistent range) in a second, independent
  session — a new connection, preferably on a different stored preset — with both sessions cited
  as evidence. A single session yields at most `observed`.
- **FR-011**: The map MUST also cover the existing hypotheses: preset 16/17 isolated one control
  at a time, preset 6 identified, global 3 (edit mode) kept or refined, status 0 explained or left
  unknown.
- **FR-011a**: Mapping MUST include comparing the current-preset buffer across at least 5
  different stored presets selected on the pedal (no host write), and the map MUST record, for
  each byte that differs between presets but changes with no front-panel control, the values seen
  per preset.

**Decoding (library and CLI)**

- **FR-012**: The library MUST decode the preset, global and status regions into named fields using
  only rows present in the documented map, each with offset/size or bit mask, name, raw value,
  interpreted value (number, on/off, or selector index), range/encoding and confidence.
- **FR-013**: Decoding MUST be a pure function of the region bytes (and firmware version), usable
  without a connection, so recorded bytes and fixtures can be decoded offline.
- **FR-014**: Undecoded bytes MUST remain visible as raw hex with offsets in every output; the raw
  hex of each region MUST always be present in JSON.
- **FR-015**: Values outside a field's documented range MUST be reported raw and flagged, not
  clamped, dropped or mapped to a guessed meaning.
- **FR-016**: `openvave preset dump` and `openvave info` MUST show decoded fields in human and JSON
  output; human output MUST label each field's confidence, and `hypothesis` fields MUST be
  visually distinct from `observed`/`confirmed` ones.
- **FR-017**: JSON changes MUST follow 001 FR-016a: new fields are additive under the same
  `schema_version`; renaming or redefining a field (e.g. a hypothesis later refuted) MUST bump
  `schema_version` and be noted in the changelog. The output contract for decoded fields MUST be
  published as a schema next to the 001 schemas.
- **FR-018**: For firmware other than 96, decoded fields MUST still be produced but marked as
  decoded with the fw-96 map, alongside the existing `firmware_untested` flag.

**Safety and testing**

- **FR-019**: This feature MUST NOT add any encodable command beyond `0x11` and `0x23`; the 001
  guarantee (no write `0x22`, erase `0x21`, MIDI `0x15`) stays in force and its test audit MUST
  still pass.
- **FR-020**: Decoder tests MUST use committed sanitized fixtures from real mapping sessions
  (Constitution III): for each mapped field at least one fixture pair (before/after a single
  control move) whose decoded difference is exactly that field.
- **FR-021**: The default test suite MUST still run without a pedal; any hardware check of the
  session MUST be opt-in.

### Out of scope (future specs)

- Any write (`0x22`), erase (`0x21`), preset select / command registers (`0xE000000x`), or editing
  presets from the host.
- Reading the 36 stored presets (756 B) or any address not confirmed in 001; their layout is
  presumed to match the 21-byte buffer but reading them needs a confirmed address first.
- Device-info block (type 5 @ `0xD0000000`, 32 B) decoding.
- MIDI, the phone app's protocol beyond what reads show, factory preset content (Constitution VI:
  no vendor preset content is committed, only the byte meanings).
- Settings reachable only from the phone app (e.g. module types/models, app-only global settings)
  and recording the app's changes; bytes that may hold them stay unknown with per-preset values.
- Human-friendly units (dB, ms, model names) unless the pedal itself displays them; values are
  reported in the pedal's own raw scale.

### Key Entities

- **Control**: a physical control on the pedal (knob, selector knob, footswitch, button, mode) —
  name as printed on the pedal, kind (continuous / selector / switch), and whether it needs edit
  mode.
- **Mapping step**: one owner action with a label, the reads before and after, and the set of
  changed region offsets with old/new values.
- **Mapping session record**: ordered steps from one connection, with firmware version, date and
  host; private by default, sanitized copy committed as evidence.
- **Byte map entry**: region, offset, bit mask (optional), name, encoding, range, linked control,
  confidence, firmware version, evidence pointer, notes (including refuted claims).
- **Decoded field**: a byte map entry applied to a read — raw value, interpreted value,
  out-of-range flag, confidence.
- **Decoded region**: raw bytes plus the list of decoded fields; bytes not covered are unknown.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Every control in the owner's inventory of front-panel controls has been exercised in
  at least one one-control-at-a-time step, and its result (mapped offset(s) or "no change") is in
  the map.
- **SC-002**: Every one of the 26 bytes appears in the map, either named with a confidence level
  or explicitly unknown; no byte is missing.
- **SC-003**: At least the preset parameter block (bytes 4–17) is fully attributed — each byte
  named at `observed` or better, or documented as unchanged by every control tried.
- **SC-004**: For every mapped field, decoding its committed before/after fixtures changes exactly
  that field and nothing else.
- **SC-005**: On a fw-96 pedal, the decoded values shown by `preset dump` match the physical knob
  positions the owner set (e.g. a knob at minimum reads its minimum value, at maximum its maximum)
  for every `observed` continuous field.
- **SC-006**: The request audit across the whole test suite still finds zero frames with a command
  byte other than `0x11` or `0x23`.
- **SC-007**: A third party can decode a 21-byte preset dump into the same named values using only
  `command-layer.md`, without reading openvave source.
- **SC-008**: The current-preset buffer of at least 5 different stored presets has been read and
  compared, and every byte that differs between them is either mapped or documented as unknown
  with its per-preset values.

## Assumptions

- Only firmware 96 is available; the map is for fw 96 and is labelled as such.
- The owner can identify each control by the name printed on the pedal and will provide (or help
  build) the control inventory at the start of the first session; the spec does not presume the
  exact list of controls.
- Knobs only change the preset buffer in edit mode (observed); every knob step starts with edit
  mode entered and ends by leaving edit mode without saving, so the stored presets are untouched.
- The owner will not save presets on the pedal during mapping unless a step explicitly needs it;
  saving is a pedal-side action and no host write is involved.
- A read interval of about 0.5 s is fast enough to catch knob extremes and slow enough for the
  pedal (the app itself polls the global block about once per second without issues).
- Value presentation uses the pedal's raw scale (0–127 for continuous knobs, raw index for
  selectors); selector labels (e.g. IR cab names) are added only if the pedal's own panel or
  manual names them, and as our own descriptive words, never vendor assets.
- The 36 stored presets are assumed to share the 21-byte layout (app-declared `patchSize = 21`),
  so this map is expected to apply to them later; that is not verified here.
- Raw session records stay in `captures/private/` (git-ignored); only sanitized excerpts used as
  evidence and fixtures are committed.
- This feature is complete when SC-001 to SC-008 hold: every front-panel control in the inventory
  has been tried one at a time, and the current-preset buffer has been compared across several
  stored presets selected on the pedal. Bytes still unknown after that are an acceptable outcome,
  as long as they are documented as unknown with the values seen.
