# Research: Pedal knowledge for applications (spec 008)

Facts were read from the tree at `origin/main` (`1af6615`) on 2026-11-26, and again after the
revision of the same day at `fc0a6ae` (tag `v0.6.0`; that commit changed only `CHANGELOG.md`). There was no open
technical unknown; these are the design decisions.

## R1. The simulated pedal is a classmethod of `FakeTransport`

**Decision**: `FakeTransport.simulated(path, *, image=None, faults=None, select_transient=0,
chunk_size=None)` returns a `FakeTransport` configured with `memory=…` and `apply_writes=True`.

**Rationale**: every behaviour needed (apply writes, faults, transient, chunking, `sent`,
`commits`, `lose_link`) already exists on the class and is tested; only the assembly of the script
and the memory is missing from the package. `FakeTransport` is already exported from `openvave`,
so no new top-level name is needed, and the name matches the one R15 of the app's spec proposed.

**Alternatives rejected**: a `SimulatedPedal` class (a second public type wrapping the first, for
no new behaviour); a new option on `from_capture` (its meaning, "replay what was recorded", is the
opposite of "let writes change the state").

## R2. What is taken from the recorded session

**Decision**: the file is parsed with the same reader as `from_capture`. Then:

| Recorded request | Becomes |
|---|---|
| handshake query (`0x11`) | scripted reply (required) |
| read that is not type 4 (device information, type 5) | scripted reply, when present |
| type-4 read of the global block (`0x20000000`, 4 B) | memory block, first reply (required) |
| type-4 read of the edit buffer (`0x10000000`, 21 B) | memory block, first reply (required) |
| type-4 read of the status byte (`0xD0000000`, 1 B) | memory block, first reply; `00` when absent |
| type-4 read of the whole stored image (`0x0`, 758 B) | the stored image, when present (R3) |
| every other recorded request (other type-4 reads, any write) | dropped |

Requests are recognised by their decoded frame, not by their label, because labels differ between
capture tools.

**Rationale**: in `FakeTransport` a scripted label wins over memory. A recorded type-4 read left
in the script would keep answering with the recorded bytes after a write, and a recorded write
would be acknowledged without being applied. Dropping them is what makes the pedal consistent.
This is exactly the work the app would otherwise do ("assembling memory blocks from addresses").

**Validation** (FR-008): a missing query, global read or buffer read raises `ValueError` naming
it. The recorded global block and buffer are classified with `openvave.protocol.classify`; a
state without a loaded preset (`index is None`: bypass, unrecognised) raises `ValueError`, because
the stored image cannot be aligned with it.

## R3. The stored image

**Decision**: in this order: the caller's `image` (758 bytes, else `ValueError`); the recorded
whole-image read; a generated image: header `a5 5a`, the recorded buffer at the loaded index, and
at every other index `i` the pattern

- bytes 0–3 (block switches): bits 0–3 of `i`;
- byte 4: `3·i mod 128`; byte 5: `i mod 9`;
- bytes 6–16: `(7·i + 11·offset) mod 128`;
- byte 17: `(i + 3) mod 9`; bytes 18–20: `i`, `0x40 + i`, `0x80 + i`.

**Rationale**: this is the pattern `tests/support/storage_fixture.py` has used since spec 003:
every mapped byte is in range, positions differ (so a select visibly changes the sound), and it is
plainly not vendor content. Using the same formula lets a test compare the library's image with
the independently written test fixture byte for byte (for the connect capture, loaded on 1B, they
must be equal). The formula is written again in `src/`; the package does not import `tests/`.

**Alternatives rejected**: 36 copies of the recorded preset (a select would change nothing, which
hides bugs in applications); partial overlay of recorded slot reads (gate captures change slots
mid-session, so "first reply" would mix states).

## R4. Options exposed

**Decision**: `faults`, `select_transient` and `chunk_size` only, with today's meaning and
validation. `split`, `drop`, `disconnect_after` and `replies` stay on the plain constructor.

**Rationale**: `drop` and `replies` are keyed by capture labels, which the simulated pedal hides;
`faults` covers "one write misbehaves" for every write kind, and `lose_link()` covers a link lost
at any moment. An application that needs the label-keyed options can still build the plain fake.

## R5. Panel data lives beside the byte map

**Decision**: a new pure-data module `openvave/protocol/panel.py` with a frozen dataclass
`PanelControl(order, label, group, kind, field, offset)`, the tuple `PANEL_CONTROLS` and
`panel_control(field)`. The groups and their enabled rules are in the same module (R11). `ByteMapEntry` is not touched.

**Rationale**: MASTER has no byte, so it cannot be a byte-map row; `ByteMapEntry` is mirrored row
for row from the protocol document by `tests/unit/test_bytemap_doc.py`, and new columns there
would force a protocol-doc table change for something that is not a protocol fact. `field` and
`offset` link each control to its byte-map entry; a test checks that link in both directions
(FR-011). The app's task T121 allows "on the byte map (or beside it)".

**Content** (from the drawing's description text and `docs/tank-g.md`):

| order | label | group | kind | field | byte |
|---|---|---|---|---|---|
| 0 | MASTER | MASTER | knob | — | — |
| 1 | IR CAB | CAB | selector | `ir_cab` | 17 |
| 2 | RVB MIX | REVERB | knob | `reverb_mix` | 16 |
| 3 | RVB DECAY | REVERB | knob | `reverb_decay` | 15 |
| 4 | DLY TIME | DELAY | knob | `delay_time` | 14 |
| 5 | DLY MIX | DELAY | knob | `delay_mix` | 13 |
| 6 | MOD SPEED | MOD | knob | `mod_speed` | 12 |
| 7 | MOD FX | MOD | knob | `mod_fx` | 11 |
| 8 | VOLUME | AMP | knob | `volume` | 10 |
| 9 | BASS | AMP | knob | `bass` | 9 |
| 10 | MIDDLE | AMP | knob | `middle` | 8 |
| 11 | TREBLE | AMP | knob | `treble` | 7 |
| 12 | GAIN | AMP | knob | `gain` | 6 |
| 13 | TYPE | AMP | selector | `amp_type` | 5 |
| 14 | NOISE GATE | GATE | knob | `noise_gate` | 4 |
| 15 | A/REVERB | REVERB | footswitch | `reverb_on` | 3 |
| 16 | B/DELAY | DELAY | footswitch | `delay_on` | 2 |
| 17 | C/MOD | MOD | footswitch | `mod_on` | 1 |
| 18 | D/AMP | AMP | footswitch | `amp_on` | 0 |

The group of each knob must be confirmed against the group brackets in the drawing while writing
the test (the group captions sit at x = 60, 123, 217, 343, 469, 720 and 940, which matches this
split of 1 / 1 / 2 / 2 / 2 / 6 / 1 knobs).

## R6. The order is one number, and the test reads the drawing

**Decision**: `order` is 0-based over all 19 controls (knobs 0–14, footswitches 15–18); `kind`
tells the two rows apart. The test parses the `<desc>` element of
`docs/images/tankg-controls.svg` and compares the sequence of field names (with `master` for the
control without a field) to `PANEL_CONTROLS`.

**Rationale**: "unique and without gaps" (app task T118) is simplest over one sequence. The
`<desc>` text already lists the controls in panel order with their field names, so it is the
machine-readable form of the drawing; the name `order` avoids a third meaning of "position"
(preset position, selector position name).

## R7. Strict position helpers with new names

**Decision**: `preset_index(position: str) -> int` and `preset_position(index: int) -> str` in
`openvave/protocol/storage.py`, exported from `openvave.protocol` and `openvave`. They accept
exactly `"1A"`…`"9D"` and exactly the integers 0–35 (not `bool`), and raise `ValueError` for
everything else, including other types.

**Rationale**: the internal `parse_position` also accepts `"2c"` and `"6"` and raises `TypeError`
for non-text; `position` raises `TypeError` for a non-integer. The CLI and the MCP tools rely on
that, and FR-020 forbids changing it, so they cannot simply be exported under the feature's
contract ("`ValueError` on anything else"). The `preset_` prefix keeps them apart from
`position_name` (amp and cab names), which is already public. `PedalState.position` is not
rewritten to call the helper; a test ties them together for all 36 indexes.

**Alternatives rejected**: exporting `parse_position` as is (lenient, wrong exception type);
making it strict (changes CLI behaviour).

## R8. No CLI or MCP surface

**Decision**: none added. **Rationale**: Constitution V asks that capabilities *intended for
users* be reachable from the CLI. These are developer conveniences: the CLI already converts
positions, already prints fields, and a simulated pedal on the command line would be a new
product feature (the app's "simulated pedal" option) that nobody asked for here.

## R9. One milestone

**Decision**: one pull request. **Rationale**: about 250 lines of application code against a
600-line ceiling; the three parts do not depend on each other but share one release. Two
milestones would mean a first PR that cannot be tagged.

## R10. Release mechanics (revised 2026-11-26)

- Base: tag `v0.6.0` on `fc0a6ae`. That commit moved the "Added (spec 007 US4)" section into
  `[0.6.0]` and left `[Unreleased]` empty, so nothing of spec 007 moves in this feature.
- `[0.7.0]` opens with a summary paragraph, then "Added (spec 008)" subsections for the simulated
  pedal, the panel data with the group enabled state, and the position helpers, then "Tested"
  (hardware-free; no pedal message added). `[Unreleased]` stays as an empty heading.
- The `[0.6.0]` section is not edited. The gate compares it with `git show v0.6.0:CHANGELOG.md`
  (a shell check in the quickstart, since the test suite does not read git history).
- `fc0a6ae` did not touch the tests: `tests/contract/test_changelog_060.py` still holds the three
  version assertions (`__version__`, `pyproject.toml`, `--version`). They move to the new
  `test_changelog_070.py`; the section checks of the 0.6.0 test stay.
- `uv.lock` carries the package version; `uv lock` updates it.
- Version text in `README.md`, `docs/README.md` and `docs/cli-reference.md` is updated where it
  names the current version.
- R15's optional U4 (captures inside the wheel) is out of scope (spec, Assumptions).

## R11. Group enabled state (revision 2026-11-26)

**Why here**: the app's constitution forbids copying protocol knowledge, and "CAB is off when
`ir_cab` is 0" is protocol knowledge. openvave publishes it as data with its confidence.

**Decision**: in `openvave/protocol/panel.py`:

- `PanelGroup(name, order, enabled_field, enabled_rule, enabled_confidence)`, frozen;
- `PANEL_GROUPS`: the seven groups in panel order;
- `panel_group(name)` → the group or `None`;
- `group_enabled(group, preset)` → `True`, `False` or `None`, where `preset` is the 21 bytes of
  a current preset (`RegionRead.data`).

| order | name | enabled_field | enabled_rule | enabled_confidence | Evidence |
|---|---|---|---|---|---|
| 0 | MASTER | — | — | — | no byte follows the knob (spec 007) |
| 1 | CAB | `ir_cab` | `nonzero` | `confirmed` | manual; the vendor app shows 0 as OFF; heard in spec 007 gate session C, 2026-11-19 |
| 2 | REVERB | `reverb_on` | `switch` | `confirmed` | byte-map row and `block_switch` write row |
| 3 | DELAY | `delay_on` | `switch` | `confirmed` | same |
| 4 | MOD | `mod_on` | `switch` | `confirmed` | same |
| 5 | AMP | `amp_on` | `switch` | `confirmed` | same |
| 6 | GATE | `noise_gate` | `nonzero` | `documented` | the vendor app shows 0 as `OFF` (`specs/protocol/app-features.md`, GATE row; `docs/tank-g.md`); never heard as off |

Rules: `switch` → `True` when the byte equals the field's on value (1), `False` when it equals the
off value (0), `None` otherwise; `nonzero` → `byte != 0`.

**The bypass placeholder**: 21 zero bytes are not a preset (spec 004; spec 007 gives no amp or cab
name there). `group_enabled` returns `None` for every group on that buffer. Returning `False`
would read "this preset has every block off", which is a statement about a preset the buffer does
not hold; the fact "everything is bypassed" is `PedalState.kind == "bypass"` and stays there. A
real preset with every block off still has non-zero knob bytes in practice; a stored preset of 21
zeros would also give `None`, the same trade spec 007 made for names.

**Separate table, not fields on `PanelControl`**: the state belongs to a group, and a group has
several controls (AMP has six); repeating the rule on each would let them disagree. Each
`PanelControl.group` is the `name` of one `PanelGroup` (tested).

**Confidence values**: `confirmed` and `documented` only. `documented` is not in
`openvave.models.Confidence` (`confirmed`, `observed`, `hypothesis`), which types byte-map rows;
it is the word `openvave.protocol.names` uses for "from the vendor's material, not checked on the
pedal". `PanelGroup.enabled_confidence` has its own literal type; `models.py` is not touched.

**Not in the rule**: the off zones between effect types (raw 40–43 and 84–87 of `mod_fx`,
`delay_mix`, `reverb_decay`). The manual says the module is off there; `docs/tank-g.md` lists it
as unverified. `type_parts()` already tells an application when a knob sits in such a zone.

**Protocol document**: `specs/protocol/command-layer.md` gets a "Front panel" section with this
table (six rules; MASTER as "none"); `tests/unit/test_panel_doc.py` parses it and compares it with
`PANEL_GROUPS`, as `test_names_doc.py` does for names. The byte map and the write table are not
edited.

**Alternatives rejected**: `enabled(preset) -> dict` only, without the data (the app could not
show the confidence or which control to dim); a callable stored in the table (not serialisable,
harder to mirror in the protocol document); accepting a `RegionRead` (ties a pure function to a
session type; `read.data` is one attribute away).
