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
| `fw96/20261116-probe-connect.jsonl` | 96 | macOS, ATT MTU 185 | The app's 5 connect requests (query + 4 reads) and their replies. The preset read is stored preset 1B |
| `fw96/20261116-step-<field>.jsonl` | 96 | macOS, ATT MTU 185 | One mapping step each, cut from the owner's `openvave watch` sessions of 2026-11-16 (excerpt rules below; index: `tests/integration/fixture_pairs.py`). Knobs and selectors come from session 18:25 (no stdin labels; steps named by the owner afterwards), block switches and `mode-1847` from session 18:47 (labelled), `mode-1843` from session 18:43, `preset_select-*` from the preset walk at 18:41 |

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

## `openvave watch` session records

`openvave watch` writes its session record in this same format, to
`captures/private/<YYYYMMDD-HHMMSS>-watch.jsonl` by default (git-ignored). `--record PATH`
refuses a path inside `captures/` unless it is under `captures/private/`. Every line is flushed
as it is written, so a record cut short by a crash is valid JSONL up to its last line.

- `meta` also has `interval` (seconds between poll cycles), and `tool` is
  `"openvave watch <version>"`.
- `tx` / `rx-chunk` / `rx` cover every frame: the handshake (label `query`) and each poll cycle
  (labels `global`, `preset`, `status`, in that order). Labels repeat once per cycle.
- Three more events:

| `event` | Fields | Meaning |
|---|---|---|
| `label` | `t`, `text` | the owner typed a line (the label of the next mapping step) |
| `change` | `t`, `cycle`, `region` (`global`/`preset`/`status`), `offset`, `old`, `new`, `label` | one changed byte; `label` is the current label text or `null` |
| `stop` | `t`, `reason` (`quit`, `interrupt`, `duration`, `connection_lost`, `protocol_error`), `error` | last line; `error` is a message or `null` |

`FakeTransport.from_capture` serves repeated replies in order (the last one repeats) and ignores
`label`/`change`/`stop`, so a contiguous slice of a record replays as a test fixture.

### Committing an excerpt

Raw records are never committed. A committed excerpt `fw96/<date>-step-<field>.jsonl` keeps:

- the `meta` line and the handshake `tx`/`rx-chunk`/`rx`;
- the `tx`/`rx-chunk`/`rx` of the cycle before the step and of the cycle(s) showing the change,
  contiguous;
- the step's `label` and `change` events.

Review the label text before committing: it must not contain personal preset names. Preset,
global and status bytes and the handshake payload hold no identifiers; if a byte is ever
replaced, list it in `sanitized` and recompute the frame checksum.

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
