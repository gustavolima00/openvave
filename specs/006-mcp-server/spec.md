# Feature Specification: MCP server, so an AI assistant can read and control a Tank-G

**Feature Branch**: `claude/spec-006-mcp-server-1da712` (feature directory `006-mcp-server`)

**Created**: 2026-11-19

**Status**: Draft

**Input**: User description: "An `openvave mcp` command (stdio transport, official MCP Python SDK as
an optional extra) so an AI assistant (Claude Desktop, Claude Code, etc.) can read and control a
Tank-G pedal by wrapping the existing library only (no new protocol writes). Tools: scan/select
pedal, device status, info, read current preset with named fields and effect types, changes since
last read, set one or several fields, preset select/reload, backup to file, bypass on/off; gated
dangerous actions: preset save/restore (persistent) and experimental writes, off by default,
enabled by server flags, tool annotations (read-only / destructive / idempotent hints), dry-run
previews. One long-lived connection held by the server, opened lazily, reconnect on demand after a
lost link, explicit disconnect so the phone app can take the pedal. Resources (byte map, effect
type docs, safety notes) and maybe prompts. Config snippets for Claude Desktop / Claude Code in the
docs. Offline tests with the fake transport; hardware gate run by the user in their terminal."

**Builds on**: [`005-device-selection`](../005-device-selection/spec.md) (known pedals, the
`--device` > `OPENVAVE_DEVICE` > default > only-one-in-range rule, no fallback, long-lived library
connection with `open` / `close` / `is_connected`) and
[`004-remote-edit-save-restore`](../004-remote-edit-save-restore/spec.md) (normal-mode editing,
several fields per connection, typed knobs, reload, select, bypass, loopback, save/restore with
`--unsafe` and automatic backups).

**Protocol source of truth**: [`specs/protocol/command-layer.md`](../protocol/command-layer.md)
("Write messages") and [`specs/protocol/`](../protocol/). This feature sends **no new pedal
message** and adds no new write target: every tool calls a library operation that already exists,
with the same refusals, opt-ins, checks and backups as the matching CLI command.

## Starting point (0.5.0, 2026-11-19)

- Everything the owner can do with the pedal is reachable from the library and the CLI: identify,
  decode the current preset and global settings, watch changes, back up the 36 stored presets, set
  one or several fields of the current sound (typed MOD FX / DLY MIX / RVB DECAY knobs), select and
  reload presets, bypass, loopback (experimental), and save / restore stored presets (`--unsafe`,
  automatic verified backup first).
- Writes are gated twice: `experimental` for messages not yet `confirmed` (block switches, LED
  colour, loopback) and for firmware other than 96; `unsafe` for anything that overwrites stored
  presets. Every write supports a plan (dry-run) that reads the pedal and shows the exact frames
  without sending.
- The library keeps one connection open for many operations (`open` / `close` / `is_connected`);
  a lost link makes every later operation fail at once, and nothing reconnects by itself.
- The pedal accepts **one** Bluetooth connection at a time and stops advertising while connected:
  while openvave holds it, the phone app and other openvave commands cannot see it.
- Known pedals and the default pedal live in one configuration file, shared by every openvave
  command.

## User Scenarios & Testing *(mandatory)*

Actors:

- **Pedal owner**: talks to an AI assistant (Claude Desktop, Claude Code or another MCP client)
  configured to start openvave's server; asks in plain language ("make it darker", "what reverb is
  on?", "back up my presets", "save this as 2A").
- **AI assistant**: the MCP client and its model; calls the server's tools, reads its resources,
  and must be able to tell from the tool list which calls only read, which change the sound, and
  which change stored presets.

### User Story 1 - Ask the assistant what the pedal is doing (Priority: P1)

The owner adds openvave to the assistant's configuration once. From then on they can ask what the
pedal is set to, and the assistant answers from the live pedal: firmware, mode/state, loaded
preset, and every decoded field of the current sound by name (gain, treble, which amp, which MOD
FX type at which position, reverb type and decay, …), with the same names and values the CLI uses.

**Why this priority**: reading is safe, needs no opt-in, and is the base of every other story.

**Independent Test**: with the fake transport loaded from a fw 96 capture, start the server
in-process, list its tools, call the info and current-preset tools, and compare the result with
what `openvave info --json` and `openvave preset dump --json` produce from the same capture.

**Acceptance Scenarios**:

1. **Given** the server configured in the assistant and one pedal switched on (phone app closed),
   **When** the owner asks what preset is loaded, **Then** the assistant calls a read-only tool, the
   server connects to the pedal (first use), and the answer names the pedal, firmware, state and
   loaded preset position.
2. **Given** the same, **When** the owner asks for the current sound, **Then** the tool returns
   every decoded field with name, displayed value, raw value, confidence and, for typed knobs, the
   effect type and position.
3. **Given** the pedal is bypassed or in tuner mode, **When** the current preset is read, **Then**
   the result says so (state) instead of decoding fields that do not apply, as `preset dump` does.
4. **Given** the phone app holds the pedal, **When** any pedal tool is called, **Then** it returns
   a tool error that says no pedal was found and that the phone app (or another program) may hold
   it, and the server keeps running.
5. **Given** the pedal is firmware other than 96, **When** it is read, **Then** results carry the
   untested-firmware warning.

---

### User Story 2 - Change the current sound by talking (Priority: P1)

The owner asks for a change ("more gain", "spring reverb at 10", "turn the delay on") and the
assistant changes the current sound through the server: one or several fields in one call, with
the same rules as `openvave set`. Changes are never saved; the owner can ask to discard them
(reload) or to load another preset.

**Why this priority**: remote editing is the main value of an assistant over the CLI.

**Independent Test**: on the fake transport, call the set tool with one field, with several
fields, with a typed knob, with an out-of-range value and with an experimental field; check the
frames sent, the reported before/after values, and the refusals; call preview mode and check that
nothing is sent.

**Acceptance Scenarios**:

1. **Given** a connected pedal in normal mode, **When** the assistant sets `gain=95` and
   `reverb_decay=spring:10` in one call, **Then** the server applies them as one batch (as
   `openvave set gain=95 reverb_decay=spring:10`) and returns, per field, the value before, the
   value after and whether it was applied, plus a reminder that nothing is saved and how to discard
   it.
2. **Given** the same, **When** the assistant calls the set tool in preview mode, **Then** the
   result lists every frame that would be sent and every field change, and nothing is sent.
3. **Given** a field that needs the experimental opt-in (block switch, LED colour), **When** the
   server was started without allowing experimental writes, **Then** the call is refused before
   anything is sent, the error names the reason and says how the owner can enable it (a server
   option in the assistant's configuration), and no other field of the batch is sent.
4. **Given** the pedal is in tuner mode or bypassed, **When** a set is requested, **Then** it is
   refused with the library's reason (`tuner_mode`, `bypassed`).
5. **Given** unsaved edits, **When** the assistant asks to reload or select another preset,
   **Then** the call is refused unless it explicitly says to discard edits, as the CLI's
   `--discard-edits`.
6. **Given** the owner asks to load preset 2C, **When** the assistant calls preset select, **Then**
   the server loads it and reports the loaded position afterwards.
7. **Given** the owner asks for a clean sound, **When** the assistant calls bypass on, **Then** the
   pedal is bypassed and the result says which position to return to; bypass off returns there.

---

### User Story 3 - One connection the assistant can hold and give back (Priority: P1)

The server connects when a tool first needs the pedal and keeps that connection for the following
calls, so a conversation of many small changes does not scan and handshake each time. The owner
(or assistant) can ask which pedal the server is using and whether it is connected, can disconnect
so the phone app can take the pedal, and the next pedal tool reconnects. A lost link (pedal
switched off, out of range) does not kill the server: the call reports it and the next call
reconnects.

**Why this priority**: the pedal accepts one connection at a time; a server that holds it forever
locks the phone app out, and one that dies on a lost link breaks the conversation.

**Independent Test**: on the fake transport, call two read tools and check one connection was
opened; call disconnect and check it was closed; call a read tool and check a new connection was
opened; simulate a lost link between calls and check the next call returns a lost-link error or
reconnects as the requirements say, and the server stays up.

**Acceptance Scenarios**:

1. **Given** the server just started, **When** no pedal tool has been called, **Then** the server
   holds no Bluetooth connection and has not scanned.
2. **Given** two read calls in a row, **When** they run, **Then** the pedal is scanned for and
   handshaken once.
3. **Given** a connection is held, **When** the status tool is called, **Then** it reports the
   pedal (nickname, identifier, how it was chosen), firmware, whether connected, and since when,
   without sending anything to the pedal.
4. **Given** a connection is held, **When** disconnect is called, **Then** the connection is closed
   and the result says the pedal is free for the phone app; calling disconnect again is harmless.
5. **Given** the link was lost (pedal switched off) between calls, **When** the next pedal tool is
   called, **Then** the server tries one fresh connection before running it; if the pedal is not
   found the error says so and the server keeps running.
6. **Given** the link is lost **during** a write, **When** the call returns, **Then** it reports the
   library's partial result (applied / unknown / not applied / not sent) and **never** resends the
   write on the new connection.
7. **Given** the server is idle with a connection held for longer than the release timeout,
   **When** the timeout passes, **Then** the server closes the connection by itself so the phone
   app can take the pedal, and the next pedal tool reconnects.

---

### User Story 4 - Choose among pedals from the assistant (Priority: P2)

The owner with two pedals asks the assistant to list the pedals in range and use one of them. The
server follows the same choice rule as the CLI (explicit pedal, then the environment variable, then
the saved default, then the only one in range) and never falls back to another pedal.

**Why this priority**: most owners have one pedal; the rule already exists, the server only needs
to expose it.

**Independent Test**: on a fake scanner with two pedals and a temporary configuration file, call
scan, select one for the session, check every later tool acts on it; call select with "remember"
and check the configuration file's default changed.

**Acceptance Scenarios**:

1. **Given** two pedals in range, **When** the assistant calls scan, **Then** both are listed
   (identifier, name, signal strength, nickname, default marker) and nothing is connected to; if
   the server holds a connection, its pedal is listed as connected (it does not advertise).
2. **Given** two pedals and no default, **When** a pedal tool is called without a choice, **Then**
   it refuses with the list of pedals and says to choose one (select tool).
3. **Given** the assistant selects pedal `home` for the session, **When** later tools run, **Then**
   they act on `home`; the saved default is unchanged unless the select call asked to remember it.
4. **Given** a connection to pedal A is held, **When** pedal B is selected, **Then** the connection
   to A is closed before B is used.
5. **Given** the chosen pedal is not in range, **When** a pedal tool runs, **Then** it refuses
   naming the pedal and listing what was seen; no other pedal is used.

---

### User Story 5 - Back up, save and restore, only when the owner allowed it (Priority: P2)

The owner asks the assistant to back up the presets (always allowed, read-only, written to a file),
and, only if they started the server with the persistent-writes option, to save the current sound
to a position or restore presets from a backup. Every save/restore takes the automatic verified
backup first, exactly as the CLI does, and the assistant can preview what would change.

**Why this priority**: backups are valuable and safe; save/restore are the only writes that can
lose the owner's presets, so they come last and behind the strongest gate.

**Independent Test**: on the fake transport, call backup and check the file and its verification;
start the server without the persistent option and check save/restore are refused (or absent) and
nothing is sent; start it with the option and check preview sends nothing, the real call writes
the automatic backup before the first write and returns the sequence result.

**Acceptance Scenarios**:

1. **Given** any server options, **When** the assistant calls backup, **Then** all 36 presets are
   read, verified and written to a new file in the backup folder (never overwriting), and the
   result gives the path and a summary (preset count, firmware, warnings).
2. **Given** the server started **without** persistent writes allowed, **When** the assistant asks
   to save or restore, **Then** nothing is sent and the error says this server does not allow
   changing stored presets and how the owner can enable it.
3. **Given** persistent writes allowed, **When** the assistant previews a save to 2A, **Then** it
   gets the planned steps and frames and whether 2A already holds this sound, and nothing is sent.
4. **Given** persistent writes allowed, **When** the assistant saves to 2A, **Then** the server
   writes the automatic backup first (path reported), runs the library's save sequence, and returns
   every step's outcome; if the backup fails nothing is written.
5. **Given** persistent writes allowed, **When** the assistant restores one slot or all presets
   from a backup file, **Then** the file is checked before connecting, the slots that differ are
   listed, the automatic backup is taken, and the result reports every step; a file from another
   firmware also needs the experimental opt-in.
6. **Given** a restore file path outside the backup folder, **When** restore is called, **Then**
   it is refused unless the server allows other folders.

---

### User Story 6 - See what changes on the pedal (Priority: P3)

The owner turns a knob on the pedal and asks the assistant "what did I just change?". The server
reports which fields changed since the last read (or within a short wait), with names and old/new
values, as `openvave watch` would.

**Why this priority**: useful for learning and for "match what I'm dialling in", but every other
story stands without it.

**Independent Test**: on the fake transport with a scripted change between reads, call the changes
tool and check the reported fields; with no change within the wait, check it says nothing changed.

**Acceptance Scenarios**:

1. **Given** a previous read of the current sound, **When** the owner moves a knob and the
   assistant calls the changes tool, **Then** it lists each changed field (name, before, after) and
   any state change (e.g. bypass, preset change).
2. **Given** a wait time, **When** nothing changes within it, **Then** the tool returns "no change"
   after at most that time; the wait is capped so a call cannot hold the server indefinitely.

---

### User Story 7 - Reference material for the assistant (Priority: P3)

The assistant can read, without touching the pedal, the list of writable fields with their ranges
and types, the effect types of the typed knobs, the byte map, and the safety rules, so it can
plan a change and explain it before calling a tool.

**Why this priority**: improves answers but tools already return names and refusals.

**Independent Test**: list the server's resources and read each; check content matches the
library's tables (writable fields, effect types, byte map) and the safety summary.

**Acceptance Scenarios**:

1. **Given** the server, **When** the assistant lists resources, **Then** it sees the writable
   fields, effect types, byte map and safety notes, each readable without a pedal connection.
2. **Given** the assistant reads the writable fields, **Then** every field the set tool accepts is
   listed with its value syntax and range, and which ones need the experimental opt-in.

---

### Edge Cases

- **openvave without the MCP extra installed**: `openvave mcp` exits with a clear message naming
  the install command; nothing else of openvave changes.
- **Two tool calls at once** (clients may send requests concurrently): pedal operations run one at
  a time on the single connection; a second call waits for the first to finish rather than
  interleaving requests.
- **A CLI command run while the server holds the pedal**: the CLI does not see the pedal (exit 3
  with the existing hint); the server's status/disconnect tools are the way to free it.
- **Configuration file invalid**: tools that need nicknames or the default report the error with the
  existing hint; explicit identifiers still work, as in the CLI.
- **Server stdout**: stdout carries only protocol messages; every log and warning goes to stderr,
  so a stray print cannot break the client.
- **Assistant asks for a field that does not exist or a malformed value**: the tool returns the
  library's refusal (`unknown_field`, value syntax error) with the list of valid fields; nothing is
  sent.
- **Client cancels a call** while a write is in flight: the server does not resend; the next call
  sees the pedal's actual state on its own read.
- **Firmware other than 96**: every write needs the experimental opt-in (library rule); reads work
  with a warning.
- **Untrusted input in tool arguments**: file paths for backup/restore are confined to the backup
  folder unless the owner allowed more; nicknames and identifiers are validated by the existing
  rules.
- **Server stopped by the client** (assistant closed) while connected: the connection is closed on
  shutdown so the pedal advertises again.

## Requirements *(mandatory)*

### Functional Requirements

**Server and installation**

- **FR-001**: openvave MUST provide an `openvave mcp` command that runs an MCP server over standard
  input/output, for MCP clients that start local servers (Claude Desktop, Claude Code and others).
- **FR-002**: The MCP support MUST be an optional install extra; installing openvave without it
  MUST keep the 0.5.0 dependencies, and `openvave mcp` without it MUST exit 2 with the install
  command.
- **FR-003**: The server MUST be a thin layer over the public library: every tool MUST call
  existing library operations and MUST NOT encode, send or relax anything the library does not
  already allow. No new pedal message, write target or protocol code.
- **FR-004**: The server MUST write nothing but protocol messages to stdout; logs, warnings and
  traces go to stderr. `--trace` (hex trace of frames, as in the CLI) MUST be available.
- **FR-005**: Server options MUST be set at start (command-line flags, usable in the client's
  configuration file) and MUST be reported by the status tool: allowed write levels, chosen pedal
  option, backup folder, idle release timeout.

**Write levels and gating**

- **FR-006**: The server MUST have write levels set at start, from least to most powerful:
  (a) **read-only** — no tool that changes the pedal; (b) **volatile** — changes to the current
  sound, preset select/reload and bypass using `confirmed` messages (default);
  (c) **experimental** — also messages not yet `confirmed` (block switches, LED colour, loopback)
  and writes on untested firmware, as the CLI's `--experimental`;
  (d) **persistent** — also save and restore of stored presets, as the CLI's `--unsafe`.
  Experimental and persistent MUST be independent opt-ins (persistent does not imply experimental,
  as in the library).
- **FR-007**: Tools whose level is not enabled MUST NOT be listed to the client; a call to one by
  name MUST return a tool error naming the server option that enables it. Within an enabled tool,
  a field or argument needing a higher level (e.g. an experimental field in a set batch) MUST be
  refused with the library's reason and the option that enables it, before anything is sent.
- **FR-008**: Every tool MUST carry MCP annotations that match what it does: read-only tools
  `readOnlyHint=true`; volatile write tools `readOnlyHint=false, destructiveHint=false`; save and
  restore `destructiveHint=true`; `idempotentHint` true only where calling twice equals once (set
  to the same values, select the same preset, bypass on, disconnect, select pedal);
  `openWorldHint=false` for all (they act only on the local pedal and files).
- **FR-009**: Every write tool MUST accept a preview flag (dry-run) that runs the library's plan —
  reads only — and returns the exact frames and the planned changes or steps without sending.
- **FR-010**: Save and restore MUST also require an explicit confirmation argument in the call
  (in addition to the server's persistent level); a call without it returns the preview and says
  what to add to run it.

**Connection**

- **FR-011**: The server MUST connect lazily (no scan or connection at start), keep one connection
  for later calls, and run pedal operations one at a time (calls queue; no interleaved requests).
- **FR-012**: When the held connection was lost, the next pedal tool MUST make one fresh connection
  attempt before running; it MUST NOT retry beyond that and MUST NOT resend any write that was in
  flight when the link was lost (the library's partial result is returned for that call).
- **FR-013**: A disconnect tool MUST close the connection (idempotent) so the phone app or the CLI
  can use the pedal; the next pedal tool reconnects.
- **FR-014**: The server MUST close an idle connection after a release timeout (default
  `5 minutes`, configurable, `0` disables) and on shutdown.
- **FR-015**: A status tool MUST report, without sending anything to the pedal: connected or not,
  the pedal (nickname, identifier, how it was chosen, signal strength at connection), firmware and
  untested flag, connected since, last error, and the server options of FR-005.

**Pedal choice**

- **FR-016**: The server MUST choose the pedal with the 0.5.0 rule: the pedal selected in this
  server session, else the server's `--device` option, else `OPENVAVE_DEVICE`, else the saved
  default, else the only Tank-G in range; never fall back to another pedal; several pedals and no
  choice is a tool error listing them.
- **FR-017**: A scan tool MUST list Tank-G pedals in range (identifier, name, signal strength,
  nickname, default marker) without connecting, and MUST report a pedal the server is connected to
  as connected (it does not advertise).
- **FR-018**: A select tool MUST choose a pedal (identifier, unique identifier prefix of ≥ 4 hex
  digits, or nickname) for the server session, closing any connection to another pedal; with a
  `remember` argument it MUST also save it as the default (and optional nickname) in the shared
  configuration file, with the same validation as `openvave select`.

**Tools (each maps to an existing library operation)**

- **FR-019**: Read tools: pedal info (identity, state, loaded preset); current preset decoded
  (every field with name, display, raw, confidence, typed-knob type and position, state); global
  settings decoded; changes since the last read (FR-024).
- **FR-020**: Set tool: one or several fields in one call, with the value syntax of `openvave set`
  (`POSITION`, `TYPE:POSITION`, `raw:N`, `on/off`, `#rrggbb`), applied as one batch with the
  library's per-field outcomes (applied / unknown / not applied / not sent) and the "not saved;
  discard with reload" reminder.
- **FR-021**: Preset tools: select by position (`1A`–`9D`) or index; reload (discard edits); both
  refuse to lose unsaved edits unless the call says to discard them.
- **FR-022**: Bypass on and bypass off (to a position; default the position bypass on reported in
  this session). Loopback on/off at the experimental level.
- **FR-023**: Backup tool (read-only level and above): reads and verifies all 36 presets and writes
  a new file in the backup folder (never overwriting); returns the path and summary. Save tool
  (persistent level): store the current sound in the loaded or a given position. Restore tool
  (persistent level): one slot or all from a backup file in the backup folder. Both take the
  automatic verified backup first and return the library's sequence result.
- **FR-024**: The changes tool MUST compare the pedal's current reads with the server's previous
  read (or poll for up to a wait time capped at `30 s`) and return changed fields by name with old
  and new values and any state change; the first call returns the baseline.
- **FR-025**: Tool results MUST be structured (the same JSON shapes as the CLI's `--json` output
  where one exists) with a short human-readable summary, so any client can show them.
- **FR-026**: Library errors MUST become tool errors (not server crashes) carrying the refusal or
  error kind, the message and the hint the CLI prints; the server MUST keep running after any
  pedal error.

**Resources and prompts**

- **FR-027**: The server MUST expose read-only resources that need no pedal: writable fields (value
  syntax, range, level needed), effect types of the typed knobs, the byte map, and a safety
  summary (volatile vs persistent, write levels, what openvave never sends).
- **FR-028**: Prompts are out of scope for this feature (see Assumptions).

**Documentation and tests**

- **FR-029**: Documentation MUST explain installing the extra, configuring Claude Desktop and
  Claude Code (copy-paste snippets, including the options for experimental and persistent levels),
  the connection behaviour (one connection, phone app, disconnect, idle release), the tool list
  with levels and annotations, and safety.
- **FR-030**: The hardware-free test suite MUST cover every tool, resource, write level,
  annotation, preview, the connection lifecycle (lazy, reuse, disconnect, idle release, lost link,
  shutdown) and error mapping, using the fake transport and an in-process MCP client. A hardware
  gate, run by the owner in their own terminal and assistant, MUST check the reads, one volatile
  write, disconnect/phone-app hand-over and lost link on fw 96.

### Key Entities

- **Server options**: write levels enabled, pedal option, backup folder, allowed restore folders,
  idle release timeout, trace flag. Fixed for the life of the server.
- **Server session**: the chosen pedal for this session (and why), the held connection (or none),
  connected since, last read baseline (for changes), the position to return to after bypass, last
  error.
- **Tool**: name, write level, annotations, input arguments, structured result.
- **Resource**: read-only reference document (writable fields, effect types, byte map, safety).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An owner can go from a fresh install to asking their assistant "what preset is
  loaded?" by following the docs in under 10 minutes, without editing anything but the client's
  configuration file.
- **SC-002**: After the first call, read tools answer without a new scan or handshake: at least 10
  consecutive calls in a conversation use one connection.
- **SC-003**: With the default options, no tool call — whatever its arguments — can change a stored
  preset or send a message that is not `confirmed`; verified by tests that try every tool with
  every gated argument.
- **SC-004**: 100 % of the tools carry annotations consistent with their level (tested), and every
  write tool has a preview that sends nothing (tested).
- **SC-005**: After a lost link, the next call recovers (reconnects or reports "not found") within
  the scan timeout, and the server process never exits because of a pedal error.
- **SC-006**: After disconnect or the idle release timeout, the phone app can connect to the pedal
  without restarting the assistant.
- **SC-007**: Every value the server reports for a capture equals what the CLI's JSON reports for
  the same capture (field names, values, confidence).

## Assumptions

- **Default write level is volatile** (confirmed messages only, never stored presets), because
  changing the current sound is the main reason to have the server and is undone by reload or a
  power cycle; owners who want a read-only assistant start it with the read-only option.
  *(To confirm in clarify.)*
- **Gated tools are hidden** from the tool list when their level is off, so the assistant cannot
  even try them; a direct call still returns an explanatory error. *(To confirm in clarify.)*
- **Idle release timeout of 5 minutes** balances fewer reconnects against letting the phone app
  take the pedal. *(To confirm in clarify.)*
- **Pedal selection from the assistant is per server session** unless `remember` is passed, so an
  assistant cannot silently change what the CLI uses.
- **Backup folder** defaults to a per-user data folder (e.g. `~/.local/share/openvave/backups`,
  platform equivalent), because the working directory of a server started by a desktop assistant
  is not meaningful; configurable by option.
- **Prompts are out of scope**: tools and resources cover the stories; prompt templates can come
  later if a concrete need appears (Constitution VII, YAGNI).
- **stdio only**: network transports (HTTP/SSE) are out of scope; a networked pedal server would
  need authentication and is not requested.
- **The MCP SDK is the official Python SDK**, added only as an optional extra (justified in the
  plan's Complexity Tracking).
- **Hardware gate** steps run in the owner's own terminal / assistant; this development session has
  no Bluetooth permission.
- **Out of scope**: new protocol messages, edit/tuner mode control, a web UI, a CLI interactive
  shell, multi-pedal simultaneous connections, remote (non-local) access.
