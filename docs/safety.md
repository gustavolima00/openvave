# Safety

openvave is an unofficial tool for hardware you own, so it is built to make damage hard: it can only
send messages it has documented, it checks every write, and anything that changes stored presets
sits behind a separate opt-in and an automatic backup.

## Volatile and persistent

| Kind | What it changes | Commands | Undo |
|---|---|---|---|
| Read only | nothing | `info`, `preset dump`, `watch`, `preset backup` | — |
| **Volatile** | the sound you hear now (edit buffer), which preset is loaded, bypass | `set`, `preset select`, `preset reload`, `bypass on/off` | `preset reload`, select a preset, or power-cycle |
| Volatile, but kept | the loopback flag (survives a power cycle, but is not a preset) | `loopback on/off` | set it back |
| **Persistent** | stored presets | `preset save`, `preset restore` only | `preset restore` from a backup |

Nothing but `preset save` and `preset restore` can change a stored preset, and openvave never
saves on its own after a `set`.

## The two opt-ins

**`--experimental`** (`experimental=True` in the library) is about *evidence*. It is needed for a
write whose message is not yet `confirmed` (seen the same way in two independent sessions on a
pedal), for any write on firmware other than 96, and to restore a backup made on another firmware.

**`--unsafe`** (`unsafe=True`) is about *consequences*. Every command that overwrites stored
presets requires it, whatever the evidence. `--experimental` never implies `--unsafe`, and never
unlocks a persistent write by itself.

| Message | Used by | Confidence (fw 96) | Needs |
|---|---|---|---|
| knob block (every knob and selector) | `set` knobs, selectors, typed knobs | confirmed | — |
| preset select | `preset select`, `preset reload`, `bypass off`, end of save/restore | confirmed | — |
| bypass | `bypass on` | confirmed | — |
| block switch | `set amp_on` / `mod_on` / `delay_on` / `reverb_on` | observed | `--experimental` |
| LED colour | `set led_colour` | observed | `--experimental` |
| loopback | `loopback on` / `off` | observed | `--experimental` |
| stored slot, commit, stored image | `preset save`, `preset restore` | confirmed | `--unsafe` |

Each row, with its evidence, is under "Write messages" in
[`command-layer.md`](../specs/protocol/command-layer.md#write-messages).

## What every write does

1. **Reads first.** Every write command reads the pedal state, then plans the exact frame.
   `--dry-run` stops here, prints the frame(s), and sends nothing.
2. **Refuses rather than guesses.** A write is refused before anything is sent when the value is
   out of range, the pedal is in tuner mode, bypassed or in a state openvave does not recognise,
   edits would be lost without `--discard-edits`, or an opt-in is missing. The error names the
   reason (`refused (tuner_mode)`), exit code 1.
3. **Checks the reply.** Anything but the pedal's ACK stops the command (exit 7) and prints the
   raw reply.
4. **Verifies by re-reading.** After the ACK, openvave reads the pedal again and reports `applied`
   only if the change is there; otherwise exit 8.
5. **Never retries.** A NAK, a lost connection or a write that did not apply stops the command and
   reports what was and was not sent.

## Save and restore

On top of that, `preset save` and `preset restore`:

- take a **full, cross-checked backup** of all 36 presets before the first write and write it to
  `--backup-dir` (by default `~/.local/share/openvave/backups`, outside any project folder; never
  overwriting a file); if that fails, nothing is written, and the backup
  cannot be skipped;
- read a written slot back before committing it, and stop if it differs;
- verify the result at the end (slot contents, loaded preset, buffer; a full read after
  `--all`);
- on failure, list every step, say whether stored presets may have changed, and print the
  recovery commands.

A power loss while a save or restore is writing has an unknown outcome; openvave says so before
the first write.

## What openvave never sends

These cannot be encoded at all, by any command or library call:

- the erase command;
- writes to the global block, including the mode byte (openvave never enters or leaves edit mode
  or the tuner);
- the app's whole-edit-buffer write;
- factory restore images;
- firmware updates.

Only the handshake query, region reads and writes to a closed list of targets can be built; any
other request raises `UnsafeCommandError`.

## Your part

- Take a backup (`openvave preset backup`) before writing, and keep it.
- Use `--dry-run` first when trying something new.
- Close the phone app; do not change the pedal by hand while a save or restore runs.
- On firmware other than 96, everything still reads, but every write needs `--experimental`:
  the byte map was built on 96 and has not been checked on other versions.
