# Feature Specification: Remote editing in normal mode, save, restore, bypass and loopback

**Feature Branch**: `004-remote-edit-save-restore` (feature directory `004-remote-edit-save-restore`)

**Created**: 2026-11-17

**Status**: Draft

**Input**: User description: "Spec 004: remote editing in normal mode, save, restore, bypass and
loopback for the M-VAVE Tank-G (fw 96). Builds on 003. (1) `set` in normal mode, with typed
input for reverb decay (`set reverb_decay 10 --type spring`) and a way to discard unsaved remote edits.
(2) Bypass on/off (`01` to `0xE1000000 + i`; off = select `i`), and report slot `ff` + zero buffer
as bypass. (3) `preset save [--to POS]` behind `--unsafe`: automatic backup, slot write, 300 ms,
commit `0xF0000000`, 100 ms, select, read back. (4) Restore one slot or all 36 from an openvave
backup behind `--unsafe`; all 36 with the app's one 758-byte image write. (5) Loopback on/off
(`0xD0000000`) behind `--experimental`. Every write keeps dry-run, ACK check, read-back, no
retries. Each new write message gets a gated first send approved by the owner, with a backup
before and after. Out of scope: erase `0x21`, factory images, firmware update, global-block
writes, MIDI."

**Builds on**: [`003-preset-backup-edit-writes`](../003-preset-backup-edit-writes/spec.md)
(backup file, guarded edit-buffer writes, preset select, dry run, the experimental opt-in, gate
sessions, exit codes 0–8, JSON envelope).

**Protocol source of truth**: [`specs/protocol/command-layer.md`](../protocol/command-layer.md)
(frame format, address map, byte map, write messages) and
[`specs/protocol/app-features.md`](../protocol/app-features.md) (what the official app does, and
hardware checks 1–4 of 2026-11-17). This feature ships what those checks showed and records its own
gate results there.

## Starting point (fw 96, 2026-11-17)

| Message | Purpose | Confidence before this feature |
|---|---|---|
| write `0x10000004` × 14 in **normal** mode | knob block, applied without edit mode; mode stays normal | confirmed (check 1, two connections) |
| write `0x10000000 + k` × 1, `0x10000012` × 3 in normal mode | block switches, LED colour | observed in edit mode only; not sent in normal mode |
| write `01` to `0xE0000000 + i` | select preset `i`; selecting the loaded preset discards unsaved edits | confirmed |
| write `01` to `0xE1000000 + i` | bypass on for loaded preset `i` | observed (check 2, one session) |
| write `2 + 21·i` × 21 | stored preset `i` | observed (checks 3 and 4, i = 1 and 2) |
| write `0xF0000000` × 0 | commit stored presets | observed (checks 3 and 4); whether it is required is not tested |
| write `0x00000000` × 758 | whole stored image (app's "import all") | hypothesis (app code) |
| write `01` / `00` to `0xD0000000` | loopback flag | hypothesis (app code); read confirmed |

Pedal behaviour that shapes this feature (all on the owner's pedal, backups identical before and
after each check):

- The pedal needs no edit mode for host writes, and the official app has no notion of it.
- In bypass the edit buffer reads 21 × `00`, the global slot reads `ff`, the mode stays normal, the
  LEDs are off and the sound is clean. Selecting the preset again leaves bypass. The pedal does
  **not** report which slot was loaded while it is bypassed.
- A save (slot write, 300 ms, commit, 100 ms, select) survived a power cycle and changed exactly
  the one byte that was changed; writing the original bytes back the same way restored it. The
  pedal boots on the last selected preset. The owner heard a mute of a few milliseconds during a
  save.
- The block LEDs follow preset bytes 0–3.
- Reverb decay is shown by the app as three colour sections (blue, orange, green) of 44 raw values,
  numbered 1–40 (observed). The app draws MOD FX and DLY Mix with the same widget (hypothesis).
  Reverb mix is a plain 0–127 knob: on 2026-11-17 the owner confirmed that an earlier remark about
  "reverb mix having types" meant reverb decay.

## User Scenarios & Testing *(mandatory)*

Actors:

- **Pedal owner**: has the Tank-G, runs every pedal step in their own terminal (the assistant's
  session has no Bluetooth permission), and approves each first hardware write in chat.
- **Researcher**: writes the gate steps, reads their records, updates the protocol docs and
  confidence levels. May be the owner or an assistant.
- **Library / CLI user**: anyone who later tweaks, saves or restores presets from a script.

### User Story 1 - Edit the current preset without touching the pedal (Priority: P1)

With the pedal in its normal playing mode, the user sets a parameter from the computer and hears
the change at once. Nothing is stored: one command puts the preset back as it was saved. For
reverb decay the user can give the reverb type named in the Tank-G manual (room, spring, cloud)
and a position inside it.

**Why this priority**: it removes the need to press a button on the pedal before every remote
edit, it is volatile (worst case: reload the preset), and it is already confirmed on hardware.

**Independent Test**: offline, the dry run in normal mode prints the knob-block frame, and typed
input maps to the documented raw value. On hardware: set gain in normal mode, see it in the
re-read, reload the preset, see the stored value return, with identical backups before and after.

**Acceptance Scenarios**:

1. **Given** the pedal in normal mode, **When** the user sets a knob (gain = 90), **Then** the
   tool reads the buffer, sends one knob-block write that differs only in that byte, gets the
   ACK, re-reads and reports "applied" with before → after; the mode is still normal.
2. **Given** the pedal in edit mode, **When** the user sets a knob, **Then** it works as in 0.3.0.
3. **Given** the pedal in tuner mode or in bypass, **When** the user sets a field, **Then** the
   tool refuses before sending any write and says why.
4. **Given** `reverb_decay 10 --type spring`, **When** the user sets it, **Then** the tool writes
   raw 53 and reports both readings (`53`, `spring 10`). Without `--type` the position is taken in
   the preset's current type; `--raw 53` writes the raw byte.
5. **Given** a typed input that is not valid (unknown type, position outside 1–40, or `--type` on
   a field without an observed type split such as `reverb_mix` or `gain`), **When** the user sets it,
   **Then** the tool refuses without contacting the pedal for the write and lists what is accepted.
6. **Given** unsaved remote edits, **When** the user asks to reload the current preset, **Then**
   the tool selects the loaded preset again and reports that the buffer equals the stored preset.
7. **Given** a block switch or the LED colour in normal mode, **When** the user sets it without
   the experimental opt-in, **Then** the tool refuses and names the opt-in (those writes are not
   yet confirmed in normal mode).

---

### User Story 2 - Bypass on and off (Priority: P2)

The user turns the whole pedal off (clean sound, LEDs off) and back on from the computer, as with
the app's BYPASS button. While the pedal is bypassed, every read command says "bypass" instead of
showing a preset of zeros or "loading".

**Why this priority**: volatile and already observed once; it also fixes a wrong reading in the
existing read commands (a bypassed pedal looks like an empty preset today).

**Independent Test**: offline, replay the check 2 capture: bypass on is ACKed and verified, `info`
/ `preset dump` / `watch` report bypass, bypass off restores the preset. On hardware: a second,
independent session with identical backups.

**Acceptance Scenarios**:

1. **Given** a loaded preset in normal mode with no unsaved edits, **When** the user turns bypass
   on, **Then** the tool sends one bypass write for the loaded preset, gets the ACK, re-reads and
   reports "bypassed" when the slot reads `ff` and the buffer is all zero. It prints the command
   that leaves bypass, including the position.
2. **Given** unsaved edits in the buffer (buffer ≠ stored preset), **When** the user turns bypass
   on, **Then** the tool refuses unless the user confirms that the edits will be lost.
3. **Given** a bypassed pedal, **When** the user turns bypass off with a position, **Then** the
   tool selects that preset and reports success when the pedal shows that position and the buffer
   equals the stored preset.
4. **Given** a bypassed pedal, **When** the user turns bypass off without a position in a new
   invocation, **Then** the tool refuses, explains that the pedal does not report the slot while
   bypassed, and shows the bank it does report.
5. **Given** a bypassed pedal, **When** the user runs `info`, `preset dump` or `watch`, **Then**
   the state is shown as "bypass", not as a preset whose knobs are all 0 and not as "loading".
6. **Given** a preset that is loading (slot `ff` for one poll), **When** `watch` sees it, **Then**
   it is still reported as a transient, not as bypass.

---

### User Story 3 - Save the current sound to a preset slot (Priority: P3)

After editing, the user saves the current sound into the loaded slot, or into another slot. The
tool first takes a full backup, shows what will change, writes, commits, and reads the slot back to
prove the save. This overwrites a stored preset, so it only runs with an explicit unsafe opt-in.

**Why this priority**: it is what makes remote editing useful, but it is the first persistent
write the project ships. It needs Stories 1 and 2 (state detection) and the 003 backup.

**Independent Test**: offline, replay the check 4 captures through a fake transport and compare
every frame; refusals tested without hardware. On hardware: save one changed byte, power cycle,
back up (exactly that byte differs), save the original back, back up (equal to the first backup).

**Acceptance Scenarios**:

1. **Given** unsaved edits in normal mode and the unsafe opt-in, **When** the user saves, **Then**
   the tool writes a backup file first, then sends slot write → wait → commit → wait → select,
   checks every ACK, reads the slot back, and reports "saved" with the bytes that changed and the
   backup file's path.
2. **Given** no unsafe opt-in, **When** the user saves, **Then** the tool refuses before any write,
   explains that a stored preset would be overwritten, and names the opt-in.
3. **Given** `--to 3B`, **When** the user saves, **Then** slot 3B receives the buffer, the pedal
   ends on 3B, and the previously loaded slot is unchanged.
4. **Given** the buffer equals the target slot, **When** the user saves, **Then** the tool says
   "nothing to save" and sends no write.
5. **Given** a bypassed pedal, tuner mode or edit mode, **When** the user saves, **Then** the tool
   refuses (in bypass the buffer is all zeros and would erase the preset).
6. **Given** the automatic backup fails its cross-check or cannot be written, **When** the user
   saves, **Then** no write is sent.
7. **Given** a dry run, **When** the user saves, **Then** the exact frames, in order and with the
   waits, are printed, a byte-level diff of the slot is shown, and nothing is written (no backup
   file either).
8. **Given** the read-back differs from what was written, **When** the save finishes, **Then** the
   tool reports "not saved as written", shows both versions, names the backup file and the restore
   command, and exits non-zero.
9. **Given** a NAK or a lost connection after the slot write but before the commit or select,
   **When** the tool stops, **Then** it says exactly which steps were acknowledged, that the stored
   state is uncertain, and how to check it (backup) and undo it (restore from the automatic backup).
   It does not retry.

---

### User Story 4 - Restore presets from a backup file (Priority: P4)

The user gives the tool an openvave backup file and restores either one preset slot or all 36. The
tool backs up the current state first, shows which slots differ, writes, commits and verifies
against the file. This replaces the app's import and factory-restore flows without shipping any
vendor preset content: the user restores their own backup.

**Why this priority**: it is the undo for Story 3 and the most destructive action in scope (all
36 presets); the all-presets message is still a hypothesis and needs its own hardware check.

**Independent Test**: offline, restore a synthetic backup into a fake pedal and compare the frames
and the resulting image; file validation tested without hardware. On hardware (gated): restore the
unchanged backup (no-op), then a backup with known differences, power cycle, compare, restore the
original.

**Acceptance Scenarios**:

1. **Given** a valid backup file and the unsafe opt-in, **When** the user restores one slot,
   **Then** the tool backs up the current state, writes that slot's 21 bytes, commits, selects it,
   reads it back and reports "restored" when it equals the file.
2. **Given** a valid backup file and the unsafe opt-in, **When** the user restores all presets,
   **Then** the tool backs up the current state, writes the whole image in one message, commits,
   reloads the preset that was loaded, takes a full read and reports "restored" only when all 36
   presets and the header equal the file.
3. **Given** the pedal already equals the file (one slot or all), **When** the user restores,
   **Then** the tool says "nothing to restore" and sends no write.
4. **Given** a file that is not a valid backup (wrong format version, not 36 presets, a preset that
   is not 21 bytes, raw bytes and whole image disagreeing, a header other than `a5 5a`), **When**
   the user restores, **Then** the tool refuses before contacting the pedal for any write and says
   what is wrong.
5. **Given** a backup taken on another firmware version, **When** the user restores, **Then** the
   tool refuses unless the experimental opt-in is also given.
6. **Given** a dry run, **When** the user restores, **Then** the tool lists the slots that differ,
   prints the exact frames and writes nothing.
7. **Given** a failure part-way (NAK, lost connection, read-back mismatch), **When** the tool
   stops, **Then** it reports what was acknowledged, names the automatic backup and exits non-zero,
   as in Story 3.

---

### User Story 5 - Loopback on and off (Priority: P5)

The user switches the pedal's loopback flag (the app's Loopback button) from the computer. What
loopback does on the Tank-G is not known yet, so the command is experimental and its first use is
a hardware check that finds out.

**Why this priority**: smallest value and least known; one byte, no commit, but unknown meaning
and persistence.

**Independent Test**: offline, dry run and fake-transport tests. On hardware (gated): read the
flag, turn it off, listen and record over USB, power cycle, read it, turn it back on.

**Acceptance Scenarios**:

1. **Given** the experimental opt-in, **When** the user turns loopback off, **Then** the tool reads
   the flag, sends one 1-byte write, gets the ACK, re-reads and reports before → after.
2. **Given** no experimental opt-in, **When** the user sets loopback, **Then** the tool refuses and
   names the opt-in and the current confidence.
3. **Given** the flag already has the requested value, **When** the user sets it, **Then** the tool
   says "no change" and sends nothing.
4. **Given** `info`, **When** the gate has shown what the flag does, **Then** the status byte is
   shown as loopback on/off with its confidence; until then it stays an unknown byte.

---

### User Story 6 - Gate each new write and record the evidence (Priority: P1 for the gate, applies to Stories 2–5)

Before a new write message is sent by openvave for the first time, the researcher states the exact
frame and the expected result, the owner approves that frame in chat, takes a backup, runs the
step and takes a second backup. The record becomes evidence; the message is `confirmed` only after
a second, independent session.

**Why this priority**: Constitution IV. The checks of 2026-11-17 were sent by throwaway scripts;
this feature's own sends are what the write-messages table may cite.

**Independent Test**: each gate step has a checklist item with the approved frame, the two backup
files, the record path and the observed result.

**Acceptance Scenarios**:

1. **Given** a write message openvave has never sent, **When** its gate step runs, **Then** the
   owner's approval of that exact frame is quoted in the record and backups from before and after
   exist.
2. **Given** a volatile gate step (set in normal mode, bypass, loopback), **When** it ends,
   **Then** the backup after equals the backup before.
3. **Given** a persistent gate step (save, restore), **When** it ends, **Then** the backup after
   differs from the one before only in the bytes the step meant to change, and the last step of the
   session returns the pedal to the first backup.
4. **Given** a gate result, **When** the docs are updated, **Then** the message's row cites the
   committed excerpt and carries its new confidence.
5. **Given** the gate sessions, **When** they are planned, **Then** they also answer the open
   observations below where that costs no extra risk.

Open observations to record during the gates (none blocks the feature):

- Does a stored-slot write survive a power cycle **without** the commit?
- Where does the short mute during a save come from (commit or select)?
- What happens when a pedal knob is turned after a remote write in normal mode?
- Do block switches and the LED colour behave in normal mode as in edit mode? Does the LED colour
  show on the pedal?
- Do MOD FX and DLY Mix follow the same 44-value sections in the app (read-only check)?
- Does loopback survive a power cycle, and what does it do to the sound or the USB recording?

Not to be tried in this feature: bypass with an index other than the loaded preset, bypass data
other than `01`, edit-buffer writes while bypassed.

---

### Edge Cases

- The pedal's state changes between the tool's check and its write (owner presses a footswitch,
  enters the tuner): the re-read shows it and the tool reports "not applied", never success.
- A pedal knob is turned while a remote edit is unsaved: the buffer may change; a later save writes
  what the buffer holds at that moment, and the save's diff shows every byte that will change.
- Save or restore while the phone app is connected: the pedal does not advertise; "no device" as
  today.
- Slot `ff` with a buffer that is **not** all zero, or a zero buffer with a valid slot: reported as
  read, flagged as unexpected, and every write is refused.
- The whole-image write is longer than one Bluetooth write can carry: how the request is split is
  not yet shown on hardware (only replies have been reassembled). If the gate shows the pedal
  rejects it, restoring all presets falls back to slot-by-slot writes with one commit, after its
  own gate.
- Power is lost during a save or restore: outcome unknown and stated in the warning shown before
  an unsafe write; the automatic backup on disk is the recovery path.
- The backup file used for a restore is the automatic backup the tool has just written: allowed;
  it is then a no-op.
- The target file for the automatic backup already exists: a new name is chosen; an existing
  backup is never overwritten.
- Restoring one slot that is the loaded preset: the unsaved edits in the buffer are lost on the
  final select; the tool says so and needs the same confirmation as bypass.
- Firmware other than 96: volatile writes need the experimental opt-in (as in 0.3.0); persistent
  writes need both opt-ins.
- Setting a field to the value it already has, saving an unchanged buffer, restoring an identical
  backup: "no change", nothing sent.

## Requirements *(mandatory)*

### Functional Requirements

Remote editing in normal mode

- **FR-001**: Setting a field MUST work when the pedal is in normal mode or in edit mode, and MUST
  be refused, before any write, in tuner mode, in bypass and in any state the tool does not
  recognise.
- **FR-002**: A set MUST keep the 0.3.0 sequence: fresh read, one write that changes only the
  targeted bytes, ACK check, re-read, report applied / not applied with every byte that changed.
- **FR-003**: For reverb decay the user MUST be able to give the value as a type named in the
  Tank-G manual (room, spring, cloud) and a position 1–40 inside it; without a type the preset's
  current type is kept (refused when the knob sits between two types); the raw value 0–127 stays
  reachable with an explicit `--raw`. Reports MUST show both readings (raw and type). The app's
  colours are not used as names (amended 2026-11-17 during the M0 gate, owner's decision).
- **FR-004**: Typed input MUST be refused for every field whose type split is not at least
  `observed` in the protocol docs. MOD FX (chorus, phaser, tremolo) and DLY MIX (analog, tape,
  dual) gain typed input only if this feature's read-only check observes their split (it did:
  T022, 2026-11-17); reverb mix has none.
- **FR-005**: The tool MUST offer a named action that discards unsaved edits by reloading the
  loaded preset, and verifies that the buffer equals the stored preset.
- **FR-006**: The help and the output of a remote edit MUST say that the change is not saved and
  how to discard or save it.

Bypass

- **FR-007**: The tool MUST offer bypass on and bypass off as named actions. Bypass on sends the
  bypass write for the **loaded** preset only; bypass off selects a preset.
- **FR-008**: Bypass on MUST be refused when the pedal is not in normal mode with a valid loaded
  slot, and MUST need an explicit confirmation when the buffer differs from the stored preset.
- **FR-009**: Bypass on is verified by a re-read showing slot `ff` and an all-zero buffer; bypass
  off by the pedal showing the requested position and the buffer equal to the stored preset.
- **FR-010**: Bypass off MUST take the position to return to; when it is missing and the pedal is
  bypassed, the tool refuses and explains why. Bypass on MUST print that position.
- **FR-011**: Every read command (`info`, `preset dump`, `watch`) MUST report a pedal whose slot
  reads `ff` with an all-zero buffer as "bypass" once the state is seen on two consecutive reads,
  and as a transient when it lasts one read. In bypass, decoded preset fields MUST NOT be presented
  as the preset's values. JSON gains this state as an added field; existing fields keep their
  meaning.

Save (persistent)

- **FR-012**: The tool MUST offer a save action that stores the current buffer in the loaded slot,
  or in a slot given by position (`1A`–`9D`) or index (0–35).
- **FR-013**: Save MUST be refused without an explicit unsafe opt-in; the refusal names the opt-in
  and says that a stored preset will be overwritten.
- **FR-014**: Before the first persistent write of a save or restore, the tool MUST take a full
  backup (the 003 backup with its cross-check), write it to a new file and report its path. If the
  backup fails, nothing is written to the pedal.
- **FR-015**: Save MUST send, in this order and with nothing in between: the 21-byte slot write, a
  wait of 300 ms, the empty commit write, a wait of 100 ms, the select of the target slot. Each
  write's ACK is checked before the next step; a NAK stops the sequence.
- **FR-016**: The 21 bytes written MUST be the bytes read from the buffer in the same invocation,
  unchanged. Save MUST be refused when the pedal is bypassed, in tuner mode, in edit mode, or in an
  unrecognised state.
- **FR-017**: After the sequence the tool MUST read the stored slot back and report "saved" only
  if it equals the bytes written, the pedal shows the target position and the buffer equals the
  slot. Otherwise it reports the mismatch with both versions and exits with the not-applied code.
- **FR-018**: When the buffer already equals the target slot, save sends nothing.

Restore (persistent)

- **FR-019**: The tool MUST offer a restore action that takes an openvave backup file and restores
  either one named slot (to the same position) or all 36 presets.
- **FR-020**: Restore MUST validate the file before any write: supported format version, 36
  presets of 21 bytes, positions complete and unique, per-preset bytes equal to the image they
  were cross-checked with, header `a5 5a`. A file from another firmware version needs the
  experimental opt-in as well.
- **FR-021**: Restore MUST be refused without the unsafe opt-in, and MUST take the automatic
  backup of FR-014 first.
- **FR-022**: Restoring one slot uses the save sequence of FR-015 with the file's bytes. Restoring
  all presets writes the whole 758-byte image (header and 36 presets) in one message, then the
  commit, then reloads the preset that was loaded before the restore.
- **FR-023**: Restore is verified by reading back: the slot for a single restore, a full backup
  read for a full restore. It reports "restored" only when the result equals the file.
- **FR-024**: Restore MUST list the slots that differ from the file before writing, and send
  nothing when none differs.
- **FR-025**: The tool MUST NOT ship, download or embed any preset content; the only source for a
  restore is a file the user provides.

Loopback

- **FR-026**: The tool MUST offer loopback on and off as a named action behind the experimental
  opt-in: read the flag, one 1-byte write, ACK check, re-read. It is never followed by a commit.
- **FR-027**: Once this feature's gate has observed the flag's effect, the status byte MUST be
  named and decoded in the read commands with its confidence; otherwise it stays unknown.

Safety, opt-ins and failure reporting

- **FR-028**: Every write action MUST support a dry run that performs the reads, prints the exact
  frames that would be sent, in order, with the waits, and sends no write. The frames printed are
  the frames that would be sent.
- **FR-029**: Two opt-ins exist and are independent. **Unsafe**: required, always, for any action
  that changes stored presets (save, restore). **Experimental**: required for any write whose
  message is not yet `confirmed` by this project's own sends, and on firmware other than 96. An
  action may need both.
- **FR-030**: Before an unsafe action sends its first write, the tool MUST show what will be
  overwritten (slot or slots, byte-level diff for a single slot), the backup file path, and a
  warning that a power loss during the write has an unknown outcome.
- **FR-031**: Writes MUST never be retried. After a NAK, a lost connection or a failed
  verification in a multi-step action, the tool MUST report each step as acknowledged / not sent /
  unknown, state whether stored presets may have changed, and give the recovery commands.
- **FR-032**: The only write messages the tool can produce are those of 0.3.0 plus: bypass
  (`0xE1000000 + i`, data `01`), stored slot (`2 + 21·i` × 21), commit (`0xF0000000` × 0), stored
  image (`0x0` × 758) and loopback (`0xD0000000` × 1, data `00` or `01`). Erase (`0x21`), type 6,
  writes to the global block (`0x20000000`–`0x20000003`), the whole-edit-buffer write
  (`0x10000000` × 21), MIDI over the command channel (`0x15`) and any other address MUST remain
  impossible to produce in any code path.
- **FR-033**: The stored-slot write, the commit and the stored-image write MUST be reachable only
  through save and restore; no generic "write any address" action is exposed.
- **FR-034**: All new actions MUST support human-readable and JSON output, emit the hex trace, and
  use the existing exit codes (refused 1, usage 2, no device 3, several devices 4, Bluetooth
  unavailable 5, connection lost 6, protocol error / NAK 7, acknowledged but not applied 8). No
  new exit code is added.

Docs and evidence

- **FR-035**: Every new write message MUST be documented in `command-layer.md` (address, length,
  data, reply, confidence, evidence) in the same change as the code, and `app-features.md` MUST be
  updated with each gate result.
- **FR-036**: Each new message's first send by openvave MUST happen in a gate step: exact frame
  approved by the owner in chat, backup before and after, record kept privately, sanitised excerpt
  committed. A message is `confirmed` only after two independent sessions.
- **FR-037**: Committed fixtures MUST NOT contain the stored image or any stored preset other than
  those already public in `captures/fw96/`; save and restore fixtures use those presets or
  synthetic bytes.
- **FR-038**: The 0.3.0 statement "openvave never saves or overwrites a stored preset" MUST be
  replaced in the user docs and changelog by an accurate one: it does so only through save and
  restore, only with the unsafe opt-in, and always after a backup.

### Out of scope

- Erase (`0x21`), factory restore from vendor images, firmware update: never sent.
- Writes to the global block, including the mode byte: the tool never enters or leaves edit mode
  or the tuner for the user.
- MIDI (command `0x15` and the BLE-MIDI service).
- The app's preset swap and `.tkg` single-preset files; copying a slot is done with select and
  `save --to`.
- Restoring a slot from a backup into a different position.
- Names for the 9 amp types, the 9 IR cabs and the colour sections; the meaning of the header.
- Bypass variations (other index, other data) and edit-buffer writes while bypassed.

### Key Entities

- **Pedal state**: what the tool derives from the global block and the buffer before any action:
  normal, edit, tuner, bypass, loading (transient) or unrecognised, plus the loaded position when
  the pedal reports one.
- **Remote edit**: an unsaved change to the edit buffer; ends by reload (discarded), bypass
  (discarded) or save (stored).
- **Typed value**: a reverb-decay value given as type (room, spring, cloud) and position,
  equivalent to one raw value; between two types the module is off (manual).
- **Stored preset / stored image**: as in 003 (21 bytes; header + 36 presets = 758 bytes).
- **Backup file**: the 003 file; now also the input of restore and the automatic safety copy of
  every unsafe action.
- **Persistent action**: save or restore: a fixed sequence of writes (slot or image, commit,
  select) with a step-by-step outcome and a read-back verdict.
- **Gate record**: as in 003: approved frame, backups before and after, frames exchanged, result.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user can change a knob of the current preset from the computer in normal mode and
  have it confirmed in under 5 seconds, without touching the pedal.
- **SC-002**: After any number of remote edits followed by a reload, a backup equals the backup
  taken before them (0 stored bytes changed).
- **SC-003**: A save changes only the target slot: the backup after differs from the automatic
  backup before in that slot only, and the slot equals the buffer that was saved (checked on
  hardware across a power cycle).
- **SC-004**: A full restore followed by a backup yields preset data identical to the restored
  file (36 of 36 presets and the header), and restoring the automatic backup returns the pedal to
  its previous state byte for byte.
- **SC-005**: 100% of save and restore runs leave a verified backup file on disk before the first
  write; 0 persistent writes are possible without the unsafe opt-in (covered by offline tests of
  every entry point).
- **SC-006**: For every write action, the frames printed by the dry run equal the frames sent in
  the corresponding offline test (100% of actions).
- **SC-007**: A bypassed pedal is reported as "bypass" by all three read commands, and a one-read
  loading transient is not (both covered by replayed captures).
- **SC-008**: Every NAK, lost connection and verification mismatch in tests and gates ends with a
  non-zero exit and a step-by-step report; none is reported as success, and none triggers a retry.
- **SC-009**: Each new message (bypass, stored slot, commit, stored image, loopback) reaches at
  least `observed` from openvave's own sends; bypass, stored slot and commit reach `confirmed`.
- **SC-010**: After the last gate session the pedal's backup equals the backup taken before the
  first one.
- **SC-011**: The full offline test suite runs without hardware and passes; no committed file
  contains the stored image.

## Assumptions

- Defaults taken instead of clarification markers; `/speckit-clarify` can revisit them:
  - The automatic backup before a persistent write cannot be skipped.
  - Save is refused in edit mode (never exercised on hardware; the pedal has its own save there).
  - Persistent writes need the experimental opt-in in addition to unsafe until their messages are
    `confirmed` by openvave's own gate sessions.
  - After a full restore the tool reloads the previously loaded preset with the confirmed select
    message, instead of the app's whole-edit-buffer write, so that message stays impossible to send.
  - Bypass off needs the position on the command line; the tool keeps no state between runs.
  - Section input covers positions 1–40 only; the raw values the app shows as `X` are reachable by
    raw value.
- Decisions by the owner (2026-11-17): "reverb mix has types" meant reverb decay; a full restore
  uses the app's single image write rather than 36 slot writes (nothing important is stored on the
  pedal), subject to its gate; loopback is included as experimental.
- The save timing (300 ms, 100 ms) is the app's and the one checks 3 and 4 used; it is not tuned.
- The short mute during a save is accepted behaviour and is documented to the user.
- A host write changes the buffer and the sound but not the physical knobs (003); a later knob
  move on the pedal may overwrite a remote edit.
- The backup file format of 0.3.0 already holds everything a restore needs; if not, it gets a new
  format version and old files stay readable.
- The owner runs every hardware step in their own terminal; throwaway scripts live in `poc/`
  (git-ignored). Firmware 96 is the only firmware covered.
