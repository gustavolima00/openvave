# Quickstart: validating feature 006

Contract: [contracts/tools.md](contracts/tools.md). State: [data-model.md](data-model.md).
Sections 1–2 need no pedal. Section 3 is run by the owner with their own pedal, terminal and
assistant (this development session has no Bluetooth permission).

## 1. Hardware-free suite (every milestone)

```bash
uv sync
```

```bash
uv run pytest
```

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy
```

Expected: green. `tests/mcp/` drives the server in-process with the SDK's `Client` against
`FakeTransport` captures; no Bluetooth backend is loaded and no test waits for the real idle
timeout.

## 2. The server starts and lists its tools (M0+)

Without the extra (a fresh environment):

```bash
uv run --no-dev --isolated openvave mcp
```

Expected: `error: the MCP server needs the 'mcp' extra: pip install 'openvave[mcp]'`, exit 2.

With the extra, the MCP Inspector (needs Node) lists the tools and resources without a pedal:

```bash
npx @modelcontextprotocol/inspector uv run --extra mcp openvave mcp
```

Expected: the tools of the contract table with their annotations; `pedal_status` answers
`connected: false` without scanning. With `--read-only` the write tools are absent.

## 3. Hardware gate (owner, fw 96; M4)

Setup, in the owner's assistant configuration (docs/mcp.md has the snippets):

```bash
claude mcp add openvave -- uvx --from 'openvave[mcp] @ git+https://github.com/gustavolima00/openvave' openvave mcp
```

Phone app closed, pedal on. In a conversation:

1. "Qual preset está carregado?" → `pedal_info`: firmware 96, state, loaded position. Then
   `pedal_status`: `connected: true`.
2. "Mostra o som atual" → `preset_read`: every field by name, typed knobs with type and position;
   compare with `openvave preset dump --json` run afterwards (after disconnecting).
3. Three more reads in a row → no new scan (stderr log of the server shows one connection).
4. "Aumenta o gain para 80" with `dry_run` first, then for real → `pedal_set` applied; hear it.
   Then `preset_reload` → the stored sound is back.
5. "Liga o delay" without `experimental` → refused `experimental_required`, nothing sent.
6. `pedal_disconnect` → open the phone app: it connects. Close it; ask for the info again → the
   server reconnects.
7. Switch the pedal off between two calls → the next call returns `no_device_found` (or reconnects
   when switched back on); the server is still running.
8. Leave the conversation idle for 5 minutes (or start the server with `--idle-release 30`) → the
   phone app can connect without closing the assistant.
9. `preset_backup` → a file in the backup folder; `backups_list` shows it `restorable`.
10. Optional, persistent: `preset_save` to the **loaded** position with `unsafe: true` on an
    unchanged preset → `nothing to save`, nothing written (no slot is touched). If the client
    supports elicitation, a save of a real change asks first; answering *no* sends nothing.

Record firmware, client and version, and each result, under "Hardware check" in `tasks.md`.
