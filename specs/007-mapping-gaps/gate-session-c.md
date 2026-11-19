# Gate session C (spec 007, fw 96): runbook

Second independent session for the writes still `observed` (FR-001…FR-004), plus the IR cab 0
listening step and the MASTER watch step (FR-008, FR-009). Run by the owner in their own terminal
(Bluetooth permission); every frame below was encoded independently from the frame format in
`specs/protocol/command-layer.md` and must be approved in chat before it is sent. Nothing here is
persistent except loopback (kept across a power cycle; the session puts it back).

Differences from spec 004 session A (what makes it independent): another day, a new connection per
command, loaded preset **1A** (session A used 1B), and the opposite direction for each switch where
1A allows it.

## Setup

```bash
cd /Users/gustavomarques/personal/riffmind/openvave/.claude/worktrees/recursing-shannon-99d063
P=/Users/gustavomarques/personal/riffmind/openvave/captures/private
```

Phone app disconnected. Pedal on, in normal mode, on **1A** (`uv run openvave preset select 1A` if
not).

## Steps

| # | Step | Command | Expected frame (TX) | Check |
|---|---|---|---|---|
| 0 | backup C0 | `uv run openvave preset backup --output $P/20261119-gate007-C0.json` | reads only | 36 presets, cross-check OK |
| 1 | info | `uv run openvave info` | reads only | state normal, preset 1A, note status (loopback) |
| 2 | amp off | `uv run openvave --trace set amp_on off --experimental 2> $P/20261119-gate007-switch_amp_c.trace` | `00 59 22 09 00 00 04 00 00 00 10 01 00 00 00 ea` | ACK, applied; amp LEDs off |
| 3 | mod on | `uv run openvave --trace set mod_on on --experimental 2> $P/20261119-gate007-switch_mod_c.trace` | `00 59 22 09 00 00 04 01 00 00 10 01 00 00 01 e8` | ACK, applied; MOD LED on |
| 4 | delay off | `uv run openvave --trace set delay_on off --experimental 2> $P/20261119-gate007-switch_delay_c.trace` | `00 59 22 09 00 00 04 02 00 00 10 01 00 00 00 e8` | ACK, applied; delay LEDs off |
| 5 | reverb off | `uv run openvave --trace set reverb_on off --experimental 2> $P/20261119-gate007-switch_reverb_c.trace` | `00 59 22 09 00 00 04 03 00 00 10 01 00 00 00 e7` | ACK, applied; reverb LEDs off |
| 6 | LED green | `uv run openvave --trace set led_colour '#00ff00' --experimental 2> $P/20261119-gate007-led_colour_c.trace` | `00 59 22 0b 00 00 04 12 00 00 10 03 00 00 00 ff 00 d7` | ACK, bytes 18–20 = `00 ff 00`; **is the 1A footswitch LED green?** |
| 7 | reload | `uv run openvave --trace preset reload 2> $P/20261119-gate007-reload_c.trace` | `00 59 22 09 00 00 04 00 00 00 e0 01 00 00 01 19` | buffer = stored 1A again |
| 8 | loopback off | `uv run openvave --trace loopback off --experimental 2> $P/20261119-gate007-loopback_off_c.trace` | `00 59 22 09 00 00 04 00 00 00 d0 01 00 00 00 2a` | ACK, status `00` |
| 9 | loopback on | `uv run openvave --trace loopback on --experimental 2> $P/20261119-gate007-loopback_on_c.trace` | `00 59 22 09 00 00 04 00 00 00 d0 01 00 00 01 29` | ACK, status `01` (skip 8–9 order if step 1 read `00`: do on, then off) |
| 10 | IR cab 0 | `uv run openvave set ir_cab 0`, play, then `uv run openvave set ir_cab 1`, play, then `uv run openvave preset reload` | knob block (confirmed; dry run first) | **does 0 sound like no cabinet (raw, fizzy amp) and 1 like a cabinet?** |
| 11 | MASTER | `uv run openvave watch --duration 40 --record $P/20261119-gate007-master.jsonl`; type `master` + Enter, turn only MASTER fully down and up twice, then `q` + Enter | reads only | does any byte change? |
| 12 | backup C1 | `uv run openvave preset backup --output $P/20261119-gate007-C1.json` | reads only | equal to C0 apart from `created_at` |

Optional, if loopback can be heard: with a phone playing over Bluetooth audio and a USB recording
running, steps 8/9 should remove / restore the phone audio in the recording.

After the session the excerpts are cut with `tests/support/gate_excerpt.py` and the rows that pass
are promoted to `confirmed` (spec 007 tasks).
