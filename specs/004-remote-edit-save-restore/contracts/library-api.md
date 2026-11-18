# Library API additions: `openvave` (feature 004)

Extends [003 `library-api.md`](../../003-preset-backup-edit-writes/contracts/library-api.md).
All additions are additive (MINOR: 0.4.0). Types: [data-model.md](../data-model.md).

```python
import openvave
from openvave.protocol import WriteTarget, classify, section_raw, SECTION_FIELDS

async with openvave.TankG.connect() as pedal:
    state = await pedal.state()                       # PedalState; confirms bypass with a 2nd read

    # Volatile (no stored preset changes)
    await pedal.set_field("gain", 90)                 # now also in normal mode
    await pedal.set_field("reverb_decay", ("orange", 10))   # section value → raw 53
    await pedal.reload_preset(discard_edits=False)    # WriteResult; select of the loaded preset
    plan = await pedal.plan_reload()                  # WritePlan; reads only (no_change: nothing to discard)
    plan = await pedal.plan_bypass_on()               # WritePlan; reads only (no_change if bypassed)
    await pedal.bypass_on(discard_edits=False, experimental=True)     # WriteResult (+ .return_index)
    plan = await pedal.plan_bypass_off(1)             # WritePlan; refusal not_bypassed unless bypassed
    await pedal.bypass_off(1, experimental=True)      # = select 1B, only when bypassed
    plan = await pedal.plan_loopback(False)           # WritePlan; plan.before = status byte
    await pedal.set_loopback(False, experimental=True)

    # Persistent: unsafe=True is mandatory, a backup is always taken first
    plan = await pedal.plan_save(to=None)             # SequencePlan; reads only
    result = await pedal.save_preset(
        to=None, unsafe=True, experimental=True,
        on_backup=store,                              # called with the Backup before the first write;
        on_plan=show,                                 # optional: the plan, before the backup (M2)
    )                                                 # if either raises, nothing is written
    backup = openvave.Backup.from_document(document)
    plan = await pedal.plan_restore(backup, slot=2)   # or all=True
    result = await pedal.restore(backup, all=True, unsafe=True, experimental=True,
                                 discard_edits=False, on_backup=store)   # SequenceResult

# Pure protocol layer
classify(global_bytes, buffer)                        # PedalState (no bypass confirmation)
section_raw("orange", 10)                             # 53
WriteTarget.bypass(1), WriteTarget.loopback()
WriteTarget.stored_slot(2), WriteTarget.commit(), WriteTarget.stored_image()   # .persistent is True
```

Every `plan_*` and every write method also accepts `sleep=` (injectable, for tests).

## New exports

| Name | Kind | Notes |
|---|---|---|
| `PedalState` | dataclass | `kind`, `index`, `bank`, `transient` |
| `SequencePlan`, `SequenceStep`, `SequenceResult`, `StepOutcome` | dataclasses | persistent actions |
| `protocol.classify` | function | pure state classification |
| `protocol.section_raw`, `protocol.SECTION_FIELDS` | function, data | section input |
| `WriteTarget.bypass`, `.loopback`, `.stored_slot`, `.commit`, `.stored_image` | constructors | closed; `.persistent` property |
| `WriteRefusedError.reason` | values | + `unsafe_required`, `bypassed`, `tuner_mode`, `edit_mode`, `unrecognised_state`, `not_bypassed`, `firmware_mismatch` |
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
  protocol layer always sees whole frames.
