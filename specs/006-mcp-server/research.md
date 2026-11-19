# Research: MCP server (spec 006)

Decisions taken while planning, each with what was checked. SDK facts come from spikes run on
2026-11-19 against `mcp` **2.3.0** (the current release on PyPI), in-process with its `Client`.

## R1. SDK: the official `mcp` package, 2.x, `MCPServer`

- **Decision**: depend on `mcp>=2.3,<3` as the optional extra `openvave[mcp]` (and in the dev
  group, so the hardware-free suite tests the server). Build the server with
  `mcp.server.mcpserver.MCPServer` (the 2.x name of FastMCP) and run it with `run_stdio_async()`.
- **Rationale**: official, maintained, typed; decorators give input schemas from Python signatures,
  `ToolAnnotations`, structured output, resources, and an in-process `Client(server)` for tests.
  2.x is what `pip install mcp` gives today; 1.x code (`mcp.server.fastmcp`) fails to import on 2.x,
  so pinning the major avoids a silent break.
- **Alternatives**: low-level `mcp.server.lowlevel.Server` (more code for the same result);
  `mcp<2` (outdated, and the 2.x import error shows the API moved); the third-party `fastmcp`
  package (another dependency tree, not official); hand-written JSON-RPC over stdio (re-implements
  the protocol, Constitution VII).
- **Cost**: `mcp` pulls pydantic, anyio, httpx, starlette, uvicorn, opentelemetry-api and others
  (~28 packages). Acceptable only because it is an **optional** extra: `pip install openvave`
  keeps `bleak` as the only runtime dependency (FR-002). Recorded in Complexity Tracking.

## R2. Where the server lives

- **Decision**: a new subpackage `openvave.mcp_server` (`server.py` tool/resource registration,
  `holder.py` connection holder, `results.py` result shapes, `backups.py` backup folder). It imports
  the public library and reuses `openvave.cli.render` JSON builders and `openvave.cli` value
  parsing, so a tool's result is the CLI's `--json` document for the same operation (SC-007). The
  CLI imports the subpackage lazily only in `openvave mcp`.
- **Rationale**: the server is another front end, like the CLI (Constitution V: library first). Not
  named `openvave.mcp` to avoid any confusion with the top-level `mcp` package in imports and
  tracebacks.
- **Alternatives**: moving the JSON builders out of `cli/` into the library first (cleaner, but a
  refactor of 1 400 lines touched by the parallel polish session; deferred until a third front end
  needs them).

## R3. Opt-ins as per-call arguments (clarification 1)

- **Decision**: write tools take `dry_run`, `experimental`, `discard_edits` (where the CLI has it)
  and save/restore take `unsafe`, all `bool = False`, passed to the library unchanged. Refusals come
  from the library's plan (`plan.refusal`) and become tool errors with the reason and the argument
  name. `--read-only` removes every write tool at start (`MCPServer.remove_tool`); a call by name
  then gets the SDK's unknown-tool error, and the status tool reports `read_only: true`.
- **Rationale**: parity with the CLI, which the owner asked for; the library already enforces
  every gate, so the server adds no rule of its own (FR-003).

## R4. Annotations

- **Decision**: `ToolAnnotations(read_only_hint, destructive_hint, idempotent_hint,
  open_world_hint=False)` per tool, from one table in [contracts/tools.md](contracts/tools.md);
  a test compares the listed tools with the table (SC-004). Tool descriptions name the opt-ins
  each tool accepts and what they unlock.
- **Spike**: `list_tools()` returns the annotations as given; defaults are `None`, so every field
  is set explicitly.

## R5. Errors

- **Decision**: library errors (`OpenvaveError` and subclasses, `ValueError` from value parsing)
  are caught in one wrapper and re-raised as `mcp.server.mcpserver.exceptions.ToolError` with a
  single-line JSON-ish text: `kind`, `message`, `hint` (the CLI's hint for the same error),
  `exit_code` (the CLI's), and, for errors raised mid-batch / mid-sequence, the partial result
  (`edit_json` / `sequence_json`). Any other exception is logged to stderr with its traceback and
  returned as `kind: internal`.
- **Spike**: a `ToolError` becomes `isError: true` with the text as content; the server keeps
  serving. The SDK prefixes `Error executing tool <name>:`; tests match the suffix.

## R6. Structured results

- **Decision**: every tool returns a `dict` (the SDK publishes an object output schema and sends
  both `structuredContent` and a JSON text block) built from the CLI's JSON builders; each result
  adds a short `summary` string (the first line of the CLI's human output) so clients that only show
  text still say something useful.
- **Alternatives**: pydantic models per tool for precise output schemas (duplicates the CLI's
  JSON schemas, which already exist and are tested; can come later).

## R7. Connection holder

- **Decision**: one `PedalHolder` per server, owning at most one `TankG` and an `asyncio.Lock`.
  `async with holder.use() as pedal` (every pedal tool):
  1. acquire the lock (calls queue; no interleaved requests on the single link);
  2. cancel the idle-release timer;
  3. if no session, or the session was lost (`not pedal.is_connected` after an open), `close()` it
     and open a new one: resolve the target (session choice → `--device` → `OPENVAVE_DEVICE` →
     default → only one), build the transport through the same factory as the CLI, `open()`, record
     last seen; **one** attempt, errors propagate as tool errors;
  4. yield; a `ConnectionLostError` raised inside propagates unchanged (with its partial result)
     and leaves the session in the lost state, so the **next** call reconnects (FR-012); nothing is
     resent;
  5. release the lock and re-arm the idle timer (`--idle-release`, default 300 s; 0 disables).
  `disconnect()` and shutdown take the lock and `close()`; `status()` reads holder fields only,
  without the lock (never waits behind a pedal call).
- **Rationale**: spec 005's library lifecycle (`open`, `close`, `is_connected`, lost state that
  fails fast) is exactly what is needed; the holder only adds the choice rule, the lock and the
  timer. The CLI's `choice.choose/annotate/record_seen` are reused (they take a namespace; the
  holder passes a small one with `device`).
- **Alternatives**: reconnect inside the same call after a lost link (would hide that a write may
  have been lost, and risks resending; rejected by FR-012); a connection per call like the CLI
  (clarification 2 chose holding with idle release).

## R8. Concurrency model

- **Decision**: run on the SDK's asyncio backend (anyio over asyncio, the default), so `TankG`
  (asyncio, bleak) runs on the same loop. The holder lock serialises pedal tools; tools that need
  no pedal (status, resources, backups list, select without scan) never take it.
- **Spike**: `MCPServer` handlers are `async def`; `asyncio` primitives work inside them.

## R9. Elicitation for save/restore (clarification 3)

- **Decision**: save and restore declare a parameter filled by a resolver
  (`Annotated[ElicitationResult[Confirm], Resolve(ask)]`). The resolver returns
  `Elicit(message, Confirm)` only when `unsafe` is true, `dry_run` is false and the client declared
  the elicitation capability; otherwise it returns a pre-made "not asked" accepted result. The
  tool body then: not asked → proceed (CLI parity); accepted with `confirm=true` → proceed;
  anything else (`decline`, `cancel`, `confirm=false`) → tool error `declined_by_owner`, nothing
  sent. The message names the action, the target position(s) and the backup folder; it is built
  from the arguments (no pedal read inside the resolver).
- **Spike**: with the consumer annotated with the full `ElicitationResult[...]` union, decline and
  cancel reach the tool body in both the legacy (initialize, server-to-client request mid-call)
  and the modern (`InputRequiredResult` round-trip) protocol modes, and the tool body runs once.
  Calling `ctx.elicit()` directly fails in the modern mode (`NoBackChannelError`), and a
  `| None` in the annotation makes decline abort with the SDK's own message, so both are avoided.

## R10. Backup folder (clarification 4)

- **Decision**: `$XDG_DATA_HOME/openvave/backups`, else `~/.local/share/openvave/backups`;
  `%LOCALAPPDATA%\openvave\backups` on Windows; `--backup-dir DIR` overrides. Created (mode 0700)
  on first write. Manual backups: `tankg-backup-<time>.json`; automatic:
  `tankg-backup-<time>-before-save|restore.json` (the CLI's `files.automatic_backup_path`), never
  overwriting. Restore takes `file` as a **name**: resolved inside the folder, refused when it is
  absolute, contains a path separator or `..`, or resolves (after links) outside the folder; then
  `openvave.backup.restore_problems` as the CLI.
- **Rationale**: a desktop client starts the server in an arbitrary working directory; confining
  restore to one folder keeps a model from reading arbitrary files.

## R11. Changes tool

- **Decision**: the holder keeps the last reads of global, current preset and status (set by the
  read tools and by the changes tool itself). `pedal_changes(wait_seconds=0)` reads the three
  regions; with a baseline it returns the decoded `diff` (field name, before, after) and the pedal
  state before/after; with `wait_seconds > 0` it polls every 0.5 s until a change or the wait ends
  (capped at 30 s), holding the lock for that time. First call: returns the baseline only.
- **Rationale**: same reads and diff as `watch` (`decode_region`, `diff`), no streaming needed.
- **Alternatives**: MCP resource subscriptions with a background poller (needs a long-lived
  polling loop holding the radio; more moving parts; later if wanted).

## R12. Pedal selection from the server

- **Decision**: `pedal_select(target, remember=False, nickname=None)`: target = nickname (no scan),
  full identifier (checked by a scan), or identifier prefix (≥ 4 hex digits, one match in a scan).
  Without `remember` it only sets the holder's session choice (`chosen_by: "session"`… mapped to
  the existing `device_option` value to keep the JSON enum unchanged); with `remember` it also saves
  the default (and nickname) through `KnownDevices.select().save()`. A held connection to another
  pedal is closed first. `pedal_scan()` = library `scan()` + known nicknames; when connected, the
  held pedal is added as `connected: true`.

## R13. Logging and stdout

- **Decision**: `openvave mcp` configures logging to stderr (`--trace` enables the hex trace as
  in the CLI) before the SDK takes stdin/stdout. Tests assert no `print` reaches stdout during a
  tool call (capsys).

## R14. Testing

- **Decision**: `tests/mcp/` with an in-process `mcp.Client(server)` (both `mode="legacy"` and
  `"auto"` for elicitation), `FakeTransport.from_capture(...)` sources and the existing scripted
  fakes; a factory fixture counts opens/handshakes. Idle release uses an injectable clock/sleep so
  no test waits 5 minutes. The suite never imports bleak backends.
