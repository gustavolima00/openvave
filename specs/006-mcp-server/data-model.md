# Data model: MCP server (spec 006)

No new persistent format: the server reads and writes the 0.5.0 known-pedals file
(`devices.json`) and openvave backup files exactly as the CLI does. Everything below lives in
memory for the life of one `openvave mcp` process.

## ServerOptions (frozen, from the command line)

| Field | Type | Default | Rule |
|---|---|---|---|
| `device` | str \| None | None | as `--device`; validated by `resolve_target` on first use |
| `read_only` | bool | False | write tools are removed at start |
| `backup_dir` | Path | data folder (research R10) | created 0700 on first write; must be a directory if it exists |
| `idle_release` | float (s) | 300 | ≥ 0; 0 = never |
| `scan_timeout` | float (s) | CLI default (5) | > 0 |
| `timeout` | float (s) | CLI default | > 0 |
| `trace` | bool | False | hex trace on stderr |

## PedalHolder (one per server)

| Field | Type | Meaning |
|---|---|---|
| `options` | ServerOptions | |
| `session_target` | Target \| None | set by `pedal_select`; wins over `--device` / env / default |
| `pedal` | TankG \| None | the held session (open, or lost) |
| `device` | DeviceInfo \| None | the held pedal, annotated (nickname, `chosen_by`) |
| `connected_since` | datetime \| None | UTC, set after a successful `open()` |
| `last_error` | str \| None | `kind: message` of the last failed pedal call |
| `baseline` | dict[Region, RegionRead] \| None | last reads for `pedal_changes` |
| `bypass_return` | int \| None | index reported by the last `bypass_on` in this process; cleared by a real `bypass_off` or `preset_select` |
| `lock` | asyncio.Lock | one pedal operation at a time |
| `idle_task` | asyncio.Task \| None | the pending idle release |

### Connection states

```text
            use() / first pedal tool
 idle ──────────────────────────────▶ connecting ──ok──▶ connected
  ▲                                       │ fail (error returned, state idle)
  │                                       ▼
  │◀──── disconnect / idle timeout / select other pedal / shutdown ──── connected
  │                                                                       │ link lost
  │                                                                       ▼
  └──────────── next use(): close() + one new open() attempt ◀──────── lost
```

- `connected` = `pedal is not None and pedal.is_connected`.
- `lost` = `pedal is not None and not pedal.is_connected`; the error that revealed it was returned
  to its caller with any partial result; nothing is resent.
- `baseline` and `bypass_return` survive a reconnect to the **same** pedal identifier and are
  cleared when another pedal is chosen.
- The idle timer starts when a pedal call ends while connected and is cancelled when the next one
  starts; it fires `close()` under the lock.

## Tool registry (static)

One row per tool in [contracts/tools.md](contracts/tools.md): name, `writes` (bool), annotations,
description (names the opt-ins). `writes` tools are removed when `read_only`. A test checks the
registry against the listed tools and the contract table.

## Elicitation answer

| Value | From | Effect |
|---|---|---|
| not asked | `unsafe` false, `dry_run`, or no client capability | proceed as the CLI |
| accepted, `confirm: true` | client | proceed |
| accepted `confirm: false`, declined, cancelled | client | `declined_by_owner`, nothing sent |

## Backup file names (in `backup_dir`)

| Kind | Name | Writer |
|---|---|---|
| manual | `tankg-backup-<YYYYMMDD-HHMMSS>.json` | `preset_backup` |
| automatic | `tankg-backup-<YYYYMMDD-HHMMSS>-before-save.json` / `-before-restore.json` | `preset_save` / `preset_restore` (CLI `files.automatic_backup_path`) |

Never overwritten (a clash adds `-1`, `-2`, … as the CLI does). `preset_restore.file` must be a
bare file name of an existing regular file whose resolved path is inside `backup_dir`.
