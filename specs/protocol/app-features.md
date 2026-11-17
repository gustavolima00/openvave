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
- **Keep (save)**: the app writes its own 21-byte copy of the preset to the stored slot
  `2 + 21·i`, waits 300 ms, writes zero bytes to `0xF0000000` (commit), waits 100 ms, then selects
  `i` (hypothesis). It does not read the buffer back first, so a host should read
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
numbered 1–40 with `X` past 40. For REV Decay this split is observed on hardware ("Reverb decay
sections" in command-layer.md); for MOD FX and DLY Mix it is **hypothesis** (same widget, same
range, not yet checked against the app on the pedal). The colours most likely select the effect
type (for example three modulation or three delay types) and the number its amount, but the app
names none of them. REV Mix (16) and MOD Speed / DLY Time are plain 0–127 knobs.

### Action row

| Control | Messages | Confidence | Risk |
|---|---|---|---|
| Save | 21 B at `2 + 21·i` (loaded `i`) → 300 ms → empty write `0xF0000000` → 100 ms → select `i` | hypothesis | persistent |
| Save to | same, with a slot chosen in a dialog (the dialog passes an empty name; Tank-G has no names) | hypothesis | persistent |
| BYPASS on | write `01` to `0xE1000000 + i` (loaded `i`) | hypothesis | volatile (meaning unknown: probably all blocks off) |
| BYPASS off | select `i` (`0xE0000000 + i`), then read `0x10000000` × 21 | hypothesis | volatile; reloads the stored preset, so unsaved edits are lost |
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
2. **BYPASS** (volatile, new register): `01` to `0xE1000000 + i`; read global and the buffer, listen;
   then select `i` to undo.
3. **Save as a no-op** (persistent, but writes the bytes already there): write 1B's own stored 21
   bytes back to `2 + 21·5` + commit + select. The backup after must equal the one before. Then a
   real save of a changed field, and a restore of the original bytes from the backup.

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
