# Library contract additions (feature 005, openvave 0.5.0)

Extends [004 `library-api.md`](../../004-remote-edit-save-restore/contracts/library-api.md).
Additions only: no 0.4.0 name changes meaning (MINOR bump). Shapes:
[data-model.md](../data-model.md).

## Finding pedals

```python
entries = await openvave.scan(timeout=5.0, include_all=False, known=None)   # list[ScanEntry]
pedals = await openvave.discover(timeout=5.0)                               # unchanged
```

`scan` uses the whole timeout and connects to nothing. With `known` (a `KnownDevices`), entries
carry `nickname`, `known` and `selected`. `identify(entries, timeout=2.0)` connects to each Tank-G
entry in turn, runs the handshake only, and returns the entries with `firmware` or
`identify_error`.

## Known pedals

```python
known = openvave.KnownDevices.load()            # default path (research R1); missing file = empty
known = openvave.KnownDevices.load(path)        # raises ConfigError on an invalid file
known = known.select("8F3A21C4-…-01", nickname="stage")   # returns a new value
known = known.rename("stage", "live")
known = known.forget()            # clear the default
known = known.forget("live")      # remove one
known.save()                      # atomic
known.default                     # KnownDevice | None
known.find("live")                # by nickname or identifier
openvave.default_config_path()    # honours OPENVAVE_CONFIG
```

Nothing in the library reads the configuration unless one of these is called.

## Choosing and connecting

```python
target = openvave.resolve_target(option=None, environment=None, known=known)   # Target | None, pure

async with openvave.TankG.connect() as pedal: ...                # 0.4.0 rules, no configuration read
async with openvave.TankG.connect("8F3A21C4-…-01") as pedal: ...  # identifier, as in 0.4.0
async with openvave.TankG.connect(known.find("home")) as pedal: ...   # KnownDevice
async with openvave.TankG.connect(target) as pedal: ...               # Target
async with openvave.TankG.connect_selected() as pedal: ...       # the default pedal; ConfigError if none
```

`pedal.device` is the `DeviceInfo` connected to, with `nickname` and `chosen_by` when the session
was opened from a `KnownDevice`, a `Target` or `connect_selected` (`chosen_by` is `"selected"` for
`connect_selected`, `"device_option"` for an explicit device, `"only_one_found"` for the no-argument
form). A target that is not seen raises `TargetNotFoundError` (`.target`, `.seen`).

## Long-lived connection

```python
pedal = openvave.TankG.connect_selected()
await pedal.open()                  # scan, connect, handshake (what `async with` does on enter)
try:
    while running:
        await pedal.set_field("gain", value)      # any number of operations, one connection
        if not pedal.is_connected: break
finally:
    await pedal.close()             # idempotent; releases the pedal
```

- `is_connected`: true between a successful `open()` and `close()` or a lost link.
- Lost link: the pending operation and every later one raise `ConnectionLostError`; nothing is
  sent, retried or reconnected. `close()`, then `open()` again to reconnect (a new scan and
  handshake).
- `open()` on a session that is open or lost raises `RuntimeError`.
- One session talks to one pedal; to switch, close it and open a session to the other.
- The pedal accepts one connection: while a session is open, the phone app and any scan (including
  `openvave scan` in another process) do not see it.

## New exports

`scan`, `identify`, `ScanEntry`, `KnownDevice`, `KnownDevices`, `Target`, `resolve_target`,
`default_config_path`, `ConfigError`, `TargetNotFoundError`. `DeviceInfo` gains `nickname` and
`chosen_by` (optional, default `None`).

## Testing without a pedal

`resolve_target` and every `KnownDevices` operation are pure. Scans take a `scanner_factory` (as
`_scan` does today); `FakeTransport` gains `lose_link()` (new) to simulate a lost link between operations for the
lifecycle tests; its scripted `disconnect` failure of 004 is unchanged.
