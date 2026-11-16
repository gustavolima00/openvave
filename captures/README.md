# Captures

Sanitized protocol captures from real hardware. They are the **only** source of test fixtures
(Constitution II/III, spec FR-022): tests load them through `tests/support/captures.py`, and
negative cases are derived from them with the named helpers in `tests/support/mutations.py`.

Raw, unsanitized captures stay in `captures/private/`, which is git-ignored and never committed.

## Layout

```text
captures/
└── fw<firmware>/<date>-<what>.jsonl
```

| File | Firmware | Platform | What |
|---|---|---|---|
| `fw96/20261116-probe-connect.jsonl` | 96 | macOS, ATT MTU 185 | The app's 5 connect requests (query + 4 reads) and their replies |

## JSONL format

One JSON object per line.

The first line is a **meta** record describing provenance:

| Field | Meaning |
|---|---|
| `event` | `"meta"` |
| `firmware` | firmware version reported by the handshake (int) |
| `device` | device name reported by the handshake |
| `platform` | host OS the capture was taken on |
| `att_mtu` | negotiated ATT MTU |
| `date` | capture date, `YYYY-MM-DD` |
| `tool` | program that produced the capture |
| `sanitized` | list of byte ranges that were altered before committing (empty = none) |

Every following line is a protocol event:

| Field | Meaning |
|---|---|
| `t` | seconds since the tool started (float) |
| `event` | `tx` (frame written to `ae41`), `rx-chunk` (one `ae42` notification), `rx` (one reassembled reply frame) |
| `label` | request name; a `tx` and its `rx` share the same label |
| `hex` | bytes, lowercase, space-separated |
| `cmd` | on `rx`: command byte of the reply (int) |

## Sanitization rules (Constitution VI)

- No MAC addresses, serial numbers, account identifiers or personal preset names in committed
  files.
- If a byte range is replaced, the replacement is documented in `sanitized` (e.g.
  `"devinfo[19:22]"`) and the frame checksum is recomputed so the frame stays valid.

### `fw96/20261116-probe-connect.jsonl` — device-info bytes 19–21 (research R7)

The device-info block (type 5 @ `0xD0000000`) contains three unexplained bytes `b7 43 f3` at
offsets 19–21. On 2026-11-16 they were compared, in either byte order, against the pedal's
BLE and Classic Bluetooth MAC addresses as recorded in an Android bugreport of the pairing:
**no match**. No serial number for the pedal was found to compare against. The bytes are
therefore committed unchanged (`"sanitized": []`) and documented as unknown.
