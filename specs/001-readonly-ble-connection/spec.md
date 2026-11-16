# Feature Specification: Read-only BLE connection to the Tank-G

**Feature Branch**: `001-readonly-ble-connection`

**Created**: 2026-11-16

**Status**: Draft

**Input**: User description: "Read-only connection to the M-VAVE Tank-G over BLE: discover and connect to the pedal, perform the name/firmware handshake, and read device info, global settings, current preset and status, exposed as a library and a CLI (`info`, `preset dump`) with human-readable and JSON output. No write operations."

**Protocol source of truth**: [`specs/protocol/ble-gatt.md`](../protocol/ble-gatt.md) and
[`specs/protocol/command-layer.md`](../protocol/command-layer.md). Only behaviour marked
`confirmed` there is in scope. Anything this spec relies on that is not yet `confirmed` is
called out explicitly.

## Clarifications

### Session 2026-11-16

- Q: Behaviour when the handshake reports a firmware version other than 96? → A: Warn on stderr and continue; JSON output carries `firmware_untested: true`.
- Q: Source of test fixtures? → A: Commit sanitized raw frames from the fw-96 probe capture under `captures/` first; derive all fixtures (incl. mutated negative cases) from them.
- Q: Which OSes need real-pedal verification for v1? → A: macOS verified; Linux and Windows best-effort, documented as untested on hardware.
- Q: Stability of `--json` output? → A: Versioned schema (`schema_version`); additive fields don't bump it, renames/removals do; raw hex always included.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Identify a connected pedal (Priority: P1)

A Tank-G owner runs `openvave info` with the pedal powered on nearby. The tool finds the
pedal, connects, performs the name/firmware handshake and prints the device name and firmware
version (for example `TANK-Gv2`, firmware `96`), then disconnects. With `--json` the same
facts come out as a machine-readable document for scripts.

**Why this priority**: It is the smallest end-to-end slice that proves discovery, connection,
framing, checksum validation and reply parsing all work. Every later feature (preset decoding,
writes, backups) depends on it.

**Independent Test**: With a fake transport replaying the recorded handshake reply, the library
returns name `TANK-Gv2` and firmware `96`; the CLI prints them in both output formats. On real
hardware (opt-in), `openvave info` against a fw-96 pedal shows the same values.

**Acceptance Scenarios**:

1. **Given** one Tank-G advertising nearby, **When** the user runs `openvave info`, **Then** the
   tool connects, sends only the name/version query and the confirmed read requests, prints the
   device name and firmware version, disconnects, and exits with status 0.
2. **Given** the same pedal, **When** the user runs `openvave info --json`, **Then** stdout
   contains a single valid JSON document with at least the device name and firmware version,
   and nothing else is written to stdout.
3. **Given** no Tank-G is advertising, **When** the user runs `openvave info`, **Then** the tool
   gives up after a bounded scan time, prints a clear "no pedal found" message on stderr and
   exits non-zero.
4. **Given** the pedal's handshake reply has an invalid checksum or does not arrive, **When** the
   handshake is attempted, **Then** the tool retries (up to 3 attempts, as the official app does)
   and, if all attempts fail, reports a handshake error on stderr and exits non-zero.

---

### User Story 2 - Read device state: info block, global settings and status (Priority: P2)

The same `openvave info` command also reads the device-info block, the global settings block and
the status byte that the official app reads on connect, and shows them. Because the meaning of
most of these bytes is still unknown, they are shown as raw bytes with offsets, clearly labelled
as undecoded, alongside any field whose meaning is documented.

**Why this priority**: These reads are confirmed on hardware and are what the app does on every
connect; surfacing them gives reverse-engineers a scriptable way to observe the device (e.g. the
global "edited" flag hypothesis) without the app.

**Independent Test**: With a fake transport replaying the recorded replies for the device-info,
global and status reads, the library returns exactly the recorded data bytes and the CLI renders
them in both formats.

**Acceptance Scenarios**:

1. **Given** a connected fw-96 pedal (or the recorded replies), **When** `openvave info` runs,
   **Then** it shows the 32-byte device-info block, the 4-byte global block (`00 00 01 01` in the
   recording) and the 1-byte status (`01` in the recording).
2. **Given** a field whose meaning is only `hypothesis` or `observed` in the protocol docs,
   **When** it is displayed, **Then** the output labels it with that confidence level and never
   presents it as a fact.
3. **Given** `--json`, **When** `info` runs, **Then** each region is present with its raw bytes
   (as hex) so that scripts can diff successive reads.

---

### User Story 3 - Dump the current preset (Priority: P3)

A user runs `openvave preset dump` to see the 21-byte current/edit preset buffer the pedal holds.
The output shows every byte with its offset, marks the known-unknown bytes as unknown, and in
JSON gives the raw bytes for further analysis or comparison with other dumps.

**Why this priority**: It is the read side of preset handling and the primary tool for the next
reverse-engineering step (mapping knobs to preset bytes by moving one control at a time and
re-dumping). It is not needed to prove connectivity, hence P3.

**Independent Test**: With a fake transport replaying the recorded preset reply
(`01 00 00 01 0f 04 3c 3c 46 32 32 00 00 00 00 05 04 07 43 16 43`), the library returns those
21 bytes and the CLI renders them in both formats.

**Acceptance Scenarios**:

1. **Given** a connected pedal (or the recorded reply), **When** the user runs
   `openvave preset dump`, **Then** the 21 preset bytes are printed with offsets 0–20.
2. **Given** `--json`, **When** `preset dump` runs, **Then** stdout is a single JSON document
   containing the 21 bytes and the firmware version of the device they came from.
3. **Given** the user moves a knob on the pedal between two dumps, **When** they dump again,
   **Then** the new value is visible (the tool re-reads; it does not cache between invocations).

---

### User Story 4 - Use the same capabilities as a library (Priority: P2)

A developer building another tool (a GUI, a MIDI bridge, a test harness) uses the openvave
library directly to discover the pedal, connect, handshake and read the four regions, receiving
structured results and typed errors rather than parsing CLI text. The developer can supply their
own transport (including an in-memory fake) to test their code without a pedal.

**Why this priority**: Constitution V makes the library the product and the CLI a thin layer;
the CLI stories above cannot be built correctly without it.

**Independent Test**: A test plugs a fake transport preloaded with the recorded replies into the
library and asserts on the returned structured values and on the exact request bytes sent.

**Acceptance Scenarios**:

1. **Given** a fake transport preloaded with the recorded replies, **When** the library performs
   the connect sequence, **Then** the request bytes it sends are byte-identical to the documented
   requests (e.g. the query `00 59 11 00 00 00 FF` and the preset read
   `00 59 23 08 00 00 04 00 00 00 10 15 00 00 D6`).
2. **Given** a reply split across several notifications, **When** the library receives it,
   **Then** it reassembles the frame using the length field before validating it.
3. **Given** frame-level hex tracing is enabled, **When** any request/reply is exchanged,
   **Then** every frame sent and received is emitted as hex; tracing is off by default.

---

### Edge Cases

- More than one Tank-G advertising: the tool must not silently pick one in a way the user cannot
  control; it lists candidates or accepts an explicit device identifier.
- Pedal found but connection drops mid-sequence: the operation fails with a clear error and
  non-zero exit; no partial result is presented as complete.
- Reply with wrong checksum, wrong echoed command byte, or echoed type/address/length that does
  not match the request: rejected as a protocol error (never silently accepted).
- Reply never arrives: the operation times out instead of hanging (constitution: timing &
  reliability).
- Unsolicited or unexpected notifications on the response channel: ignored or reported in the
  trace, never mistaken for the reply to a pending request.
- Handshake reports a firmware version other than `96` (the only one observed): see FR-013.
- Bluetooth is off or the OS has not granted Bluetooth permission to the terminal: a specific,
  actionable error message rather than a generic failure.
- The pedal's Classic Bluetooth / A2DP identity (`TANK-Gv2`, no `_BLE` suffix) appears in scans:
  it is not treated as the BLE control endpoint.

## Requirements *(mandatory)*

### Functional Requirements

**Discovery & connection**

- **FR-001**: The system MUST discover Tank-G pedals by their BLE advertisement (local name
  `TANK-Gv2_BLE`, confirmed) and MUST allow the user to target a specific device explicitly.
- **FR-002**: The system MUST connect, locate the vendor command service and its command
  (`ae41`, host → pedal) and response (`ae42`, pedal → host, notify) characteristics, and enable
  notifications on the response characteristic before sending any command.
- **FR-003**: The system MUST disconnect cleanly at the end of every CLI invocation, including on
  error.

**Protocol (read-only subset)**

- **FR-004**: The system MUST encode and decode frames in the confirmed format
  `00 59 | command | length (3 bytes, LE) | body | checksum`, where checksum is the bitwise
  complement of the byte sum of the body, truncated to 8 bits.
- **FR-005**: The system MUST validate every reply (marker, length, checksum, echoed command, and
  for reads the echoed type/address/length) and reject invalid replies with a protocol error.
- **FR-006**: The system MUST reassemble replies that span multiple notifications using the
  length field.
- **FR-007**: The system MUST perform the name/version handshake (query command `0x11`) with up
  to 3 attempts and expose the device name and firmware version parsed from the reply
  (`TANK-Gv2_096` → name `TANK-Gv2`, firmware `96`).
- **FR-008**: The system MUST read, using the read-memory command `0x23`, exactly these regions
  (all confirmed on fw 96): device-info block (type 5, `0xD0000000`, 32 bytes); global settings
  (type 4, `0x20000000`, 4 bytes); current preset (type 4, `0x10000000`, 21 bytes); status
  (type 4, `0xD0000000`, 1 byte).
- **FR-009**: The system MUST time out each request after a bounded wait and report the timeout
  as an error rather than hanging.

**Device safety**

- **FR-010**: The system MUST NOT be able to send any command other than the query (`0x11`) and
  read-memory (`0x23`) commands in this feature. Write (`0x22`), erase (`0x21`), MIDI-over-command
  (`0x15`) and any other command byte MUST NOT be encodable through the public API or CLI.
- **FR-011**: The system MUST NOT read addresses other than those listed in FR-008 by default.
  Arbitrary-address reads, if ever offered, are a separate future decision.
- **FR-012**: The system MUST NOT perform background polling; each CLI command issues only the
  requests it needs and then disconnects.
- **FR-013**: When the handshake reports a firmware version other than `96`, the system MUST
  continue with the (non-destructive) reads, print a warning on stderr naming the reported and
  tested versions, and set `firmware_untested: true` in JSON output (`false` for fw 96). The
  library MUST expose the same flag on its result.

**Library & CLI**

- **FR-014**: All capabilities MUST be available from the library without the CLI; the protocol
  layer MUST work against any transport that implements a minimal send/receive interface,
  including an in-memory fake.
- **FR-015**: The CLI MUST provide `info` (name, firmware, device-info block, global settings,
  status) and `preset dump` (current preset buffer).
- **FR-016**: Every CLI command MUST support human-readable output (default) and JSON output;
  results go to stdout, diagnostics and errors to stderr, and failures exit non-zero with
  distinct exit codes at least for "no device found", "connection/timeout error" and "protocol
  error".
- **FR-016a**: Every JSON document MUST carry a `schema_version`. Adding fields MUST NOT change
  it; renaming, removing or changing the meaning of a field MUST bump it and be recorded in the
  changelog. The raw hex of every region read MUST always be present, so newly decoded fields
  are purely additive.
- **FR-017**: Output MUST present undecoded bytes as raw hex with offsets and MUST label any
  interpreted field with its confidence level from the protocol docs; unknown bytes are shown as
  unknown, never guessed.
- **FR-018**: The library MUST be able to emit a hex trace of every frame sent and received, off
  by default, and the CLI MUST expose a flag to turn it on (to stderr).

**Testing**

- **FR-019**: The default test suite MUST run without a pedal, using fixtures derived from the
  values recorded in `command-layer.md` "First values read from hardware" (fw 96) through a fake
  transport, covering the handshake, all four reads, multi-notification reassembly and each
  rejection case in FR-005.
- **FR-020**: Encoder/decoder tests MUST round-trip the fixture bytes (decode → model → encode
  yields identical bytes) for every request and reply in scope.
- **FR-021**: Tests that need a physical pedal MUST be opt-in and excluded from CI.
- **FR-022**: Test fixtures MUST derive from real on-the-wire bytes: before protocol code is
  written, the request/reply frames of the fw-96 probe
  (`captures/private/20261116-111832-probe.jsonl`) MUST be sanitized (no device MAC, serial or
  personal identifiers) and committed under `captures/` with firmware version, date and source
  recorded, and `command-layer.md` MUST cite them. Negative-case fixtures (bad checksum, wrong
  echo, split notifications, truncation) MUST be produced by documented mutations of those
  captured frames, not written from scratch.

### Out of scope (future specs)

- Any write: write memory (`0x22`), preset change registers (`0xE000000x`), erase (`0x21`).
- Interpreting preset or global bytes beyond what the protocol docs mark as known; preset bank /
  stored-preset reads (36 × 21 B layout).
- MIDI (BLE-MIDI characteristic or command `0x15`) and the Classic Bluetooth A2DP audio path.
- Background polling / watch mode, USB transport, GUI.

### Key Entities

- **Device**: a discovered Tank-G — advertised name, platform-specific identifier, signal
  strength (for disambiguation).
- **Device identity**: result of the handshake — name (`TANK-Gv2`), firmware version (`96`),
  raw 27-byte reply payload.
- **Frame**: one protocol message — command byte, body, checksum; request or reply.
- **Memory region read**: type, address, length and the data bytes returned.
- **Device snapshot**: identity plus the four regions (device-info block, global settings,
  current preset, status) from one connection, with the time they were read.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: With a fw-96 pedal powered on within normal Bluetooth range, `openvave info`
  completes discovery, handshake, reads and disconnect in under 10 seconds in at least 9 of 10
  runs.
- **SC-002**: Values reported by `info` and `preset dump` on a fw-96 pedal match byte-for-byte
  the values the protocol docs record for the same device state.
- **SC-003**: The full default test suite passes on macOS, Linux and Windows machines with no
  Bluetooth hardware at all.
- **SC-004**: An audit of the request bytes produced across the whole test suite finds zero
  frames with a command byte other than `0x11` or `0x23`.
- **SC-005**: Every failure mode listed in Edge Cases ends with an explanatory message on stderr
  and a non-zero exit within the configured timeout — no hangs, no stack traces by default.
- **SC-006**: Two consecutive `--json` runs against an unchanged pedal produce outputs that differ
  only in timestamp fields, so users can diff dumps to locate changed bytes.

## Assumptions

- Only firmware 96 has been observed; all byte-level expectations are for fw 96.
- The pedal is strictly request/response and never pushes data unsolicited (observed); the tool
  does not need to listen for spontaneous updates.
- The four reads the official app performs on connect are safe to repeat (confirmed: they were
  replayed on hardware with identical results and no observable effect).
- The CLI is invoked once per action (connect → work → disconnect); keeping a persistent
  connection between commands is out of scope.
- If several pedals are found and none is specified, the CLI lists them and asks the user to pick
  one via an explicit identifier rather than guessing.
- Frame payload size fits the negotiated MTU for every request in scope (largest request is 15
  bytes); replies may still span notifications and are reassembled.
- Supported platforms: v1 requires hardware verification on macOS only. Linux and Windows are
  best-effort and documented as "untested on hardware" until verified by a contributor; the
  hardware-free test suite runs on all three.
- The protocol docs under `specs/protocol/` are committed before or with this feature; per
  Constitution I, any new protocol finding during implementation updates them in the same PR.
