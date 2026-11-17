# Quickstart: Preset backup and first edit-buffer writes

Validation guide for feature 003. Commands, flags and output: [contracts/cli.md](contracts/cli.md).
Types: [data-model.md](data-model.md).

## Prerequisites

- Tank-G (fw 96) powered on; the phone app closed (the pedal stops advertising while it is
  connected).
- A terminal with Bluetooth permission on the host (macOS: Terminal, not the assistant's app
  session); `uv sync` done in the repository.
- For any step that **writes**: a backup from the same session, and the owner's explicit approval
  of that exact write in chat (gate rule, FR-019).

## 1. Offline (no hardware)

```bash
uv run pytest -q
```

Expected: all tests pass; the command audit reports no `0x21` frame and no `0x22` frame outside the
allowlist; backup, set and select tests run against the fake transport.

## 2. Backup (read-only, M0 gate)

```bash
uv run openvave preset backup --output /tmp/backup-a.json
```

```bash
uv run openvave preset backup --output /tmp/backup-b.json
```

Expected: both exit 0, 36 presets each, header `a5 5a`, "Cross-check … OK". Comparing the two
files without `created_at` shows no difference (SC-002). `--trace` shows only `0x11`/`0x23`.

## 3. Dry runs (reads only, M1 gate)

Put the pedal in edit mode, then:

```bash
uv run openvave set gain 90 --dry-run
```

```bash
uv run openvave preset select 2C --dry-run --discard-edits
```

Expected: the exact write frames are printed, "dry run: nothing sent", exit 0; the trace shows only
reads. Leave edit mode without saving afterwards.

## 4. First writes (M2/M3 gates — only with approval)

For each approved step: take a backup, run the step, leave edit mode **without saving**, take a
second backup.

```bash
uv run openvave set gain 90 --experimental --trace
```

Expected: `reply … ACK`, `after [6] gain 90 applied`, exit 0; the pedal sounds different; after
leaving edit mode without saving, `preset dump` shows the stored gain again and the second backup
equals the first (SC-004). Same pattern for a block switch (`set mod_on on`), the LED colour
(`set led_colour '#ff0000'`, check the LED) and preset select (`preset select 2C`, pedal shows 2C,
not in edit mode).

Stop the session on any NAK (exit 7) or "not applied" (exit 8): record the output, do not retry,
and report it before the next step.

## 5. Release check (M4)

Re-run sections 1–3 and, once messages are `confirmed`, section 4 without `--experimental` for the
knob block and preset select. `openvave --version` reports 0.3.0.
