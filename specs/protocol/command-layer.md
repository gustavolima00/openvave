# Tank-G command layer (vendor service `ae40`)

Status: early research. Confidence per Constitution II.

Evidence: the official app's own logcat output, recovered from an Android bugreport on 2026-11-16
(`captures/private/android/`, not committed). App: `com.digAmp.m_efcs` ("M-effects")
v3.9.2314, Flutter + `flutter_blue_plus`. The app logs its command queue (`[CmdQ]`) with
addresses and lengths, but **not the raw bytes**; byte-level framing is still unknown.

Device reported: name `TANK-Gv2`, firmware version `96` (handshake reply `"TANK-Gv2_096"`).

## Transport

| Item | Value | Confidence |
|---|---|---|
| Host → pedal | write to `ae41` | observed |
| Pedal → host | notify on `ae42` (CCCD `2902` enabled right after discovery) | observed |
| MTU | app requests 517; app reports effective MTU 247 | observed |
| Connection priority | app requests "high" | observed |
| Model | strict request/response; app waits for a reply before the next command | observed |
| Unsolicited data | none seen (also confirmed from macOS, 90 s idle) | observed |

## Connection sequence (as performed by the app)

1. Connect, request MTU, request high connection priority, discover services (3), enable notify
   on `ae42`, wait ~200 ms.
2. **Handshake**: send `CMD_Q_NAME_AND_VER` (up to 3 attempts). Reply carries 27 payload bytes:
   ASCII `TANK-Gv2_096` + zero padding → name `TANK-Gv2`, version `96`.
3. Read `0xD0000000`, type 5, 32 bytes.
4. Read `0x20000000`, type 4, 4 bytes ("global" settings; app logs `globOk`).
5. Read `0x10000000`, type 4, 21 bytes ("loadPreset": the current preset).
6. Read `0xD0000000`, type 4, 1 byte.
7. Then a write to `ae41` + notify on `ae42` **every ~1 s** while the app is idle: periodic read
   of the global block (see "Background polling").

## Memory-mapped register model (hypothesis, strongly suggested by app log names)

Every command is a **read or write of `len` bytes at a 32-bit address**, plus a `type` field.

| Op | Request frame size | Reply frame size | Confidence |
|---|---|---|---|
| write `len` bytes | `len + 15` (14 → 29, 1 → 16) | 8 (ack) | observed |
| read `len` bytes | unknown | `len + 15` (32 → 47, 21 → 36, 4 → 19, 1 → 16) | observed |
| `CMD_Q_NAME_AND_VER` | unknown | 34 (27 payload + 7) | observed |

### Frame format

Derived on 2026-11-16 from a local analysis of the app's compiled code (no vendor code is kept in
this repo; description in our own words). Every size below matches the sizes in the app's logs.
Confidence: **confirmed** for header, length field, checksum, query (`0x11`) and read (`0x23`):
on 2026-11-16 `poc/probe_readonly.py` sent the app's 5 connect requests to a Tank-G (fw 96) and
all 5 replies parsed with valid checksums and echoed type/address/length
(`captures/private/20261116-111832-probe.jsonl`). Write (`0x22`) is still **observed** only.

```
offset  size  field
0       1     0x00
1       1     0x59            frame marker
2       1     command
3       3     body length n, little endian (bytes between header and checksum)
6       n     body
6+n     1     checksum = (~ sum(body)) & 0xFF      -- the 6-byte header is not summed
```

| Command | Byte | Request body | Reply body |
|---|---|---|---|
| query name + version (`CMD_Q_NAME_AND_VER`) | `0x11` | empty → request is `00 59 11 00 00 00 FF` | 27 bytes ASCII, NUL padded (`TANK-Gv2_096`) |
| read memory | `0x23` | type(1) · address(4, LE) · length(3, LE) | same 8-byte prefix · data(length) |
| write memory | `0x22` | type(1) · address(4, LE) · length(3, LE) · data | 1 status byte (reply frame = 8 bytes) |
| erase | `0x21` | 5 bytes | not analysed; **never sent by this project** without an explicit unsafe opt-in |
| MIDI over command channel | `0x15` | not analysed yet | — |

Worked example (read the current preset): `00 59 23 08 00 00 04 00 00 00 10 15 00 00 D6`.

Reply handling in the app: the command byte (offset 2) is echoed back; a write reply carries a
status byte at offset 6; read data starts at offset 14. Replies longer than one notification
are reassembled from consecutive `ae42` notifications using the length field.
Reassembly across notifications stays **observed** (from the app's code only): in the committed
capture every reply, the largest being 47 bytes, fit in one notification at ATT MTU 185.

Committed evidence: [`captures/fw96/20261116-probe-connect.jsonl`](../../captures/fw96/20261116-probe-connect.jsonl)
(sanitized copy of `captures/private/20261116-111832-probe.jsonl`, fw 96, macOS) is the fixture
for the frame format, the query (`0x11`) and the read (`0x23`) rows above; the test suite
round-trips every frame in it.

### First values read from hardware (fw 96, 2026-11-16, confirmed)

| Request | Data returned |
|---|---|
| query | `TANK-Gv2_096` + 15 × `00` (27 bytes) |
| type 5 @ `0xD0000000` ×32 | `0a 30 39 36` (`.096`) · zeros · `b7 43 f3` at offsets 19–21 · zeros (bytes 20–21 vary between reads, see below) |
| type 4 @ `0x20000000` ×4 (global) | `00 00 01 01` |
| type 4 @ `0x10000000` ×21 (current preset) | `01 00 00 01 0f 04 3c 3c 46 32 32 00 00 00 00 05 04 07 43 16 43` |
| type 4 @ `0xD0000000` ×1 (status) | `01` |

Preset reading: bytes 4–17 are the 14-byte block the app rewrites when a knob moves.

### Preset / global byte map (in progress)

Method: poll the regions read-only while moving one control at a time (2026-11-16, fw 96): first
with a probe script, then with `openvave watch` (six sessions, 18:25–18:50, owner at the pedal).

One row per byte of the current preset (21), the global block (4) and the status byte (1): 26
rows. This table is authoritative; `src/openvave/protocol/bytemap.py` mirrors it row for row, and
`tests/unit/test_bytemap_doc.py` fails on any difference. Columns:

- **Mask**: `—` for a whole byte; a bit mask for `flag` rows (several rows may share an offset).
- **Name**: stable machine name used in JSON; `—` when the byte is unknown.
- **Encoding**: `continuous` (integer range), `switch` (on/off raw values), `selector` (stepped
  position), `flag` (one bit), `index` (a position, base in Notes), `unknown` (raw value only).
- **Range**: `min–max`, or `on=<raw> off=<raw>` for a switch; `—` otherwise.
- **Confidence**: per Constitution II. `observed` rows cite at least one committed capture;
  `confirmed` rows cite captures from two independent sessions.
- **Evidence**: committed capture paths. Raw session records stay in `captures/private/`.
- **Notes**: values seen (the fw 96 value from the committed capture), controls tried, refuted
  claims.

Decoding a byte (what `preset dump`, `info` and `watch` display):

- `continuous` and `index`: the raw value itself, unscaled and with no unit (an `index` stays
  0-based; Notes give what position 0 means, e.g. slot `0` = A).
- `switch`: `on` for the `on` raw value, `off` for the `off` one.
- `flag`: `on` when `raw & mask` is non-zero, else `off`.
- `selector`: the position's label where the row has labels (only `mode`: `0` edit, `1` normal,
  `2` tuner), else `#` and the raw value (`#7`).
- Outside its Range (or a switch value that is neither `on` nor `off`): the raw value is shown
  as-is and flagged out of range, never clamped.
- `unknown`: no field; the offset is listed as unknown and only the raw byte is shown.

| Region | Offset | Mask | Name | Encoding | Range | Control | Confidence | Firmware | Evidence | Notes |
|---|---|---|---|---|---|---|---|---|---|---|
| global | 0 | — | `browse_bank` | index | 0–8 | preset selection | observed | 96 | `captures/fw96/20261116-step-preset_select-bank.jsonl`, `captures/fw96/20261116-step-preset_select-slots.jsonl` | Bank shown while browsing, base 0 (0 = bank 1 … 8 = bank 9). Moves 0.5–1.5 s **before** global 1 when the owner changes bank, then global 1 follows as the preset loads. Seen 0, 1, 8 (preset walk 9A–9D, 1A–1D, 2A, 2026-11-16). fw96: `0x00` |
| global | 1 | — | `bank` | index | 0–8 | preset selection | observed | 96 | `captures/fw96/20261116-step-preset_select-bank.jsonl`, `captures/fw96/20261116-step-preset_select-slots.jsonl` | Bank of the loaded preset, base 0. 9 banks × 4 slots = the app's `presetNum = 36`. Seen 0, 1, 8. fw96: `0x00` |
| global | 2 | — | `slot` | index | 0–3 | preset selection | observed | 96 | `captures/fw96/20261116-step-preset_select-bank.jsonl`, `captures/fw96/20261116-step-preset_select-slots.jsonl` | Slot of the loaded preset, base 0 (0–3 = A–D); changes in the same cycle as the preset bytes. `0xff` seen for one cycle while a preset loaded, with every preset byte `00` (session 18:43): a loading state, flagged out of range. fw96: `0x01` (the capture is preset 1B) |
| global | 3 | — | `mode` | selector | 0–2 | edit mode, tuner | confirmed | 96 | `captures/fw96/20261116-probe-connect.jsonl`, `captures/fw96/20261116-step-mode-1843.jsonl`, `captures/fw96/20261116-step-mode-1847.jsonl` | Pedal mode: `0` edit, `1` normal, `2` tuner. Edit 1 → 0 → 1 seen in four sessions, tuner 1 → 2 → 1 in three (labelled in session 18:47). Was documented as an edit-mode switch; the tuner value refutes a two-state reading. JSON name `not_in_edit_mode` until 0.1.x, renamed `mode` in 0.2.0. fw96: `0x01` |
| preset | 0 | — | `amp_on` | switch | on=1 off=0 | amp block switch | confirmed | 96 | `captures/fw96/20261116-step-amp_on.jsonl`, `captures/fw96/20261116-step-amp_on-1917.jsonl` | Amp block on/off; labelled off/on steps (session 18:47). `1` on every compared preset. Session 19:17 (labelled): `amp switch off` 1 → 0, `amp switch on` 0 → 1, nothing else moved. fw96: `0x01` |
| preset | 1 | — | `mod_on` | switch | on=1 off=0 | mod block switch | confirmed | 96 | `captures/fw96/20261116-step-mod_on.jsonl`, `captures/fw96/20261116-step-mod_on-1917.jsonl` | Mod block on/off; toggled twice (session 18:47). `1` only on 1D, the only compared preset with mod settings above 0. Session 19:17 (labelled): on 0 → 1, off 1 → 0, alone. fw96: `0x00` |
| preset | 2 | — | `delay_on` | switch | on=1 off=0 | delay block switch | confirmed | 96 | `captures/fw96/20261116-step-delay_on.jsonl`, `captures/fw96/20261116-step-delay_on-1917.jsonl` | Delay block on/off (session 18:47). `1` exactly on the compared presets with delay settings above 0. Session 19:17 (labelled): on 0 → 1, off 1 → 0, alone. fw96: `0x00` |
| preset | 3 | — | `reverb_on` | switch | on=1 off=0 | reverb block switch | confirmed | 96 | `captures/fw96/20261116-step-reverb_on.jsonl`, `captures/fw96/20261116-step-reverb_on-1917.jsonl` | Reverb block on/off (session 18:47). `1` on every compared preset. Session 19:17 (labelled): off 1 → 0, on 0 → 1, alone. fw96: `0x01` |
| preset | 4 | — | `noise_gate` | continuous | 0–127 | noise gate knob | confirmed | 96 | `captures/fw96/20261116-step-noise_gate.jsonl`, `captures/fw96/20261116-step-noise_gate-1917.jsonl` | Only byte to move with the noise gate knob (session 18:25); range seen 2–15 in the step, 0–78 across presets. Session 19:17 (labelled `noise gate`): alone, swept fully down and up, reaching `0` and `127`. fw96: `0x0f` |
| preset | 5 | — | `amp_type` | selector | 0–8 | amp type selector | confirmed | 96 | `captures/fw96/20261116-step-amp_type.jsonl`, `captures/fw96/20261116-step-amp_type-1917.jsonl` | Stepped: 4 → 3 → 1 → 0 in the step (session 18:25); 0, 3, 4, 5, 8 across presets. Session 19:17 (labelled): 8 → 7 → … → 0, one click at a time: **9 positions, 0–8**. fw96: `0x04` |
| preset | 6 | — | `gain` | continuous | 0–127 | gain knob | confirmed | 96 | `captures/fw96/20261116-step-gain.jsonl`, `captures/fw96/20261116-step-gain-1917.jsonl` | Gain: the knob behind this byte, unidentified until 2026-11-16 (60 → 120 → 96 → 127, alone). JSON name `knob_unknown` until 0.1.x, renamed `gain` in 0.2.0. Session 19:17 (labelled `gain`): alone, swept fully down and up, reaching `0` and `127`. fw96: `0x3c` |
| preset | 7 | — | `treble` | continuous | 0–127 | treble knob | confirmed | 96 | `captures/fw96/20261116-step-treble.jsonl`, `captures/fw96/20261116-step-treble-1917.jsonl` | Alone; reached 0, top not yet swept (session 18:25). Session 19:17 (labelled `treble`): alone, swept fully down and up, reaching `0` and `127`. fw96: `0x3c` |
| preset | 8 | — | `middle` | continuous | 0–127 | middle knob | confirmed | 96 | `captures/fw96/20261116-step-middle.jsonl`, `captures/fw96/20261116-step-middle-1917.jsonl` | Alone; range seen 60–80. Session 19:17 (labelled `middle`): alone, swept fully down and up, reaching `0` and `127`. fw96: `0x46` |
| preset | 9 | — | `bass` | continuous | 0–127 | bass knob | confirmed | 96 | `captures/fw96/20261116-step-bass.jsonl`, `captures/fw96/20261116-step-bass-1917.jsonl` | Alone; range seen 50–91. Session 19:17 (labelled `bass`): alone, swept fully down and up, reaching `0` and `127`. fw96: `0x32` |
| preset | 10 | — | `volume` | continuous | 0–127 | volume knob | confirmed | 96 | `captures/fw96/20261116-step-volume.jsonl`, `captures/fw96/20261116-step-volume-1917.jsonl` | Alone; range seen 20–64 in the step; 127 stored on preset 2B. Session 19:17 (labelled `volume`): alone, swept fully down and up, reaching `0` and `127`. fw96: `0x32` |
| preset | 11 | — | `mod_fx` | continuous | 0–127 | mod fx knob | confirmed | 96 | `captures/fw96/20261116-step-mod_fx.jsonl`, `captures/fw96/20261116-step-mod_fx-1917.jsonl` | Alone, 0 → 127 (session 18:25); smooth values. Whether it picks the effect type or its depth is not known. Session 19:17 (labelled `mod fx`): alone, swept fully down and up, reaching `0` and `127`. fw96: `0x00` |
| preset | 12 | — | `mod_speed` | continuous | 0–127 | mod speed knob | confirmed | 96 | `captures/fw96/20261116-step-mod_speed.jsonl`, `captures/fw96/20261116-step-mod_speed-1917.jsonl` | Alone, 0 → 127. Session 19:17 (labelled `mod speed`): alone, swept fully down and up, reaching `0` and `127`. fw96: `0x00` |
| preset | 13 | — | `delay_mix` | continuous | 0–127 | delay mix knob | confirmed | 96 | `captures/fw96/20261116-step-delay_mix.jsonl`, `captures/fw96/20261116-step-delay_mix-1917.jsonl` | Alone, 0 → 127. Session 19:17 (labelled `delay mix`): alone, swept fully down and up, reaching `0` and `127`. fw96: `0x00` |
| preset | 14 | — | `delay_time` | continuous | 0–127 | delay time knob | confirmed | 96 | `captures/fw96/20261116-step-delay_time.jsonl`, `captures/fw96/20261116-step-delay_time-1917.jsonl` | Alone, 0 → 127, swept three times. Session 19:17 (labelled `delay time`): alone, swept fully down and up, reaching `0` and `127`. fw96: `0x00` |
| preset | 15 | — | `reverb_decay` | continuous | 0–127 | reverb decay knob | confirmed | 96 | `captures/fw96/20261116-probe-connect.jsonl`, `captures/fw96/20261116-step-reverb_decay.jsonl`, `captures/fw96/20261116-step-reverb_decay-1917.jsonl` | Session 1 (probe, 2026-11-16): `05` → `7f` when only this knob was turned to max in edit mode. Session 2 (`openvave watch`, 2026-11-16 18:25): in edit mode, only this knob swept fully down then up, twice; only preset byte 15 moved, reaching `0` and `127` (excerpt: cycles 936–942; the owner named the step afterwards, the record has no stdin label). Session 19:17 (labelled `reverb decay`): alone, swept fully down and up, reaching `0` and `127`. fw96: `0x05` |
| preset | 16 | — | `reverb_mix` | continuous | 0–127 | reverb mix knob | confirmed | 96 | `captures/fw96/20261116-step-reverb_mix.jsonl`, `captures/fw96/20261116-step-reverb_mix-1917.jsonl` | Alone, 4 → 127 → 0 → 127 (session 18:25). The earlier probe moved it together with IR cab (hypothesis then). Session 19:17 (labelled `reverb mix`): alone, swept fully down and up, reaching `0` and `127`. fw96: `0x04` |
| preset | 17 | — | `ir_cab` | selector | 0–8 | IR cab selector | confirmed | 96 | `captures/fw96/20261116-step-ir_cab.jsonl`, `captures/fw96/20261116-step-ir_cab-1917.jsonl` | Stepped, alone: 7 → 6 → 2 → 0 → 2 → 7 → 8 (session 18:25); 0, 1, 4, 7, 8 across presets. Session 19:17 (labelled): 0 → 1 → … → 8, one click at a time: **9 positions, 0–8**. fw96: `0x07` |
| preset | 18 | — | — | unknown | — | — | — | 96 | — | Differs per preset (see Preset comparison); no control moved it. fw96: `0x43` |
| preset | 19 | — | — | unknown | — | — | — | 96 | — | Differs per preset (see Preset comparison); no control moved it. fw96: `0x16` |
| preset | 20 | — | — | unknown | — | — | — | 96 | — | Differs per preset (see Preset comparison); no control moved it. fw96: `0x43` |
| status | 0 | — | — | unknown | — | — | — | 96 | — | `0x01` in all seven watch sessions of 2026-11-16, on all ten compared presets and in edit, normal and tuner modes: it does not track the selected preset. fw96: `0x01` |

Edit-mode experiment (2026-11-16, fw 96, `openvave info` between steps, nothing saved):

| Step | Global | Preset bytes 16–17 |
|---|---|---|
| normal (after power-on) | `00 00 01 01` | `04 07` |
| entered edit mode, no knob touched | `00 00 01 00` | `04 07` |
| turned IR cab and reverb mix to max (still in edit mode) | `00 00 01 00` | `7f 08` |
| left edit mode without saving | `00 00 01 01` | `04 07` |

This refutes the earlier "edited / unsaved" hypothesis for global byte 3: it tracks edit mode,
not whether a parameter differs from the stored value. Knobs do nothing outside edit mode (user
report). The byte 16 / 17 assignment rests on the ranges (127 = continuous maximum; +1 = one
selector step, and the user confirms IR cab is a selector); both knobs were moved in the same
step, so a one-knob-at-a-time run is needed to promote them to observed. Leaving edit mode
without saving restores the preset buffer (observed).
Later the same day (session 18:25) reverb mix and IR cab were each moved alone: rows 16 and 17
are now `observed`, and global 3 turned out to have a third value (tuner).

Reads are deterministic for global, current preset and status: two probes minutes apart returned
byte-identical frames (confirmed), and 10 `openvave info` runs agreed (2026-11-16). **Exception**:
device-info bytes 20–21 vary. Over 11 hardware reads on 2026-11-16 they were `43 f3` nine times,
`00 00` once and `43 77` once; byte 19 (`b7`) never changed (observed). They are not a stable
identifier (consistent with the R7 "no MAC match" result); meaning unknown.
Hypothesis (2026-11-16): device-info bytes 20–21 are stale bytes from the **previous reply**, not
device data. Each time, they equalled the last data byte and the checksum of the preset reply
read just before: `43 f3` after the capture's preset reply (`… 43 f3`), `43 79` after the
reverb-decay reply (`… 43 79`), and `00 00` on a first connection. Two paired readings fit and none
contradicts it; the one `43 77` reading had no logged preset reply to compare with.
Pedal edits are **not** pushed: they only become visible to a host that re-reads (confirmed).

### Watch session findings (2026-11-16, fw 96)

Seven `openvave watch` sessions by the owner, 18:25–19:24, phone app disconnected. Raw records stay
in `captures/private/`; the committed step excerpts are listed in the Evidence column above and
indexed in `tests/integration/fixture_pairs.py`. Session 18:25 has no stdin labels (they were
typed into the wrong window): its steps are identified by the owner's report and their timing.
Sessions 18:43 and 18:41 are unlabelled too; sessions 18:47 and 19:17 are fully labelled.
Session 19:17 repeated every knob, selector and block switch (second independent session: those
rows are `confirmed`).

- **Edit buffer vs knob position** (observed). In edit mode, switching a block off and on copies
  the **current physical knob positions** of that block into its bytes. Switching reverb off made
  preset 15/16 jump from the stored `05 04` to `7f 7f`; switching amp off set preset 5–10 to
  `00 7f 0d 3c 44 37`. Both match where the knobs had been left at the end of session 18:25.
  Leaving edit mode without saving restores the stored bytes (all of them, in one cycle). The
  stored value and the knob position are therefore separate, which matters for writes and for
  range sweeps (a value only reaches an end once the knob has really moved there).
- **Block switches** (observed): preset 0–3 = amp, mod, delay, reverb on/off. The first
  off-switch of a block in edit mode co-moves that block's knob bytes (previous bullet), so the
  fixture for each switch is a step that moved the switch byte alone.
- **Preset position** (observed): global 0 = bank being browsed, global 1 = bank of the loaded
  preset, global 2 = slot A–D, all 0-based. Changing bank moves global 0 first; global 1 and 2 move
  in the cycle where the preset bytes change. One load showed a transient (global 2 = `ff`, all
  preset bytes `00`) for a single cycle.
- **Mode** (confirmed): global 3 = 0 edit, 1 normal, 2 tuner.
- **Status byte**: `01` throughout (unknown; the earlier "current preset index?" guess is not
  supported).
- **Disconnect**: the 18:46 session lost the link with the tuner on (`stop` reason
  `connection_lost`, exit 6), and the next connection found the pedal still in tuner mode. A
  later tuner on/off (18:47) kept the link; cause unknown.

### Preset comparison (fw 96)

Stored presets read during the walk (sessions 18:41 and 18:43; nothing saved), identified by
position only. Bytes not listed were equal on all ten: preset 0 and 3 (`01`). 1C holds the same
bytes as 1B (the fw96 capture), and 2A the same as 1A. preset 18–20 differ per preset but never
moved with a control; their meaning is unknown.

| Byte | 1A | 1B | 1C | 1D | 2A | 2B | 9A | 9B | 9C | 9D | Field |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `preset[1]` | 00 | 00 | 00 | 01 | 00 | 00 | 00 | 00 | 00 | 00 | mod on |
| `preset[2]` | 01 | 00 | 00 | 01 | 01 | 00 | 00 | 00 | 00 | 01 | delay on |
| `preset[4]` | 12 | 0f | 0f | 40 | 12 | 00 | 00 | 4e | 4c | 00 | noise gate |
| `preset[5]` | 05 | 04 | 04 | 05 | 05 | 00 | 00 | 03 | 08 | 08 | amp type |
| `preset[6]` | 41 | 3c | 3c | 64 | 41 | 50 | 5e | 66 | 4a | 4f | gain |
| `preset[7]` | 37 | 3c | 3c | 2b | 37 | 3f | 5a | 44 | 50 | 42 | treble |
| `preset[8]` | 41 | 46 | 46 | 58 | 41 | 3f | 3f | 3f | 32 | 46 | middle |
| `preset[9]` | 37 | 32 | 32 | 53 | 37 | 3f | 3f | 37 | 40 | 54 | bass |
| `preset[10]` | 32 | 32 | 32 | 40 | 32 | 7f | 64 | 3c | 37 | 32 | volume |
| `preset[11]` | 00 | 00 | 00 | 14 | 00 | 00 | 00 | 00 | 00 | 00 | mod fx |
| `preset[12]` | 00 | 00 | 00 | 29 | 00 | 00 | 00 | 00 | 00 | 00 | mod speed |
| `preset[13]` | 0c | 00 | 00 | 0f | 0c | 00 | 00 | 00 | 00 | 31 | delay mix |
| `preset[14]` | 28 | 00 | 00 | 35 | 28 | 00 | 00 | 00 | 00 | 37 | delay time |
| `preset[15]` | 35 | 05 | 05 | 09 | 35 | 18 | 0c | 0c | 38 | 0c | reverb decay |
| `preset[16]` | 0f | 04 | 04 | 05 | 0f | 00 | 05 | 05 | 00 | 08 | reverb mix |
| `preset[17]` | 07 | 07 | 07 | 04 | 07 | 00 | 00 | 01 | 01 | 08 | IR cab |
| `preset[18]` | ff | 43 | 43 | 77 | ff | 87 | ff | 55 | ff | 55 | unknown |
| `preset[19]` | f7 | 16 | 16 | b3 | f7 | 00 | 00 | aa | aa | ff | unknown |
| `preset[20]` | 00 | 43 | 43 | b3 | 00 | ca | 00 | ff | ff | 7f | unknown |

### Control inventory (fw 96)

Every control exercised so far, in our own words. "Mapped" means the byte moved alone when only
that control was used.

| Control | Kind | Needs edit mode | Result | Date |
|---|---|---|---|---|
| amp type | stepped knob | yes | preset 5 | 2026-11-16 |
| gain | knob | yes | preset 6 | 2026-11-16 |
| treble | knob | yes | preset 7 | 2026-11-16 |
| middle | knob | yes | preset 8 | 2026-11-16 |
| bass | knob | yes | preset 9 | 2026-11-16 |
| volume | knob | yes | preset 10 | 2026-11-16 |
| noise gate | knob | yes | preset 4 | 2026-11-16 |
| mod fx | knob | yes | preset 11 | 2026-11-16 |
| mod speed | knob | yes | preset 12 | 2026-11-16 |
| delay mix | knob | yes | preset 13 | 2026-11-16 |
| delay time | knob | yes | preset 14 | 2026-11-16 |
| reverb decay | knob | yes | preset 15 | 2026-11-16 |
| reverb mix | knob | yes | preset 16 | 2026-11-16 |
| IR cab | stepped knob | yes | preset 17 | 2026-11-16 |
| amp block switch | switch | yes | preset 0 | 2026-11-16 |
| mod block switch | switch | yes | preset 1 | 2026-11-16 |
| delay block switch | switch | yes | preset 2 | 2026-11-16 |
| reverb block switch | switch | yes | preset 3 | 2026-11-16 |
| edit mode | mode | — | global 3 (`0`) | 2026-11-16 |
| tuner | mode | no | global 3 (`2`) | 2026-11-16 |
| bank / preset selection | selection | no | global 0, 1, 2 (+ preset bytes) | 2026-11-16 |

Not yet known: whether other controls exist that we have not tried. Amp type and IR cab have 9
positions each (0–8), and every knob reaches 0 and 127 (session 19:17).

### Background polling

While connected and when the command queue is idle, the app reads the global block about once
per second ("glob polling"). This is the 1 s write/notify pair seen in the logs (observed).

### Address map

| Address | Type | Len | Seen as | Meaning (hypothesis) |
|---|---|---|---|---|
| `0xD0000000` | 5 | 32 | read at handshake | device info block |
| `0xD0000000` | 4 | 1 | read after preset load | status byte (current preset index?) |
| `0x20000000` | 4 | 4 | read on connect | global settings |
| `0x10000000` | 4 | 21 | read on connect and after each `0xE000000x` write | current/edit preset buffer (1 patch = 21 B) |
| `0x10000001` | 4 | 1 | write | single preset field at offset 1 (effect on/off or module select?) |
| `0x10000004` | 4 | 14 | write, many times while editing | parameter block at offsets 4–17 of the patch (knob moves send the whole block) |
| `0xE0000002` | 4 | 1 | write, then preset re-read | command register (preset change?) |
| `0xE0000003` | 4 | 1 | write, then preset re-read | command register (preset change?) |

### Storage layout (app-declared)

`patchSize = 21 B × presetNum = 36 = 756 B`, `presetStoreOffset = 2`, factory image 758 B,
tail 0 B (the app verifies this layout for the `tankG` product).

## Next steps

- ~~Validate the frame format on hardware~~ done: `openvave info` reads all four regions (fw 96).
- ~~Replay **read-only** commands (`CMD_Q_NAME_AND_VER`, reads) from the library~~ done: the
  read-only client lives in `src/openvave/` (`openvave info`, `openvave preset dump`, `TankG`). Its
  encoder only accepts `0x11` and `0x23`; writes stay disabled until confirmed (Constitution IV).
- Note: a macOS relay (`poc/ble_mitm.py`) is not discovered by the app, likely because it matches
  advertising data macOS cannot emit; a Linux/ESP32 relay would be needed for live app captures.
- ~~Correlate `0x10000004` byte positions with specific knobs~~ done (2026-11-16): preset 4–17
  are the 14 front-panel knobs, preset 0–3 the block switches (see the byte map). The app's
  14-byte write to `0x10000004` therefore carries every knob of the preset at once.
- Still unknown (read-only work): preset 18–20 (per preset, no control moves them); the status
  byte (always `01`); the names of the 9 amp types and 9 IR cabs; any app-only settings not on
  the front panel.
- Questions for the write spec: is the edit buffer (`0x10000000`) written directly while the
  knobs keep their physical positions (see "Edit buffer vs knob position")? Do `0xE0000002/3`
  select a slot or save one (the app re-reads the preset after them; global 0–2 hold the bank and
  slot)? How are stored presets addressed (`presetStoreOffset = 2`, 36 × 21 B)?
- Determine what `0xE0000002/3` do (preset up/down? select index?).

### Host observations (from the 001 milestone gates)

- macOS: a process launched from a host app that has no `NSBluetoothAlwaysUsageDescription` is
  killed by TCC (SIGABRT, exit 134) on its first Bluetooth access, before Python can report an
  error; from Terminal with Bluetooth permission it works (observed, 2026-11-16, macOS 26.5.2).
- With the M-effects phone app connected to the pedal, `openvave info` finds nothing and exits 3
  after the full scan: the pedal stops advertising while a central is connected (observed,
  2026-11-16, fw 96). Exit 6 (connection refused) did not occur.
- With the Mac's Bluetooth turned off, bleak reports it as unavailable and `openvave` exits 5
  (observed, 2026-11-16).
