# Data model: Preset backup and first edit-buffer writes

Immutable value types (frozen dataclasses, as in 001/002). Pure protocol data lives in
`openvave.protocol`; models in `openvave.models`. Decisions: [research.md](research.md).

## Storage layout (`protocol/storage.py`, pure data)

| Name | Value | Source |
|---|---|---|
| `STORE_OFFSET` | 2 | app-declared, confirmed 2026-11-17 |
| `PRESET_SIZE` | 21 | = `Region.CURRENT_PRESET.length` |
| `PRESET_COUNT` | 36 | 9 banks × 4 slots |
| `IMAGE_SIZE` | 758 | `STORE_OFFSET + PRESET_SIZE × PRESET_COUNT` |
| `EXPECTED_HEADER` | `a5 5a` | observed 2026-11-17 (meaning unknown) |

Position helpers: `position(index) -> "1A"…"9D"`, `parse_position("2C" | "6") -> 6` (index =
(bank − 1)·4 + slot, slot A–D = 0–3); invalid → `ValueError`.

## StorageRead

A read request target outside the `Region` enum. Constructed only by:

- `StorageRead.header()` → type 4, address 0, length 2
- `StorageRead.preset(index)` → type 4, address `2 + 21·index`, length 21 (0 ≤ index ≤ 35)
- `StorageRead.image()` → type 4, address 0, length 758

Fields: `type`, `address`, `length`, `index: int | None`. `Region` and `StorageRead` both satisfy
the internal `ReadTarget` protocol (`type`, `address`, `length`) used by the read builder/parser.

## StoredPreset

| Field | Type | Rule |
|---|---|---|
| `index` | int | 0–35 |
| `position` | str | `"1A"`…`"9D"` |
| `data` | bytes | exactly 21 |
| `decoded` | `DecodedRegion` | byte map of `CURRENT_PRESET` applied to `data` |

## Backup

| Field | Type | Rule |
|---|---|---|
| `identity` | `DeviceIdentity` | from the handshake |
| `created_at` | datetime (UTC) | taken after the last read |
| `header` | bytes | 2 bytes |
| `image` | bytes | 758 bytes; `image[0:2] == header`; `image[2+21i : 23+21i] == presets[i].data` |
| `presets` | tuple[StoredPreset, …] | exactly 36, index order |
| `warnings` | tuple[str, …] | e.g. `unexpected_header`, `untested_firmware` |

Invariant checked on construction: the image equals header + concatenated presets; otherwise
`ProtocolError("backup_mismatch", <positions>)`. Serialization: `backup.to_document()` /
`Backup.from_document()` ([`backup.schema.json`](contracts/backup.schema.json)).

## WriteTarget (`protocol/writes.py`)

| Constructor | Type | Address | Len | Data rule |
|---|---|---|---|---|
| `knob_block()` | 4 | `0x10000004` | 14 | each byte within its byte-map range |
| `block_switch(k)`, k 0–3 | 4 | `0x10000000 + k` | 1 | the row's on/off raw value |
| `led_colour()` | 4 | `0x10000012` | 3 | 0–255 each |
| `preset_select(i)`, i 0–35 | 4 | `0xE0000000 + i` | 1 | always `01` |

Fields: `kind` (`knob_block` / `block_switch` / `led_colour` / `preset_select`), `type`,
`address`, `length`, `argument` (k or i, else `None`). No other constructor exists; `build_write`
rejects data whose length differs.

## WriteMessage (`WRITE_MESSAGES`, mirrored from the "Write messages" doc table)

| Field | Type |
|---|---|
| `kind` | write kind or `ack` |
| `argument` | k for switches, else `None` |
| `confidence` | `confirmed` / `observed` / `hypothesis` |
| `firmware` | frozenset[int] of firmware versions the evidence covers |
| `evidence` | tuple of capture paths |

Gate rule: `sendable_by_default(kind, arg, firmware)` ⇔ row confidence is `confirmed`, the `ack`
row is ≥ `observed`, and firmware ∈ row firmware.

## WritePlan

| Field | Type | Meaning |
|---|---|---|
| `action` | str | `set <field>` or `select <position>` |
| `target` | `WriteTarget` | |
| `data` | bytes | bytes to write |
| `frame` | bytes | the exact `0x22` frame |
| `reads` | tuple[bytes, …] | the read frames already sent to build the plan |
| `before` | `RegionRead` | edit buffer at plan time |
| `global_before` | `RegionRead` | global block at plan time (mode, bank, slot) |
| `no_change` | bool | requested value equals current; nothing will be sent |
| `refusal` | str \| None | reason code if the write would be refused (dry-run shows it) |

## WriteResult

| Field | Type | Meaning |
|---|---|---|
| `plan` | `WritePlan` | |
| `reply` | bytes | the raw 8-byte ACK |
| `after` | `RegionRead` | edit buffer re-read |
| `global_after` | `RegionRead` | global block re-read |
| `changes` | tuple[`ByteChange`, …] | every byte that changed (002 `diff`) |
| `applied` | bool | targeted bytes equal the request (select: bank/slot and stored bytes match) |

State flow of a write action:

```text
plan (reads) ─► refused?  ── yes ─► WriteRefusedError (exit 1)   [dry-run: print, exit 0]
      │ no
      ├─► no_change ─► report, exit 0
      ▼
   send frame ─► reply ─► NAK ─► WriteNakError (exit 7)
                   │ timeout ─► RequestTimeoutError (exit 6)
                   ▼ ACK
              re-read ─► applied ─► exit 0
                     └─► not applied ─► WriteNotAppliedError (exit 8)
```
