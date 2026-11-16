# Implementation Plan: Read-only BLE connection to the Tank-G

**Branch**: `001-readonly-ble-connection` | **Date**: 2026-11-16 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-readonly-ble-connection/spec.md`

## Summary

Deliver the first usable slice of openvave: a Python library that discovers a Tank-G over BLE,
performs the name/firmware handshake (`0x11`) and reads the four confirmed memory regions
(`0x23`), plus a thin `openvave` CLI (`info`, `preset dump`) with human-readable and versioned
JSON output. Writes are impossible by construction: the frame encoder only accepts command bytes
`0x11`/`0x23` and reads can only target a closed set of four regions. All protocol code is
tested from sanitized real captures through an in-memory fake transport; hardware tests are
opt-in. See [research.md](research.md) for the decisions behind each choice.

## Technical Context

**Language/Version**: Python ≥ 3.11 (R1)

**Primary Dependencies**: `bleak` ≥ 0.22 (only runtime dep, R2); dev: `pytest`,
`pytest-asyncio`, `jsonschema`, `ruff`, `mypy` (R5)

**Storage**: N/A (committed captures under `captures/` are test fixtures, not runtime storage)

**Testing**: `pytest`; default suite hardware-free; `@pytest.mark.hardware` + `--hardware` for
real-pedal tests (R5)

**Target Platform**: macOS (hardware-verified), Linux and Windows (best-effort, documented
untested on hardware) — spec clarification Q3

**Project Type**: library + CLI (single Python package)

**Performance Goals**: `openvave info` end-to-end < 10 s in ≥ 9/10 runs (SC-001); observed
reply latency 40–90 ms

**Constraints**: per-request timeout 2 s, handshake ≤ 3 attempts, scan ≤ 5 s default (R9);
only command bytes `0x11`/`0x23` may ever be encoded (R10); no background polling (FR-012)

**Scale/Scope**: 1 device per invocation; 5 request/reply pairs per `info`; 2 per `preset dump`
(handshake + preset read)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Pre-research evaluation (2026-11-16):

- [x] **I. Protocol docs**: every message used (`0x11`, `0x23` × 4 regions) is already in
  `specs/protocol/command-layer.md`; M0 adds capture citations; any new finding updates those
  docs in the same PR. *Precondition*: the protocol docs must be committed first (they are
  currently uncommitted in the main checkout).
- [x] **II. Evidence**: all in-scope claims are `confirmed` on fw 96 (probe capture
  `20261116-111832`); reassembly stays `observed` (R6); firmware/app/platform recorded in the
  capture header (R6).
- [x] **III. Capture-driven tests**: fixture loader + round-trip tests are written first in M1,
  from committed sanitized captures (R6); the default suite needs no Bluetooth; hardware tests
  opt-in and excluded from CI (R5).
- [x] **IV. Device safety**: no writes in this feature; command allowlist + closed `Region` enum
  make writes and arbitrary reads unencodable (R10); no `hypothesis`-level message is sent
  (`0x11`/`0x23` are confirmed). Dry-run/backup N/A (no writes).
- [x] **V. Library-first/CLI**: `openvave.protocol` is pure (bytes in/out, no I/O); `openvave.cli`
  only parses args and renders; human + JSON output; distinct exit codes (R13).
- [x] **VI. Clean-room**: no vendor code or binaries; capture sanitized incl. the device-info
  bytes check (R7); "unofficial" disclaimer added to package metadata in M0.
- [x] **VII. Simplicity**: one `Transport` protocol with two implementations (`BleakTransport`,
  `FakeTransport`); one runtime dependency; no sync facade, no `scan` command (YAGNI). Dev deps
  justified in Complexity Tracking.

Result: **PASS** (no unjustified violations).

Post-design re-evaluation (after Phase 1, 2026-11-16): **PASS** — the data model, contracts and
layout below keep the protocol layer I/O-free, expose only the four regions, and put every
fixture under `captures/`. No new dependency or abstraction was introduced during design.

## Delivery Plan

Projected PR count: **4** (≤ 8, no re-scoping needed). Each milestone is independently
reviewable and leaves `main` green.

| # | Milestone | Scope | Stories | Verification gate |
|---|---|---|---|---|
| M0 | Evidence & scaffold | Sanitized `captures/fw96/20261116-probe-connect.jsonl` + `captures/README.md` (R6, R7); capture citations in `command-layer.md`; `pyproject.toml` (metadata incl. unofficial disclaimer, `openvave` entry point), `ruff`/`mypy`/`pytest` config, CI (Linux/macOS/Windows, no hardware), fixture loader + mutation helpers with their own tests | — | CI green on 3 OSes; loader parses all 15 capture events; reviewer confirms R7 sanitization decision |
| M1 | Protocol layer | `frame` (encode/decode/checksum/allowlist), `assembler` (chunk reassembly), `commands` (query, `Region` reads), `identity` (handshake parse, firmware gate); round-trip + negative tests from captures, written first | US4 (protocol part) | All 5 captured requests encode byte-identical; all 5 replies decode → model → encode identical; every FR-005 rejection covered; allowlist test |
| M2 | Session & transports | `Transport` protocol, `FakeTransport`, `BleakTransport`, discovery/selection, `TankG` session (connect sequence, 200 ms settle, timeouts, handshake retries), `DeviceSnapshot`, hex trace, SC-004 audit fixture | US4, US1/US2/US3 library side | Integration tests replay the full capture through `FakeTransport`; timeout/retry/disconnect tests; SC-004 audit passes over whole suite |
| M3 | CLI & hardware check | `openvave info`, `openvave preset dump`, human + JSON renderers, JSON schemas enforced in contract tests, exit codes, `--trace`, `--device`, `--timeout`, `--scan-timeout`; opt-in hardware tests; README usage section | US1, US2, US3 | Contract tests validate output against `contracts/*.schema.json`; quickstart scenarios 1–6 pass hardware-free; quickstart hardware scenario passes on macOS + fw 96 (recorded in PR) |

## Project Structure

### Documentation (this feature)

```text
specs/001-readonly-ble-connection/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   ├── cli.md                    # CLI commands, flags, exit codes, stdout/stderr rules
│   ├── library-api.md            # public Python API surface
│   ├── info.schema.json          # JSON output of `openvave info --json`
│   └── preset-dump.schema.json   # JSON output of `openvave preset dump --json`
├── checklists/requirements.md
└── tasks.md             # Phase 2 output (/speckit-tasks — not created here)
```

### Source Code (repository root)

```text
pyproject.toml
captures/
├── README.md                        # JSONL format, provenance, sanitization rules
└── fw96/
    └── 20261116-probe-connect.jsonl # sanitized hardware capture (fixture source)

src/openvave/
├── __init__.py          # public API re-exports, __version__
├── __main__.py          # python -m openvave → cli.main()
├── errors.py            # OpenvaveError hierarchy (maps 1:1 to exit codes)
├── models.py            # DeviceInfo, DeviceIdentity, Region, RegionRead, DeviceSnapshot
├── protocol/            # pure, no I/O, no asyncio
│   ├── __init__.py
│   ├── frame.py         # Frame, encode/decode, checksum, command allowlist
│   ├── assembler.py     # FrameAssembler: notification chunks → complete frames
│   ├── commands.py      # build_query(), build_read(Region), parse replies
│   └── identity.py      # handshake payload → DeviceIdentity, TESTED_FIRMWARE
├── transport/
│   ├── __init__.py      # Transport protocol
│   ├── fake.py          # FakeTransport (scripted replies, records sent frames) — public
│   └── ble.py           # BleakTransport + discovery (only module importing bleak)
├── session.py           # TankG: connect sequence, timeouts, retries, snapshot()
├── trace.py             # openvave.trace logger helpers
└── cli/
    ├── __init__.py      # main(): argparse, asyncio.run, error → exit code
    └── render.py        # human and JSON renderers

tests/
├── conftest.py          # --hardware option, capture loader fixture, SC-004 audit fixture
├── support/
│   ├── captures.py      # load captures/*.jsonl
│   └── mutations.py     # flip_checksum, set_echo_cmd, set_echo_addr, truncate, split
├── unit/                # protocol: frame, assembler, commands, identity
├── integration/         # TankG session over FakeTransport, full capture replay
├── contract/            # CLI JSON vs schemas, exit codes, public API surface
└── hardware/            # @pytest.mark.hardware, opt-in only
```

**Structure Decision**: single Python package with a `src/` layout. The `protocol/` subpackage is
the reusable, I/O-free core (Constitution V/VII); `transport/` isolates `bleak` to one module;
`cli/` is a thin consumer. Tests are split by layer so the hardware-free suite is everything
except `tests/hardware/`.

## Complexity Tracking

No constitution violations. Dependency justifications required by Principle VII:

| Addition | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| `bleak` (runtime) | Cross-platform BLE GATT client | Writing three native backends is far more code |
| `pytest-asyncio` (dev) | Session/transport code is asyncio | Hand-rolled `asyncio.run` in every test duplicates setup and hides failures |
| `jsonschema` (dev) | Enforce the published JSON contract (FR-016a) | Ad-hoc dict assertions drift from the schema files |
| `mypy`, `ruff` (dev) | Typed public API, consistent style for contributors | None needed at runtime; standard tooling |
