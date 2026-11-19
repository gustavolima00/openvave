# Library guide

The `openvave` package is what the CLI is built on. It is `asyncio`-based: you open a `TankG`
session with `async with`, and every pedal operation is a coroutine. Everything exported from
`openvave` and `openvave.protocol` is public and follows semantic versioning; anything else is
internal.

The authoritative API contracts are in the specs:
[0.1.0](../specs/001-readonly-ble-connection/contracts/library-api.md),
[0.2.0](../specs/002-preset-byte-map/contracts/library-api.md),
[0.3.0](../specs/003-preset-backup-edit-writes/contracts/library-api.md),
[0.4.0](../specs/004-remote-edit-save-restore/contracts/library-api.md) and
[0.5.0](../specs/005-device-selection/contracts/library-api.md) additions. Runnable
scripts are in [`examples/`](examples/).

## Sessions

```python
import asyncio
from openvave import TankG


async def main() -> None:
    async with TankG.connect() as pedal:  # scan, pick the single pedal, connect, handshake
        print(pedal.identity.name, pedal.identity.firmware)  # TANK-Gv2 96
        print(pedal.device)  # DeviceInfo(identifier, name, rssi), or None


asyncio.run(main())
```

- `TankG.connect(device=None, *, scan_timeout=5.0, timeout=2.0)` connects over Bluetooth LE. Pass
  `device="…"` to pick one identifier (the CLI's `--device`). It raises `NoDeviceFoundError` or
  `MultipleDevicesError` when there is not exactly one pedal.
- `TankG.over(transport, *, timeout=2.0, device=None)` runs a session over any `Transport`, such
  as a `FakeTransport` (below).
- `await openvave.discover(timeout=5.0)` scans for the whole timeout and returns every pedal
  found, without connecting.

One session is one Bluetooth connection: do as much as you can inside one `async with`. Requests
are sent one at a time; do not run two operations of the same session concurrently.

`TankG.connect()` also takes a `Target` or a `KnownDevice`. Without an argument it reads no
configuration and behaves as in 0.4.0. With a chosen pedal it never connects to another one: a
pedal that is not seen raises `TargetNotFoundError` (exit 3; `.target`, `.seen`).

### Choosing a pedal

```python
import openvave

entries = await openvave.scan(timeout=5.0)  # every Tank-G in range; no connection
entries = await openvave.identify(entries)  # + firmware (handshake only)

known = openvave.KnownDevices.load()  # devices.json; default_config_path()
known = known.select(entries[0].device.identifier, nickname="stage")  # pure: returns a new value
known.save()  # atomic, mode 0600

target = openvave.resolve_target(option, environment, known)  # --device > env > default
async with openvave.TankG.connect(target) as pedal:
    print(pedal.device.nickname, pedal.device.chosen_by)  # stage selected
```

`KnownDevices` operations (`select`, `rename`, `forget`, `forget_all`, `find`, `record_seen`)
never touch the file; only `save()` writes. An invalid file raises `ConfigError` (exit 2).

### Long-lived connection

`open()` and `close()` are what `async with` does on enter and exit, for code that keeps one
connection for many operations:

```python
pedal = openvave.TankG.connect_selected()  # the default pedal (openvave select)
await pedal.open()
try:
    for _ in range(5):
        print((await pedal.state()).kind, pedal.is_connected)
        await asyncio.sleep(1)
finally:
    await pedal.close()  # idempotent; open() scans and connects again
```

- `connect_selected(*, config_path=None, scan_timeout=…, timeout=…)` reads the file when called
  and raises `ConfigError` when there is no default.
- `is_connected` is true between a successful `open()` and `close()` or a lost link.
- A lost link makes the pending operation and every later one raise `ConnectionLostError` at once,
  without sending anything. Nothing is retried or reconnected; call `close()` then `open()`.
- `open()` on a session that is open or lost raises `RuntimeError`; an operation on a closed
  session raises `ConnectionLostError("session is closed")`.

## Reading

```python
from openvave import Region
from openvave.protocol import decode_region, type_parts

async with TankG.connect() as pedal:
    state = await pedal.state()  # PedalState(kind, index, bank, transient)
    print(state.kind, state.index)  # "normal" 1   (index 1 = preset 1B)

    preset = await pedal.read(Region.CURRENT_PRESET)  # RegionRead: .data is the 21 bytes
    for field in decode_region(preset, pedal.identity.firmware).fields:
        print(field.entry.offset, field.entry.name, field.display, field.entry.confidence)

    print(type_parts("reverb_decay", preset.data[15]))  # ("room", 6)

    snap = await pedal.snapshot()  # device info, global, preset, status at once
    backup = await pedal.backup()  # all 36 stored presets, cross-checked
```

- `Region` has `DEVICE_INFO`, `GLOBAL`, `CURRENT_PRESET` and `STATUS`.
- `decode_region(read, firmware)` returns a `DecodedRegion`: `fields` (each a `DecodedField` with
  `entry` from the byte map, `raw`, `value`, `display`, `interpreted`, `out_of_range`) and
  `unknown_offsets`. The byte map itself is `openvave.protocol.BYTE_MAP`.
- `state()` reads the global block and the buffer; when the pedal looks bypassed it confirms with
  a second read 300 ms later. `kind` is `normal`, `edit`, `tuner`, `bypass` or `unrecognised`;
  `index` is the loaded preset 0–35 (`None` while bypassed).
- `backup()` returns a `Backup` (`identity`, `created_at`, `header`, `image`, `presets`, each a
  `StoredPreset` with `index`, `position` like `"1C"`, `data`, `decoded`). Save it with
  `json.dump(backup.to_document(), fh)` and load it with
  `Backup.from_document(json.load(fh))`; that is the same file format as `openvave preset backup`.

[`examples/read_preset.py`](examples/read_preset.py) prints every field and runs without a pedal:

```bash
python docs/examples/read_preset.py --fake
```

## Watching

```python
from openvave import WatchChange, WatchStart

async with TankG.connect() as pedal:
    async for event in pedal.watch(interval=0.5):  # read-only polling
        if isinstance(event, WatchStart):
            print("start", event.identity.firmware)
        elif isinstance(event, WatchChange):
            for change in event.changes:  # ByteChange
                name = change.field.name if change.field else "unknown"
                print(
                    f"+{event.t:.1f}s {change.region.name}[{change.offset}] {name} {change.old} -> {change.new}"
                )
```

`watch(interval=0.5, *, regions=…, cycles=None)` yields a `WatchStart`, then one `WatchChange`
per poll in which something changed. Pass `cycles=N` to stop after N polls; otherwise break out
of the loop.

## Writing: plan, then apply

Every write comes as a pair. The `plan_*` method only reads and returns exactly what would be
sent, or why it would be refused; the other method builds the same plan, refuses or sends it,
and verifies the result.

| Plan (reads only) | Apply | Result | Persistent |
|---|---|---|---|
| `plan_set(field, value)` | `set_field(field, value)` | `WriteResult` | no |
| `plan_set_fields(changes)` | `set_fields(changes)` | `EditResult` | no |
| `plan_select(index)` | `select_preset(index)` | `WriteResult` | no |
| `plan_reload()` | `reload_preset()` | `WriteResult` | no |
| `plan_bypass_on()` | `bypass_on()` | `WriteResult` (`.return_index`) | no |
| `plan_bypass_off(index)` | `bypass_off(index)` | `WriteResult` | no |
| `plan_loopback(on)` | `set_loopback(on)` | `WriteResult` | no (flag survives power-off) |
| `plan_save(to=None)` | `save_preset(to=None, …)` | `SequenceResult` | **yes** |
| `plan_restore(backup, slot= / all=True)` | `restore(backup, …)` | `SequenceResult` | **yes** |
| `plan_copy(source, target)` | `copy_preset(source, target, …)` | `SequenceResult` | **yes** |
| `plan_swap(first, second)` | `swap_presets(first, second, …)` | `SequenceResult` | **yes** |
| `plan_import(preset_file, target)` | `import_preset(preset_file, target, …)` | `SequenceResult` | **yes** |
| — | `export_preset(index)` | `PresetFile` | no (reads only) |

Keyword options mirror the CLI flags: `experimental=True` (`--experimental`),
`discard_edits=True` (`--discard-edits`), `unsafe=True` (`--unsafe`). A plan is the CLI's
`--dry-run`.

Indexes are 0–35 (`4 × (bank − 1) + slot`; 1B = 1, 2C = 6). There is no name parser in the
public API; [`examples/backup_and_save.py`](examples/backup_and_save.py) has a three-line one.

### Values

`set_field` and `set_fields` take these values:

| Field kind | Value |
|---|---|
| knob (`gain`, …) | `int` 0–127 |
| selector (`amp_type`, `ir_cab`) | `int` 0–8 |
| block switch (`amp_on`, …) | `True` / `False`, or `"on"` / `"off"` |
| `led_colour` | `(r, g, b)`, `"#rrggbb"` or `"r,g,b"` |
| typed knob (`mod_fx`, `delay_mix`, `reverb_decay`) | `(type, position)` like `("spring", 10)`, `(None, 10)` to keep the current type, or an `int` raw value 0–127 |

```python
from openvave.protocol import TYPED_FIELDS, type_parts, type_raw

TYPED_FIELDS["mod_fx"]  # ("chorus", "phaser", "tremolo")
type_raw("reverb_decay", "spring", 10)  # 53
type_parts("delay_mix", 73)  # ("tape", 30); (None, None) in an off zone
```

### One field

```python
async with TankG.connect() as pedal:
    plan = await pedal.plan_set("reverb_decay", ("spring", 10))
    print(plan.frame.hex(" "), plan.refusal, plan.no_change)  # what would be sent

    result = await pedal.set_field("reverb_decay", ("spring", 10))
    for change in result.changes:  # ByteChange
        print(
            change.offset, change.field.name, change.old, "->", change.new
        )  # 15 reverb_decay 5 -> 53
    print(result.applied)  # True
```

`WritePlan` has `action`, `target`, `data`, `frame`, `reads`, `before`, `global_before`,
`no_change`, `refusal` (a reason string, or `None`) and `confidence`. `WriteResult` has `plan`,
`reply`, `after`, `global_after`, `changes` (a tuple of `ByteChange`: `region`, `offset`, `old`,
`new`, `field`) and `applied`. If `plan.no_change`, `set_field` returns at once and sends nothing.

### Several fields over one connection

```python
CHANGES = {"gain": 95, "treble": 58, "reverb_decay": ("room", 18), "delay_on": True}

async with TankG.connect() as pedal:
    plan = await pedal.plan_set_fields(CHANGES, experimental=True)  # EditPlan
    if plan.refusal:
        print(plan.refusal, plan.refused_field)  # the whole batch is refused
    for write in plan.writes:  # EditWrite: target, data, frame
        print(write.target.kind, write.frame.hex(" "))

    result = await pedal.set_fields(CHANGES, experimental=True)  # EditResult
    print(dict(result.field_status))  # {"gain": "applied", …}
```

All knob fields go in one knob-block write (rebuilt from the read just before it), then one write
per block switch and one for the LED colour, each acknowledged and re-read before the next.
`field_status` gives each field as `applied`, `unchanged`, `not_applied`, `unknown` or `not_sent`.
`changes` may be a dict or an iterable of `(field, value)` pairs.
[`examples/dial_in_sound.py`](examples/dial_in_sound.py) is a complete script.

### Saving and restoring (persistent)

```python
import json

from openvave import Backup


def keep(backup: Backup) -> None:  # called with the automatic backup, before any write
    with open("before-save.json", "x") as fh:
        json.dump(backup.to_document(), fh, indent=2)


async with TankG.connect() as pedal:
    plan = await pedal.plan_save(to=2)  # SequencePlan; refusal "unsafe_required"
    result = await pedal.save_preset(to=2, unsafe=True, on_backup=keep)
    print(result.verified)

    with open("backup-a.json") as fh:
        backup = Backup.from_document(json.load(fh))
    result = await pedal.restore(backup, all=True, unsafe=True, on_backup=keep)  # or slot=2

    await pedal.copy_preset(0, 10, unsafe=True, on_backup=keep)  # 1A → 3C, ends on 3C
    await pedal.swap_presets(5, 15, unsafe=True, on_backup=keep)  # 2B ↔ 4D
    tone = await pedal.export_preset(13)  # PresetFile; tone.to_document() for the file
    await pedal.import_preset(tone, 6, unsafe=True, on_backup=keep)  # into 2C
```

`PresetFile.from_document(json.load(fh))` reads a file written by `preset export`; it raises
`ValueError` for another kind (a full backup points to `restore`), version or size.

- `unsafe=True` is always required; without it the call raises `WriteRefusedError`
  (`unsafe_required`) before any backup or write.
- `on_backup` is required. It receives the full, cross-checked backup taken before the first
  write; if it raises, nothing is written. `on_plan` (optional) receives the plan before the
  backup is taken.
- When there is nothing to do (`plan.no_change`), the call returns at once: no backup, no write.
- `SequenceResult` has `plan`, `steps` (each `StepOutcome`: `step`, `status` among `acked`,
  `nak`, `no_reply`, `not_sent`, `waited`, and `reply`), `stored_may_have_changed`, `verified`,
  `read_back`, `backup` and `mismatched_slots`.

[`examples/backup_and_save.py`](examples/backup_and_save.py) backs up to a file and optionally
saves.

## Errors

Every error derives from `OpenvaveError` and carries the CLI's exit code as `exit_code`.

| Error | Exit | When |
|---|---|---|
| `ConfigError` | 2 | unknown nickname, invalid nickname, invalid configuration file, no default for `connect_selected()`; `.reason`, `.path` |
| `NoDeviceFoundError` | 3 | no pedal found while scanning |
| `TargetNotFoundError` (a `NoDeviceFoundError`) | 3 | the chosen pedal was not seen; `.target`, `.seen` |
| `MultipleDevicesError` | 4 | more than one pedal and no `device` |
| `BluetoothUnavailableError` | 5 | Bluetooth off or permission denied |
| `ConnectionLostError`, `RequestTimeoutError` | 6 | link dropped, no reply in `timeout` |
| `ProtocolError`, `HandshakeError` | 7 | malformed reply, failed handshake, backup cross-check mismatch |
| `WriteNakError` (a `ProtocolError`) | 7 | the pedal did not acknowledge a write; `.reply` is the raw frame |
| `WriteRefusedError` (an `UnsafeCommandError`) | 1 | refused before sending; `.reason` (below) |
| `WriteNotAppliedError` | 8 | acknowledged, but the re-read does not show it; `.result` |
| `UnsafeCommandError` | 1 | a request outside the allowlist |

`WriteRefusedError.reason` is one of `out_of_range`, `unknown_field`, `type_required`,
`experimental_required`, `untested_firmware`, `unsafe_required`, `firmware_mismatch`,
`tuner_mode`, `bypassed`, `edit_mode`, `not_bypassed`, `unrecognised_state` or
`edits_would_be_discarded`. A plan carries the same string in `plan.refusal` without raising.
Values of the wrong type or syntax (a position of 41, an unknown type name) raise `ValueError`.

**Partial results.** An error raised partway through a multi-step operation carries what
happened so far:

- `err.edit`: the `EditResult` of a `set_fields` batch that stopped (which fields were applied,
  unknown, not sent);
- `err.sequence`: the `SequenceResult` of a `save_preset` / `restore` that stopped (every step's
  status and `stored_may_have_changed`).

```python
from openvave import OpenvaveError

try:
    await pedal.set_fields(CHANGES, experimental=True)
except OpenvaveError as err:
    if err.edit is not None:
        print(dict(err.edit.field_status))
    raise
```

Nothing is ever retried for you. If you retry, re-plan first: the pedal state may have changed.

## Testing without a pedal

`FakeTransport` replays a recorded session. The repository's committed captures (in
[`captures/fw96/`](../captures/fw96/), format in [`captures/README.md`](../captures/README.md))
work out of the box:

```python
from openvave import FakeTransport, TankG

fake = FakeTransport.from_capture("captures/fw96/20261116-probe-connect.jsonl")
async with TankG.over(fake) as pedal:
    print(pedal.identity.firmware)  # 96
    print((await pedal.state()).kind)  # normal
```

`FakeTransport.from_capture(path, *, replies=…, memory=…, apply_writes=False, …)` can also serve
extra replies, emulate pedal memory and apply allowlisted writes to it, which is how openvave's own
test suite exercises the write paths (see `tests/support/write_fixture.py`). `fake.sent` lists
every frame the session sent.

## The protocol layer

`openvave.protocol` is the pure codec: bytes in, bytes out, no I/O. Use it to build your own
transport or to decode captures: `encode_frame` / `decode_frame`, `build_read`, `build_write`
(only allowlisted `WriteTarget`s), `parse_read_reply`, `decode_region`, `diff`, `classify`
(pedal state from the global block and buffer), `BYTE_MAP`, `WRITE_MESSAGES`, `TYPED_FIELDS`,
`type_raw`, `type_parts`. The wire format is documented in
[`command-layer.md`](../specs/protocol/command-layer.md).

## JSON documents

The CLI's `--json` output is built from these same objects. If you want the documents rather than
the objects, their schemas are listed in the [CLI reference](cli-reference.md#json-output).
