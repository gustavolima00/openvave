# Feature Specification: Finding, selecting and connecting to Tank-G pedals

**Feature Branch**: `claude/spec-005-device-selection-170117` (feature directory `005-device-selection`)

**Created**: 2026-11-19

**Status**: Draft

**Input**: User description: "Polished pedal discovery, selection and connection for the M-VAVE
Tank-G (CLI + library): search for pedals (scan/list with name, ID, signal strength, selected
marker), select a default pedal (optional nickname) remembered per user, show which pedal every
command acts on, switch and forget the selection, clear behaviour when the selected pedal is absent
or several are present, cross-host ID differences (macOS CoreBluetooth UUIDs vs MAC addresses),
single-connection limitation of the pedal, library API for selecting a device, and whether a
persistent connection (interactive shell or background service with connect/disconnect/status)
belongs in this spec or a later one."

**Builds on**: [`004-remote-edit-save-restore`](../004-remote-edit-save-restore/spec.md) and the
connection behaviour of [`001-readonly-ble-connection`](../001-readonly-ble-connection/spec.md)
(scan, `--device ID`, `--scan-timeout`, exit codes 0–8, JSON envelope with a `device` object).

**Protocol source of truth**: [`specs/protocol/ble-gatt.md`](../protocol/ble-gatt.md) (advertising
data) and [`specs/protocol/command-layer.md`](../protocol/command-layer.md) (connection notes). This
feature sends **no new pedal message**: it changes how a pedal is found, chosen and reported, and
reuses the confirmed handshake only where a story says so.

## Starting point (0.4.0, 2026-11-19)

What openvave does today:

- Every command scans for up to `--scan-timeout` seconds (default 5) and stops 1 s after the first
  pedal advertising `TANK-Gv2_BLE` is seen, so a second pedal can still be noticed.
- With exactly one pedal it connects to it. With none it exits 3 (`no TANK-Gv2_BLE found`, hint:
  switch the pedal on, close the phone app). With two or more it exits 4 and lists their
  identifiers and signal strength on stderr, with the hint `re-run with --device <identifier>`.
- `--device ID` connects to that identifier whatever its advertised name, and stops the scan as
  soon as it is seen.
- Each command opens one connection and closes it on exit. Nothing is remembered between commands.
- Only `info` prints the pedal's address; other commands do not say which pedal they used. JSON
  documents carry a `device` object (identifier, name, signal strength).
- The library offers `discover(timeout)` (every `TANK-Gv2_BLE` seen) and
  `TankG.connect(device=None, scan_timeout=…)` with the same rules as the CLI.

Facts that shape this feature (from the protocol docs and earlier gate sessions):

- The pedal accepts **one** BLE connection at a time and **stops advertising while connected**
  (observed, fw 96). A pedal held by the phone app, or by another openvave command, is not "busy":
  it is invisible to a scan.
- The advertisement carries the local name, the BLE-MIDI service and fixed manufacturer data
  (`"sinco"`), the same for every unit. **Nothing in it tells two pedals apart** except the
  identifier the computer assigns.
- That identifier is a MAC address on Linux and Windows, and on macOS a CoreBluetooth UUID that is
  **different on every Mac** for the same pedal and can change if the Mac's Bluetooth state is reset
  (platform behaviour, documented by Apple; not yet observed on this pedal).
- The firmware version is only known after connecting and running the handshake (about 1 s per
  pedal); it cannot be read from the advertisement.
- The pedal needs no pairing or bonding.

## User Scenarios & Testing *(mandatory)*

Actors:

- **Pedal owner**: has one Tank-G (possibly two, e.g. home and rehearsal, or a friend's in the same
  room), uses the CLI from one or more computers, and runs every hardware step in their own terminal.
- **Script / library user**: drives the pedal from Python or a shell script and needs predictable,
  explicit device choice with no hidden prompts.

### User Story 1 - Search for pedals (Priority: P1)

The owner runs one command and sees every Tank-G the computer can reach right now: an identifier
they can copy, the advertised name, the signal strength (so they can tell the near one from the
far one), the nickname if they gave one, and which one is selected. Nothing is sent to any pedal.

**Why this priority**: today the only place identifiers appear is the exit-4 error. Every other
story needs the owner to see what is in range first.

**Independent Test**: with zero, one and two pedals switched on (or with a fake scanner in the
hardware-free suite), run the search and check the list, the markers, the JSON document and the
message when nothing is found.

**Acceptance Scenarios**:

1. **Given** two pedals switched on and the phone app closed, **When** the owner runs
   `openvave scan`, **Then** both are listed, strongest signal first, each with identifier, name and
   signal strength, and the command exits 0 without connecting to either.
2. **Given** a selected pedal named `stage` is in range, **When** the owner searches, **Then** its
   row is marked as selected and shows `stage`.
3. **Given** no pedal is in range (or the phone app holds the only one), **When** the owner searches,
   **Then** the command says no Tank-G was found, explains that a pedal connected to the phone app
   or to another program stops advertising, and exits 3.
4. **Given** the selected pedal is not in range but another one is, **When** the owner searches,
   **Then** the other is listed and a line says the selected pedal (by nickname and identifier) was
   not seen.
5. **Given** `--json`, **When** the owner searches, **Then** stdout carries one document listing
   every pedal found (possibly none) with identifier, name, signal strength, nickname and selected
   flag.
6. **Given** `--all`, **When** the owner searches, **Then** other advertising devices are listed too
   (name possibly empty), marked as not a Tank-G, so a pedal with an unexpected name can still be
   found.

---

### User Story 2 - Select a pedal once and have every command use it (Priority: P1)

The owner picks a pedal from the search (by identifier, or by its position in the list) and
optionally gives it a short nickname. From then on, every pedal command on that computer, for that
user, connects to that pedal without asking for `--device`, even when another Tank-G is in range.

**Why this priority**: it removes the exit-4 dead end with two pedals and makes the single-pedal
case faster (the scan can stop the moment the selected pedal is seen).

**Independent Test**: select a pedal (fake scanner or hardware), run `info` with a second pedal in
range, and check the selected one is used; restart the shell and check the selection is still in
effect.

**Acceptance Scenarios**:

1. **Given** two pedals in range and none selected, **When** the owner runs
   `openvave select 3F1A…  --name stage`, **Then** the selection and nickname are remembered and the
   command confirms what was saved (nickname, identifier, where it is stored).
2. **Given** `stage` is selected and both pedals are in range, **When** the owner runs any pedal
   command, **Then** it connects to `stage` and the scan ends as soon as `stage` is seen.
3. **Given** the owner selects an identifier that is not in range, **When** the command runs,
   **Then** it refuses (exit 3), says the identifier was not seen, and saves nothing, unless
   `--offline` is given (for preparing a selection while the pedal is off).
4. **Given** no pedal is selected and exactly one is in range, **When** the owner runs a pedal
   command, **Then** it behaves as in 0.4.0 (uses that pedal) and does not save a selection
   silently.
5. **Given** no pedal is selected and two are in range, **When** the owner runs a pedal command,
   **Then** it exits 4 as today, lists both, and the hint names both ways out: `--device ID` for
   this run, `openvave select ID` to remember one.
6. **Given** the owner runs `openvave select` with no argument, **When** exactly one pedal is in
   range, **Then** that pedal is selected; with several, the list is shown and nothing is selected
   (no interactive prompt, so scripts never hang).

---

### User Story 3 - Know which pedal a command acts on (Priority: P2)

Every command that talks to a pedal says which pedal it used and why that one (selected, given with
`--device`, or the only one found). A separate command shows the current selection without
connecting.

**Why this priority**: with two pedals a write to the wrong one is the main risk this feature adds;
seeing the target on every run is the cheapest guard (Constitution IV).

**Independent Test**: run each pedal command against a fake transport with each of the three
choice reasons and check the human line and the JSON fields.

**Acceptance Scenarios**:

1. **Given** `stage` is selected, **When** the owner runs `openvave set gain=90`, **Then** before the
   result a line names the pedal (`stage`, short identifier, signal strength) and says it was the
   selected one; the line goes to stderr so stdout stays as in 0.4.0.
2. **Given** `--json`, **When** any pedal command succeeds, **Then** its `device` object also
   carries the nickname (or none) and how the pedal was chosen (`selected`, `device_option`,
   `only_one_found`).
3. **Given** a selection exists, **When** the owner runs `openvave device` (show), **Then** it prints
   the nickname, identifier, when it was selected and the firmware last seen, without scanning or
   connecting, and exits 0; with no selection it says so and how to make one, and exits 0.
4. **Given** `openvave device --check`, **When** it runs, **Then** it also scans and says whether
   the selected pedal is in range now (exit 3 if not), still without connecting.

---

### User Story 4 - Switch, rename, override and forget (Priority: P2)

The owner switches the default to another pedal, renames a nickname, uses a different pedal for one
command without changing the default, and forgets the selection (or a remembered pedal) entirely.

**Why this priority**: the selection is only safe if it is easy to change and to undo.

**Independent Test**: on a temporary configuration, run select → select other → rename → forget,
checking the stored state and the `device` output after each step; run one command with
`--device` and check the stored selection did not change.

**Acceptance Scenarios**:

1. **Given** `stage` is selected, **When** the owner selects another pedal, **Then** the new one is
   the default and the confirmation says which one it replaced.
2. **Given** `stage` is selected, **When** the owner runs a command with `--device home` (a
   nickname) or `--device 7C02…` (an identifier), **Then** that pedal is used for this run only and
   the selection is unchanged.
3. **Given** a nickname exists, **When** the owner renames it, **Then** commands accept the new
   nickname and reject the old one as unknown (exit 2, nothing scanned).
4. **Given** a selection, **When** the owner runs `openvave forget`, **Then** nothing is selected any
   more, the confirmation says what was forgotten, and the next command behaves as in 0.4.0.
5. **Given** the environment variable `OPENVAVE_DEVICE` is set, **When** a command runs without
   `--device`, **Then** the variable's identifier or nickname is used for that run, ahead of the
   saved selection; `--device` still wins over both.

---

### User Story 5 - Choose a pedal from Python (Priority: P3)

A library user lists pedals in range, picks one by identifier or nickname, reads or changes the
remembered selection, and opens a session to the chosen pedal, with the same rules and errors as
the CLI. Nothing is read from the user's configuration unless the caller asks for it.

**Why this priority**: Constitution V requires every CLI capability in the library; scripts and other
projects need explicit, testable device choice.

**Independent Test**: in the hardware-free suite, with a fake scanner and a temporary configuration
location, exercise listing, choosing, saving and forgetting, and connecting to the chosen pedal.

**Acceptance Scenarios**:

1. **Given** a fake scanner with two pedals, **When** the library lists pedals, **Then** it returns
   both with identifier, name, signal strength and, when a configuration is given, nickname and
   selected flag.
2. **Given** a saved selection, **When** a script opens a session asking for "the selected pedal",
   **Then** it connects to it; **When** it opens a session with no device argument and does not ask
   for the selection, **Then** the 0.4.0 rules apply unchanged (backwards compatible).
3. **Given** a session is open, **When** the script inspects it, **Then** it can read which pedal it
   is connected to and how it was chosen.

---

### User Story 6 - Keep one connection across several commands (Priority: P3, scope to be decided)

The owner wants to "connect" once, run several commands quickly over the same connection, see
whether openvave is connected, and "disconnect" (for example to hand the pedal back to the phone
app). Today every command connects and disconnects (about 1–2 s each), and there is nothing to
disconnect.

**Why this priority**: it would make interactive use faster and match the owner's mental model, but
it changes the process model (something must stay running and hold the pedal's only connection),
which affects safety, scripting and every platform. The batch `set FIELD=VALUE ...` form from 0.4.0
already covers the most common multi-change case on one connection.

**Scope**: [NEEDS CLARIFICATION: Should a persistent connection be part of spec 005? Options: (A)
no, defer it to a later spec and only make the one-connection-per-command model clear (`device`
shows "not connected; each command connects for its own run"); (B) an interactive shell
(`openvave shell`) that connects once and runs commands typed into it until `quit`/`disconnect`;
(C) a background service with `openvave connect`, `openvave status`, `openvave disconnect`, that
other commands route through.]

**Independent Test** (if in scope): open the persistent connection, run three reads and one write,
check only one connection was made, disconnect, and check the pedal advertises again.

**Acceptance Scenarios** (if in scope):

1. **Given** a persistent connection to `stage`, **When** the owner runs two commands in a row,
   **Then** neither scans nor reconnects, and each still states which pedal it acted on.
2. **Given** a persistent connection, **When** the owner disconnects, **Then** the pedal is released
   and becomes visible to the phone app and to a new scan.
3. **Given** the link drops while connected (pedal switched off), **When** the next command runs,
   **Then** it reports the lost connection (exit 6) and the status shows not connected; nothing is
   retried silently.

---

### Edge Cases

- **Selected pedal not in range, another Tank-G is**: [NEEDS CLARIFICATION: what should a pedal
  command do? Options: (A) refuse every command (exit 3), name the selected pedal and list what
  was seen, hint `--device` / `select`; (B) refuse writes but let reads fall back to the only other
  pedal with a warning; (C) fall back for every command with a warning line naming the pedal used.]
  Whatever the answer, a write MUST NOT go to a pedal other than the selected one without the user
  naming it for that run.
- **Selected pedal not in range, no Tank-G in range**: exit 3; the message names the selected pedal
  and keeps the existing hint (switch it on, close the phone app, another program may hold it).
- **Pedal held by the phone app or by another openvave process**: it does not advertise, so it is
  reported as not found (never as "busy"); the hint says so.
- **macOS identifier changed** (Bluetooth reset) or **configuration copied from another computer**:
  the saved identifier is never seen; the message says identifiers are specific to this computer and
  suggests `openvave scan` then `openvave select`.
- **Nickname that looks like an identifier**, or a nickname used twice: refused when saving (exit 2).
  Identifiers and nicknames are matched case-insensitively.
- **`--device` with an identifier that is not a Tank-G**: kept as in 0.4.0 (connects whatever the
  name) but the "acting on" line flags the unexpected name.
- **Configuration missing**: treated as "nothing selected". **Configuration unreadable or invalid**:
  reported with its path; pedal commands stop with exit 2 instead of guessing a pedal; `forget` can
  still reset it.
- **Two openvave commands at the same time**: the second does not see the pedal (it stops
  advertising) and exits 3 with the "another program may hold it" hint.
- **Bluetooth off or permission denied during `scan`**: exit 5 with the existing hints.
- **Search with `--json` and nothing found**: one document with an empty list, exit 3 (consistent
  with the other commands' "no pedal" code).

## Requirements *(mandatory)*

### Functional Requirements

**Search**

- **FR-001**: The CLI MUST offer a search command (`openvave scan`) that scans for up to
  `--scan-timeout` seconds and lists every device advertising `TANK-Gv2_BLE`, without connecting to
  any of them.
- **FR-002**: Each row MUST show the identifier (in full, copyable), advertised name, signal
  strength (or unknown), nickname if any, and whether it is the selected pedal; rows are ordered by
  signal strength, strongest first, and numbered so a row can be referred to.
- **FR-003**: The search MUST use the full scan time (it does not stop at the first pedal), so every
  pedal in range has the chance to be listed.
- **FR-004**: `--all` MUST include other advertising devices, flagged as not a Tank-G.
- **FR-005**: The firmware version MUST NOT be shown by default (it needs a connection). An opt-in
  (`--identify`) MAY connect to each listed Tank-G in turn, run the confirmed handshake only, and add
  its firmware; a pedal that cannot be identified is still listed with the reason.
- **FR-006**: When the selected pedal is not seen, the search MUST say so, naming it.
- **FR-007**: With `--json`, the search MUST print one document (new schema, same envelope and
  `schema_version` rules as the other commands) with the list, possibly empty.
- **FR-008**: Exit codes: 0 when at least one Tank-G is listed, 3 when none, 5 when Bluetooth is
  unavailable. No new exit code is introduced by this feature.

**Selection**

- **FR-009**: The CLI MUST offer `openvave select <ID | NICKNAME | ROW>` with an optional
  `--name NICKNAME`, which remembers that pedal as the default for this user on this computer.
- **FR-010**: Selecting MUST check that the pedal is in range (a scan that stops when it is seen)
  and refuse with exit 3 otherwise, unless `--offline` is given with a full identifier.
- **FR-011**: `select` with no argument MUST select the only Tank-G in range, or list them and
  select nothing when there are several (exit 4) or none (exit 3). The CLI MUST never prompt
  interactively.
- **FR-012**: The selection MUST be stored in a per-user configuration file in the platform's
  standard per-user configuration location, in a documented human-readable format, holding for the
  selected pedal at least: identifier, nickname, when it was selected, and the name and firmware
  last seen. The file MUST contain no other personal data and MUST never be sent anywhere.
- **FR-013**: The configuration location MUST be overridable (environment variable
  `OPENVAVE_CONFIG`) so tests and scripts can use a temporary one.
- **FR-014**: [NEEDS CLARIFICATION: does the configuration remember only the one selected pedal, or
  a list of known pedals, each with a nickname, of which one is the default? A list makes
  `--device home` and switching by nickname work for pedals that are not the default; one entry is
  simpler.]
- **FR-015**: Nicknames MUST be short (1–32 characters: letters, digits, `-`, `_`), unique,
  case-insensitive, and MUST NOT look like an identifier (MAC or UUID form).

**Choosing the pedal for a command**

- **FR-016**: Every pedal command MUST choose its pedal in this order: `--device` (identifier or
  nickname) → `OPENVAVE_DEVICE` → saved selection → the only Tank-G in range (0.4.0 behaviour). The
  first one present decides; later ones are not consulted.
- **FR-017**: With a known target (any of the first three), the scan MUST stop as soon as that
  pedal is seen and MUST NOT connect to any other pedal.
- **FR-018**: An unknown nickname MUST be refused before scanning (exit 2), listing known nicknames.
- **FR-019**: Behaviour when the saved selection is not in range follows the Edge Cases decision;
  in every option a write MUST only go to the selected pedal or one named with `--device` /
  `OPENVAVE_DEVICE` for that run.
- **FR-020**: When several Tank-G are in range and no target is known, commands MUST exit 4 as
  today, list the candidates (numbered, strongest first), and hint both `--device ID` and
  `openvave select ID`.

**Reporting the pedal**

- **FR-021**: Every pedal command MUST print, in human mode, one line on stderr before its result
  naming the pedal (nickname, shortened identifier, signal strength) and how it was chosen. With
  `--json`, the `device` object MUST add `nickname` (or null) and `chosen_by`
  (`device_option`, `environment`, `selected`, `only_one_found`); existing fields are unchanged, so
  `schema_version` stays 2.
- **FR-022**: `openvave device` MUST show the saved selection (or that there is none) and the
  configuration path without using Bluetooth; `--check` MUST add a scan reporting whether it is in
  range; `--json` MUST print one document.
- **FR-023**: After a successful connection, the name and firmware last seen for the selected pedal
  SHOULD be updated in the configuration (best effort: a failure to write it MUST NOT fail the
  command).

**Switching and forgetting**

- **FR-024**: Selecting another pedal MUST replace the default and report what it replaced.
- **FR-025**: The CLI MUST offer renaming a nickname and `openvave forget` (forget the selection;
  with a nickname or identifier, forget that entry if FR-014 keeps a list). Forgetting MUST work
  without Bluetooth and on an invalid configuration file (it resets it, keeping a copy).
- **FR-026**: `--device` and `OPENVAVE_DEVICE` MUST NOT change the saved configuration.

**Library**

- **FR-027**: The library MUST expose: listing pedals in range (with signal strength, and with
  nickname/selected flag when given a configuration); loading, saving, renaming and forgetting the
  selection in a given or default configuration location; resolving an identifier or nickname to a
  pedal; and opening a session to a chosen pedal or to "the selected pedal".
- **FR-028**: Opening a session with no device argument MUST keep the 0.4.0 behaviour and MUST NOT
  read the user's configuration implicitly (explicit is better for scripts; MINOR version bump, no
  breaking change).
- **FR-029**: An open session MUST report the pedal it is connected to and how it was chosen.
- **FR-030**: All selection rules (FR-016 to FR-020) MUST be implemented as pure logic covered by
  the hardware-free test suite with fake scan results.

**Connection model**

- **FR-031**: Unless User Story 6 is brought into scope, each command keeps its own connection and
  closes it on exit, and the README MUST state this plainly ("openvave holds the pedal only while a
  command runs; there is nothing to disconnect"), next to the single-connection note.

**Documentation**

- **FR-032**: README Usage MUST cover search, select, show, switch, forget, the choice order, the
  per-computer identifiers on macOS, and the "pedal stops advertising while connected" behaviour;
  the CLI and library contracts and CHANGELOG MUST be updated.

### Out of scope

- Any new pedal message, write, or change to the pedal's advertised name.
- Pairing/bonding, Bluetooth Classic (`TANK-Gv2`), USB-MIDI.
- Talking to two pedals in the same command.
- A pedal identity that is the same on every computer (for example from device-info bytes whose
  meaning is unknown). Recorded as a research idea; it needs two pedals and is `hypothesis` today.
- Syncing the configuration between computers.

### Key Entities

- **Found pedal**: one advertiser seen in a scan: identifier, advertised name, signal strength,
  whether it is a Tank-G; optionally firmware (with `--identify`).
- **Remembered pedal**: identifier (specific to this computer), nickname, selected-at time, name and
  firmware last seen. One of them (or the only one, per FR-014) is the **selection**.
- **Configuration**: the per-user file holding remembered pedals; location overridable; versioned
  format.
- **Pedal choice**: the pedal a command will use and its reason (`device_option`, `environment`,
  `selected`, `only_one_found`).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: With two pedals in range and nothing selected, a first-time user goes from nothing to
  a command acting on the pedal they want in at most three commands (search, select, the command),
  without reading documentation beyond the hints shown.
- **SC-002**: With a pedal selected and in range, a pedal command takes no longer than the same
  command with `--device ID` in 0.4.0 (the scan ends when the pedal is seen), and at least 1 s less
  than 0.4.0 without `--device` (no grace wait).
- **SC-003**: Every pedal command, in every output mode, states which pedal it used (checked for
  100% of commands in the hardware-free suite).
- **SC-004**: In the hardware-free suite, no combination of options, environment, configuration and
  scan result leads to a write reaching a pedal other than the one named for that run or the
  selected one.
- **SC-005**: The search lists every Tank-G in range within the scan time (default 5 s) on macOS
  and Linux; checked on hardware by the owner with their pedal (and a second one if available).
- **SC-006**: Scripts written for 0.4.0 (single pedal, or `--device ID`) behave the same: same
  stdout, same exit codes; only the new stderr line and new JSON fields are added.

## Assumptions

- Defaults taken instead of clarification markers: no interactive prompts anywhere; the firmware is
  opt-in in the search (`--identify`); an unselected single pedal is used but not auto-saved;
  `OPENVAVE_DEVICE` sits between `--device` and the saved selection; the "acting on" line goes to
  stderr; no new exit codes; `select` checks the pedal is in range unless `--offline`; the library
  never reads the configuration implicitly; an invalid configuration stops pedal commands (exit 2)
  rather than guessing.
- Command names (`scan`, `select`, `device`, `forget`, rename) are proposals for planning; the CLI
  contract fixes them.
- The owner has one pedal; behaviour with two is tested with fake scan results, and on hardware only
  if a second pedal is available. Hardware checks are reads only (scan, connect, handshake) and are
  run by the owner in their own terminal.
- The configuration is per user and per computer; identifiers are not portable across computers on
  macOS, and the docs say so.
- The pedal's behaviour of not advertising while connected holds for any central (observed with the
  phone app, fw 96).
