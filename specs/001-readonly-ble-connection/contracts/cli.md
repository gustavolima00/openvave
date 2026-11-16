# CLI contract: `openvave`

Constitution V: args in, results on stdout, diagnostics on stderr, non-zero exit on failure,
human + JSON output.

## Global options (valid on every command)

| Option | Default | Meaning |
|---|---|---|
| `--json` | off | Emit exactly one JSON document on stdout (schemas in this folder) |
| `--device ID` | auto | Connect to this platform identifier; skips the name filter |
| `--scan-timeout SECONDS` | 5 | Max scan time when `--device` is not given |
| `--timeout SECONDS` | 2 | Per-request reply timeout |
| `--trace` | off | Hex trace of every frame (`TX`/`RX`) on stderr |
| `--version` | — | Print openvave version, exit 0 |

## Commands

### `openvave info`

Connect → handshake → read `DEVICE_INFO`, `GLOBAL`, `CURRENT_PRESET`, `STATUS` → disconnect.
JSON: [`info.schema.json`](info.schema.json).

Human output (fw 96 capture, illustrative layout):

```text
Device     TANK-Gv2  (firmware 96)
Address    3F1A…  (TANK-Gv2_BLE, -58 dBm)

Device info   type 5 @ 0xD0000000, 32 bytes   [meaning: unknown]
  00: 0a 30 39 36 00 00 00 00 00 00 00 00 00 00 00 00
  10: 00 00 00 b7 43 f3 00 00 00 00 00 00 00 00 00 00
Global        type 4 @ 0x20000000, 4 bytes    [meaning: unknown]
  00: 00 00 01 01
      [3] not in edit mode = 1   (observed)
Status        type 4 @ 0xD0000000, 1 byte     [meaning: unknown]
  00: 01
```

(The current preset is read for the JSON snapshot but its human block is printed only by
`preset dump`, to keep `info` short. JSON `info` includes all four regions.)

### `openvave preset dump`

Connect → handshake → read `CURRENT_PRESET` → disconnect.
JSON: [`preset-dump.schema.json`](preset-dump.schema.json).

```text
Current preset  (TANK-Gv2, firmware 96)   type 4 @ 0x10000000, 21 bytes
  00: 01 00 00 01 0f 04 3c 3c 46 32 32 00 00 00 00 05
  10: 04 07 43 16 43
      [6] knob (which one: unknown) = 60   (observed)
      [16] reverb mix? = 4   (hypothesis)
      [17] IR cab? = 7   (hypothesis)
```

## stderr rules

- Errors: one line `error: <message>` plus, where useful, one `hint: <action>` line (e.g.
  permission denied → how to grant Bluetooth access to the terminal on macOS).
- Warnings: `warning: <message>` (e.g. untested firmware, clarification Q1).
- `MultipleDevicesError`: lists `  <identifier>  <name>  <rssi> dBm` per candidate and
  `hint: re-run with --device <identifier>`.
- No Python traceback unless `OPENVAVE_DEBUG=1` is set.
- With `--json`, stdout carries only the JSON document on success and nothing on failure.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Unexpected internal error |
| 2 | Usage error |
| 3 | No pedal found within `--scan-timeout` |
| 4 | More than one pedal found and no `--device` |
| 5 | Bluetooth unavailable or permission denied |
| 6 | Connection lost or request timed out |
| 7 | Protocol error (bad frame, wrong echo, handshake failed after 3 attempts) |

Codes are part of the public contract; changing one is a breaking change (MAJOR).

## Explicitly absent

No `write`, `set`, `load`, `erase`, `raw`, `send` or arbitrary-address command exists in this
feature (FR-010, FR-011).
