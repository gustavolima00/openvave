# Tank-G: what the official app does, feature by feature

Status: research inventory for spec 004 (2026-11-17). Described in our own words; no vendor code
or strings are kept in this repo.

Sources: a local analysis of the official app's compiled code (`com.digAmp.m_efcs`, "M-effects",
v3.9.2314, Flutter); the app's own logcat from 2026-11-16 (`[CmdQ]` lines, addresses and lengths
only); this project's hardware sessions on fw 96 (see [command-layer.md](command-layer.md)). Frame
format, address map and byte map live in command-layer.md; this page only says which app feature
uses which message.

Confidence (Constitution II): **confirmed** = this project replayed it on hardware in two sessions;
**observed** = seen once on hardware or in the app's log; **hypothesis** = read from app code only.
Risk: **volatile** = edit buffer only, gone after a preset change; **persistent** = changes the
stored presets (the app always follows these with the commit `0xF0000000`); **destructive** =
overwrites many or all stored presets.

All writes are command `0x22`, type 4, with the reply ACK `00 59 00 01 00 00 00 ff`. "Select `i`"
below means write `01` to `0xE0000000 + i`, `i = bank·4 + slot` (0–35).

## Edit mode from the computer (priority question)

**The app has no notion of edit mode.** It never writes global byte 3 (`mode`), nor any other
register to enter or leave edit mode, and the Tank-G screen has no edit button (hypothesis, code).
When a knob, block switch or colour moves in the app, it writes the edit buffer straight away:
14 bytes at `0x10000004`, 1 byte at `0x10000000 + k`, or 3 bytes at `0x10000012`. The only
conditions it checks are its own (connected, not busy with another operation). The 1 s global
poll is only used for the loaded bank and slot (`bank · 4 + slot`, kept while slot reads `ff`); the
app ignores `mode`. The app's log agrees: its 16 writes are 13 knob blocks, one block switch and
two selects, and none goes to `0x20000000` (observed; the pedal's mode during that session was
not recorded).

What this means for openvave:

- To change a sound remotely, write the edit buffer in **normal** mode, like the app. There is
  nothing to enter first. **Confirmed on fw 96** (check 1, 2026-11-17, two connections, owner at
  the pedal, preset 1B): the confirmed knob-block write (gain 60 → 90) sent in normal mode got
  the ACK; the buffer re-read showed byte 6 = 90 and nothing else changed, also a moment later;
  the owner heard more gain; global stayed `00 00 01 01` (mode **stays normal**, the pedal does not
  switch to edit mode, and the display showed nothing); selecting 1B again restored the stored
  bytes and the sound. Backups before and after were identical. Evidence:
  `captures/fw96/20261117-gate-normal_knob_gain.jsonl`,
  `captures/fw96/20261117-gate-normal_knob_gain_b.jsonl` (both connections used the same preset
  and knob). Still open: what happens when someone turns a pedal knob after a remote write, and
  whether the other edit-buffer writes (switches, LED colour) behave the same in normal mode
  (very likely, same buffer, but not sent).
- **Discard**: select the same preset again; the pedal reloads the stored copy. The app does
  exactly this to restore a preset after bypass (below). On hardware, leaving pedal-side edit mode
  without saving also restores the stored bytes (observed).
- **openvave (spec 004, unreleased)**: `openvave set` now works in normal mode as well as edit mode
  (refused in tuner mode, bypass and unrecognised states), takes reverb decay as the app shows it
  as the manual's reverb type and a position (`set reverb_decay 10 --type spring`), and `openvave preset reload` discards unsaved edits with the
  confirmed preset-select write. Only already-confirmed messages are involved; hardware run of
  quickstart §2 pending (M0 gate).
- **Keep (save)**: the app writes its own 21-byte copy of the preset to the stored slot
  `2 + 21·i`, waits 300 ms, writes zero bytes to `0xF0000000` (commit), waits 100 ms, then selects
  `i` (observed, checks 3 and 4: the change survives a power cycle). It does not read the buffer back first, so a host should read
  `0x10000000` × 21 and write those bytes. "Save" uses the loaded slot, "Save to" lets the user pick
  any slot. Whether the slot write survives a power cycle without the commit is unknown.
- Writing global byte 3 by hand (`0x20000003`) is untested and not something the app ever does:
  do not.

## Screen inventory

The Tank-G screen has: a preset bar, an effect chain of six blocks, an action row (Save, Save to,
BYPASS, Loopback) and a "more" menu. There is no tuner, no global settings page, no naming, no
MIDI page and no firmware update on this screen.

### Preset bar

| Control | Messages | Confidence | Risk |
|---|---|---|---|
| 36 presets `1A`–`9D` | names are generated from the index; nothing is read or written for names | hypothesis | — |
| tap a preset | select `i`, wait 100 ms, read `0x10000000` × 21 | confirmed | volatile (unsaved edits are lost) |
| preset LED colour swatch + colour picker | shown from preset bytes 18–20 (R, G, B); picker writes 3 bytes at `0x10000012` | write observed; LED meaning hypothesis | volatile until saved |

### Effect chain

Six blocks, in order; parameter counts 1, 6, 2, 2, 2, 1 (14 knob bytes = preset bytes 4–17). Every
knob change writes the whole 14-byte block at `0x10000004`, rebuilt from the app's copy.

| Block | Switch (preset byte, write) | Parameters (preset byte) | App display |
|---|---|---|---|
| GATE | none | Gate (4) | 0 shown as `OFF` |
| AMP | byte 0, `0x10000000` | Type (5), Gain (6), Treble (7), Middle (8), Bass (9), Volume (10) | Type as a number 1–9; no amp names in the app |
| MOD | byte 1, `0x10000001` | FX (11), Speed (12) | FX is a **section** knob |
| DLY | byte 2, `0x10000002` | Mix (13), Time (14) | Mix is a **section** knob |
| REV | byte 3, `0x10000003` | Decay (15), Mix (16) | Decay is a **section** knob |
| CAB | none | IR (17) | a number 1–9; no cab names in the app |

Switch writes: 1 byte, `01` on / `00` off (observed on hardware for all four, confirmed for none
yet). Knob block: confirmed.

**Section knobs.** The app draws three parameters with the same three-colour arc: MOD FX, DLY Mix
and REV Decay (all range 0–127). The arc has `ceil(128 / 44) = 3` colours of 44 raw values, each
numbered 1–40 with `X` past 40. The split is **observed** on hardware for all three (REV Decay
2026-11-17; MOD FX and DLY Mix in spec 004 T022, same day: every reading fits; "Reverb decay
sections" in command-layer.md). The app names none of the colours; the Tank-G manual does: REV
Decay room / spring / cloud, MOD FX chorus / phaser / tremolo, DLY Mix analog / tape / dual, and
the `X` positions between two types turn the module off (manual). openvave uses these names
(`set mod_fx 20 --type phaser`). REV Mix (16) and MOD Speed / DLY Time are plain 0–127 knobs.

### Action row

| Control | Messages | Confidence | Risk |
|---|---|---|---|
| Save | 21 B at `2 + 21·i` (loaded `i`) → 300 ms → empty write `0xF0000000` → 100 ms → select `i` | observed (checks 3 and 4): a changed save persists across a power cycle | persistent |
| Save to | same, with a slot chosen in a dialog (the dialog passes an empty name; Tank-G has no names) | hypothesis | persistent |
| BYPASS on | write `01` to `0xE1000000 + i` (loaded `i`) | observed (check 2) | volatile: all blocks off, clean sound; edit buffer reads all zero and global slot reads `ff` |
| BYPASS off | select `i` (`0xE0000000 + i`), then read `0x10000000` × 21 | observed (check 2) | volatile; reloads the stored preset, so unsaved edits are lost |
| Loopback | read `0xD0000000` × 1 on connect; toggle writes `01` / `00` there (no commit) | read confirmed; write and meaning hypothesis | unknown persistence |

### More menu

| Item | Messages | Confidence | Risk |
|---|---|---|---|
| Share current preset | no device traffic: the app's 21-byte copy is saved to a `.tkg` file and shared | hypothesis | none |
| Import current preset | file (size must match) → 21 B at `2 + 21·i` of the **loaded** slot → commit → select `i` | hypothesis | persistent (overwrites the loaded slot) |
| Swap preset | read `2 + 21·a` and `2 + 21·b` (21 B each) → write each to the other → commit → select | read confirmed; writes hypothesis | persistent (two slots) |
| Share all presets | read `0x0` × 758 (one request) → file | confirmed (read) | none |
| Import all presets | file of 758 B → write `0x0` × 758 → commit → write the loaded preset's 21 B to `0x10000000` → re-read | hypothesis | destructive (all 36) |
| Factory Restore | image bundled with the app → write `0x0` × 758 → commit → write `0x10000000` × 21 → re-read | hypothesis | destructive (all 36) |

Notes:

- Two writes appear here that openvave cannot encode yet: the **whole stored image**
  (`0x0` × 758, sent in chunks of at most 1015 bytes, so one frame) and the **whole edit buffer**
  (`0x10000000` × 21). Both hypothesis.
- The Tank-G flows never use erase (`0x21`) or type 6. Those appear only in other products'
  restore paths and a generic "restore all" (hypothesis). This project never sends them.
- Import checks only the file size; the file is the raw preset bytes (21 or 758, hypothesis). An
  openvave backup holds the same bytes, so "restore from backup" is the same message as "import
  all" or "import current".

## Not on the Tank-G screen

| Feature | Finding | Confidence |
|---|---|---|
| Edit-mode toggle | none (see above) | hypothesis |
| Tuner | the app's tuner belongs to another product; the Tank-G tuner is pedal-side only (global 3 = `2`) | hypothesis |
| Global settings | none; the generic "global bypass" write (1 byte at `0x20000002`) is for other products. On a Tank-G that byte is the slot: never write it | hypothesis |
| Preset names / renaming | none; positions only | hypothesis |
| Snapshots, chain order, drum, resource names | registers `0x70xxxxxx` and friends belong to other products | hypothesis |
| Firmware update | no in-app update; the app can only show a "firmware outdated, visit the website" notice after connecting (trigger not analysed) | hypothesis |
| MIDI over the command channel (`0x15`) | built only for another product's drum playback; never for the Tank-G | hypothesis |
| BLE-MIDI service (`03b80e5a…`) | the app does not use it; all traffic is on `ae40` | hypothesis |

## Hardware checks for spec 004 (proposed, nothing sent)

Each needs the owner's approval for that exact frame, with `openvave preset backup` before and
after. Ordered by risk:

1. ~~**Edit-buffer write in normal mode**~~ done 2026-11-17: applied, mode stays normal, select
   restores, backups identical (see "Edit mode from the computer").
2. ~~**BYPASS**~~ done 2026-11-17, see "BYPASS on hardware" below.
3. ~~**Save as a no-op**~~ done 2026-11-17, see "Save on hardware" below.
4. ~~**Real save, power cycle, restore**~~ done 2026-11-17, see "Save on hardware" below.

## Save on hardware (check 3, 2026-11-17, fw 96, observed as a no-op)

One session, owner at the pedal, 1B in normal mode. The app's save sequence with the bytes 1B
already holds (read fresh from the pedal), so stored data must not change:

- 21 bytes to stored slot 1B (`0x17`), the same bytes: ACK; stored 1B read back identical.
- 300 ms, then the empty write to `0xF0000000` (commit): ACK; global and the edit buffer
  unchanged.
- 100 ms, then select 1B: ACK; 1B loaded, buffer = stored 1B, same sound.
- The owner heard a mute of a few milliseconds during the sequence, like a blink, and saw no
  LED or display change. Whether it came from the commit (for example while the pedal writes its
  flash) or from the reload by the select is not separated; checks 1 and 2 also ended with a
  select and no mute was reported there.
- Backups before and after were identical (all 36 presets and the image), and equal to the
  backup taken before check 1.

So the pedal accepts the stored-area write and the commit and harms nothing when the bytes are
unchanged. It does not yet show that a changed slot write is stored, nor that the commit is what
makes it survive a power cycle.

Evidence: `captures/fw96/20261117-check3-noop_save.jsonl` (not a `-gate-` excerpt: openvave cannot
encode these writes yet), checked by `tests/integration/test_noop_save_capture.py`.

### Check 4: a real save persists (2026-11-17, fw 96, observed)

Slot 1C, which on this pedal holds the same bytes as 1B (the public preset), so the original is
known. Two runs, owner at the pedal, normal mode:

- Run 1: 1C written with gain 60 → 90 (`0x2C` × 21), ACK, read back changed; commit, ACK; select
  1C, ACK. The preset LED moved from 1B to 1C, the block LEDs stayed as they were (both presets
  use the same blocks), and 1C had audibly more gain than 1B.
- The owner switched the pedal off and on.
- A full backup after the power cycle differed from the one before run 1 in **exactly one byte**:
  1C byte 6, `3c` → `5a`. The pedal also came back on 1C (global `00 00 02 01`): it remembers the
  last selected preset across a power cycle.
- Run 2 read stored 1C = gain 90, wrote the original bytes back, committed, selected 1C (gain 60)
  and then 1B. The final backup equals the backup from before check 1.

So host saving works like the app's: slot write, commit, select, and only the written slot
changes. Still open: whether a slot write **without** the commit also survives a power cycle
(that would tell whether the commit is what writes flash), and the short mute's source.

Evidence: `captures/fw96/20261117-check4-real_save.jsonl`,
`captures/fw96/20261117-check4-verify_restore.jsonl`, checked by
`tests/integration/test_real_save_capture.py`. The backups themselves hold the factory presets
and stay in `captures/private/`.

## BYPASS on hardware (check 2, 2026-11-17, fw 96, observed)

One session, owner at the pedal, 1B in normal mode, phone app disconnected:

- `01` to `0xE1000001` got the ACK. Right after, and still 2 s later: global `00 00 ff 01` (slot
  `ff`, mode still normal), edit buffer all 21 bytes `00`, status byte `01` unchanged. The owner
  heard a clean (unprocessed) sound and saw every LED go off, as with the app's BYPASS button.
- Select 1B (`0xE0000001`) got the ACK and restored global `00 00 01 01`, the stored 1B bytes and
  the original sound. Backups before and after were identical: nothing stored changed.
- So bypass is a pedal state, not a preset: the buffer of zeros (every block off, every knob 0,
  LED black) and slot `ff` are how it reads. The one-cycle "slot `ff`, all preset bytes `00`"
  seen while loading a preset on 2026-11-16 is most likely the pedal passing through the same
  state (hypothesis). A host that sees slot `ff` for more than a moment should report "bypass",
  not "loading"; the app likewise keeps its last preset index while slot reads `ff`.
- Owner's comparison with the app (same day): the pedal's block LEDs follow the block switches
  of the loaded buffer (preset bytes 0–3): bypass turns every LED off, switching AMP on lights
  the amp LEDs, and selecting a preset shows that preset's switch states, exactly as when the app
  does it. Disconnecting saves nothing (observed).
- Not tried: `0xE1000000 + j` with `j` other than the loaded preset, `00` as data, edit-buffer
  writes while bypassed, and how the pedal's footswitches leave bypass.

Evidence: `captures/fw96/20261117-check2-bypass.jsonl` (not a `-gate-` excerpt: openvave cannot
encode this write yet), checked by `tests/integration/test_bypass_capture.py`.

## Spec 004 gate session A (2026-11-18, fw 96, openvave's own sends)

Owner at the pedal, macOS, one CLI connection per command, each message's frames posted and checked
before its first send, a backup before and after every step. Evidence:
`captures/fw96/20261118-gate-<step>.jsonl` (stored presets sanitised), replayed by
`tests/integration/test_gate_replay.py`; full record in `specs/004-remote-edit-save-restore/tasks.md`
T071–T081.

| Feature | Result |
|---|---|
| Bypass on / off | `bypass on` ACK, pedal read bypass (slot `ff`, buffer zeros); `bypass off 1B` restored 1B. Owner: clean sound, every LED off (as in check 2) |
| Remote edit in normal mode | MOD switch on (MOD LED lit) and LED colour `#ff0000` (preset LED turned red) applied in normal mode; `preset reload` discarded both |
| Loopback | off → status `00`, **kept across a power cycle**, on → `01`. Owner test after the session (phone backing track over Bluetooth audio, USB recording): on = the backing track is in the USB recording; off = still heard, not recorded |
| Save to a slot | 1B + gain 90 saved to 1C, **kept across a power cycle**; backup differed only at 1C byte 6 |
| Restore one slot | 1C restored from the backup; backup then equal to the pre-session one |
| Stored-image write | the 773-byte request (5 Bluetooth writes) got one ACK and no stray reply, as a no-op and as `restore --all`; the full restore was **kept across a power cycle**; final backup equal to the pre-session one key by key |

Open questions, answered or still open:

- **Commit required?** Still open: the slot write without the commit (T080) was not run. openvave
  always commits.
- **Mute source**: a very short mute, almost unnoticed, during the restore sequence (slot write,
  commit, select); which of the three causes it is not separated.
- **Knob after a remote write**: not tested (T080 not run).
- **LED colour**: in normal mode, preset bytes 18–20 do drive the preset LED (written `ff 00 00`,
  LED turned red).
- **Loopback**: answered. The flag decides whether the pedal's Bluetooth audio is mixed into the USB
  recording (`01` yes, `00` no; monitoring unaffected); it persists without a commit. USB playback
  from a computer was not tested.
- **Unexplained preset changes**: twice the pedal was found on another preset than the last select
  left it (1B → 1A, then 1A → 1B) with no command sent, no footswitch pressed and the app not
  connected. Every persistent step re-reads the state first, so no write went to the wrong slot.
  Cause unknown.

## Spec 004 gate session B (2026-11-18, fw 96, confirmations)

Same pedal and owner, after a power cycle, one CLI connection per command, **another loaded preset
(1A) and another target slot (1D)** than session A. Each step's frames were encoded independently,
posted and approved in chat before the send, and compared with the command's dry run; every step
matched. Evidence: `captures/fw96/20261118-gate-{bypass_b,bypass_off_b,save_b,restore_slot_b,restore_all_b}.jsonl`;
full record in `specs/004-remote-edit-save-restore/tasks.md` T086–T089.

Reference state: backup **B0**, not A0. Between the sessions the owner saved two sounds of their own
to 2C and 2D; B0 differs from A0 only in those two slots, and every check of this session is
against B0.

| Feature | Result |
|---|---|
| Bypass on / off | on 1A: ACK, slot `ff`, buffer zeros, `info` reported bypass; `bypass off 1A` restored 1A; backup equal to B0 |
| Save to a slot | 1A + treble 70 saved to 1D (ACK ×3, read back equal), **kept across a power cycle**; backup differed from B0 only in 1D |
| Restore one slot | 1D restored from B0 (ACK ×3); backup equal to B0 |
| Stored-image write | after saving 1D gain 90, `restore --all` from B0: one ACK after the 5 chunks, 36 of 36 equal; after a power cycle the backup equals B0 key by key |

Result: `bypass`, `stored_slot`, `commit` and `stored_image` are `confirmed` (two independent
sessions each) and run without `--experimental`; save and restore still need `--unsafe`. Loopback,
the block switches and the LED colour were not repeated and stay `observed`.

Observations:

- **Unexplained preset change, again**: `info` read 2D at the B0 backup; about two minutes later
  `preset select 1A` reported "from 1B". No command in between wrote anything. As in session A,
  every step re-read the state first, so nothing went to the wrong slot.
- After each power cycle the pedal booted on **1B** (session A: on 1A), not on the preset it was
  switched off on.
- The automatic backup still lands in the current directory (the repo root) when `--backup-dir`
  is not given; each one was moved to `captures/private/`.

## Recommended scope for spec 004

1. **Remote editing without the pedal's edit mode**: lift the `set` refusal in normal mode (check 1
   passed); keep a fresh-read-then-write per field. Accept section input for the three
   section knobs (`reverb_decay orange 10`, later `mod_fx` / `delay_mix` once observed).
2. **Save** (`openvave preset save [--to POS]`): read the buffer, write the slot, commit, select,
   verify by reading the slot back. Behind an explicit `--unsafe` opt-in, with an automatic backup
   first (Constitution IV).
3. **Restore from an openvave backup** (one slot or all 36): the same slot / image write + commit,
   behind `--unsafe` and with a backup of the current state first. This replaces the app's
   import and factory-restore flows without shipping vendor preset content.
4. Optional, small: BYPASS and loopback toggles, after their checks.

Out of scope: erase `0x21`, factory restore from vendor images, firmware update, writes to the
global block, MIDI.
