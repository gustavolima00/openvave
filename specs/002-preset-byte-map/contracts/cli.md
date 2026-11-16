# CLI contract additions: `openvave` (feature 002)

Extends [001 `cli.md`](../../001-readonly-ble-connection/contracts/cli.md). Global options, stderr
rules and exit codes are unchanged unless stated.

## `openvave preset dump` / `openvave info`: decoded fields

The hex dump stays as it is. Under it, one line per **named** field from the byte map, then one
line that lists the unknown offsets:

```text
Current preset  (TANK-Gv2, firmware 96)   type 4 @ 0x10000000, 21 bytes
  00: 01 00 00 01 0f 04 3c 3c 46 32 32 00 00 00 00 05
  10: 04 07 43 16 43
      [6]  knob (which one: unknown)   60      0–127      observed
      [15] reverb decay                 5      0–127      observed
      [16] reverb mix                   4      0–127      hypothesis ?
      [17] IR cab                      #7      selector   hypothesis ?
      unknown: 0 1 2 3 4 5 7 8 9 10 11 12 13 14 18 19 20
```

Rules:

- Columns: `[offset]` (or `[offset.mask]` for flags, e.g. `[1.0x04]`), label, display value,
  range/encoding, confidence.
- `hypothesis` rows end with ` ?` (visually distinct, FR-016).
- Out-of-range values: display shows the raw value followed by `  OUT OF RANGE` (FR-015).
- With `firmware_untested`, the region header ends with `  (decoded with the fw 96 map)` (FR-018).
- `info` adds the same lines under the Global and Status blocks. Device info stays undecoded.

JSON: each region's `fields[]` items gain additive keys (see
[`decoded-field.schema.json`](decoded-field.schema.json)), and each region gains
`"map_firmware": 96` and `"unknown_offsets": [...]`. `schema_version` stays `1` until the M4
release, which bumps it to `2` for the field renames listed in the CHANGELOG (research R8).

## `openvave watch`

Connect → handshake → poll `GLOBAL`, `CURRENT_PRESET`, `STATUS` every `--interval` →
print/record changes → stop → disconnect. Read-only: only `0x11` and `0x23` are ever sent.

| Option | Default | Meaning |
|---|---|---|
| `--interval SECONDS` | `0.5` | Time between cycle starts; minimum `0.2` (usage error, exit 2, below that) |
| `--duration SECONDS` | none | Stop after this long (exit 0) |
| `--record PATH` | `captures/private/<YYYYMMDD-HHMMSS>-watch.jsonl` | Session record file; parent dirs created. A path inside a `captures/` folder but outside `captures/private/` is rejected (usage error, exit 2) |
| `--no-record` | off | Do not write a record (live view only) |
| `--json` | off | **JSON Lines** on stdout, one event per line ([`watch-event.schema.json`](watch-event.schema.json)). This is the documented exception to "one JSON document" |

Global options `--device`, `--scan-timeout`, `--timeout`, `--trace` apply.

### stdin

- Each line typed (trimmed, non-empty) becomes the **current label**, attached to every change
  until the next line.
- A line that is exactly `q` or `quit` stops the watch (exit 0).
- EOF on stdin stops label reading only. Polling continues until Ctrl-C, `q`, or `--duration`.

### Human output (stdout)

```text
Watching TANK-Gv2 (firmware 96), every 0.5 s. Type a label and Enter before each step; q to quit.
Recording to captures/private/20261117-101500-watch.jsonl
  global  00 00 01 01   not in edit mode = on
  preset  01 00 00 01 0f 04 3c 3c 46 32 32 00 00 00 00 05 04 07 43 16 43
  status  01
── label: edit mode on ──
 +3.02s  global[3]   not in edit mode   on → off
── label: reverb decay min→max ──
 +9.51s  preset[15]  reverb decay         5 → 64
+10.02s  preset[15]  reverb decay        64 → 127
── label: reverb mix only ──
+21.50s  preset[16]  reverb mix           4 → 90     (co-moving: 2)
         preset[17]  IR cab              #7 → #8
Stopped after 34.0 s: 4 changes in 3 cycles. Record: captures/private/20261117-101500-watch.jsonl
```

- Each change line: time since start, `region[offset]`, field label (or `unknown`), old → new
  in the field's display form (raw hex for unknown bytes).
- Two or more bytes changed in one cycle: the time is printed once, and the first line carries
  `(co-moving: N)` (FR-005).
- No heartbeat lines when nothing changes.
- stderr hint (once): `hint: no preset byte changed in 30 s and the pedal is not in edit mode`
  when a label was typed, global[3] reads "not in edit mode", and no preset byte changed since.

### Exit codes

As in 001, plus: 0 on `q` / Ctrl-C / `--duration`. A connection lost during polling → 6 and a
protocol error → 7. In both cases the record is complete up to the failure and ends with a
`stop` event.
