# Library API additions: `openvave` (feature 003)

Extends [002 `library-api.md`](../../002-preset-byte-map/contracts/library-api.md). All
additions are additive (MINOR: 0.3.0). Types: [data-model.md](../data-model.md).

```python
import openvave
from openvave.protocol import StorageRead, WriteTarget, WRITE_MESSAGES, build_write, parse_write_reply

# Backup (read-only)
async with openvave.TankG.connect() as pedal:
    backup = await pedal.backup()                 # openvave.Backup; raises ProtocolError on mismatch
backup.presets[6].position, backup.presets[6].data, backup.header, backup.image
document = backup.to_document()                   # dict matching backup.schema.json
openvave.Backup.from_document(document)           # round-trip, validates the invariants

# Edit-buffer writes (explicit, named)
async with openvave.TankG.connect() as pedal:
    plan = await pedal.plan_set("gain", 90)       # reads only; WritePlan (frame, refusal, no_change)
    plan = await pedal.plan_set("gain", 90, experimental=True)  # refusal as set_field would see it
    result = await pedal.set_field("gain", 90, experimental=True)    # WriteResult
    result = await pedal.set_field("led_colour", (255, 0, 0), experimental=True)
    plan = await pedal.plan_select(6, discard_edits=False, experimental=False)
    result = await pedal.select_preset(6, discard_edits=False, experimental=True)  # sleep= injectable

# Pure protocol layer
target = WriteTarget.knob_block()                 # also block_switch(k), led_colour(), preset_select(i)
frame = build_write(target, data)                 # 0x22 frame; ValueError on wrong length
parse_write_reply(reply)                          # None on ACK; raises WriteNakError otherwise
encode_frame(0x22, body)                          # UnsafeCommandError unless body is allowlisted
StorageRead.preset(6), StorageRead.header(), StorageRead.image()
```

## New exports

| Name | Kind | Notes |
|---|---|---|
| `Backup`, `StoredPreset` | dataclasses | backup content |
| `WritePlan`, `WriteResult` | dataclasses | write planning / outcome |
| `WriteRefusedError` | exception (exit 1) | `.reason` in `not_edit_mode`, `out_of_range`, `untested_firmware`, `experimental_required`, `edits_would_be_discarded`, `unknown_field` |
| `WriteNakError` | exception (exit 7) | `.reply` raw bytes |
| `WriteNotAppliedError` | exception (exit 8) | `.result` (`WriteResult`) |
| `protocol.StorageRead` | value | closed constructors only |
| `protocol.WriteTarget` | value | closed constructors only |
| `protocol.WRITE_MESSAGES` | data | mirrors the "Write messages" doc table |
| `protocol.build_storage_read`, `parse_storage_reply` | functions | storage reads |
| `protocol.build_write`, `parse_write_reply` | functions | the only way to encode `0x22` |

## Guarantees

- `encode_frame` accepts `0x11`, `0x23` and `0x22`; `0x22` frames are only produced by
  `build_write` from a `WriteTarget`. `0x21` is never encodable.
- `TankG.read`, `snapshot`, `watch`, `backup` and every `plan_*` method send no write.
- `set_field` / `select_preset` send at most one write frame per call, and only after all checks
  pass. No method sends the commit (`0xF0000000`), a stored-area write or the loopback write.
- Writes are never retried automatically.
