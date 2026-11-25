# Contract: `openvave mcp` (spec 006)

Server name `openvave`, version = package version. Transport: stdio only. Every result is a JSON
object (`structuredContent`, also sent as a JSON text block) with a `summary` string; where a CLI
`--json` document exists for the same operation, the result **is** that document plus `summary`
(schemas under `specs/001…005/contracts/`). Errors are tool errors (`isError: true`, see
[Errors](#errors)); the server never exits because of a pedal error.

## Command

```text
openvave mcp [--device ID|NICKNAME] [--read-only] [--backup-dir DIR]
             [--idle-release SECONDS] [--scan-timeout S] [--timeout S] [--trace]
```

| Option | Default | Meaning |
|---|---|---|
| `--device` | none | as the CLI: the pedal when the session has not selected one (then `OPENVAVE_DEVICE`, the default, the only one) |
| `--read-only` | off | write tools are not listed (`pedal_set`, `preset_select`, `preset_reload`, `bypass_on`, `bypass_off`, `loopback`, `preset_save`, `preset_restore`) |
| `--backup-dir` | `$XDG_DATA_HOME/openvave/backups`, else `~/.local/share/openvave/backups` (`%LOCALAPPDATA%\openvave\backups` on Windows) | backup folder (research R10) |
| `--idle-release` | `300` | seconds without a pedal tool before the connection is closed; `0` never |
| `--scan-timeout`, `--timeout`, `--trace` | as the CLI | |

Exit codes: `0` on a clean shutdown (stdin closed), `2` on a usage error or when the `mcp` extra
is missing (`error: the MCP server needs the 'mcp' extra: pip install 'openvave[mcp]'`).
stdout carries only MCP messages; logs, warnings and the trace go to stderr.

## Tools

Annotations: **RO** `readOnlyHint`, **D** `destructiveHint`, **I** `idempotentHint`;
`openWorldHint` is `false` for every tool. "Pedal" = takes the connection (holder lock).

| Tool | Arguments | Library call | Pedal | RO | D | I | `--read-only` |
|---|---|---|---|---|---|---|---|
| `pedal_status` | — | holder fields | no | ✓ | ✗ | ✓ | listed |
| `pedal_disconnect` | — | `TankG.close()` | no¹ | ✗ | ✗ | ✓ | listed |
| `pedal_scan` | `include_all=false` | `scan()` | no² | ✓ | ✗ | ✓ | listed |
| `pedal_select` | `target`, `remember=false`, `nickname=null` | `KnownDevices` (+ `scan()` for identifiers / prefixes) | no¹ | ✗ | ✗ | ✓ | listed |
| `pedal_info` | — | `snapshot()` | yes | ✓ | ✗ | ✓ | listed |
| `preset_read` | `region="current"` (`current` \| `global` \| `status`) | `read()` + `decode_region` + `state()` | yes | ✓ | ✗ | ✓ | listed |
| `pedal_changes` | `wait_seconds=0` (0–30) | `read()` × 3 + `diff` | yes | ✓ | ✗ | ✗ | listed |
| `preset_backup` | — | `backup()` → file | yes | ✗³ | ✗ | ✗ | listed |
| `backups_list` | — | folder + `restore_problems` | no | ✓ | ✗ | ✓ | listed |
| `pedal_set` | `changes` (object: field → value text), `dry_run`, `experimental` | `plan_set_fields` / `set_fields` | yes | ✗ | ✗ | ✓ | hidden |
| `preset_select` | `position` (`1A`–`9D` or `0`–`35`), `dry_run`, `discard_edits`, `experimental` | `plan_select` / `select_preset` | yes | ✗ | ✗ | ✓ | hidden |
| `preset_reload` | `dry_run`, `discard_edits`, `experimental` | `plan_reload` / `reload_preset` | yes | ✗ | ✗ | ✓ | hidden |
| `bypass_on` | `dry_run`, `discard_edits`, `experimental` | `plan_bypass_on` / `bypass_on` | yes | ✗ | ✗ | ✓ | hidden |
| `bypass_off` | `position=null` (default: the one `bypass_on` reported in this session), `dry_run`, `experimental` | `plan_bypass_off` / `bypass_off` | yes | ✗ | ✗ | ✓ | hidden |
| `loopback` | `on` (bool), `dry_run`, `experimental` | `plan_loopback` / `set_loopback` | yes | ✗ | ✗ | ✓ | hidden |
| `preset_save` | `to=null`, `dry_run`, `unsafe`, `experimental` | `plan_save` / `save_preset` | yes | ✗ | ✓ | ✗ | hidden |
| `preset_restore` | `file` (name in the backup folder), `slot=null` \| `all=false`, `dry_run`, `unsafe`, `discard_edits`, `experimental` | `plan_restore` / `restore` | yes | ✗ | ✓ | ✗ | hidden |
| `preset_export` | `position` | `export_preset()` → file (spec 007) | yes | ✗³ | ✗ | ✗ | listed |
| `preset_copy` | `source`, `target`, `dry_run`, `unsafe`, `discard_edits`, `experimental` | `plan_copy` / `copy_preset` (spec 007) | yes | ✗ | ✓ | ✗ | hidden |
| `preset_swap` | `first`, `second`, `dry_run`, `unsafe`, `discard_edits`, `experimental` | `plan_swap` / `swap_presets` (spec 007) | yes | ✗ | ✓ | ✗ | hidden |
| `preset_import` | `file` (a preset file in the backup folder), `to`, `dry_run`, `unsafe`, `discard_edits`, `experimental` | `plan_import` / `import_preset` (spec 007) | yes | ✗ | ✓ | ✗ | hidden |

¹ takes the lock to close a held connection, but never opens one. ² waits for a running pedal call (holder lock) but never
connects; a held pedal does not advertise, so it is added to the list as `connected: true`. ³ writes a file, so not read-only for the
client, though it sends only reads to the pedal.

### Values (`pedal_set.changes`)

Each value is a string with the CLI's `set FIELD=VALUE` syntax (`openvave.cli.parse_assignments`):
a number, `on`/`off`, `#rrggbb`, `TYPE:POSITION` for `mod_fx` / `delay_mix` / `reverb_decay`,
`raw:N`. JSON numbers and booleans are accepted and converted to that text. Unknown fields and
bad syntax are refused before any read (`unknown_field`, `invalid_value`), naming the writable
fields (resource `openvave://fields`).

### Results (beyond the CLI document)

- `pedal_status`: `{connected, since, pedal: device|null, chosen_by, firmware, firmware_untested,
  last_error, options: {read_only, device, backup_dir, idle_release, scan_timeout, timeout},
  bypass_return: position|null}`.
- `pedal_disconnect`: `{was_connected, summary}`; free for the phone app.
- `pedal_select`: the `device` document of `openvave select --json` + `remembered: true` when
  `remember`, else `{session_choice: {identifier, nickname, name, rssi}, remembered: false}`
  (`name` / `rssi` are `null` for a nickname, which needs no scan).
- `pedal_scan`: the `scan --json` document; every row adds `connected` (bool); the held pedal,
  which does not advertise, is appended with `connected: true` when the scan did not see it.
  No pedal found is a result (summary says so), not an error.
- `preset_read`: `region="current"` → the `preset dump --json` document + `pedal_state`;
  `global` / `status` → the same envelope (`command: "preset read"`) + `pedal_state` +
  `region` (the region object of `info --json`). Typed knobs in `fields[]` add `knob_type` and
  `knob_position` (`null` between two types). In bypass the document is still the CLI's (the
  zeroed buffer decoded); `pedal_state` and the summary say the fields do not apply. Sets the
  `pedal_changes` baseline for that region.
- `preset_backup`: the `preset backup --json` document + `path`.
- `backups_list`: `{folder, backups: [{file, created_at, firmware, presets, restorable,
  problems: [...]}]}` newest first.
- `pedal_changes`: `{baseline: bool, changed: bool, waited: seconds, state_before, state_after,
  changes: [{region, offset, name, before, after, display_before, display_after}]}`; `region` is
  `global`, `current_preset` or `status` (as `watch --json`), `name` is `null` for an unknown or
  flag byte, `display_*` is `5 (room 6)` for a typed knob and hex for an unknown byte.
  `baseline: true` when no earlier read existed (then, with a wait, it polls against this
  call's first read). `wait_seconds` outside 0–30 → `invalid_value`.
- `backups_list`: `created_at` / `firmware` / `presets` are `null` when the file does not
  carry them; only `*.json` regular files are listed; a missing folder is an empty list.
- Write tools: `set --json` / `preset select --json` / … documents (`set-fields-result`,
  `write-result`, `sequence-result` schemas), so `dry_run` results carry the frames and no reply.
- Every write result adds `reminder`: `"dry run: nothing sent"` with `dry_run`; after
  `pedal_set` `"not saved; discard with preset_reload"` (edit mode: `"… and discard_edits:
  true"`; nothing to change: `"nothing changed"`); after `bypass_on` `"bypassed; bypass_off
  returns to 1B"` (the position it reported); after `preset_select` / `preset_reload` /
  `bypass_off` `"nothing saved; the stored presets are unchanged"`; after `loopback` `"a volatile
  setting; nothing saved to the presets"`; the automatic backup path for save/restore.
- `pedal_set` and every single-frame write tool return their document even when the plan is
  refused under `dry_run` (the plan shows `refusal`, as `--dry-run` does); without `dry_run` a
  refusal is an error. `bypass_return` is set by a real `bypass_on` and cleared by a real
  `bypass_off` or `preset_select`.

## Elicitation (save, restore)

With `unsafe: true`, `dry_run: false` and a client that declared the elicitation capability, the
server asks before connecting for the write: *"Overwrite stored preset 2A with the current sound?
A full backup is written to <folder> first."* (restore: the file and `slot` / all 36 presets),
schema `{confirm: boolean}`. Accept with `confirm: true` → run; decline, cancel or
`confirm: false` → error `declined_by_owner`, nothing sent. Restore and import read their file once
per call and the question names its fingerprint (first 12 hex digits of its SHA-256); the pedal is
written only from those bytes. In the modern protocol (≥ 2026-07-28), where the client answers in a
retry of the call, the retry reuses that read (pinned in the server until a call for the same file
and destination ends, at most 10 minutes), so the question is the same, the owner's answer, *no*
included, is final, and a file replaced meanwhile is neither written nor asked about. The next call
reads the file again. Two identical restore / import calls that overlap while the file is replaced,
or an answer given after the 10 minutes, can be asked again about the new bytes (the SDK gives no
per-call id that survives the retry); nothing is written without an accepted answer to the question
that names the bytes written. Clients without the capability are not asked (CLI parity). Nobody is
asked for a call the tool refuses from its arguments alone (bad position, `slot` and `all` both or
neither, a restore `file` that is not a valid backup in the
folder): that call fails with `invalid_value` / `invalid_file` instead.

Save / restore errors add, after the hints: `stored presets may have changed; nothing was
retried` once a persistent frame was sent, and `backup: <path> (…)` once the automatic backup is
written. An automatic backup that cannot be written (folder not writable) is `invalid_file`, and
nothing is sent to the pedal.

## Resources

All `application/json` unless noted, readable without a pedal:

| URI | Content |
|---|---|
| `openvave://fields` | every writable field: name, kind (knob / block switch / LED / typed knob), value syntax, range, types and their position ranges, opt-in needed (`experimental` for observed messages) |
| `openvave://effect-types` | MOD FX, DLY MIX, RVB DECAY types with raw ranges (`MOD_FX_TYPES`, `DELAY_MIX_TYPES`, `REVERB_TYPES`) |
| `openvave://byte-map` | `BYTE_MAP` entries per region (offset, name, encoding, range, confidence) |
| `openvave://safety` (`text/markdown`) | volatile vs persistent, the opt-ins, what openvave never sends, the one-connection rule |

## Errors

Text of the tool error: `<kind>: <message>` then, on following lines, `hint: …` (the CLI's hint)
and, when present, `partial: <JSON>` (the batch or sequence result so far). `kind` is the
library's refusal reason (`experimental_required`, `unsafe_required`, `unsaved_edits`,
`tuner_mode`, `bypassed`, `out_of_range`, `type_required`, `not_bypassed`, `firmware_mismatch`,
`unknown_field`, …) or one of: `no_device_found`, `target_not_found` (+ seen pedals),
`multiple_devices` (+ candidates), `bluetooth_unavailable`, `handshake_failed`, `timeout`,
`connection_lost`, `write_nak`, `write_not_applied`, `config_error`, `invalid_value`,
`invalid_file`, `declined_by_owner`, `internal`.
