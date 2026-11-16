# Research: Preset and global byte map (read-only decoding)

Phase 0 for [plan.md](plan.md). Technical Context had no open `NEEDS CLARIFICATION` items. The
spec clarifications settled scope (watch command, `confirmed` bar, completion bar). The items
below record the design decisions that follow from them.

## R1. Single source of truth for the byte map

- **Decision**: the byte map table in `specs/protocol/command-layer.md` is authoritative. The
  code table `openvave.protocol.bytemap.BYTE_MAP` is kept by hand to match it, and
  `tests/unit/test_bytemap_doc.py` parses the doc table and fails on any difference. The doc
  table uses fixed columns:
  `Region | Offset | Mask | Name | Encoding | Range | Control | Confidence | Firmware | Evidence | Notes`.
  `Name` is the stable machine name (snake_case) in backticks; `Mask` is `—` for whole-byte
  fields; unknown bytes have Encoding `unknown` and Name `—`.
- **Rationale**: Constitution I (docs first, same PR) and SC-007 (a third party decodes from the
  doc alone). The test makes drift impossible to merge.
- **Alternatives**: generate code from Markdown at build time (adds a build step and a parser
  as a runtime concern); keep a YAML/JSON map file and render the doc from it (the doc would
  stop being hand-written findings, and contributors edit two places anyway).

## R2. Field encodings

- **Decision**: a closed set of encodings, each with its own rendering and range check:
  - `continuous` — integer `min..max` (knobs: 0–127 observed so far);
  - `switch` — on/off, with the raw value meaning "on" (and "off") stated;
  - `selector` — index `min..max`, with optional labels in our own words;
  - `flag` — a single bit selected by `mask` (for bytes that pack several switches);
  - `index` — a 0- or 1-based position (status byte if it is the preset number);
  - `unknown` — no meaning; raw value only.
  Fields are 1 byte or a bit within 1 byte. Multi-byte fields are not modelled until one is
  observed (YAGNI).
- **Rationale**: covers every control kind the spec names (knobs, selectors, switches, edit
  flag, preset index) and gives FR-015 a precise "out of range" meaning per encoding.
- **Alternatives**: free-form value strings (not testable); arbitrary bit-width fields (no
  evidence yet).

## R3. Watch polling uses the existing read path

- **Decision**: `TankG.watch()` loops over `TankG.read()` for `GLOBAL`, `CURRENT_PRESET` and
  `STATUS` (in that order, matching the app's connect order minus device info), once per
  interval, on the already-open connection. The device-info block is not polled (its bytes
  20–21 echo the previous reply; spec edge case).
- **Rationale**: no new frame type, region or address. The 001 guarantees (allowlist, closed
  enum, one request in flight, timeouts) apply unchanged, and the SC-004 audit covers `watch`
  for free.
- **Alternatives**: a raw-frame poller in the CLI (bypasses the session's checks); polling only
  the region that changed most recently (misses co-moving bytes in other regions).

## R4. Interval

- **Decision**: default `--interval 0.5` s between cycle starts, minimum 0.2 s. If a cycle takes
  longer than the interval, the next one starts right away (no backlog, no overlap).
- **Rationale**: a cycle of 3 reads takes ≈ 0.15–0.3 s at the observed 40–90 ms reply latency.
  0.5 s catches the ends of a knob sweep (spec FR-003 asks for ≥ 2 reads/s). The app polls the
  global block at ~1 Hz without trouble.
- **Alternatives**: back-to-back reads with no sleep (no benefit beyond catching intermediate
  values, which the spec does not need; more radio traffic).

## R5. Session record format

- **Decision**: the record is a JSONL file in the existing capture format (`captures/README.md`).
  It has a `meta` first line (firmware, device name, platform, ATT MTU, date, tool
  `openvave watch`, interval), then the handshake and every `tx`/`rx` frame with labels
  `global`, `preset`, `status`, plus two new event types:
  - `label` — `{t, event:"label", text}` when the owner types a line;
  - `change` — `{t, event:"change", region, offset, old, new, label}`, one per changed byte.
  Each event is written and flushed as it happens (FR-004). The default path is
  `captures/private/<YYYYMMDD-HHMMSS>-watch.jsonl`, and `--record PATH` overrides it.
  `--record` refuses a path inside the repository's `captures/` folder unless it is under
  `captures/private/`, to avoid committing raw records by accident.
- **Rationale**: a contiguous slice of a record (meta + handshake + the reads before and after
  one step) is already a valid capture. `FakeTransport.from_capture` replays it, so fixtures
  need no conversion step (FR-020). Preset/global/status bytes and the handshake payload
  (`TANK-Gv2_096`) hold no identifiers. Excerpts therefore need no byte replacement, only the
  owner's label text reviewed (personal preset names must not leak, Constitution VI).
- **Size**: ≈ 6 frames per 0.5 s cycle, ≈ 120 bytes per JSON line → ≈ 5 MB/hour. Acceptable for
  private files.
- **Alternatives**: store only changes (excerpts could not be replayed as fixtures); a new
  binary format (no tooling, against "boring plumbing").

## R6. Fixture pairs for decoder tests

- **Decision**: each mapped field gets one committed excerpt
  `captures/fw96/<date>-step-<field>.jsonl` holding the `label` event, the reads just before the
  step and the read where the control reached its extreme. `tests/integration/test_fixture_pairs.py`
  is parametrised over a small index (field name → fixture, labels of the before/after reads).
  It asserts that decoding "after" vs "before" changes exactly that field (SC-004), and that the
  values match the documented range ends where the owner swept min → max.
- **Rationale**: Constitution III (tests from real bytes, written before the map row). It also
  makes SC-004 mechanical.
- **Alternatives**: one big fixture per session (hard to review, slow tests); synthetic byte
  pairs (forbidden by Constitution III).

## R7. Watch output

- **Decision**:
  - Human (default), stdout: a start line with the initial decoded state of the three regions,
    then one line per changed byte:
    `+12.34s  preset[15]  reverb decay   5 → 127   « reverb decay min→max »`.
    Several bytes changed in one cycle print under one shared timestamp, marked `(co-moving: 2)`
    (FR-005). Labels typed by the owner are echoed as `── label: … ──`. No heartbeats.
    Diagnostics stay on stderr. A one-line hint goes to stderr when preset bytes have not
    changed for 30 s while global byte 3 says "not in edit mode" after a label was typed (the
    "forgot edit mode" edge case).
  - `--json`: **JSON Lines**, one object per event (`start`, `label`, `change`, `stop`),
    validated by `watch-event.schema.json`. This is the one documented exception to 001's
    "exactly one JSON document on stdout", because `watch` streams.
- **Rationale**: a researcher reads the human stream live, and scripts consume the JSON Lines.
  The record file (R5) remains the evidence.
- **Alternatives**: a full-screen TUI (dependency, harder to log); printing all 26 bytes every
  cycle (noise hides the change).

## R8. JSON compatibility and the schema bump

- **Decision**: during M0–M3 only additive changes are made under `schema_version` 1. The new
  per-field keys are `raw`, `mask`, `encoding`, `range`, `display`, `out_of_range`, and each
  region gets `map_firmware`. The existing `value` keeps its meaning (the raw integer of the
  byte, masked for flags). Field names are part of the contract: renaming a provisional name
  (e.g. `knob_unknown`) or refuting a field counts as a breaking change. Those
  changes are collected and released once in M4 as `schema_version` 2, with a CHANGELOG
  table old → new.
  New fields added at `hypothesis` level get neutral names that describe the byte's behaviour
  (e.g. `preset_byte_6_knob`) until they are `observed`, to limit later renames.
- **Rationale**: 001 FR-016a, and spec FR-017. Main stays unreleased between milestones, so
  one bump per release avoids a version per PR.
- **Alternatives**: bump on every rename (several versions inside one feature); treat field
  names as non-contractual (scripts would break silently).

## R9. Testing `watch` without hardware

- **Decision**: `FakeTransport` gains ordered replay. When a capture (or script) has several
  `rx` events for the same request label, replies are served in order, and the last one
  repeats once the list is exhausted. `TankG.watch()` takes an injectable `sleep` (default
  `asyncio.sleep`) so tests run instantly and deterministically. The stdin label reader is
  fed an in-memory stream in CLI contract tests.
- **Rationale**: same fake, same capture format. Excerpts from real sessions drive the watch
  tests too.
- **Alternatives**: monkeypatching time globally (brittle); a separate `SequenceTransport`
  (duplicates split/drop/disconnect logic).

## R10. Stopping `watch`

- **Decision**: `watch` stops on Ctrl-C (SIGINT), on a stdin line that is exactly `q` or
  `quit`, or after `--duration SECONDS`; in all three cases it exits 0 and writes a `stop`
  event. End of input on stdin stops label reading but not polling, so `watch < /dev/null`
  with `--duration` works in scripts. Connection loss writes `stop` with the error and exits
  with the 001 code (6 / 7). Labels are read with a background thread
  (`asyncio.to_thread(readline)`), which works on Windows too (no `add_reader`).
- **Rationale**: spec Story 1 scenario 4 (the record is saved whatever ends the session, and
  the pedal disconnects cleanly). `TankG.__aexit__` already closes the transport on any exit.
- **Alternatives**: raw-mode single-key commands (platform-specific terminal handling).

## R11. No new dependencies

- **Decision**: none. JSON Lines, threads for stdin, Markdown table parsing (simple split on
  `|`) are all standard library.
- **Rationale**: Constitution VII.

## R12. Firmware other than 96

- **Decision**: decoding always applies the fw-96 map. Each decoded region carries
  `map_firmware: 96`. Human output adds `(decoded with the fw 96 map)` to region headers when
  `firmware_untested` is true (FR-018). `watch` warns once on stderr, as `info` does.
- **Rationale**: consistent with 001 clarification Q1 (warn and continue, never refuse a read).

## R13. Control inventory and naming

- **Decision**: the first M2 session starts by having the owner list every physical control
  (as printed on the pedal, plus footswitches and modes). The list goes into `command-layer.md`
  as a "Control inventory" table: name in our own words, kind (continuous / selector / switch
  / mode), whether it needs edit mode, and the mapped offset(s) or "no change". Map `Name`
  values derive from it.
- **Rationale**: SC-001 is measured against this list. The spec deliberately does not presume
  the controls.

## Open items carried into implementation

- The exact number and names of controls: known only after the owner's inventory (M2).
- Whether any byte is a bit field: decided from evidence; R2's `flag` encoding is ready if so.
- How the status byte relates to presets: decided in M3.
