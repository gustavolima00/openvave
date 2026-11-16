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

Method: poll the regions read-only while moving one control at a time (2026-11-16, fw 96).

| Region | Offset | Meaning | Range | Confidence |
|---|---|---|---|---|
| preset | 6 | one front-panel knob (which one: TBD) | 0–127 (`0x00`–`0x7F`) | observed |
| preset | 16 | reverb mix (continuous knob): `04` → `7f` when turned to max in edit mode | 0–127 | hypothesis (moved together with IR cab, see below) |
| preset | 17 | IR cab (selector knob): `07` → `08` when turned to max in edit mode | small index | hypothesis (moved together with reverb mix, see below) |
| global | 3 | **edit mode flag**: `1` normally, `0` while the pedal is in edit mode — flips on entering edit mode before any knob moves, stays `0` while knobs move, returns to `1` on leaving edit mode without saving | 0/1 | observed |

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

Reads are deterministic for global, current preset and status: two probes minutes apart returned
byte-identical frames (confirmed), and 10 `openvave info` runs agreed (2026-11-16). **Exception**:
device-info bytes 20–21 vary. Over 11 hardware reads on 2026-11-16 they were `43 f3` nine times,
`00 00` once and `43 77` once; byte 19 (`b7`) never changed (observed). They are not a stable
identifier (consistent with the R7 "no MAC match" result); meaning unknown.
Pedal edits are **not** pushed: they only become visible to a host that re-reads (confirmed).

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
- Correlate `0x10000004` byte positions with specific knobs: enter edit mode, then move one knob
  at a time (bytes 16/17 started above).
- Determine what `0xE0000002/3` do (preset up/down? select index?).

### Host observations (from the 001 milestone gates)

- macOS: a process launched from a host app that has no `NSBluetoothAlwaysUsageDescription` is
  killed by TCC (SIGABRT, exit 134) on its first Bluetooth access, before Python can report an
  error; from Terminal with Bluetooth permission it works (observed, 2026-11-16, macOS 26.5.2).
- With the Mac's Bluetooth turned off, bleak reports it as unavailable and `openvave` exits 5
  (observed, 2026-11-16).
