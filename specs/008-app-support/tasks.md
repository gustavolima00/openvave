# Tasks: spec 008 pedal knowledge for applications (openvave 0.7.0)

**Input**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md),
[data-model.md](data-model.md), [contracts/library-api.md](contracts/library-api.md),
[quickstart.md](quickstart.md)

**Tests**: required and written first (Constitution III; the app's tasks T118–T120). Every test
here is hardware-free.

**Format**: `[ID] [P?] [Story] description with file path`. `[P]` = another file, no dependency on
an unfinished task.

## Delivery Plan

| # | Milestone | PR | Tasks | Builds on | Needs the pedal? |
|---|---|---|---|---|---|
| 1 | Milestone 1: Panel data, preset position helpers, simulated pedal and release 0.7.0 | 1 | T001–T018 | none | no |

Tasks are commits inside the one pull request, never separate pull requests.

---

## Milestone 1: Panel data, preset position helpers, simulated pedal and release 0.7.0

**Goal**: openvave publishes the simulated pedal that accepts writes (US1), the front panel as
data (US2) and the strict position helpers (US3), and is ready to be tagged `v0.7.0` (US4).

**Independent test criteria** (stated before implementation):

- With public imports and one committed capture, `FakeTransport.simulated(...)` gives a pedal on
  which `set_field`, `set_fields`, `select_preset`, `reload_preset`, `bypass_on`, `bypass_off`,
  `backup`, `save_preset` and `restore` succeed through `TankG.over(...)`, with results equal to
  the internal write fixture's; each documented fault makes one write misbehave once; `sent` lists
  every frame (US1).
- `openvave.protocol.PANEL_CONTROLS` lists 19 controls in the order of the description text of
  `docs/images/tankg-controls.svg`, covers every front-panel field of the byte map, lists MASTER
  without a byte and has nothing for the LED colour bytes (US2).
- `preset_index` and `preset_position` agree with `PedalState.position` for all 36 indexes and
  raise `ValueError` for everything else (US3).
- The package says `0.7.0`; `CHANGELOG.md` has a `[0.7.0]` section with the three additions and
  the spec 007 names; `[0.6.0]` is unchanged; nothing public was removed and `schema_version`
  stays 2 (US4).

### Setup

- [ ] T001 Create the implementation branch from `origin/main` and run `uv sync && uv run pytest`
  once to record the green baseline (test count) in the pull request description; no file changes

### Tests first (write them, see them fail)

- [ ] T002 [P] [US2] `tests/unit/test_panel.py`: `PANEL_CONTROLS` has 19 entries with
  `order == index` (unique, no gaps); the sequence of fields (with `master` for the entry without
  one) equals the sequence parsed from the `<desc>` element of `docs/images/tankg-controls.svg`
  (FR-013); labels and groups equal the table in research R5; every `CURRENT_PRESET` entry of
  `BYTE_MAP` with encoding `CONTINUOUS`, `SELECTOR` or `SWITCH` except `led_red` / `led_green` /
  `led_blue` has exactly one control whose `offset` and `kind` agree with the entry (FR-011);
  exactly one control (MASTER, order 0) has `field is None and offset is None` (FR-012);
  `panel_control()` returns the entry for each field and `None` for `led_red`, `mode`, `loopback`,
  `"nope"` and `None` (FR-015); `PanelControl` is frozen
- [ ] T003 [P] [US3] `tests/unit/test_preset_positions.py`: for every index 0–35,
  `preset_position(i) == PedalState(kind="normal", index=i, bank=i // 4).position` and
  `preset_index(preset_position(i)) == i` (FR-019); `preset_index` raises `ValueError` for `"0A"`,
  `"10A"`, `"1E"`, `""`, `"1a"`, `" 1A"`, `"1A "`, `"6"`, `6`, `None` and `b"1A"` (FR-017);
  `preset_position` raises `ValueError` for `-1`, `36`, `True`, `1.0`, `"1"` and `None` (FR-018);
  both names are importable from `openvave` and `openvave.protocol` and are the same objects
  (FR-016); the internal `parse_position("2c")`, `parse_position("6")` and `position(6)` still
  return what they did (FR-020)
- [ ] T004 [P] [US1] `tests/unit/test_simulated_build.py`: from
  `captures/fw96/20261116-probe-connect.jsonl` the simulated pedal answers the handshake and the
  global, preset, status and device-information reads with the recorded bytes (FR-002); its
  stored image equals `tests.support.storage_fixture.synthetic_image()` byte for byte (generated
  image, FR-003, research R3); from `captures/fw96/20261117-storage-synthetic.jsonl` plus nothing
  else it raises `ValueError` naming the missing global read (FR-008); from a temporary capture
  that adds a whole-image read, that image is used; `image=` replaces both and a 757-byte image
  raises `ValueError`; a capture without a status read starts with status `00`; a capture that repeats the global
  and preset reads (a `watch` step capture such as `captures/fw96/20261116-step-gain.jsonl`)
  starts from the first reply of each; a capture whose global block says edit mode builds, with
  the recorded buffer as the stored preset at the loaded position; a capture whose
  recorded state is bypass raises `ValueError`; a capture without the query raises `ValueError`;
  a recorded write and a recorded stored-slot read are not replayed (a later read shows memory,
  research R2); unknown fault kind or action raises `ValueError`; `FakeTransport(...)` and
  `from_capture(...)` signatures are unchanged (`inspect.signature`, FR-020). Temporary captures
  are derived from committed ones with `tests/support/mutations.py` / `tests/support/captures.py`
- [ ] T005 [P] [US1] `tests/integration/test_simulated_pedal.py`, through the public session API
  only (`TankG.over(FakeTransport.simulated(...))`), each case run twice (simulated pedal, and
  `tests.support.write_fixture.make_fake(NORMAL, status=b"\x01")` as the oracle: the capture
  records 1B, normal mode, loopback on) and compared on
  result objects, `sent` frames and a final `backup()`: the opening `state()` (normal, `1B`) and current preset
  equal the capture's; `set_field` (a knob, a typed knob, a
  block switch, `led_colour`), `set_fields` (several kinds in one call), `select_preset`,
  `reload_preset`, `bypass_on` then `bypass_off`, `set_loopback`, `backup` (36 presets, loaded
  position equals the recorded preset), `save_preset` in place and `to=` another slot, `restore`
  with `slot=` and `all=True`, `copy_preset`, `swap_presets`, `export_preset` and `import_preset`
  (FR-004, FR-005, SC-001, SC-002); every fault action (`nak`, `no_reply`, `disconnect`,
  `corrupt`, `ignore`) on one volatile and one persistent write kind raises the same error with
  the same partial result as the oracle, and the next write of that kind succeeds (FR-006);
  `select_transient=2` shows the loading state twice; `chunk_size=182` still passes a backup;
  `sent` holds every request in order (FR-007); a frame outside the allowlist raises
  `AssertionError` (FR-009). Tests that send stored-slot, commit or stored-image writes carry the
  `persistent_writes` marker (the suite's audit requires it)
- [ ] T006 [P] [US4] `tests/contract/test_changelog_070.py` (modelled on
  `tests/contract/test_changelog_060.py`): the `[0.7.0]` section exists between `[Unreleased]` and
  `[0.6.0]`, opens with a summary paragraph, names `FakeTransport.simulated`, `PANEL_CONTROLS`,
  `PanelControl`, `panel_control`, `preset_index`, `preset_position`, `POSITION_NAMES` and
  "amp type and IR cab names", says "`schema_version` stays 2", has a `### Tested` subsection
  saying no pedal was needed; `[Unreleased]` has no entry; `openvave.__version__`, `pyproject.toml`
  and `openvave --version` say `0.7.0` (FR-022, FR-023). In the same commit move the three version
  assertions out of `tests/contract/test_changelog_060.py` (its section checks stay)
- [ ] T007 [P] [US4] `tests/contract/test_public_api.py`: add `preset_index` and `preset_position`
  to `CONTRACT_EXPORTS`, and a test that `{"PANEL_CONTROLS", "PanelControl", "panel_control",
  "preset_index", "preset_position"} <= set(openvave.protocol.__all__)`; no existing expectation
  is removed or weakened (SC-005)
- [ ] T008 [P] [US4] `tests/integration/test_example_simulated_pedal.py` (new; no existing test
  runs the scripts in `docs/examples/`): run `docs/examples/simulated_pedal.py` with
  `runpy.run_path(..., run_name="__main__")` and assert it finishes without error and prints the
  panel's first (`MASTER`) and last (`D/AMP`) labels and a verified save; marked
  `persistent_writes` because the example saves and restores on the simulated pedal (FR-024,
  quickstart §2)

### Implementation

- [ ] T009 [P] [US3] `src/openvave/protocol/storage.py`: add `preset_index(position)` and
  `preset_position(index)` (strict, `ValueError` only, research R7); leave `parse_position`,
  `position` and `_check_index` as they are
- [ ] T010 [P] [US2] `src/openvave/protocol/panel.py` (new): `PanelControl` (frozen dataclass),
  `PANEL_CONTROLS` (the 19 rows of research R5) and `panel_control(field)`; pure data, imports
  nothing but the standard library (data-model.md)
- [ ] T011 [US2] [US3] `src/openvave/protocol/__init__.py`: export `PANEL_CONTROLS`,
  `PanelControl`, `panel_control`, `preset_index`, `preset_position`; `src/openvave/__init__.py`:
  export `preset_index`, `preset_position` (after T009, T010)
- [ ] T012 [US1] `src/openvave/transport/fake.py`: `FakeTransport.simulated(path, *, image=None,
  faults=None, select_transient=0, chunk_size=None)` with two private helpers: one that splits the
  parsed capture into the script (query, non-type-4 reads) and the memory blocks (global, edit
  buffer, status, optional whole image) by decoded frame, raising the `ValueError`s of FR-008
  (state check with `openvave.protocol.state.classify`), and one that generates the stored image
  (research R3). Share the capture parsing with `from_capture` without changing its behaviour.
  Docstring states every argument, the starting state, the error cases and that it is a model,
  not evidence. Update the module docstring's first line ("for tests and simulations") only if
  needed
- [ ] T013 [US1] `docs/examples/simulated_pedal.py` (new, runnable without a pedal, public imports
  only): build the simulated pedal, print `PANEL_CONTROLS`, edit two fields, select 2C through
  `preset_index("2C")`, backup, save with `unsafe=True` and `on_backup`, restore, print
  `len(fake.sent)` (after T011, T012)

### Documentation and release

- [ ] T014 [US4] `docs/library.md`: under "Testing without a pedal" document
  `FakeTransport.simulated` (arguments, starting state, stored image, faults, `sent`, "a model,
  not evidence") and replace the pointer to `tests/support/write_fixture.py`; under "Writing"
  replace "There is no name parser in the public API…" with `preset_index` / `preset_position`
  (strict; the CLI stays lenient); under "The protocol layer" add `PANEL_CONTROLS`,
  `PanelControl`, `panel_control` with a short example; add 008's contract to the list of
  contracts at the top; link `examples/simulated_pedal.py` (FR-024)
- [ ] T015 [P] [US4] `docs/tank-g.md` (one sentence after the knob table pointing to
  `openvave.protocol.PANEL_CONTROLS`), `docs/images/README.md` (the drawing's description text is
  checked against the panel data by `tests/unit/test_panel.py`; change both together),
  `specs/protocol/command-layer.md` (a short "Front panel" pointer to `docs/tank-g.md` and the
  panel data; no byte-map or write-table row changes, so `tests/unit/test_bytemap_doc.py` and
  `test_writes_doc.py` stay green), `docs/README.md` and `README.md` (current version 0.7.0, one
  line on what it adds), `docs/examples/README.md` (the new example), and `docs/cli-reference.md` only if a sentence
  there names the current version
- [ ] T016 [US4] `CHANGELOG.md`: new `## [0.7.0]` with a summary paragraph, "Added (spec 008)"
  entries for the simulated pedal, the panel data and the position helpers, the existing
  "Added (spec 007 US4)" subsection moved unchanged from `[Unreleased]`, and `### Tested`
  (hardware-free suite; no pedal message added; names `documented`); leave `## [Unreleased]`
  empty; do not touch `[0.6.0]` or anything below it (FR-023, research R10)
- [ ] T017 [US4] `pyproject.toml` (`version = "0.7.0"`), `src/openvave/__init__.py`
  (`__version__ = "0.7.0"`), then `uv lock` so `uv.lock` carries 0.7.0 (FR-022)

### Live verification (milestone gate)

- [ ] T018 Run [quickstart.md](quickstart.md) §1–§3 and record the output in the pull request:
  - `uv run ruff check`, `uv run ruff format --check`, `uv run mypy src`, `uv run pytest` all
    green; the test count is the T001 baseline plus the new tests, with no test removed or skipped
    and no expectation changed apart from the moved version assertions (SC-005).
  - `uv run python docs/examples/simulated_pedal.py` exits 0 (SC-001).
  - `uv run openvave --version` prints `openvave 0.7.0`.
  - The `[0.6.0]` section equals the one in `git show 61fdf6a:CHANGELOG.md` (quickstart §3 prints
    `0.6.0 unchanged`).
  - `git diff --stat origin/main -- src/openvave/cli src/openvave/mcp_server
    src/openvave/session.py src/openvave/models.py src/openvave/protocol/bytemap.py
    src/openvave/protocol/writes.py` prints nothing: the CLI, the MCP server, the session, the
    byte map and the allowlist are untouched (FR-009, FR-020, FR-021).
  - No pedal is needed: nothing in this milestone sends a new message.
  - Not part of the pull request (owner, after the merge): tag `v0.7.0` on the merge commit, then
    quickstart §4; `v0.6.0` on `61fdf6a` is the owner's separate step (FR-025, SC-007).

**Checkpoint**: Milestone 1 DONE — the suite, linters and type check are green, the three
additions are public and documented, the version is 0.7.0, and the pull request waits for the
owner's merge and tag `v0.7.0`.

---

## Dependencies

- T001 first. T002–T008 (tests) before T009–T013 (code); they must fail first.
- T009 and T010 are independent; T011 needs both; T012 is independent of them; T013 needs T011
  and T012.
- T014–T017 after the code (docs describe the final names); T016 before T006 can pass; T017 last
  before the gate.
- T018 last.

## Parallel opportunities

- T002–T008: seven test files, no shared edits.
- T009, T010 and T012: three source files.
- T015 beside T014.

## Implementation strategy

One pull request. A useful order of commits inside it: tests (T002–T008), position helpers and
panel (T009–T011), simulated pedal and example (T012–T013), docs (T014–T015), release
(T016–T017), gate (T018). US1 is the part the app waits for; US2 and US3 are small and can land in
any order before the release commit.

## Coverage

| Requirement | Tasks |
|---|---|
| FR-001–FR-003, FR-008 | T004, T012 |
| FR-004–FR-007, FR-009 | T005, T012 |
| FR-010–FR-015 | T002, T010, T011 |
| FR-016–FR-019 | T003, T009, T011 |
| FR-020, FR-021 | T003, T004, T007, T018 |
| FR-022, FR-023 | T006, T016, T017, T018 |
| FR-024 | T008, T013, T014, T015 |
| FR-025 | T018 (owner step, outside the pull request) |
| SC-001, SC-002 | T005, T018 |
| SC-003 | T002 |
| SC-004 | T003 |
| SC-005 | T007, T018 |
| SC-006 | T005 (suite audit in `tests/conftest.py`), T018 |
| SC-007 | T018 (owner, after the tag) |
