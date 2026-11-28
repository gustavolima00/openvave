# Implementation Plan: Pedal knowledge for applications (openvave 0.7.0)

**Branch**: `spec-app-support` (spec) → one implementation branch for Milestone 1 | **Date**: 2026-11-26 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/008-app-support/spec.md`

## Summary

Publish three things the repository already knows, as public and documented API, and release them
as 0.7.0 on top of tag `v0.6.0` (`fc0a6ae`, which already holds the spec 007 names):

1. `FakeTransport.simulated(path, …)`: a simulated pedal that accepts every allowlisted write,
   built from one recorded session, with its memory assembled inside the library (research R1–R4).
2. `openvave.protocol.PANEL_CONTROLS`, `PanelControl` and `panel_control()`: the front panel in
   the order of `docs/images/tankg-controls.svg` (R5–R6), and `PANEL_GROUPS`, `PanelGroup`,
   `panel_group()` and `group_enabled()`: per group, how to read whether it is enabled, with its
   confidence (R11).
3. `preset_index()` and `preset_position()`: strict `"1A"`…`"9D"` ↔ 0–35 (R7).

Everything is additive. No pedal message, no byte-map row, no write-table row and no JSON document
changes. One milestone, one pull request (R9).

## Technical Context

**Language/Version**: Python ≥ 3.11 (unchanged)

**Primary Dependencies**: `bleak` ≥ 0.22 (unchanged). No new dependency.

**Storage**: none. The simulated pedal keeps its memory in the process.

**Testing**: `pytest` + `pytest-asyncio`, hardware-free. New tests use only public imports for the
code under test and the existing independent fixtures (`tests/support/write_fixture.py`,
`tests/support/storage_fixture.py`) as the oracle. The whole-suite frame audit in
`tests/conftest.py` already covers every `FakeTransport`, including the new constructor.

**Target Platform**: as the library (pure Python; nothing platform-specific).

**Project Type**: library + CLI + MCP server (single Python package).

**Performance Goals**: none new (in-memory).

**Constraints**: additive only; `schema_version` stays 2; CLI and MCP output unchanged; the
existing `FakeTransport(...)`, `from_capture(...)`, `parse_position` and `position` keep their
behaviour; no pedal message; no hardware step; the `[0.6.0]` changelog section stays identical to
tag `v0.6.0` (`fc0a6ae`).

**Scale/Scope**: about 310 lines of application code: one new classmethod and two private helpers
in `transport/fake.py` (~110), one new module `protocol/panel.py` (~150, with the groups), two
functions in `protocol/storage.py` (~25), exports (~20). Nine new public names in
`openvave.protocol`, two of them also in `openvave`. Documentation and the version bump.

## Constitution Check

*GATE: passed before Phase 0; re-checked after Phase 1 design (no change).*

- [x] **I. Protocol docs**: no message is added or changed. The panel order and labels are
  already documented in `docs/tank-g.md` and the drawing; `specs/protocol/command-layer.md` gains
  a short "Front panel" section: a pointer for the order and labels, and the table of the six
  group-enabled rules with confidence and evidence (FR-030), mirrored by a test.
- [x] **II. Evidence**: no new observation; the group rules restate documented findings with
  their existing evidence (block switches `confirmed`; IR cab 0 = off `confirmed`, heard in spec
  007 gate session C; noise gate 0 = off `documented`, from the vendor app's display only, and
  said so). Panel labels come from the owner's own pedal (the
  drawing's stated source); MASTER "no byte" is spec 007's `observed` finding and keeps that
  wording. The simulated pedal is documented as a model, not evidence (FR-024).
- [x] **III. Capture-driven tests**: tests are written first from the committed captures and fail
  before the code exists; the suite runs without hardware.
- [x] **IV. Device safety**: nothing is sent to a real pedal. The simulated pedal refuses frames
  outside the allowlist; the allowlist is not touched. Persistent operations on it still need
  `unsafe=True` and the backup callback, because the session code is unchanged.
- [x] **V. Library-first/CLI**: library additions for developers. They are not user operations,
  so no CLI command is added (the CLI already converts positions and renders fields); recorded in
  R8.
- [x] **VI. Clean-room**: the generated stored image is a formula, not vendor preset content; the
  only real preset in it is the already public 1B of the recorded session.
- [x] **VII. Simplicity**: no new dependency, no new abstraction: one classmethod on the existing
  fake, one data table, two functions.

## Delivery Plan

Projected PR count: **1** (≤ 8). The application code is about 310 lines, well under one sitting,
and the three additions share the release bump, so splitting would only add a second release
step.

| # | Milestone | PR | Scope | Verification gate | Builds on |
|---|---|---|---|---|---|
| 1 | Milestone 1: Panel data, preset position helpers, simulated pedal and release 0.7.0 | 1 | `FakeTransport.simulated` with its memory built in the library; `PANEL_CONTROLS`, `PanelControl`, `panel_control`; `PANEL_GROUPS`, `PanelGroup`, `panel_group`, `group_enabled`; `preset_index`, `preset_position`; exports; `docs/library.md`, `docs/tank-g.md`, `docs/README.md`, `README.md`, `docs/images/README.md`, protocol-doc pointer, runnable example; `CHANGELOG.md` `[0.7.0]` (this feature only), version `0.7.0` in `pyproject.toml`, `__init__` and `uv.lock`; `test_changelog_070` | Machine-checked, no pedal: `uv run pytest`, `ruff check`, `ruff format --check` and `mypy src` green; the new tests (simulated pedal equals the internal write fixture for every operation and fault; panel order equals the drawing's description text; group-enabled answers equal the rules and the protocol-doc table; the bypass placeholder gives no answer; helpers agree with `PedalState.position`) pass; every 0.6.0 test passes with unchanged expectations except the version assertion; `[0.6.0]` section identical to tag `v0.6.0`; `openvave --version` prints `0.7.0`; quickstart §2 runs with public imports only | none |

After the gate the owner merges and creates tag `v0.7.0` on the merge commit (`v0.6.0` already exists on
`fc0a6ae`). The tag is not part of the pull request.

## Project Structure

### Documentation (this feature)

```text
specs/008-app-support/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── library-api.md
├── checklists/requirements.md
└── tasks.md
```

### Source Code (repository root)

```text
src/openvave/
├── __init__.py                 # + preset_index, preset_position; __version__ = "0.7.0"
├── protocol/
│   ├── __init__.py             # + PANEL_CONTROLS, PanelControl, panel_control, PANEL_GROUPS, PanelGroup, panel_group, group_enabled, preset_index, preset_position
│   ├── panel.py                # NEW: the front panel as data (controls, groups, enabled rules)
│   └── storage.py              # + preset_index, preset_position (strict); parse_position / position untouched
└── transport/
    └── fake.py                 # + FakeTransport.simulated, _generated_image, _simulated_parts

tests/
├── unit/
│   ├── test_panel.py           # NEW (US2)
│   ├── test_panel_groups.py    # NEW (US2: enabled rules, bypass placeholder)
│   ├── test_panel_doc.py       # NEW (US2: protocol-doc rule table = data)
│   ├── test_preset_positions.py# NEW (US3)
│   └── test_simulated_build.py # NEW (US1: start state, image rules, ValueErrors)
├── integration/
│   ├── test_simulated_pedal.py # NEW (US1: every operation and fault, against write_fixture)
│   └── test_example_simulated_pedal.py # NEW (the documented example runs)
└── contract/
    ├── test_public_api.py      # + the new names (the list only grows)
    ├── test_changelog_060.py   # version assertions move out; section checks stay
    └── test_changelog_070.py   # NEW (US4)

docs/
├── library.md                  # three additions; two sentences replaced
├── tank-g.md                   # pointer from the panel table to PANEL_CONTROLS
├── README.md, images/README.md # version; the drawing is now checked against the data
└── examples/simulated_pedal.py # NEW runnable example (no pedal)
specs/protocol/command-layer.md # "Front panel": pointer + group-enabled rule table
CHANGELOG.md, pyproject.toml, uv.lock, README.md
```

**Structure Decision**: the existing single package. The panel is its own module beside the byte
map (R5); the position helpers live with the stored-image layout they describe; the simulated
pedal is a classmethod of the fake it configures.

## Complexity Tracking

No constitution violation; nothing to justify.
