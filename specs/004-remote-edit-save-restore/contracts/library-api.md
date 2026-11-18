# Library API additions: `openvave` (feature 004)

Extends [003 `library-api.md`](../../003-preset-backup-edit-writes/contracts/library-api.md).
All additions are additive (MINOR: 0.4.0). Types: [data-model.md](../data-model.md).

```python
import openvave
from openvave.protocol import WriteTarget, classify, type_raw, type_parts, TYPED_FIELDS

async with openvave.TankG.connect() as pedal:
    state = await pedal.state()                       # PedalState; confirms bypass with a 2nd read

    # Volatile (no stored preset changes)
    await pedal.set_field("gain", 90)                 # now also in normal mode
    await pedal.set_field("reverb_decay", ("spring", 10))   # (type, position) → raw 53
    await pedal.set_field("reverb_decay", (None, 10))       # keep the current type
    plan = await pedal.plan_set_fields({"gain": 95, "delay_on": True})   # EditPlan; reads only
    await pedal.set_fields({"gain": 95, "treble": 58})      # EditResult; one connection, one knob block
    await pedal.reload_preset(discard_edits=False)    # WriteResult; select of the loaded preset
    plan = await pedal.plan_reload()                  # WritePlan; reads only (no_change: nothing to discard)
    plan = await pedal.plan_bypass_on()               # WritePlan; reads only (no_change if bypassed)
    await pedal.bypass_on(discard_edits=False)        # WriteResult (+ .return_index); confirmed on fw 96
    plan = await pedal.plan_bypass_off(1)             # WritePlan; refusal not_bypassed unless bypassed
    await pedal.bypass_off(1)                         # = select 1B, only when bypassed
    plan = await pedal.plan_loopback(False)           # WritePlan; plan.before = status byte
    await pedal.set_loopback(False, experimental=True)   # loopback is observed, not confirmed

    # Persistent: unsafe=True is mandatory, a backup is always taken first
    plan = await pedal.plan_save(to=None)             # SequencePlan; reads only
    result = await pedal.save_preset(
        to=None, unsafe=True,                         # experimental=True only on firmware other than 96
        on_backup=store,                              # called with the Backup before the first write;
        on_plan=show,                                 # optional: the plan, before the backup (M2)
    )                                                 # if either raises, nothing is written
    backup = openvave.Backup.from_document(document)
    plan = await pedal.plan_restore(backup, slot=2)   # or all=True
    result = await pedal.restore(backup, all=True, unsafe=True,
                                 discard_edits=False, on_backup=store)   # SequenceResult

# Pure protocol layer
classify(global_bytes, buffer)                        # PedalState (no bypass confirmation)
type_raw("reverb_decay", "spring", 10)                # 53
type_parts("reverb_decay", 53)                        # ("spring", 10); (None, None) between types
WriteTarget.bypass(1), WriteTarget.loopback()
WriteTarget.stored_slot(2), WriteTarget.commit(), WriteTarget.stored_image()   # .persistent is True
```

Every `plan_*` and every write method also accepts `sleep=` (injectable, for tests).

`experimental=True` is needed only for a message that is not `confirmed` on the pedal's firmware
(research R4). On fw 96 after the spec 004 gate sessions that is `set_loopback`, and `set_field` /
`set_fields` of a block switch or `led_colour`; `bypass_on`, `bypass_off`, `save_preset` and
`restore` run without it. `unsafe=True` stays mandatory for `save_preset` and `restore`, and
`experimental=True` never implies it. `restore` also needs `experimental=True` for a backup from
another firmware (`firmware_mismatch`).

## New exports

| Name | Kind | Notes |
|---|---|---|
| `PedalState` | dataclass | `kind`, `index`, `bank`, `transient` |
| `SequencePlan`, `SequenceStep`, `SequenceResult`, `StepOutcome` | dataclasses | persistent actions |
| `protocol.classify` | function | pure state classification |
| `protocol.type_raw`, `protocol.type_parts`, `protocol.TYPED_FIELDS`, `protocol.REVERB_TYPES`, `protocol.MOD_FX_TYPES`, `protocol.DELAY_MIX_TYPES` | functions, data | typed knob input (`room`/`spring`/`cloud`, `chorus`/`phaser`/`tremolo`, `analog`/`tape`/`dual`; position 1–40) |
| `EditPlan`, `EditWrite`, `FieldEdit`, `EditResult`, `EditWriteOutcome` | dataclasses | `plan_set_fields` / `set_fields` (batch edit) |
| `OpenvaveError.edit` | attribute | partial `EditResult` on an error raised mid-batch |
| `WriteTarget.bypass`, `.loopback`, `.stored_slot`, `.commit`, `.stored_image` | constructors | closed; `.persistent` property |
| `WriteRefusedError.reason` | values | + `unsafe_required`, `bypassed`, `tuner_mode`, `edit_mode`, `unrecognised_state`, `not_bypassed`, `firmware_mismatch`, `type_required`; `not_edit_mode` (0.3.0) is no longer raised |
| `WriteResult.return_index` | field | `bypass_on` only: the preset `bypass_off` should select (M1) |

`WriteNakError`, `ConnectionLostError`, `RequestTimeoutError` and `WriteNotAppliedError` raised
from `save_preset` / `restore` carry `.sequence` (the partial `SequenceResult`).

## Guarantees

- `encode_frame` accepts `0x22` only for the nine target kinds (four of 0.3.0, five new). `0x21`,
  type 6, the global block, the whole edit buffer and `0x15` are never encodable.
- A persistent target is sent only by `save_preset` and `restore`, only with `unsafe=True`, and
  only after `on_backup` returned. `on_backup` is a required argument; it and the optional
  `on_plan` (added in M2 so the CLI can show what will be overwritten before the backup, FR-030)
  may be plain or coroutine functions.
- `state`, `read`, `snapshot`, `watch`, `backup` and every `plan_*` send no write.
- `set_field`, `reload_preset`, `bypass_on`, `bypass_off`, `set_loopback` send at most one write.
  `save_preset` and `restore` send at most three, in the documented order. `set_fields` sends
  at most six (one knob block, up to four block switches, the LED colour), each verified by a
  re-read before the next, and attaches the partial `EditResult` (`err.edit`) to an error raised
  mid-batch.
- No write is ever retried. No method writes the global block or changes the pedal's mode.
- A frame longer than one Bluetooth write is split by the transport into consecutive chunks; the
  protocol layer always sees whole frames. `restore(all=True)` sends the 758-byte image as one
  such frame (one ACK on fw 96, gate sessions A and B); the slot-by-slot fallback of research R11
  (T079) was not needed and does not exist.
