<!--
Sync Impact Report
- Version change: (template, unversioned) → 1.0.0
- Modified principles: all placeholders replaced (initial ratification)
  - [PRINCIPLE_1_NAME] → I. Protocol Knowledge Is the Product
  - [PRINCIPLE_2_NAME] → II. Evidence-Based Reverse Engineering
  - [PRINCIPLE_3_NAME] → III. Capture-Driven Testing (NON-NEGOTIABLE)
  - [PRINCIPLE_4_NAME] → IV. Device Safety First
  - [PRINCIPLE_5_NAME] → V. Library-First, CLI-Exposed
  - Added → VI. Clean-Room & Legal Hygiene
  - Added → VII. Simplicity & Transport Isolation
- Added sections: Additional Constraints; Development Workflow
- Removed sections: none
- Templates:
  - ✅ .specify/templates/plan-template.md (Constitution Check gates listed)
  - ✅ .specify/templates/tasks-template.md (capture-based tests mandatory for protocol code)
  - ✅ .specify/templates/spec-template.md (no change needed)
  - ✅ .specify/templates/checklist-template.md (no change needed)
  - ✅ README.md (already consistent: unofficial disclaimer, library + CLI goal)
- Deferred TODOs: none
-->

# openvave Constitution

## Core Principles

### I. Protocol Knowledge Is the Product

The documented M-VAVE Tank-G protocol is a first-class deliverable, not a side effect of code.

- Every message, GATT service/characteristic, SysEx/MIDI command, USB endpoint and data
  structure the code uses MUST be described in `specs/` protocol documentation (byte layout,
  direction, framing, checksums, value ranges, known firmware versions).
- Protocol docs and code MUST change in the same PR; code that speaks an undocumented message
  MUST NOT be merged.
- Unknown or unexplained bytes MUST be marked explicitly as unknown, never silently guessed.

Rationale: other projects should be able to implement the protocol from the docs alone, in any
language, without reading our source.

### II. Evidence-Based Reverse Engineering

Every protocol claim MUST be traceable to evidence.

- Each documented message MUST cite at least one capture (BLE HCI log, USB/MIDI dump, or
  annotated hex) stored under `captures/` or referenced as a sanitized fixture.
- Each claim MUST carry a confidence level: `confirmed` (reproduced on hardware),
  `observed` (seen in captures, not yet replayed) or `hypothesis`.
- The firmware version and app version a capture came from MUST be recorded.

Rationale: reverse-engineered knowledge decays and misleads unless its provenance is explicit.

### III. Capture-Driven Testing (NON-NEGOTIABLE)

- Every encoder/decoder/parser MUST have tests that round-trip real captured bytes
  (decode(capture) → model → encode → identical bytes, where the protocol is deterministic).
- Tests for new protocol code MUST be written from fixtures first and fail before the
  implementation exists.
- The default test suite MUST run without hardware. Tests that need a physical pedal MUST be
  opt-in (marked/flagged) and MUST NOT run in CI.
- Every bug found on hardware MUST produce a new regression fixture.

Rationale: hardware is scarce and slow; captured bytes make correctness reproducible for every
contributor.

### IV. Device Safety First

The library talks to a real device that users can brick or lose presets on.

- Read operations are the default. Any write (presets, parameters, global settings) MUST be an
  explicit, separately named API/CLI action.
- Destructive writes MUST support a dry-run that shows the exact bytes to be sent, and the CLI
  MUST offer a backup of affected presets/settings before overwriting them.
- Firmware update, factory reset, or any command not confirmed safe MUST NOT be exposed in the
  public API or CLI without an explicit "unsafe" opt-in and a documented warning.
- `hypothesis`-level messages MUST NOT be sent by default code paths.

Rationale: trust in an unofficial tool depends on it never damaging the user's gear.

### V. Library-First, CLI-Exposed

- Core functionality lives in a reusable library with no CLI, UI or transport-specific code in
  the protocol layer.
- Every library capability intended for users MUST be reachable from the CLI.
- The CLI MUST use text I/O: args/stdin in, results to stdout, errors to stderr, non-zero exit
  codes on failure, and MUST support both human-readable and JSON output.
- Public library APIs follow semantic versioning; breaking changes require a MAJOR bump and
  changelog entry.

Rationale: other projects build on the library; the CLI makes it scriptable and debuggable.

### VI. Clean-Room & Legal Hygiene

- The project MUST NOT commit vendor firmware, vendor app binaries, decompiled vendor source,
  or copyrighted vendor assets (factory preset content, IRs, artwork).
- Reverse engineering is performed for interoperability; docs MUST describe behavior in our own
  words and structures.
- The unofficial / not-affiliated disclaimer MUST remain in the README and package metadata.
- Captures MUST be sanitized (device MAC addresses, serial numbers, account identifiers,
  personal preset names) before being committed; raw captures stay in `captures/private/`,
  which is git-ignored.

Rationale: keeps the project legally defensible under MIT and safe for contributors.

### VII. Simplicity & Transport Isolation

- Transports (BLE GATT, USB-MIDI, others) MUST sit behind a single minimal transport
  interface; the protocol layer MUST be testable with an in-memory fake transport.
- New dependencies, abstractions or packages MUST be justified in the plan's Complexity
  Tracking table; YAGNI applies until a second concrete use exists.

Rationale: the protocol is the hard part; plumbing should stay boring and swappable.

## Additional Constraints

- **Platforms**: the library and CLI SHOULD work on macOS, Linux and Windows; platform-specific
  transport code MUST be isolated and its limitations documented.
- **Timing & reliability**: protocol docs MUST note required delays, chunk sizes/MTU limits,
  acknowledgements and retry behavior; the library MUST time out instead of hanging.
- **Logging**: the library MUST be able to emit a hex trace of every frame sent and received
  (off by default) to aid further reverse engineering.
- **Secrets & privacy**: no telemetry; `.env` and private captures never leave the user's
  machine.

## Development Workflow

- Features follow Spec Kit: `/speckit-specify` → `/speckit-plan` → `/speckit-tasks` →
  `/speckit-implement`, with specs under `specs/`.
- Every plan MUST pass the Constitution Check gates before research and again after design.
- Every PR MUST: pass the hardware-free test suite and linters; update protocol docs alongside
  protocol code; state the confidence level of any new protocol claims; and, if it adds write
  operations, describe how they were verified on hardware (firmware version included).
- Commits use Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:`, `test:` …).

## Governance

- This constitution supersedes other practices in this repository. When guidance conflicts,
  the constitution wins until amended.
- Amendments are made by PR that edits this file, updates the Sync Impact Report, bumps the
  version, and propagates changes to `.specify/templates/` and runtime docs in the same PR.
- Versioning: MAJOR for removing or redefining a principle; MINOR for adding a principle or
  materially expanding guidance; PATCH for clarifications and wording.
- Compliance: reviewers MUST check PRs against the principles above; any violation MUST be
  recorded and justified in the plan's Complexity Tracking table or the PR description.
- Runtime development guidance for agents lives in `CLAUDE.md` and the current feature plan.

**Version**: 1.0.0 | **Ratified**: 2026-11-16 | **Last Amended**: 2026-11-16
