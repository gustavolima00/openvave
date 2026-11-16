# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.2.0]

Every byte of the current preset, global settings and status regions is mapped or explicitly
unknown, and a new `openvave watch` command maps the pedal one control at a time. Still
**read-only**: only the handshake query (`0x11`) and region reads (`0x23`) are ever sent.

### Breaking

- JSON output is now `schema_version` 2 (`info`, `preset dump`, `watch --json`). Two field names
  changed:

  | 0.1.0 name | 0.2.0 name | Why |
  |---|---|---|
  | `knob_unknown` | `gain` | Preset byte 6 is the gain knob (one knob at a time, two sessions) |
  | `not_in_edit_mode` | `mode` | Global byte 3 is a three-state mode selector: `0` edit, `1` normal, `2` tuner. The tuner value refutes the 0.1.0 edit-mode on/off reading |

  `value` keeps its meaning (the raw byte). For `mode`, `display` reads `edit` / `normal` /
  `tuner`.

### Added

- `openvave watch`: polls global, current preset and status (default every 0.5 s, minimum
  0.2 s) and prints each byte that changes, with the field it belongs to. Type a label and Enter
  before each step to tag the changes; `q` stops. Options `--interval`, `--duration`,
  `--record PATH`, `--no-record`, `--json` (JSON Lines,
  [`watch-event.schema.json`](specs/002-preset-byte-map/contracts/watch-event.schema.json)).
  Every session is recorded by default to `captures/private/<date>-watch.jsonl` (git-ignored)
  in the [capture format](captures/README.md).
- A byte map of all 26 bytes (global 0–3, preset 0–20, status 0), mirrored from
  [`command-layer.md`](specs/protocol/command-layer.md) and checked against it by the test suite.
  Named: browsed bank, bank, slot, mode; amp/mod/delay/reverb block on/off, noise gate, amp
  type, gain, treble, middle, bass, volume, mod fx, mod speed, delay mix, delay time, reverb
  decay, reverb mix, IR cab. Unknown: preset 18–20 and status 0.
- `preset dump` and `info` print one decoded line per named field (value, range, confidence;
  ` ?` on hypotheses, `OUT OF RANGE` when a byte leaves its documented range) and an `unknown:`
  line. On firmware other than 96 the header says `(decoded with the fw 96 map)`.
- JSON `fields[]` items gain `raw`, `mask`, `encoding`, `range`, `display`, `interpreted`,
  `out_of_range`
  ([`decoded-field.schema.json`](specs/002-preset-byte-map/contracts/decoded-field.schema.json));
  each region gains `map_firmware` and `unknown_offsets`.
- Library: `TankG.watch()`, `openvave.protocol.decode_region()` / `diff()` / `BYTE_MAP` /
  `MAP_FIRMWARE`, and the types `Encoding`, `ByteMapEntry`, `DecodedField`, `DecodedRegion`,
  `ByteChange`, `WatchStart`, `WatchChange`
  ([library contract](specs/002-preset-byte-map/contracts/library-api.md)).
- `FakeTransport` serves several replies to the same request in order (the last one repeats),
  so a recorded watch session replays as it happened.

### Changed

- Confidence: preset 0–17 and global 3 are `confirmed` (two independent sessions each), global
  0–2 `observed`. `reverb_mix` and `ir_cab`, hypotheses in 0.1.0, are confirmed.
- `ir_cab` and `amp_type` are selectors with 9 positions (0–8).

### Deprecated

- `openvave.models.KNOWN_FIELDS` and `FieldSpec`: thin aliases derived from `BYTE_MAP`, so they
  carry the 0.2.0 names. Use `openvave.protocol.BYTE_MAP` and `ByteMapEntry`. They will be
  removed before 1.0.

### Tested

- Firmware 96 on macOS 26, including `watch` on hardware (seven sessions, 2026-11-16).

## [0.1.0]

First release: a **read-only** BLE client for the M-VAVE Tank-G.

### Added

- `openvave info`: finds the pedal, runs the handshake and reads the device info, global settings,
  current preset and status regions.
- `openvave preset dump`: reads the 21-byte current preset buffer and prints it with offsets and
  confidence-labelled fields (`confirmed` / `observed` / `hypothesis`).
- `--json` output for both commands, `schema_version` 1
  ([`info`](specs/001-readonly-ble-connection/contracts/info.schema.json),
  [`preset dump`](specs/001-readonly-ble-connection/contracts/preset-dump.schema.json)).
- Global options `--device`, `--scan-timeout`, `--timeout`, `--trace` (hex of every frame on stderr).
- Exit codes 0–7 as a public contract
  ([CLI contract](specs/001-readonly-ble-connection/contracts/cli.md#exit-codes)).
- Python library: `TankG` (`connect()`, `over()`, `read()`, `snapshot()`), `discover()`, typed
  models and errors, and `FakeTransport` for testing without a pedal
  ([library contract](specs/001-readonly-ble-connection/contracts/library-api.md)).
- Safety: only the handshake query (`0x11`) and region reads (`0x23`) can be encoded; every other
  command byte raises `UnsafeCommandError`.

### Tested

- Firmware 96 on macOS 26. Other firmware versions work with a `warning:` on stderr. Linux and
  Windows are untested on hardware.
