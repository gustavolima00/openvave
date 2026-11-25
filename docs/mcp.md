# Using openvave from an AI assistant (MCP)

`openvave mcp` lets an AI assistant such as **Claude Code** or **Claude Desktop** read and
control your Tank-G for you. You ask in plain words ("what preset is loaded?", "give me more
gain", "back up my presets") and the assistant uses openvave's tools to do it. It can do
everything the [command line](cli-reference.md) can, with the same safety rules: the same
opt-ins, the same dry runs, the same automatic backup before anything changes a stored preset.

It works through the [Model Context Protocol](https://modelcontextprotocol.io) (MCP): your
assistant starts `openvave mcp` in the background and talks to it. You never run it by hand.

> Unofficial project. Not affiliated with or endorsed by M-VAVE / Cuvave. The assistant can
> make mistakes: read what it is about to do before you let it save or restore presets.

## 1. Install

You need Python 3.11 or newer. The server needs openvave's optional `mcp` extra (the official
MCP Python SDK). With [uv](https://docs.astral.sh/uv/):

```bash
uv tool install 'openvave[mcp] @ git+https://github.com/gustavolima00/openvave'
```

or with pip:

```bash
pip install 'openvave[mcp] @ git+https://github.com/gustavolima00/openvave'
```

Check it, and note where it was installed (you need the full path for Claude Desktop):

```bash
openvave --version
which openvave        # macOS / Linux, e.g. /Users/you/.local/bin/openvave
where openvave        # Windows
```

If you installed openvave without the extra, `openvave mcp` stops with
`error: the MCP server needs the 'mcp' extra: pip install 'openvave[mcp]'` (exit code 2):
install again with `[mcp]` as above.

Before the first session, do what every openvave command needs (see
[Getting started](getting-started.md#before-you-connect)): **close the M-VAVE phone app** and
switch the pedal on. If you have more than one Tank-G, choose one with `openvave select`
(or the assistant can choose one for you, see [Choosing a pedal](#choosing-a-pedal)).

## 2. Add it to your assistant

### Claude Code

```bash
claude mcp add --scope user openvave -- openvave mcp
```

`--scope user` makes it available in every project; leave it out to add it to the current
project only. If `openvave` is not on your `PATH`, give the full path from `which openvave`.

To try it without installing anything first (uv downloads it on each start):

```bash
claude mcp add --scope user openvave -- uvx --from 'openvave[mcp] @ git+https://github.com/gustavolima00/openvave' openvave mcp
```

Start `claude` and type `/mcp`: `openvave` should be listed as connected. Then ask
*"What preset is loaded on my pedal?"*.

### Claude Desktop

Open Claude Desktop's settings → **Developer** → **Edit Config**. This opens
`claude_desktop_config.json` (on macOS in `~/Library/Application Support/Claude/`, on Windows in
`%APPDATA%\Claude\`). Add openvave under `mcpServers`, with the **full path** to `openvave`
(Claude Desktop does not read your shell's `PATH`):

```json
{
  "mcpServers": {
    "openvave": {
      "command": "/Users/you/.local/bin/openvave",
      "args": ["mcp"]
    }
  }
}
```

Quit Claude Desktop completely and open it again. openvave's tools appear under the tools
(connectors) button of a new chat. Ask *"What preset is loaded on my pedal?"*.

### Server options

Add these after `mcp` (`openvave mcp --read-only`, or `"args": ["mcp", "--read-only"]`):

| Option | Default | What it does |
|---|---|---|
| `--read-only` | off | the assistant gets no tool that writes to the pedal: it can look, back up and export, nothing else |
| `--device ID\|NICKNAME` | none | the pedal to use (as `openvave --device`); otherwise `OPENVAVE_DEVICE`, then your default (`openvave select`), then the only Tank-G in range |
| `--backup-dir DIR` | see [Backups](#backups) | where backups go, and the only folder restore and import read from |
| `--idle-release SECONDS` | `300` | let go of the pedal after this many seconds without a pedal request; `0` never |
| `--scan-timeout SECONDS` | `5` | how long to look for the pedal when connecting |
| `--timeout SECONDS` | `2` | how long to wait for each reply |
| `--trace` | off | log every Bluetooth frame (hex) to the server's log |

## 3. macOS: Bluetooth permission

On macOS, Bluetooth access belongs to the **app that starts the server**, not to openvave:

| You use | The app that needs Bluetooth access |
|---|---|
| Claude Code in Terminal, iTerm, Warp … | that terminal app |
| Claude Code inside VS Code, Cursor … | that editor |
| Claude Desktop | Claude |

Allow it under **System Settings → Privacy & Security → Bluetooth**. macOS usually asks the
first time openvave connects.

How a missing permission shows up:

- **The server is killed.** If macOS has not allowed (or cannot allow) that app to use
  Bluetooth, it stops the server the moment it first touches Bluetooth, with no message: the
  process exits with code 134 (`SIGABRT`). Tools that need no pedal (`pedal_status`,
  `backups_list`) work until then; the first pedal request fails and the assistant reports that
  the openvave server disconnected or closed. In Claude Code, `/mcp` shows openvave as failed;
  Claude Desktop's log for it is `~/Library/Logs/Claude/mcp-server-openvave.log`.
- **Access was denied.** The pedal request fails with `bluetooth_unavailable` and the hint to
  allow the app under Privacy & Security → Bluetooth.

To fix it, turn the app on in that list, then restart the assistant (in Claude Code, `/mcp` →
reconnect openvave). If the app is not in the list or the server keeps being killed, use the
assistant from an app that has Bluetooth access, for example Claude Code in Terminal once
`openvave info` works there.

## 4. What you can ask

A few examples; the assistant picks the tools.

| You ask | What happens | Changes the pedal? |
|---|---|---|
| "What preset is loaded?" | `pedal_info` | no |
| "Show me the current sound" | `preset_read`: every control by name | no |
| "I'll turn some knobs, tell me what changed" | `pedal_changes` | no |
| "Back up my presets" | `preset_backup`: all 36 to a file | no (writes a file) |
| "More gain, a bit less treble" | `pedal_set` | the sound you hear now, not saved |
| "Put the delay on spring reverb 10" | `pedal_set` with `reverb_decay` | the sound you hear now, not saved |
| "Undo that" / "go back to the stored sound" | `preset_reload` | discards unsaved changes |
| "Load preset 2C" / "bypass" | `preset_select` / `bypass_on` | which preset is loaded |
| "Save this sound to 3A" | `preset_save` with `unsafe` | **a stored preset** (after a backup) |
| "Swap 1A and 1B" / "copy 2C to 9D" | `preset_swap` / `preset_copy` | **stored presets** (after a backup) |
| "Put my backup from yesterday back" | `backups_list`, `preset_restore` | **stored presets** (after a backup) |
| "Let the phone app connect" | `pedal_disconnect` | no |

Nothing you change with `pedal_set` is saved unless you ask for a save; reload a preset, select
another one or power-cycle the pedal and the stored sound is back.

## 5. One connection, and the phone app

The Tank-G accepts **one** Bluetooth connection at a time. The server connects on the first
pedal request (not when the assistant starts), keeps that connection between requests so each
one is fast, and handles one request at a time. While it holds the pedal, the phone app (and
any `openvave` command in a terminal) cannot connect, and the pedal does not show up in scans.

It lets go:

- when you ask ("let the phone app connect", the `pedal_disconnect` tool);
- after 5 minutes without a pedal request (`--idle-release`);
- when the assistant closes.

The next pedal request connects again by itself. If the link drops (pedal switched off, out of
range), the request that saw it fails and **nothing is resent**; the next request connects
again. Ask "is the pedal connected?" (`pedal_status`) to see what the server holds; it never
connects to find out.

### Choosing a pedal

The server uses the same pedal every openvave command would: `--device`, then
`OPENVAVE_DEVICE`, then your default from `openvave select`, then the only Tank-G in range. It
never falls back to another pedal. The assistant can also look (`pedal_scan`) and choose one
for the rest of the session (`pedal_select`, by nickname, identifier or a prefix of at least 4
hex digits); with `remember` it becomes your default, as with `openvave select`.

## 6. Tools

**Reads** change nothing on the pedal (the backup and export tools write a file). **Volatile**
writes change the sound you hear now or which preset is loaded; nothing is stored. **Persistent**
writes overwrite stored presets.

| Tool | What it does | Kind | Opt-ins | Annotations | With `--read-only` |
|---|---|---|---|---|---|
| `pedal_status` | connection, pedal, firmware, last error, options | read | — | read-only, idempotent | listed |
| `pedal_disconnect` | let go of the pedal | — | — | idempotent | listed |
| `pedal_scan` | Tank-Gs in range | read | — | read-only, idempotent | listed |
| `pedal_select` | choose a pedal (`remember` makes it the default) | — | — | idempotent | listed |
| `pedal_info` | identity, firmware, mode, loaded preset | read | — | read-only, idempotent | listed |
| `preset_read` | the current sound, global settings or status, decoded | read | — | read-only, idempotent | listed |
| `pedal_changes` | what changed since the last read (can wait up to 30 s) | read | — | read-only | listed |
| `preset_backup` | all 36 stored presets to a new file in the backup folder | read | — | — | listed |
| `preset_export` | one stored preset to a new file in the backup folder | read | — | — | listed |
| `backups_list` | the backup folder's files, with the restore checks | read | — | read-only, idempotent | listed |
| `pedal_set` | change controls of the current sound | volatile | `dry_run`, `experimental` | idempotent | hidden |
| `preset_select` | load a stored preset | volatile | `dry_run`, `discard_edits`, `experimental` | idempotent | hidden |
| `preset_reload` | discard unsaved changes | volatile | `dry_run`, `discard_edits`, `experimental` | idempotent | hidden |
| `bypass_on` / `bypass_off` | bypass, and back to the preset | volatile | `dry_run`, `discard_edits` (on), `experimental` | idempotent | hidden |
| `loopback` | Bluetooth audio in the USB recording (kept across power-off) | volatile | `dry_run`, `experimental` | idempotent | hidden |
| `preset_save` | store the current sound | **persistent** | `unsafe`, `dry_run`, `experimental` | destructive | hidden |
| `preset_restore` | write back a backup (one slot or all 36) | **persistent** | `unsafe`, `dry_run`, `discard_edits`, `experimental` | destructive | hidden |
| `preset_copy` | copy one stored preset to another slot | **persistent** | `unsafe`, `dry_run`, `discard_edits`, `experimental` | destructive | hidden |
| `preset_swap` | exchange two stored presets | **persistent** | `unsafe`, `dry_run`, `discard_edits`, `experimental` | destructive | hidden |
| `preset_import` | write an exported preset file into a slot | **persistent** | `unsafe`, `dry_run`, `discard_edits`, `experimental` | destructive | hidden |

The opt-ins are the command line's flags, given per request:

- `dry_run`: show the plan and the exact frames, send nothing (`--dry-run`).
- `experimental`: allow a message not yet confirmed on hardware, or a pedal on untested firmware
  (`--experimental`). On firmware 96 every write openvave can send is confirmed, so you only
  need it on other firmware.
- `discard_edits`: allow losing unsaved changes to the current sound (`--discard-edits`).
- `unsafe`: allow overwriting stored presets (`--unsafe`). The server tells the assistant to ask
  you before it passes `unsafe` or `discard_edits`.

All tools are marked `openWorldHint: false` (they touch only your pedal and the backup folder).
Clients can use the annotations to ask you before a destructive tool runs. Without an opt-in a
write is refused before anything is sent, and the assistant sees why (for example
`unsafe_required` or `experimental_required`).

The assistant can also read four reference documents without a pedal: `openvave://fields`
(every control `pedal_set` accepts and its values), `openvave://effect-types`,
`openvave://byte-map` and `openvave://safety`.

Amp type and IR cab positions come with the model the Tank-G manual names for them
(`position_name` in `preset_read`, `#4 (Plexi 100 ?)` in `pedal_changes`, `position_names` in
`openvave://byte-map`). They are a **hypothesis** until matched on a firmware 96 pedal, and IR cab
names describe the factory IRs only; see [Effect types](effect-types.md#amp-types-and-ir-cabs).

## 7. Saving, restoring, and your confirmation

`preset_save`, `preset_restore`, `preset_copy`, `preset_swap` and `preset_import` work exactly
like the matching commands (see [Safety](safety.md)):

1. They need `unsafe: true`. Without it nothing is sent and no backup is taken.
2. If your assistant supports **MCP elicitation**, the server asks you directly before it
   connects, for example *"Overwrite stored preset 2A with the current sound? A full backup is
   written to … first."* Restore and import name the file and its fingerprint (the start of
   its SHA-256), and write exactly the file you were asked about, even if it changes while
   the question is open. Answer **no** (or close the question) and nothing is read or sent. Assistants without elicitation are not asked by the
   server, just as the command line does not ask: then the assistant itself should ask you in
   the chat before passing `unsafe`.
3. Before the first write, a full backup of all 36 presets is written to the backup folder.
   If it cannot be written, nothing is sent to the pedal. Its file name is in the result; to
   undo, ask the assistant to restore that file.
4. If anything goes wrong midway, the error lists what was done, whether stored presets may
   have changed, and the backup to restore.

A `dry_run` never asks and never takes a backup.

## 8. Backups

Backups (`preset_backup`), exported presets (`preset_export`) and the automatic backups of the
persistent tools all go to one folder, created if missing (mode 0700):

- `--backup-dir DIR`, if given;
- else `$OPENVAVE_BACKUP_DIR`;
- else `$XDG_DATA_HOME/openvave/backups`;
- else `%LOCALAPPDATA%\openvave\backups` on Windows, or `~/.local/share/openvave/backups`.

The command line's automatic backups go to the same folder. Files are never overwritten: a
second backup in the same second gets `-1`, `-2` … `backups_list` shows every file, newest
first, with whether it can be restored or imported.

`preset_restore` and `preset_import` read **only** from this folder, by file name: a path, `..`
or a link leading out of it is refused. To restore a backup you made elsewhere, copy it into
the folder first.

## 9. Troubleshooting

| What you see | Why | What to do |
|---|---|---|
| `error: the MCP server needs the 'mcp' extra` | installed without `[mcp]` | install again with `'openvave[mcp] @ git+…'` |
| openvave not listed, or "failed" in `/mcp` | wrong command or path | run the same command in a terminal: it should wait silently (Ctrl-C to stop); use the full path from `which openvave` |
| the server disconnects on the first pedal request (macOS) | no Bluetooth permission for the app that started it (exit 134) | see [macOS: Bluetooth permission](#3-macos-bluetooth-permission) |
| `bluetooth_unavailable` | Bluetooth off, or access denied | turn Bluetooth on; allow the app under Privacy & Security → Bluetooth |
| `no_device_found` / `target_not_found` | pedal off, out of range, or held by the phone app or another openvave | close the phone app, switch the pedal on; `target_not_found` lists the pedals it did see |
| `multiple_devices` | more than one Tank-G and none chosen | ask the assistant to choose one (`pedal_select`), or `openvave select` once |
| the phone app cannot connect | the server holds the pedal | ask the assistant to disconnect (`pedal_disconnect`), or wait 5 minutes |
| `experimental_required` | untested firmware (not 96), or a message not yet confirmed | the assistant may retry with `experimental` once you agree |
| `unsafe_required` | a persistent write without `unsafe` | intended: the assistant must ask you first |
| `declined_by_owner` | you answered no | nothing was sent |
| `edits_would_be_discarded` / `unsaved_edits` | unsaved changes to the current sound | save them first, or agree to `discard_edits` |
| `tuner_mode`, `bypassed` | the pedal is in the tuner or bypassed | leave the tuner / bypass on the pedal (or `bypass_off`) |
| `invalid_file` | the file is not in the backup folder or fails the checks | `backups_list` shows the files and their problems |
| write tools missing | the server runs with `--read-only` | remove it from the configuration |

Every error keeps the server running; the next request works as usual. The server's log (stderr)
is in your assistant's MCP logs; add `--trace` to see every Bluetooth frame.

For the protocol details behind each tool, see the
[MCP contract](../specs/006-mcp-server/contracts/tools.md).
