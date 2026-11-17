# Quickstart: Remote editing in normal mode, save, restore, bypass and loopback

Validation guide for feature 004. Commands, flags and output: [contracts/cli.md](contracts/cli.md).
Types: [data-model.md](data-model.md). Gate rules: [plan.md](plan.md) "Gate rules".

## Prerequisites

- Tank-G (fw 96) powered on, in normal mode, phone app closed.
- A terminal with Bluetooth permission (macOS: Terminal, not the assistant's app session);
  `uv sync` done.
- For any step that sends a message openvave has not sent before: the owner's approval of that
  exact frame in chat, and `openvave preset backup` before and after.

## 1. Offline (no hardware)

```bash
uv run pytest -q
```

Expected: all tests pass. The command audit reports no `0x21`, no `0x22` outside the nine target
kinds, and persistent frames only in the save and restore tests.

## 2. Remote edit in normal mode (M0 gate; knob block is already confirmed)

```bash
uv run openvave preset backup --output /tmp/q-before.json
```

```bash
uv run openvave set gain 90
```

```bash
uv run openvave set reverb_decay orange 10
```

```bash
uv run openvave preset reload
```

```bash
uv run openvave preset backup --output /tmp/q-after.json
```

Expected: both sets report `applied` in normal mode and are audible; reload reports the buffer
equal to the stored preset; the two backups hold the same presets (SC-002).

Read-only section check for MOD FX and DLY Mix: in the phone app set MOD FX to the first, 40th and
`X` position of each colour, close the app, run `uv run openvave preset dump` each time and note
byte 11; repeat for DLY Mix (byte 13). Reload the preset afterwards.

## 3. Dry runs of the new writes (M1 and M2 gates; reads only)

```bash
uv run openvave bypass on --dry-run --experimental
```

```bash
uv run openvave loopback off --dry-run --experimental
```

```bash
uv run openvave set gain 90 && uv run openvave preset save --to 1C --dry-run --unsafe --experimental
```

```bash
uv run openvave preset restore /tmp/q-before.json --all --dry-run --unsafe --experimental
```

Expected: exact frames printed, `dry run: nothing sent`, no backup file created, `--trace` shows
only reads (and the confirmed knob-block write of the `set`). Then `uv run openvave preset reload`.
Without `--unsafe`, the last two exit 1 with `unsafe_required`.

## 4. First sends (M3 gate session A; each step only with approval)

Order, lowest risk first. Take a backup before the first step and after each step.

1. `bypass on --experimental`, listen, `info` (shows `state: bypass`), `bypass off 1B --experimental`.
2. `set mod_on on --experimental`, `set led_colour '#ff0000' --experimental` in normal mode
   (look at the LEDs), `preset reload`.
3. `loopback off --experimental`, listen and record over USB, power cycle, `info`,
   `loopback on --experimental`.
4. Save, no-op: `preset save --unsafe --experimental` with no edits says "nothing sent"; then
   `set gain 90`, `preset save --to 1C --unsafe --experimental`, power cycle, backup: only 1C byte
   6 differs.
5. Restore one slot: `preset restore <first backup> --slot 1C --unsafe --experimental`; backup
   equals the first.
6. Restore all, no-op image: needs a file equal to the pedal, so the tool sends nothing; the
   no-op **send** is done with the gate helper (`tests/hardware`, `OPENVAVE_HW_UNSAFE=1`) that
   writes the image just read. Judge: one ACK, next read fine, backup identical.
7. Restore all with differences: save a change to 1C (step 4), then
   `preset restore <first backup> --all --unsafe --experimental`, power cycle, backup equals the
   first.

Stop the session on any NAK (exit 7), lost connection (exit 6) or failed verification (exit 8):
keep the output, do not retry, run `preset backup`, report before the next step.

Optional observations (each its own approved step): a slot write without commit followed by a
power cycle; turning a pedal knob after a remote edit.

## 5. Confirmations (M4 gate session B) and release check (M5)

New connection, another preset: repeat steps 1, 4, 5 and 7. Once rows are `confirmed`, repeat
bypass and save without `--experimental`. Final backup equals the backup taken before step 2 of
this guide (SC-010). `openvave --version` reports 0.4.0.
