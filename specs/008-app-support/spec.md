# Feature Specification: Pedal knowledge for applications (openvave 0.7.0)

**Feature Branch**: `spec-app-support` (feature directory `008-app-support`)

**Created**: 2026-11-26

**Status**: Draft

**Input**: User description: "openvave 0.7.0: publish three pieces of pedal knowledge that the
Riffmind app (github.com/gustavolima00/riffmind-app, spec 002 Milestone 9) would otherwise work
around, then release them as 0.7.0. (1) Panel data (U1): for every front-panel knob, selector and
switch of the current preset, its position on the front panel, the label printed on the pedal and
its group, plus the panel controls with no byte (MASTER). Order equal to
`docs/images/tankg-controls.svg`. Exported from `openvave.protocol`. (2) Preset position helpers
(U2): public helpers turning "1A"…"9D" into 0–35 and back, raising `ValueError` on anything else,
agreeing with `PedalState.position`. (3) A public simulated pedal that accepts writes (U3): a
documented public constructor in `openvave.transport.fake`, built from a recorded session, that
accepts every allowlisted write through `TankG.over(...)` (field edits, preset select, reload,
bypass on/off, backup, save, restore), with the documented fault options and a `sent` frame list.
Constraints: additive only, `schema_version` stays the same, no new pedal message, no hardware
step. Version 0.7.0: `docs/library.md`, a `CHANGELOG.md` 0.7.0 section, `pyproject.toml` and
`__init__`. The spec 007 work already in `[Unreleased]` goes out with 0.7.0 too. The owner tags
`v0.6.0` on `61fdf6a` separately, so 0.6.0's CHANGELOG section must keep describing only what is
in `61fdf6a`. The owner merges and creates tag `v0.7.0` on the merge commit."

**Builds on**: [`002-preset-byte-map`](../002-preset-byte-map/spec.md) (the byte map),
[`004-remote-edit-save-restore`](../004-remote-edit-save-restore/spec.md) (the writes, the
allowlist and the fake pedal that applies them) and
[`007-mapping-gaps`](../007-mapping-gaps/spec.md) (every preset byte named; MASTER has no byte).

**Scope source**: the Riffmind app's spec 002, Milestone 9 (tasks T117–T124) and research R15
(rows U1, U2, U3). This spec settles the names R15 only proposed.

**Protocol source of truth**: [`specs/protocol/command-layer.md`](../protocol/command-layer.md).
This feature sends **no new pedal message** and changes no row of the byte map or the write
table. It publishes knowledge the repository already holds: the panel order and labels drawn in
`docs/images/tankg-controls.svg`, the position arithmetic the command line already uses, and the
write-accepting fake pedal that openvave's own test suite builds for itself.

## Starting point (0.6.0 + the unreleased names of spec 007 US4)

| Area | Today | Gap |
|---|---|---|
| Front panel | order, printed labels and groups exist only in a drawing and a table in `docs/tank-g.md` | an application that draws the panel must copy them by hand |
| Preset positions | `PedalState.position` gives `"2C"`; the text ↔ index conversion is internal (`docs/library.md`: "There is no name parser in the public API") | applications repeat the arithmetic |
| Simulated pedal | `FakeTransport.from_capture` replays a recorded session; a pedal that accepts writes exists only in the test suite (`tests/support/write_fixture.py`), which is not installed with the package | an application must assemble memory blocks from addresses itself |
| Release | `main` holds 0.6.0 plus the amp type / IR cab names under `[Unreleased]` | the names and the three additions need a version applications can pin |

## User Scenarios & Testing *(mandatory)*

The reader is a developer who builds an application on the openvave library (the Riffmind app is
the first). They install a released version, import only public names, and run their own test
suite without a pedal.

### User Story 1 - Try every write on a simulated pedal (Priority: P1)

A developer builds a simulated pedal from one recorded session with a single documented call and
runs a normal session over it. Field edits, preset select, reload, bypass, backup, save and
restore all behave as on a real pedal: the write is acknowledged, the next read shows it, and the
stored presets change only on a save or a restore. The developer can also ask for one write to
fail in a documented way, and can list every frame the session sent.

**Why this priority**: it is what unblocks the application's write features; without it every
application copies openvave's test-only memory layout.

**Independent Test**: with only public imports and one committed capture, build the simulated
pedal, run each write operation of the library through `TankG.over(...)`, and compare each result
with the same operation on openvave's internal write fixture.

**Acceptance Scenarios**:

1. **Given** the committed connect capture (firmware 96, preset 1B, normal mode), **When** the
   developer builds the simulated pedal from it and opens a session, **Then** the handshake, the
   state (normal, 1B) and the current preset equal what the capture recorded.
2. **Given** that session, **When** the developer changes several fields in one call, **Then**
   each write is acknowledged, the result reports the fields as applied, and a new read shows the
   new values.
3. **Given** that session, **When** the developer selects another preset, reloads it, turns bypass
   on and then off, **Then** each operation succeeds and the state after it is the one the real
   pedal shows (the selected position; bypass; the position bypass returned to).
4. **Given** that session, **When** the developer takes a backup, **Then** it holds 36 presets,
   passes the library's own cross-check, and the preset at the loaded position equals the
   recorded current preset.
5. **Given** an edited current sound, **When** the developer saves it with the explicit opt-in and
   a backup callback, **Then** the automatic backup is delivered first, the sequence is verified,
   and a later backup shows the new bytes at that position and no other change.
6. **Given** a backup taken earlier, **When** the developer restores one preset or all of them
   with the explicit opt-in, **Then** the sequence is verified and a later backup equals the
   restored one.
7. **Given** a simulated pedal built with one fault (for example "the commit is not
   acknowledged"), **When** the developer runs the operation that sends that write, **Then** the
   operation fails with the same error and the same partial result as on the internal fixture, and
   the next write of that kind works normally.
8. **Given** any of the sessions above, **When** the developer reads the list of sent frames,
   **Then** it holds every request the session wrote, in order, each a query, a read or an
   allowlisted write.

---

### User Story 2 - Draw the front panel from library data (Priority: P2)

A developer draws the Tank-G front panel in an application. For each control they get, from the
library, where it sits on the panel, the label printed on the pedal, the group it is printed
under, what kind of control it is, and which field of the current preset it drives. The MASTER
knob, which no byte follows, is in the list too, so the drawing is complete and the application
can show it as not readable.

**Why this priority**: read-only and small, and it removes a hand-copied table that would drift
from the documentation.

**Independent Test**: the list read from `openvave.protocol` names the same controls, in the same
order, as the description text inside `docs/images/tankg-controls.svg`, and covers every
front-panel field of the byte map.

**Acceptance Scenarios**:

1. **Given** the panel data, **When** the developer lists it, **Then** it holds 19 controls in
   panel order: the 15 knobs left to right (MASTER, IR CAB, RVB MIX, RVB DECAY, DLY TIME, DLY MIX,
   MOD SPEED, MOD FX, VOLUME, BASS, MIDDLE, TREBLE, GAIN, TYPE, NOISE GATE), then the four
   footswitches (A/REVERB, B/DELAY, C/MOD, D/AMP).
2. **Given** any knob, selector or block switch of the current preset in the byte map, **When**
   the developer looks it up by field name, **Then** they get its order number, its printed label
   and its group (MASTER, CAB, REVERB, DELAY, MOD, AMP or GATE).
3. **Given** the three LED colour bytes, **When** the developer looks them up, **Then** there is
   no panel control for them (no control on the panel moves them).
4. **Given** the MASTER knob, **When** the developer reads its entry, **Then** it has a label, a
   group and an order number, and no field and no byte.

---

### User Story 3 - Convert preset positions (Priority: P3)

A developer turns the text a person types or reads (`"2C"`) into the index the library's write
methods take (6), and back, with public helpers instead of their own arithmetic.

**Why this priority**: the smallest of the three, but every application that selects or saves a
preset needs it.

**Independent Test**: for all 36 indexes the helpers agree with `PedalState.position`, and every
other input is rejected with `ValueError`.

**Acceptance Scenarios**:

1. **Given** each index 0–35, **When** it is turned into a position, **Then** the text equals
   `PedalState.position` for that index, and turning that text back gives the same index.
2. **Given** `"0A"`, `"10A"`, `"1E"`, `""`, `"1a"`, `" 1A"`, `"6"` or a value that is not text,
   **When** it is turned into an index, **Then** `ValueError` is raised.
3. **Given** `-1`, `36`, `True`, `1.0` or `"1"`, **When** it is turned into a position, **Then**
   `ValueError` is raised.

---

### User Story 4 - Pin a released version (Priority: P4)

A developer pins `v0.7.0` and gets the three additions together with the amp type and IR cab
names that were merged after 0.6.0. Nothing they used in 0.6.0 behaves differently.

**Why this priority**: the additions are only usable by applications that pin tags once they are
released; it depends on the other three stories.

**Independent Test**: the package reports 0.7.0, the changelog has a 0.7.0 section naming every
addition, the 0.6.0 section is unchanged, and the full 0.6.0 test suite still passes.

**Acceptance Scenarios**:

1. **Given** the merged work, **When** the developer reads the version from the package and from
   `openvave --version`, **Then** both say `0.7.0`.
2. **Given** `CHANGELOG.md`, **When** the developer reads the 0.7.0 section, **Then** it names the
   panel data, the position helpers, the simulated pedal and the amp type / IR cab names, and says
   that nothing was removed and `schema_version` stays 2.
3. **Given** `CHANGELOG.md`, **When** its 0.6.0 section is compared with the one at commit
   `61fdf6a`, **Then** they are identical.
4. **Given** `docs/library.md`, **When** the developer reads it, **Then** it documents the three
   additions with a runnable example each and no longer says there is no position parser or
   points to a test-suite file for write simulation.

---

### Edge Cases

- The recorded session lacks the handshake, the global read or the current-preset read, or
  records a state with no loaded preset (bypass, unrecognised): building the simulated pedal
  fails at once with `ValueError` naming what is missing; nothing is guessed.
- The recorded session has no status read: the simulated loopback flag starts off (`00`).
- The recorded session repeats a read (a `watch` record): the first reply of each is the starting
  state.
- The recorded session holds a read of the whole stored image: that image is used. Otherwise the
  library generates one (below). A caller-supplied image replaces both; an image of the wrong
  size is a `ValueError`.
- A write outside the allowlist reaches the simulated pedal: it is a programming error and fails
  loudly (as the existing fake does); it is never acknowledged.
- An unknown fault kind or action: `ValueError` when the simulated pedal is built.
- The simulated pedal is not hardware evidence: the documentation says that it models the pedal as
  the protocol document describes it, and that only a capture proves behaviour.
- A position in lower case (`"2c"`) or an index as text (`"6"`): rejected by the new helpers. The
  command line and the MCP tools keep accepting both, as today.
- Footswitch pairs printed on the panel (BANK −, BANK +, LIVE / PRESET, TUNER / BT) and the XLR
  jack are not controls of the current preset and are not listed.

## Requirements *(mandatory)*

### Functional Requirements

**Simulated pedal (U3)**

- **FR-001**: `openvave.transport.fake.FakeTransport` MUST offer a public constructor
  `FakeTransport.simulated(path, …)` that builds a simulated pedal from one recorded session file
  (the capture format of `captures/README.md`) and needs nothing outside the installed package
  except that file.
- **FR-002**: The simulated pedal MUST start in the recorded state: identity from the recorded
  handshake, the global block and the current preset from the first recorded read of each, the
  status byte from the recorded status read or `00`, and the recorded device-information reply
  when the session has one.
- **FR-003**: The simulated pedal MUST hold a stored image of 36 presets. In this order of
  preference: the image the caller supplies; the whole-image read of the recorded session; an
  image generated by the library with the header seen on hardware, the recorded current preset at
  the loaded position, and at every other position a documented, deterministic pattern whose
  mapped bytes are all inside their byte-map ranges and which differs between positions. The
  generated image MUST contain no vendor preset content.
- **FR-004**: Over `TankG.over(...)`, the simulated pedal MUST accept every write on the
  allowlist and answer every read the library sends, so that `set_field`, `set_fields`,
  `select_preset`, `reload_preset`, `bypass_on`, `bypass_off`, `backup`, `save_preset` and
  `restore` succeed and their re-reads show the result. `set_loopback`, `copy_preset`,
  `swap_presets`, `import_preset` and `export_preset` use the same messages and MUST work too.
- **FR-005**: For each operation in FR-004 the simulated pedal MUST behave as openvave's internal
  write fixture does for the same starting state: same frames received, same replies, same
  resulting memory.
- **FR-006**: The constructor MUST take the fault options the existing fake documents (one write
  of a named kind misbehaves once: not acknowledged, no reply, link lost, corrupted, or
  acknowledged but ignored), the loading-transient option after a preset select, and the reply
  chunk size, each with the meaning it has today. Unknown values MUST raise `ValueError`.
- **FR-007**: The simulated pedal's `sent` list MUST hold every request written, in order, a split
  request once.
- **FR-008**: Building a simulated pedal from a session that lacks the handshake, the global read
  or the current-preset read, or whose recorded state has no loaded preset, MUST raise
  `ValueError` that names the missing part. An image that is not 758 bytes MUST raise
  `ValueError`.
- **FR-009**: The simulated pedal MUST reject a write outside the allowlist exactly as the
  existing fake does. This feature MUST NOT widen the allowlist or add a message.

**Panel data (U1)**

- **FR-010**: `openvave.protocol` MUST export the front panel as ordered data: one entry per
  control, with its order number (0-based, unique, without gaps), the label printed on the pedal,
  the printed group, the kind of control (knob, selector or footswitch), and the field name and
  preset byte it drives, or neither when no byte follows it.
- **FR-011**: The data MUST have one entry for every current-preset entry of the byte map that is
  a front-panel control (the eleven knobs, the two selectors, the four block switches) and none
  for the three LED colour bytes.
- **FR-012**: The data MUST list MASTER as a control with no field and no byte, in its panel
  place (first).
- **FR-013**: The order MUST equal the order of `docs/images/tankg-controls.svg` as stated in that
  file's own description text: the fifteen knobs left to right, then the four footswitches left to
  right. A test MUST read the order from the file, so the drawing and the data cannot drift.
- **FR-014**: Labels and groups MUST be the text printed on the panel (as in the drawing and
  `docs/tank-g.md`): groups MASTER, CAB, REVERB, DELAY, MOD, AMP, GATE; a footswitch's group is
  the block it switches.
- **FR-015**: `openvave.protocol` MUST export a lookup from a field name to its panel entry that
  returns nothing for a field without one (LED colour bytes, global and status fields, unknown
  names).

**Preset positions (U2)**

- **FR-016**: The library MUST export a helper from a position text to its index and one from an
  index to its position text, from both `openvave` and `openvave.protocol`.
- **FR-017**: Text → index MUST accept exactly the 36 texts `"1A"`…`"9D"` (digit 1–9, upper-case
  letter A–D) and raise `ValueError` for every other value, including values that are not text.
- **FR-018**: Index → text MUST accept exactly the integers 0–35 and raise `ValueError` for every
  other value, including booleans and other types.
- **FR-019**: For every index 0–35 the result MUST equal `PedalState.position` of a state with
  that index, and the two helpers MUST be inverses of each other.

**Compatibility and release**

- **FR-020**: The change MUST be additive: every name public in 0.6.0 keeps its signature and
  behaviour, the command line and the MCP server print what they printed, and `schema_version` of
  the JSON documents stays 2. The existing position parsing of the command line and the MCP tools
  (which also accepts lower case and index text) MUST NOT change.
- **FR-021**: No pedal message is added and no hardware session is part of this feature.
- **FR-022**: The package version MUST be `0.7.0` in `pyproject.toml`, in `openvave.__version__`
  and in the lock file.
- **FR-023**: `CHANGELOG.md` MUST gain a `[0.7.0]` section that opens with a summary, describes
  the three additions, and carries the spec 007 US4 section (amp type and IR cab names) that is
  under `[Unreleased]` today. `[Unreleased]` MUST be left empty above it. The `[0.6.0]` section
  MUST stay identical to the one at commit `61fdf6a`.
- **FR-024**: `docs/library.md` MUST document the three additions with an example each, replace
  the sentence that says there is no position parser and the pointer to
  `tests/support/write_fixture.py`, and state that the simulated pedal is a model, not evidence.
  `docs/tank-g.md` MUST point from its panel table to the panel data. Documentation that names the
  current version MUST say 0.7.0.
- **FR-025**: The pull request MUST NOT create the tag. The owner merges and creates `v0.7.0` on
  the merge commit; `v0.6.0` on `61fdf6a` is the owner's separate step.

### Key Entities

- **Panel control**: one control printed on the Tank-G front panel: order number, printed label,
  printed group, kind, and the current-preset field and byte it drives (or none).
- **Preset position**: the text `"1A"`…`"9D"` (bank 1–9, slot A–D) of a stored preset; index =
  4 × (bank − 1) + slot, 0–35.
- **Simulated pedal**: an in-memory stand-in for one pedal: identity, global block, current
  preset (edit buffer), status byte and the stored image of 36 presets; it applies allowlisted
  writes to that memory and answers reads from it.
- **Recorded session**: a capture file of a real session (handshake and reads), the starting
  state of a simulated pedal.
- **Fault option**: one planned misbehaviour of one kind of write, used once.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A developer builds a write-accepting simulated pedal in one call from one capture
  file, with public imports only, and all nine operations named in FR-004 succeed on it.
- **SC-002**: For those operations and for every documented fault action, the simulated pedal and
  the internal write fixture give equal results in 100% of the compared cases.
- **SC-003**: The panel data covers 17 of 17 front-panel fields of the byte map plus MASTER (19
  entries), and its order matches the drawing's description text in 19 of 19 places.
- **SC-004**: The position helpers agree with `PedalState.position` for 36 of 36 indexes and
  reject 100% of the invalid inputs listed in User Story 3.
- **SC-005**: Every test of the 0.6.0 suite passes without a change to its expectations, apart
  from the tests that assert the current version number; the public-name list only grows.
- **SC-006**: Every frame sent to a simulated pedal during the test suite is a query, a read or an
  allowlisted write (the existing whole-suite audit stays green); no pedal is needed for any
  check of this feature.
- **SC-007**: After the merge and the owner's tag, a fresh install of `v0.7.0` reports `0.7.0` and
  the Riffmind app can delete its interim panel table, its position arithmetic and its own memory
  assembly.

## Assumptions

- The Riffmind app adapts to the names chosen here (its research R15 says so); no compatibility
  with its interim table is needed.
- R15's optional row U4 (shipping the recorded sessions inside the package) is **out of scope**:
  it changes what the wheel contains and needs its own decision on which captures to ship. The
  simulated pedal takes a path, so the app keeps using its copy of `captures/`.
- "Front-panel control of the current preset" means the fifteen knobs and the four footswitches
  in their block on/off role. The footswitches' slot role (A–D) and the printed pairs are
  described in `docs/tank-g.md` and are not data in this release.
- The simulated pedal models preset select, bypass, save and restore as the existing fake does
  (spec 004); where that model is not hardware evidence, the existing documentation already says
  so, and this feature repeats it rather than adding claims.
- A session recorded in edit mode is treated as if the stored preset at the loaded position
  equals the recorded buffer (the recording cannot say otherwise); the documentation states it.
- Spec 007's task T036 (the owner's look at `preset dump` showing the names on a real pedal) stays
  an open owner check; it does not block 0.7.0, which releases the names as `documented`.
- The owner merges the pull request and creates both tags; nothing here pushes a tag or publishes
  a package.
