---

description: "Task list for 001 read-only BLE connection to the Tank-G"
---

# Tasks: Read-only BLE connection to the Tank-G

**Input**: Design documents from `specs/001-readonly-ble-connection/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md),
[data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: MANDATORY here. Constitution III requires capture-based fixture tests for every
encoder/decoder/parser, written before the implementation and failing first; spec FR-019–FR-022
require a hardware-free suite with opt-in hardware tests. Every test task below precedes the
implementation it covers.

**Organization**: one milestone per PR. Milestone 0 is shared setup + foundation; Milestones 1–4
map to user stories in priority order (US1 P1 → US2 P2 → US4 P2 → US3 P3). Polish ships in the
last PR.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1–US4 from spec.md
- Paths are relative to the repository root (single Python package, `src/` layout — plan.md)

## Global rules for every task

- Only command bytes `0x11` and `0x23` may ever be encoded (FR-010, research R10). No task adds a
  write, erase, raw-send or address-based read API.
- Fixtures come only from `captures/` via `tests/support/captures.py`; negative cases only via
  `tests/support/mutations.py` (FR-022). Never hand-type a reply frame in a test.
- Hex format everywhere (captures, trace, JSON): lowercase, space-separated bytes.
- Hardware tests live in `tests/hardware/`, are marked `@pytest.mark.hardware`, and run only with
  `--hardware`.

---

## Delivery Plan

| PR | Milestone | Stories | Tasks | Gate |
|---|---|---|---|---|
| 1 | Milestone 0 — Evidence, scaffold & protocol core | — (blocks all) | T001–T024 | CI green on Linux/macOS/Windows; round-trip of all captured frames |
| 2 | Milestone 1 — Identify a connected pedal (US1) 🎯 MVP | US1 | T025–T036 | `openvave info` shows `TANK-Gv2` / fw 96 on macOS hardware |
| 3 | Milestone 2 — Read device state (US2) | US2 | T037–T043 | `info` shows all regions; JSON validates `info.schema.json` |
| 4 | Milestone 3 — Library usage (US4) | US4 | T044–T048 | Public API contract test + documented snippet run against `FakeTransport` |
| 5 | Milestone 4 — Dump the current preset (US3) + Polish | US3 | T049–T060 | `preset dump` on hardware; full quickstart passes |

Projected PR count: **5** (≤ 8). Tasks inside a milestone are commits in that PR. Milestone N+1
starts only after Milestone N's gate passes.

---

## Milestone 0 — Evidence, scaffold & protocol core (Setup + Foundational)

**Goal**: committed, sanitized evidence; an installable package with CI; the pure frame codec,
reassembler, read/query commands, models, errors, transport interface, fake transport and trace —
everything every story needs.

**Independent test criteria**:
- `uv run pytest` passes on a machine with Bluetooth disabled.
- Each of the 5 captured requests encodes byte-identically, and each of the 5 captured replies
  decodes → re-encodes byte-identically.
- Encoding command `0x22`, `0x21`, `0x15` (or any byte other than `0x11`/`0x23`) raises
  `UnsafeCommandError`.

**⚠️ CRITICAL**: no user-story work starts until this milestone's gate passes.

### Evidence (Constitution I, II, VI)

- [X] T001 Verify `specs/protocol/ble-gatt.md` and `specs/protocol/command-layer.md` are committed on this branch (they were uncommitted in the main checkout when the plan was written); if missing, stop and get them committed via `docs/constitution-v1` before continuing
  - *Done 2026-11-16*: missing on this branch; copied unchanged from the main checkout and committed here (`docs(protocol): …`). The copies in the main checkout are still uncommitted on `docs/constitution-v1`.
- [X] T002 Perform the research R7 check: compare device-info bytes 19–21 (`b7 43 f3`, from `captures/private/20261116-111832-probe.jsonl`) against the pedal's BLE and Classic Bluetooth MAC addresses and any serial number; record the outcome (match / no match, without writing the MAC itself) as a note in `captures/README.md`
- [X] T003 Create `captures/fw96/20261116-probe-connect.jsonl` from `captures/private/20261116-111832-probe.jsonl`: first line a `{"event": "meta", ...}` record with `firmware: 96`, `platform: "macOS"`, `att_mtu: 185`, `date: "2026-11-16"`, `tool: "probe_readonly (POC)"`, `sanitized: [...]`; then the 15 `tx`/`rx-chunk`/`rx` events unchanged, except that if T002 found a match, devinfo bytes 19–21 become `00 00 00` with the frame checksum recomputed and `sanitized: ["devinfo[19:22]"]`
- [X] T004 [P] Write `captures/README.md`: JSONL schema (`t`, `event` ∈ meta/tx/rx-chunk/rx, `label`, `hex`, `cmd`), the meta record fields, sanitization rules (Constitution VI: no MAC/serial/account/personal preset names; raw captures stay in git-ignored `captures/private/`), and the T002 outcome
- [X] T005 [P] Update `specs/protocol/command-layer.md`: cite `captures/fw96/20261116-probe-connect.jsonl` as the evidence for frame format, `0x11` and `0x23`; state that multi-notification reassembly remains `observed` (every reply in the capture fit in one notification at MTU 185)

### Scaffold

- [X] T006 Create `pyproject.toml`: name `openvave`, MIT, `requires-python = ">=3.11"`, description and README text containing "Unofficial. Not affiliated with or endorsed by M-VAVE / Cuvave", runtime dependency `bleak>=0.22`, dev dependency group `pytest`, `pytest-asyncio`, `jsonschema`, `ruff`, `mypy`; hatchling build backend; `[project.scripts] openvave = "openvave.cli:main"`; `[tool.pytest.ini_options]` with `asyncio_mode = "auto"`, `testpaths = ["tests"]`, marker `hardware`; `[tool.ruff]` (line length 100, rules E,F,I,UP,B); `[tool.mypy] strict = true` for `src/`
- [X] T007 [P] Create package skeleton per plan.md: `src/openvave/__init__.py` (`__version__ = "0.1.0"`), `src/openvave/__main__.py` (calls `openvave.cli.main()`), `src/openvave/py.typed`, empty `src/openvave/protocol/__init__.py`, `src/openvave/transport/__init__.py`, `src/openvave/cli/__init__.py` (stub `main()` returning 0)
- [X] T008 [P] Create `.github/workflows/ci.yml`: matrix `ubuntu-latest`, `macos-latest`, `windows-latest` × Python 3.11 and 3.13; steps `uv sync`, `uv run ruff check`, `uv run ruff format --check`, `uv run mypy src`, `uv run pytest` (never `--hardware`)
- [X] T009 [P] Create `tests/conftest.py` with a `--hardware` command-line option; tests marked `hardware` are skipped unless it is given

### Fixture support (tests first)

- [X] T010 [P] Write `tests/unit/test_captures.py`: loading `captures/fw96/20261116-probe-connect.jsonl` yields a meta record with firmware 96 and exactly 5 request/reply pairs keyed by label; every `tx` and `rx` frame has marker `00 59`, a length field matching its size and a valid checksum `(~sum(body)) & 0xFF`; no committed capture contains a 6-byte MAC-like pattern in `meta` or `label` fields
- [X] T011 [P] Write `tests/unit/test_mutations.py`: each helper changes only what it claims — `flip_checksum`, `set_command(b)`, `set_echo(type=, address=, length=)` (recomputes checksum), `with_payload(bytes)` (recomputes length + checksum), `truncate(n)`, `split(frame, n)` (n chunks concatenating to the original)
- [X] T012 Implement `tests/support/__init__.py`, `tests/support/captures.py` (`load_capture(path) -> Capture` with `.meta`, `.pairs: dict[label, (tx: bytes, rx: bytes)]`, `.ordered_tx`) and `tests/support/mutations.py` until T010–T011 pass

### Protocol core (tests first — Constitution III)

- [X] T013 [P] Write `tests/unit/test_frame.py`: `encode_frame(0x11, b"")` == `00 59 11 00 00 00 ff`; the 4 captured read requests encode byte-identically from their (command, body); each captured reply decodes to (command, body) and re-encodes identically; rejections via mutations with reason codes `bad_marker`, `length_mismatch`, `bad_checksum`; parametrised over all 256 command bytes: only `0x11` and `0x23` encode, all others raise `UnsafeCommandError`
- [X] T014 [P] Write `tests/unit/test_assembler.py`: captured replies fed as one chunk, as `split(n)` for every n from 2 to len(frame), and two frames concatenated in one chunk all yield the original frames in order; a chunk not starting with `00 59` while empty is reported as stray; `reset()` discards a partial frame
- [X] T015 [P] Write `tests/unit/test_commands.py`: `build_query()` and `build_read(Region.X)` for all four regions equal the captured requests; `parse_read_reply(region, frame)` on captured replies returns `RegionRead` with the recorded data; mutations produce `wrong_command`, `echo_mismatch` (type, address and length separately) and `short_data`
- [X] T016 [P] Implement `src/openvave/errors.py` per data-model.md: `OpenvaveError` base; `NoDeviceFoundError`, `MultipleDevicesError(candidates)`, `BluetoothUnavailableError`, `ConnectionLostError`, `RequestTimeoutError`, `ProtocolError(reason)`, `HandshakeError`, `UnsafeCommandError`; each with an `exit_code` class attribute matching contracts/cli.md (3, 4, 5, 6, 6, 7, 7, 1)
- [X] T017 [P] Implement `src/openvave/models.py` per data-model.md: `Region` enum (type, address, length for DEVICE_INFO/GLOBAL/CURRENT_PRESET/STATUS), frozen dataclasses `RegionRead`, `DeviceInfo`, `DeviceIdentity`, `DeviceSnapshot`, and `KNOWN_FIELDS: dict[Region, list[FieldSpec]]` with exactly the documented entries (GLOBAL offset 3 `edited_flag` hypothesis; CURRENT_PRESET offset 6 `knob_unknown` observed)
- [X] T018 Implement `src/openvave/protocol/frame.py` (`ALLOWED_COMMANDS`, `encode_frame`, `decode_frame`, `checksum`) until T013 passes
- [X] T019 Implement `src/openvave/protocol/assembler.py` (`FrameAssembler.feed(chunk) -> list[bytes]`, `.reset()`, stray-chunk reporting) until T014 passes
- [X] T020 Implement `src/openvave/protocol/commands.py` (`build_query`, `build_read(region)` — accepts only `Region`, `parse_read_reply`) and re-export the codec API from `src/openvave/protocol/__init__.py` until T015 passes

### Transport interface, fake transport, trace, safety audit

- [X] T021 [P] Write `tests/unit/test_fake_transport.py`: `FakeTransport.from_capture(path)` answers each captured request with its captured reply (via `on_notify`), records every written frame in `.sent`; options `split=n` (deliver replies in n chunks), `drop={label: count}` (no reply for the first k matching requests), `disconnect_after=k`, `replies={label: bytes}` override; an unknown request raises `AssertionError` in the test
- [X] T022 Implement `src/openvave/transport/__init__.py` (`Transport` Protocol per contracts/library-api.md) and `src/openvave/transport/fake.py` (including its own capture-JSONL parsing for `from_capture`, so library users need nothing from `tests/`) until T021 passes
- [X] T023 [P] Implement `src/openvave/trace.py` (logger `openvave.trace`, `trace_tx(frame)`, `trace_rx_chunk(chunk)`, `trace_rx(frame)` emitting `TX …`/`RX …` at DEBUG) with `tests/unit/test_trace.py` asserting the line format and silence when no handler is attached
- [X] T024 Add the SC-004 audit to `tests/conftest.py`: a session-scoped autouse fixture that wraps `FakeTransport.write`, collects every frame written across the whole run and fails the session if any frame's command byte (offset 2) is not `0x11`/`0x23`

### Live verification (milestone gate)

- Push the PR; CI green on all 6 matrix jobs (ruff, format, mypy, pytest).
- Reviewer confirms the T002/T003 sanitization decision in `captures/README.md`.
- `uv run pytest -q` locally with Bluetooth turned off: all pass, no hardware tests collected.

**Gate evidence (2026-11-16, macOS 26 / Darwin 25.5, local)**:

- [X] `uv run ruff check`, `uv run ruff format --check`, `uv run mypy src` (strict): clean on
  Python 3.13.12 and 3.11.13.
- [X] `uv run pytest -q`: **373 passed** on 3.13.12 and 3.11.13; `tests/hardware` collects
  nothing; `bleak` is never imported by the suite (checked via `sys.modules`), so it is
  hardware-free by construction. Bluetooth was not physically switched off for this run.
- [X] Round-trip: all 10 captured frames (5 tx, 5 rx) decode → re-encode byte-identically; the
  4 read requests and the query encode identically from (command, body); every split of every
  reply reassembles.
- [X] Allowlist: all 256 command bytes tested; only `0x11`/`0x23` encode, the rest raise
  `UnsafeCommandError`. SC-004 audit verified to fail the session on a `0x22` write
  (temporary test, removed).
- [ ] CI green on all 6 matrix jobs — pending: branch not pushed yet.
- [ ] Reviewer confirms the R7 sanitization decision (no MAC match → bytes unchanged) in
  `captures/README.md` — pending review.

**Checkpoint**: Milestone 0 DONE — pending CI run and reviewer sign-off (local gate passed)

---

## Milestone 1 — Identify a connected pedal (US1, P1) 🎯 MVP

**Goal**: `openvave info` finds the pedal, performs the handshake and prints name + firmware
(human and JSON), with correct errors and exit codes.

**Independent test criteria**:
- Over `FakeTransport.from_capture(...)`, the session reports identity `TANK-Gv2` / firmware 96 /
  `firmware_untested = false`, and the first frame sent is `00 59 11 00 00 00 ff`.
- Two dropped handshake replies then a good one → success with 3 queries sent; three dropped →
  `HandshakeError`, exit 7.
- `openvave info --json` (fake transport) prints one JSON document containing `schema_version: 1`
  and the identity; on any failure stdout is empty and the exit code matches contracts/cli.md.

### Tests for User Story 1 (write first, must fail)

- [X] T025 [P] [US1] Write `tests/unit/test_identity.py`: `parse_identity` on the captured handshake payload → name `TANK-Gv2`, firmware 96, `firmware_untested` False; payload rewritten to `TANK-Gv2_097` via `with_payload` → firmware 97, `firmware_untested` True; payload of wrong length, without `_`, with non-numeric version, or non-ASCII → `ProtocolError("bad_identity")`
- [X] T026 [P] [US1] Write `tests/unit/test_discovery.py` for the pure `select_device(found, wanted_id)` function: zero matches → `NoDeviceFoundError`; one → that device; two without `wanted_id` → `MultipleDevicesError` listing both; `wanted_id` given → that device even if its name differs; advertisement name `TANK-Gv2` (Classic identity, no `_BLE`) is never matched by the name filter
- [X] T027 [P] [US1] Write `tests/integration/test_session_handshake.py` over `FakeTransport`: identity from capture; `drop={"query name/version": 2}` → success, 3 query frames in `.sent`; `drop=…: 3` → `HandshakeError`; first reply with `flip_checksum` then good → success on retry; no reply ever with `timeout=0.1` → raises within 1 s; fw-97 reply → warning on logger `openvave`, `identity.firmware_untested` True; transport `close()` called on success and on every error path
- [X] T028 [P] [US1] Write `tests/contract/test_cli_info_identity.py` calling `openvave.cli.main([...])` with an injected transport factory: human output contains `TANK-Gv2` and `firmware 96`; `--json` stdout parses and contains `schema_version` 1, `command` "info", `identity` object (name, firmware, firmware_untested, raw); exit codes 3/4/5/6/7 for injected `NoDeviceFoundError`/`MultipleDevicesError`/`BluetoothUnavailableError`/`RequestTimeoutError`/`HandshakeError`, each with `error:` on stderr, empty stdout under `--json`, no traceback; `MultipleDevicesError` lists candidates and a `--device` hint; fw-97 prints `warning:` on stderr and exits 0; `--version` prints version

### Implementation for User Story 1

- [X] T029 [US1] Implement `src/openvave/protocol/identity.py` (`TESTED_FIRMWARE = frozenset({96})`, `parse_identity(payload) -> DeviceIdentity`) and export from `src/openvave/protocol/__init__.py` until T025 passes
- [X] T030 [US1] Implement `src/openvave/session.py` `TankG`: `TankG.over(transport, timeout=2.0)` async context manager — `open()`, wait 200 ms, handshake up to 3 attempts (retry on timeout or `ProtocolError`), one request in flight (asyncio.Lock), `FrameAssembler` reset per request, stray chunks traced and ignored, per-request `asyncio.timeout` → `RequestTimeoutError`, `ConnectionLostError` propagated, untested-firmware warning, `close()` always; properties `.identity`, `.device`; trace every TX/RX via `openvave.trace` — until T027 passes
- [X] T031 [US1] Implement `src/openvave/transport/ble.py`: `select_device` (until T026 passes); `discover(timeout)` scanning for local name `TANK-Gv2_BLE` → `list[DeviceInfo]`; `BleakTransport(device)` with characteristic UUIDs `0000ae41-0000-1000-8000-00805f9b34fb` (write without response) and `0000ae42-0000-1000-8000-00805f9b34fb` (notify), disconnect callback → `ConnectionLostError` on the pending request, bleak adapter-off/permission errors → `BluetoothUnavailableError`; add `TankG.connect(device=None, scan_timeout=5.0, timeout=2.0)` in `src/openvave/session.py` using it. This is the only module importing `bleak`
- [X] T032 [US1] Implement `src/openvave/cli/__init__.py` `main(argv=None, *, transport_factory=None) -> int`: argparse with global options from contracts/cli.md (`--json`, `--device`, `--scan-timeout`, `--timeout`, `--trace`, `--version`) and subcommand `info`; `asyncio.run`; `OpenvaveError.exit_code` mapping, `error:`/`hint:` lines (macOS Bluetooth permission hint for exit 5), traceback only with `OPENVAVE_DEBUG=1`, exit 1 for unexpected exceptions; `--trace` attaches a stderr handler to `openvave.trace`
- [X] T033 [US1] Implement `src/openvave/cli/render.py`: human identity block (`Device  TANK-Gv2  (firmware 96)`, address line when a device is known) and the JSON envelope (`schema_version` 1, `command`, `read_at` ISO 8601 UTC, `device`, `identity` with `raw` as hex) until T028 passes
- [X] T034 [US1] Write `tests/hardware/test_hw_identity.py` (`@pytest.mark.hardware`): `TankG.connect()` returns name `TANK-Gv2` and firmware 96 within 10 s

### Live verification (milestone gate)

Run on macOS with a fw-96 pedal, phone app disconnected:

- [ ] T035 [US1] Run `uv run openvave info`, `uv run openvave info --json`, `uv run openvave --trace info` and `uv run pytest --hardware tests/hardware`; confirm `TANK-Gv2 (firmware 96)`, exit 0, < 10 s, and the trace shows only `TX 00 59 11 00 00 00 ff`; record OS version, firmware and output in the PR description
- [ ] T036 [US1] With the pedal off, run `uv run openvave info --scan-timeout 3`: `error:` on stderr, exit 3, ~3 s; with Bluetooth off: exit 5 with hint; record results in the PR

**Gate evidence (2026-11-16, macOS 26.5.2, local)**:

- [X] `uv run ruff check`, `uv run ruff format --check`, `uv run mypy src` (strict): clean.
- [X] `uv run pytest -q`: **438 passed, 1 skipped** (the hardware test) on Python 3.13.12 and
  3.11.13; `bleak` is still not imported by the hardware-free suite (lazy imports in
  `transport/ble.py`).
- [X] Independent criteria over `FakeTransport`: identity `TANK-Gv2` / 96 /
  `firmware_untested = false`, first frame `00 59 11 00 00 00 ff`
  (`test_identity_from_capture`); 2 drops → success with 3 queries, 3 drops → `HandshakeError`
  / exit 7 (`test_two_drops_then_success`, `test_three_drops_handshake_error`,
  `test_handshake_error_exit_7`); `info --json` has `schema_version: 1` + identity, and on
  failure stdout is empty with the contract exit code (`test_injected_errors`).
- [ ] T035/T036 on hardware — **blocked in the agent session**: launched from the Claude
  desktop app, `uv run openvave --trace info` is killed by macOS TCC (SIGABRT, exit 134,
  "attempted to access privacy-sensitive data without a usage description …
  NSBluetoothAlwaysUsageDescription") because the responsible app has no Bluetooth usage string.
  Must be run from Terminal/iTerm with Bluetooth permission granted. Observation for T055/T059:
  on macOS a host app without a Bluetooth usage string crashes the process before Python can
  map it to exit 5.
- [X] Hardware, user's shell (macOS 26.5.2, fw 96): `uv run openvave info --json` → exit 0,
  `device.name` `TANK-Gv2_BLE` (RSSI −77), identity `TANK-Gv2` / 96 / `firmware_untested`
  false, `raw` = the captured handshake payload byte-for-byte. An earlier `uv run openvave info`
  (pedal not advertising) → `error: no TANK-Gv2_BLE found` + hint, the exit-3 path.
- [X] Hardware: `uv run openvave --trace info` → exactly one `TX 00 59 11 00 00 00 ff`; reply in
  one notification (`RX chunk` == `RX`), byte-identical to the fw96 capture; human block
  `Device     TANK-Gv2  (firmware 96)` + `Address … (TANK-Gv2_BLE, -68 dBm)`.
- [X] Hardware: `uv run pytest --hardware tests/hardware` → **1 passed in 5.94 s** (5 s scan +
  connect + handshake, inside the 10 s budget); `info --scan-timeout 3` with the pedal on also
  finds and identifies it (RSSI −66).
- [ ] Still to run for T036: `--scan-timeout 3` with pedal off
  (exit code + ~3 s), Bluetooth off → exit 5.

**Checkpoint**: Milestone 1 DONE — MVP usable — pending hardware gate (T035/T036)

---

## Milestone 2 — Read device state: info block, global settings and status (US2, P2)

**Goal**: `openvave info` also reads and shows the device-info block, global settings, current
preset (JSON only) and status, raw with offsets and confidence-labelled fields.

**Independent test criteria**:
- Over the capture, `snapshot()` returns the four regions equal to the recorded data and sends
  exactly the 5 captured request frames in capture order.
- `openvave info --json` validates against `contracts/info.schema.json`; two runs differ only in
  `read_at` (SC-006).
- Human output shows `00 00 01 01` for Global with `edited flag?` labelled `(hypothesis)`.

### Tests for User Story 2 (write first, must fail)

- [ ] T037 [P] [US2] Write `tests/integration/test_session_snapshot.py`: `snapshot()` over the capture → regions DEVICE_INFO/GLOBAL/CURRENT_PRESET/STATUS equal the recorded data, `fake.sent == capture.ordered_tx`; `disconnect_after=3` → `ConnectionLostError` and no snapshot returned; `drop={"global …": 1}` → `RequestTimeoutError` (reads are not retried); `split=4` → identical snapshot; `read_at` is timezone-aware UTC
- [ ] T038 [P] [US2] Write `tests/contract/test_cli_info_regions.py`: `info --json` validates against `specs/001-readonly-ble-connection/contracts/info.schema.json` with `jsonschema`; region `data` equals capture hex; `fields` contains GLOBAL offset 3 with `confidence` "hypothesis"; two runs with `read_at` removed are identical; human output contains the 16-bytes-per-line hex dumps with `00:`/`10:` offsets for device info, global and status, `[meaning: unknown]` headers and `(hypothesis)` on the global flag

### Implementation for User Story 2

- [ ] T039 [US2] Add `TankG.read(region: Region) -> RegionRead` (rejects non-`Region` with `TypeError`) and `TankG.snapshot() -> DeviceSnapshot` (reads in order DEVICE_INFO, GLOBAL, CURRENT_PRESET, STATUS) to `src/openvave/session.py` until T037 passes
- [ ] T040 [US2] Extend `src/openvave/cli/render.py`: human region blocks (header `type T @ 0xADDRESS, N bytes`, hex dump, `KNOWN_FIELDS` lines `[offset] name = value   (confidence)`), JSON `regions` object with `type`, `address` (`0x%08x`), `length`, `data`, `fields`; and make `info` in `src/openvave/cli/__init__.py` call `snapshot()` until T038 passes
- [ ] T041 [US2] Extend `tests/hardware/test_hw_identity.py` (or add `tests/hardware/test_hw_snapshot.py`): snapshot on fw 96 returns DEVICE_INFO bytes 0–3 `0a 30 39 36` and STATUS length 1

### Live verification (milestone gate)

- [ ] T042 [US2] On macOS + fw 96 run `uv run openvave info` and `uv run openvave info --json | python -m json.tool`; confirm Global `00 00 01 01` (after a fresh preset load) and Status `01`; move a knob and re-run to see Global byte 3 change (records evidence for the hypothesis); record results in the PR
- [ ] T043 [US2] If the knob experiment confirms or refutes the global byte 3 hypothesis, update its confidence in `specs/protocol/command-layer.md` and `KNOWN_FIELDS` in `src/openvave/models.py` in the same PR (Constitution I)

**Checkpoint**: Milestone 2 DONE

---

## Milestone 3 — Use the same capabilities as a library (US4, P2)

**Goal**: a stable, documented public API that other tools use directly, with a fake transport
for their own tests.

**Independent test criteria**:
- `openvave.__all__` equals the export list in `contracts/library-api.md`.
- The snippet in `contracts/library-api.md` runs unchanged against `FakeTransport` and
  `fake.sent` equals the documented frames.

### Tests for User Story 4 (write first, must fail)

- [ ] T044 [P] [US4] Write `tests/contract/test_public_api.py`: `set(openvave.__all__)` equals the contract export list; `openvave.protocol` exposes `encode_frame`, `decode_frame`, `FrameAssembler`, `build_query`, `build_read`, `parse_read_reply`, `parse_identity`; `TankG` has no attribute containing `write`, `erase` or `address`; `pedal.read(0x10000000)` raises `TypeError`; all public dataclasses are frozen
- [ ] T045 [P] [US4] Write `tests/integration/test_library_usage.py`: run the `FakeTransport` part of the contracts/library-api.md snippet verbatim; `fake.sent[0]` is `00 59 11 00 00 00 ff` and the preset read frame is `00 59 23 08 00 00 04 00 00 00 10 15 00 00 d6`; with a `logging` handler on `openvave.trace` every TX/RX appears, without one nothing is printed; after the `async with` block no asyncio tasks created by the session remain

### Implementation for User Story 4

- [ ] T046 [US4] Define `__all__` and re-exports in `src/openvave/__init__.py` (`discover`, `TankG`, `Region`, `DeviceInfo`, `DeviceIdentity`, `RegionRead`, `DeviceSnapshot`, `Transport`, `FakeTransport`, `TESTED_FIRMWARE`, `OpenvaveError` and subclasses); add docstrings to every public name until T044–T045 pass
- [ ] T047 [US4] Run `uv run mypy --strict` on a scratch copy of the library-api.md snippet to confirm public types are complete; fix any missing annotations in `src/openvave/`

### Live verification (milestone gate)

- [ ] T048 [US4] On macOS + fw 96, run the `TankG.connect()` part of the library-api.md snippet in `uv run python`; confirm identity and snapshot match `openvave info --json`; record in the PR

**Checkpoint**: Milestone 3 DONE

---

## Milestone 4 — Dump the current preset (US3, P3) + Polish

**Goal**: `openvave preset dump` prints the 21-byte current preset buffer with offsets and
confidence-labelled fields, in human and JSON form; then project-wide polish.

**Independent test criteria**:
- Over the capture, `preset dump --json` validates against `contracts/preset-dump.schema.json`
  and `data` equals `01 00 00 01 0f 04 3c 3c 46 32 32 00 00 00 00 05 04 07 43 16 43`.
- Exactly two frames are sent: the handshake query and the preset read.
- Two invocations against fakes with different preset data print different output (no caching).

### Tests for User Story 3 (write first, must fail)

- [ ] T049 [P] [US3] Write `tests/contract/test_cli_preset_dump.py`: `preset dump --json` validates against the schema; `fake.sent` is exactly `[00 59 11 00 00 00 ff, 00 59 23 08 00 00 04 00 00 00 10 15 00 00 d6]`; human output shows offsets `00:` and `10:` covering bytes 0–20 and `[6] knob (which one: unknown) = 60   (observed)`
- [ ] T050 [P] [US3] Write `tests/integration/test_preset_no_cache.py`: two consecutive `main(["preset", "dump", "--json"])` runs, the second with a `replies` override whose byte 6 differs (built with `with_payload`), produce different `data`

### Implementation for User Story 3

- [ ] T051 [US3] Add the `preset dump` subcommand to `src/openvave/cli/__init__.py` (handshake + `read(Region.CURRENT_PRESET)` only) and the preset renderers (human block + JSON `preset` object with `command` "preset dump") to `src/openvave/cli/render.py` until T049–T050 pass
- [ ] T052 [US3] Add `tests/hardware/test_hw_preset.py` (`@pytest.mark.hardware`): preset read returns 21 bytes on fw 96

### Polish & cross-cutting (same PR)

- [ ] T053 [P] Update `README.md`: install (`uv tool install` / `pip install`), `openvave info` and `openvave preset dump` examples, JSON output and `schema_version` policy, exit code table link, platform support (macOS hardware-verified; Linux/Windows untested on hardware), macOS Bluetooth permission note, "close the phone app first" note; keep the unofficial disclaimer
- [ ] T054 [P] Create `CHANGELOG.md` with an `Unreleased` / `0.1.0` entry: read-only `info` and `preset dump`, JSON schema_version 1, exit codes 0–7, tested firmware 96
- [ ] T055 [P] Update `specs/protocol/command-layer.md` "Next steps": read-only replay now lives in the library (`src/openvave/`); record any new hardware observation from the milestone gates (e.g. behaviour when the phone app is still connected) with its confidence level
- [ ] T056 Run `uv run ruff check`, `uv run ruff format --check`, `uv run mypy src`, `uv run pytest` and fix anything outstanding

### Live verification (milestone gate)

- [ ] T057 [US3] On macOS + fw 96: `uv run openvave preset dump`, turn one knob, run again — a parameter byte changes; `uv run openvave --trace preset dump` shows exactly two `TX` lines; record in the PR
- [ ] T058 Run every scenario in `specs/001-readonly-ble-connection/quickstart.md` (hardware-free and hardware) and record pass/fail, OS version and firmware in the PR
- [ ] T059 Run the phone-app-still-connected spot check from quickstart.md and record which exit code (3 or 6) occurs; update `contracts/cli.md` hint text if needed
- [ ] T060 Confirm SC-001 by timing 10 consecutive `uv run openvave info` runs; ≥ 9 must finish under 10 s; record timings in the PR

**Checkpoint**: Milestone 4 DONE — feature complete

---

## Dependencies & Execution Order

### Milestone dependencies

- **M0** → blocks everything. Within M0: T001–T003 before T005; T006 before T007–T009; T010–T011
  before T012; T013–T015 before T018–T020; T016–T017 before T018–T020; T021 before T022; T022
  before T024.
- **M1 (US1)** depends on M0. **M2 (US2)** depends on M1 (extends `TankG` and `info`).
  **M3 (US4)** depends on M2 (freezes the API surface that M1–M2 built). **M4 (US3)** depends on
  M1 (uses `read()` from M2 — so in practice after M2) and, by delivery order, M3.
- US3 is functionally independent of US2's *rendering*, but shares `TankG.read()` introduced in
  M2; this is why it ships after M2.

### Within each milestone

- Tests (marked "write first") must exist and fail before the implementation task that names them.
- Models/errors before protocol code; protocol before session; session before CLI.
- Live verification tasks run last and their results go in the PR description.

### Parallel opportunities

- M0: T004 ∥ T005; T007 ∥ T008 ∥ T009; T010 ∥ T011; T013 ∥ T014 ∥ T015 ∥ T016 ∥ T017; T021 ∥ T023.
- M1: T025 ∥ T026 ∥ T027 ∥ T028 (all test files).
- M2: T037 ∥ T038.
- M3: T044 ∥ T045.
- M4: T049 ∥ T050; T053 ∥ T054 ∥ T055.

## Parallel Example: Milestone 1 (US1)

```text
Task: "Write tests/unit/test_identity.py …"                (T025)
Task: "Write tests/unit/test_discovery.py …"               (T026)
Task: "Write tests/integration/test_session_handshake.py …" (T027)
Task: "Write tests/contract/test_cli_info_identity.py …"   (T028)
# then sequentially: T029 → T030 → T031 → T032 → T033 → T034
```

## Implementation Strategy

### MVP first

1. Milestone 0 (evidence, scaffold, protocol core) → gate.
2. Milestone 1 (US1) → gate on real hardware → **MVP**: `openvave info` identifies the pedal.
3. Stop and review before continuing.

### Incremental delivery

- M2 adds region reads to `info`; M3 freezes the library API; M4 adds `preset dump` and polish.
  Each PR leaves `main` green and the CLI usable.

## Notes

- [P] = different files, no dependency on incomplete tasks.
- Commit after each task or logical group (Conventional Commits: `test:`, `feat:`, `docs:`,
  `chore:`).
- Any protocol finding during implementation updates `specs/protocol/` in the same PR
  (Constitution I) with a confidence level (Constitution II).
