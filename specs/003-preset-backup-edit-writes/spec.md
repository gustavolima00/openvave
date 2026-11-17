# Feature Specification: Preset backup and first edit-buffer writes

**Feature Branch**: `claude/protocol-preset-storage-bf8bea` (feature directory `003-preset-backup-edit-writes`)

**Created**: 2026-11-17

**Status**: Draft

**Input**: User description: "Spec 003: preset backup and first writes for the M-VAVE Tank-G (fw 96).
Scope, in order of safety: (1) read-only `preset backup` CLI/library action: read all 36 stored
presets (type 4, address 2 + 21*i, 21 B each; cross-check with the single 758-byte image read at
address 0, header a5 5a), decode with the existing byte map, write to a backup file (JSON with raw
hex + decoded fields), confirmed on hardware 2026-11-17. (2) Writes to the volatile edit buffer
only: knob block 0x10000004 (14 B), block switches 0x10000000+k (1 B), LED colour 0x10000012
(3 B); explicit separately named write actions, dry-run showing exact bytes, write
acknowledgement check (8-byte reply, byte 2 = 00 and byte 6 = 00, else NAK), re-read to verify;
never followed by the 0xF0000000 commit, so leaving edit mode without saving restores the preset.
(3) `preset select`: write 01 to 0xE0000000 + i (i = bank*4 + slot) then re-read the edit buffer.
Out of scope: stored-slot writes, the 0xF0000000 save/commit, backup restore, erase 0x21, loopback
flag write at 0xD0000000 — deferred to a later spec behind an explicit unsafe opt-in. Writes are
hypothesis-level until replayed on hardware with the owner's explicit approval; each first
hardware write is a gated milestone step."

**Builds on**: [`001-readonly-ble-connection`](../001-readonly-ble-connection/spec.md) (transport,
framing, handshake, read-only client, exit codes, JSON envelope with `schema_version`) and
[`002-preset-byte-map`](../002-preset-byte-map/spec.md) (decoded fields of the current preset,
global block and status byte; `openvave watch`).

**Protocol source of truth**: [`specs/protocol/command-layer.md`](../protocol/command-layer.md),
sections "Address map", "Storage layout", "Stored presets, switching and saving", "Write
acknowledgement" and "Preset LED colour". This feature turns the backup read into a shipped,
tested action and replays the first writes on hardware, recording the result there.

## Starting point (fw 96, 2026-11-17)

| Message | Purpose | Confidence before this feature |
|---|---|---|
| read type 4 `0x00000000` × 2 | stored-image header (`a5 5a`) | confirmed (read-only probe) |
| read type 4 `2 + 21·i` × 21, i = 0–35 | one stored preset | confirmed (read-only probe) |
| read type 4 `0x00000000` × 758 | whole stored image, one request, multi-notification reply | confirmed (read-only probe) |
| write type 4 `0x10000004` × 14 | the 14 knob bytes of the edit buffer | observed (app log) |
| write type 4 `0x10000000 + k` × 1, k = 0–3 | one block switch in the edit buffer | observed for k = 1 (app log); hypothesis for k = 0, 2, 3 |
| write type 4 `0x10000012` × 3 | preset LED colour R, G, B | hypothesis (app code) |
| write type 4 `0xE0000000 + i` data `01` | load stored preset `i` | observed (app log); meaning hypothesis |
| write reply: 8 bytes, byte 2 = `00`, byte 6 = `00` | write accepted (ACK); anything else = NAK | hypothesis (app code) |

Known behaviour that shapes this feature: knobs act only in edit mode; leaving edit mode without
saving restores the stored preset (observed); in edit mode, switching a block off and on copies
the physical knob positions into the buffer (observed); the pedal never pushes changes, so the
host must re-read to see any effect.

## User Scenarios & Testing *(mandatory)*

Actors:

- **Pedal owner** — has the physical Tank-G, enters and leaves edit mode on the pedal, runs
  commands in their own terminal (host with Bluetooth permission, phone app disconnected), and
  approves each first hardware write in chat.
- **Researcher** — defines the hardware gate steps, reads their records and updates the protocol
  docs and confidence levels. May be the owner or an assistant.
- **Library / CLI user** — anyone who later backs up their presets or tweaks the current preset
  from a script.

### User Story 1 - Back up every stored preset (Priority: P1)

The pedal owner runs one read-only command and gets a file holding all 36 stored presets, each
with its position (bank and slot), its raw bytes and its decoded fields, plus the image header and
the device identity. The file is the safety net for everything that follows: before any write is
attempted, the owner has a copy of what the pedal held.

**Why this priority**: it is read-only, already confirmed on hardware, and it is the backup that
Constitution IV requires before any write. It delivers value on its own (a preset archive) even if
no write ever ships.

**Independent Test**: with the pedal connected, run the backup command; the file contains 36
presets whose bytes equal a second, independent read of the stored image, and no write or erase
frame appears in the trace. Without hardware: replay the committed fixture through a fake
transport and get a byte-identical file.

**Acceptance Scenarios**:

1. **Given** a connected pedal not in edit mode, **When** the owner runs the backup command,
   **Then** a backup file is written with 36 presets (1A … 9D), each with raw hex and decoded
   fields, the header bytes, the firmware version and a timestamp, and the command exits 0.
2. **Given** the per-preset reads and the whole-image cross-check read, **When** any preset
   differs between the two, **Then** the command reports which presets differ, writes no backup
   file (or marks it invalid), and exits non-zero.
3. **Given** the header does not read `a5 5a`, **When** the backup runs, **Then** the file is
   still written but carries a clear warning that the storage header is unexpected, and the
   command says so on stderr.
4. **Given** JSON output is requested, **When** the backup completes, **Then** stdout carries a
   JSON document with the same content as the file, inside the usual envelope with
   `schema_version`.
5. **Given** a backup file, **When** the owner inspects it, **Then** every byte the decoder does
   not name is still present as raw hex (nothing is dropped or guessed).

---

### User Story 2 - Change the current preset from the host, safely (Priority: P2)

With the pedal in edit mode, the owner sets one named parameter of the current preset (a knob, a
block switch or the LED colour) from the CLI. The tool shows exactly which bytes it will send,
sends one write to the edit buffer only, checks the acknowledgement, re-reads the buffer and
reports whether the value took. Leaving edit mode on the pedal without saving restores the
stored preset, so nothing is lost.

**Why this priority**: it is the first time the project writes to the pedal; it is volatile by
design (no commit), so the worst case is "leave edit mode". It depends on Story 1 existing (backup
before writing).

**Independent Test**: offline, the dry-run of each named parameter prints the exact frame and the
fake-transport tests check ACK/NAK handling. On hardware (gated, owner-approved): set one knob,
see it in a re-read, leave edit mode without saving, and see the stored value return.

**Acceptance Scenarios**:

1. **Given** any parameter and value, **When** the owner asks for a dry run, **Then** the tool
   prints the exact bytes of every frame it would send (including the read-before-write), sends
   no write, and exits 0.
2. **Given** the pedal in edit mode, **When** the owner sets a knob (e.g. gain = 90), **Then** the
   tool reads the current buffer, sends a single 14-byte knob-block write that differs from the
   buffer only in that knob's byte, receives the ACK, re-reads the buffer and reports
   "applied" with before → after values.
3. **Given** the pedal in edit mode, **When** the owner sets a block switch or the LED colour,
   **Then** the tool sends the matching 1-byte or 3-byte edit-buffer write, checks the ACK and
   re-reads as above.
4. **Given** the pedal is not in edit mode, **When** the owner asks for a write, **Then** the tool
   refuses before sending any write, explains that the pedal must be in edit mode, and exits
   non-zero.
5. **Given** a value outside the field's range (e.g. gain 200), **When** the owner asks for a
   write, **Then** the tool refuses without contacting the pedal for the write.
6. **Given** the pedal answers a write with anything other than the ACK, **When** the tool
   receives it, **Then** it reports a NAK with the raw reply bytes, sends nothing further, and
   exits with the protocol-error code.
7. **Given** the write is ACKed but the re-read does not show the new value, **When** the tool
   finishes, **Then** it reports "acknowledged but not applied" with the re-read bytes and exits
   non-zero.
8. **Given** a parameter whose write is still `hypothesis`, **When** the owner asks to set it
   without the experimental opt-in, **Then** the tool refuses and names the opt-in.
9. **Given** any write action, **When** it runs, **Then** no stored-area write, commit, erase or
   loopback write is ever sent (verified by the frame trace).

---

### User Story 3 - Select a stored preset from the host (Priority: P3)

The owner asks the tool to load stored preset 2C (or index 6). The tool sends the preset-select
write, checks the ACK, re-reads the global block and the edit buffer, and reports that the pedal
now shows bank 2, slot C with the stored bytes of 2C.

**Why this priority**: useful for scripting and for later write workflows, but not needed for
backup or editing; it changes which preset is active, which can discard unsaved pedal-side
edits, so it comes after the edit-buffer writes.

**Independent Test**: offline, dry-run and fake-transport tests; on hardware (gated), select a
preset that differs from the current one and compare the re-read buffer with that preset's entry
in a fresh backup.

**Acceptance Scenarios**:

1. **Given** a preset named by position (`2C`) or index (`6`), **When** the owner selects it,
   **Then** the tool sends one select write for index 6, checks the ACK, waits briefly, re-reads,
   and reports success when global bank/slot equal 2/C and the edit buffer equals the stored
   preset.
2. **Given** an invalid position (`10A`, `1E`, index 36), **When** the owner selects it, **Then**
   the tool refuses without contacting the pedal.
3. **Given** the pedal is in edit mode, **When** the owner selects a preset, **Then** the tool
   warns that unsaved edits on the pedal will be discarded and requires an explicit confirmation
   flag before sending.
4. **Given** a dry run, **When** the owner selects a preset, **Then** the exact select frame is
   printed and nothing is sent.

---

### User Story 4 - Gate each first hardware write and record the evidence (Priority: P1 for the gate, applies to Stories 2–3)

Before a write message is sent to the pedal for the first time, the researcher states the exact
frame and the expected result, the owner approves that specific write in chat, a fresh backup
exists, and the owner runs it. The record (frames sent and received) becomes evidence, and the
protocol docs move the message from `hypothesis`/`observed` to `confirmed` only when the result
is reproduced in a second, independent session.

**Why this priority**: Constitution IV forbids sending unconfirmed messages by default; the gate
is how they become confirmed without risking the pedal.

**Independent Test**: each gate step has a written checklist item with the approved frame, the
backup file it relies on, the record path and the observed result.

**Acceptance Scenarios**:

1. **Given** a write message never sent by this project, **When** the gate step runs, **Then** a
   backup taken in the same session exists and the owner's approval of that exact frame is quoted
   in the gate record.
2. **Given** the gate write succeeded, **When** the owner leaves edit mode without saving,
   **Then** a re-read and a fresh backup show the stored presets unchanged (byte-identical to the
   pre-write backup).
3. **Given** a gate result, **When** the docs are updated, **Then** the message's row in
   `command-layer.md` cites the record and carries the new confidence; a second independent
   session is needed for `confirmed`.

---

### Edge Cases

- The connection drops in the middle of a backup: no partial file is presented as complete; the
  command exits with the connection-lost code.
- The whole-image reply is incomplete (a notification lost): the frame fails length/checksum, the
  command reports a protocol error, and the per-preset reads alone are not silently trusted as the
  backup without the cross-check.
- The pedal leaves edit mode (owner presses the button) between the tool's check and its write:
  the post-write re-read reveals it (mode ≠ edit or value restored) and the tool reports "not
  applied" instead of success.
- The owner turns a physical knob while a host write is in flight: the re-read may show the knob's
  value instead; reported as "not applied" with the re-read values.
- Setting a knob to the value it already has: the tool says "no change" and sends nothing.
- A write to a block switch in edit mode may copy the block's physical knob positions into the
  buffer (pedal behaviour); the re-read report shows every byte that changed, not only the
  targeted one.
- The pedal shows the transient loading state (global slot `ff`) right after a select: the tool
  re-reads until a stable state or a timeout, and does not report bank/slot from the transient.
- The phone app is connected: the pedal does not advertise; same "no device" exit as today.
- Backup file target already exists: the tool does not overwrite it without an explicit flag.
- Firmware other than 96: backup still works (reads are generic) but the file records the
  firmware and the decoder marks fields as unverified for that firmware; writes are refused on
  firmware not covered by a confirmed gate.

## Requirements *(mandatory)*

### Functional Requirements

Backup (read-only)

- **FR-001**: The library and CLI MUST offer a read-only preset backup action that reads the
  stored-image header and all 36 stored presets, and cross-checks them against one read of the
  whole stored image.
- **FR-002**: The backup MUST use only the query and read commands; the frame trace of a backup
  MUST contain no write or erase frame.
- **FR-003**: The backup file MUST record: device identity and firmware, timestamp, header bytes,
  and for each of the 36 presets its index, position (bank 1–9, slot A–D), raw bytes and decoded
  fields (unknown bytes kept as raw), in a documented, versioned format.
- **FR-004**: The backup MUST fail (non-zero exit, no file presented as valid) when the
  per-preset reads and the whole-image read disagree, naming the differing presets.
- **FR-005**: The backup MUST warn when the header is not the expected value, and MUST refuse to
  overwrite an existing file unless explicitly told to.
- **FR-006**: The backup MUST be usable without hardware against a recorded fixture, producing a
  deterministic file (apart from the timestamp) for tests.

Edit-buffer writes

- **FR-007**: Each write MUST be a separately named action (setting a named knob, block switch or
  the LED colour of the current preset); no generic "write any address" action is exposed.
- **FR-008**: Every write action MUST support a dry run that prints the exact frames that would be
  sent and sends no write.
- **FR-009**: Before writing, the tool MUST read the global block and refuse unless the pedal is in
  edit mode; it MUST read the edit buffer and build the knob-block write from it so that only the
  targeted byte changes.
- **FR-010**: Values MUST be validated against the byte map's range for that field before
  anything is sent; out-of-range values are refused.
- **FR-011**: After each write the tool MUST check the reply: only an 8-byte reply with byte 2 =
  `00` and byte 6 = `00` counts as accepted; any other reply is a NAK, reported with its raw bytes,
  and stops the action with the protocol-error exit code.
- **FR-012**: After an accepted write the tool MUST re-read the edit buffer and report applied /
  not applied, listing every byte that changed.
- **FR-013**: Write actions MUST only address the edit buffer (`0x10000000`–`0x10000014`) and the
  preset-select register; the tool MUST NOT send stored-area writes (addresses `0`–`757`), the
  commit (`0xF0000000`), erase (`0x21`) or the loopback flag write (`0xD0000000`), in any code
  path of this feature.
- **FR-014**: A write whose message is still `hypothesis` in the protocol docs MUST be refused
  unless the user passes an explicit experimental opt-in; the refusal names the opt-in and the
  current confidence.
- **FR-015**: Writes MUST be refused on a firmware version not covered by a confirmed hardware
  gate, unless the experimental opt-in is given.

Preset select

- **FR-016**: The library and CLI MUST offer a preset-select action taking a position (`1A`–`9D`)
  or index (0–35), sending the select write for that index, checking the ACK, and re-reading the
  global block and edit buffer to verify.
- **FR-017**: Preset select MUST warn and require an explicit confirmation flag when the pedal is
  in edit mode (unsaved pedal edits would be discarded), and MUST support dry run.

Safety, docs and evidence

- **FR-018**: Every write message used by this feature MUST be documented in
  `command-layer.md` (frame layout, reply, confidence, evidence) in the same change as the code.
- **FR-019**: Each message's first hardware send MUST happen in a gated milestone step with a
  same-session backup and the owner's explicit approval of that exact frame; the step's record is
  kept in `captures/private/` and a sanitized excerpt is committed as a fixture.
- **FR-020**: Committed fixtures MUST NOT contain the full stored image (factory preset content,
  Constitution VI); fixtures use the header plus presets already public in `captures/fw96/`, or
  synthetic preset bytes.
- **FR-021**: All new actions MUST support human-readable and JSON output and use the existing
  exit codes (no device 3, multiple devices 4, Bluetooth unavailable 5, connection lost/timeout 6,
  protocol error/NAK 7, refused/unsafe 1, usage 2).
- **FR-022**: The library MUST emit its hex trace for every frame sent and received by the new
  actions.

### Out of scope (future specs, behind an explicit unsafe opt-in)

- Writing stored presets (address `2 + 21·i` or the whole image), saving with the `0xF0000000`
  commit, and restoring a backup to the pedal.
- Erase (`0x21`), factory restore, firmware update.
- Writing the loopback flag (`0xD0000000`).
- Naming the 9 amp types and 9 IR cabs, and the meaning of the header `a5 5a`.
- Any polling beyond the re-reads needed to verify a write or select.

### Key Entities

- **Stored preset**: one of 36 slots, identified by index 0–35 = bank·4 + slot; 21 bytes laid
  out exactly like the edit buffer (byte map of spec 002).
- **Stored image**: header (2 bytes) followed by the 36 stored presets, 758 bytes in total.
- **Backup**: a file snapshot of the stored image with identity, firmware, timestamp, per-preset
  raw and decoded data and a format version.
- **Edit buffer**: the 21-byte current preset that host writes change; volatile until saved on the
  pedal.
- **Write action**: a named, validated change to one field of the edit buffer (or a preset
  select), with its dry-run frames, its reply (ACK/NAK) and its verification result.
- **Gate record**: the evidence of a message's first hardware sends: approved frame, backup used,
  frames exchanged, observed result, session.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An owner can produce a complete, verified backup of all 36 presets with one command
  in under 10 seconds, with zero write frames in its trace.
- **SC-002**: Two backups taken without any write in between are byte-identical in their preset
  data (100% of 36 presets).
- **SC-003**: For every write action, the dry run's printed frames equal the frames actually sent
  in the corresponding test (100% of write actions covered by offline tests).
- **SC-004**: After each gated hardware write, leaving edit mode without saving returns the pedal
  to its stored preset, and a post-gate backup equals the pre-gate backup (0 stored bytes changed).
- **SC-005**: Each write message in scope (knob block, each of the 4 block switches, LED colour,
  preset select) reaches at least `observed` from this project's own hardware sends, and at least
  the knob block and preset select reach `confirmed` (two independent sessions).
- **SC-006**: 100% of NAK or "not applied" outcomes in tests and gates are reported to the user
  with the raw bytes and a non-zero exit; none is reported as success.
- **SC-007**: The full offline test suite still runs without hardware and passes.

## Assumptions

- Hypothesis-level writes require an explicit experimental opt-in (Constitution IV: hypothesis
  messages are not sent by default); confirmed ones do not. The opt-in's exact name is a plan
  decision.
- Edit-buffer writes require the pedal to be in edit mode (global 3 = `0`), the state in which
  leaving without saving is known to restore the preset. Whether the pedal accepts host writes
  outside edit mode is unknown and is not explored by default.
- A knob change is sent the way the app sends it: the whole 14-byte knob block, rebuilt from a
  fresh read of the edit buffer so that only one byte differs.
- The physical knobs keep their own positions; a host write changes the buffer (and the sound)
  but not the knob, so a later physical move or block toggle may overwrite it (observed pedal
  behaviour, documented to the user).
- The backup reads the 36 presets one by one (each reply fits in one notification) and uses the
  whole-image read as cross-check; both were confirmed on 2026-11-17 (fw 96, MTU 185).
- The backup file format is JSON with its own `format_version`, written to a path the user gives
  (default: a timestamped file in the current directory); restoring from it is a later spec.
- The owner runs every hardware step in their own terminal; the assistant's app session has no
  Bluetooth permission.
- Firmware 96 is the only firmware covered; the pedal reports name `TANK-Gv2`.
