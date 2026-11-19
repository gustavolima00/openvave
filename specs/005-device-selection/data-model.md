# Data Model: Finding, selecting and connecting to Tank-G pedals

Decisions: [research.md](research.md). Library names are the public API of
[contracts/library-api.md](contracts/library-api.md).

## DeviceInfo (changed, `openvave.models`)

A pedal found by a scan, and the pedal a session is connected to.

| Field | Type | Notes |
|---|---|---|
| `identifier` | str | MAC (Linux/Windows) or CoreBluetooth UUID (macOS); specific to this computer on macOS |
| `name` | str | advertised local name |
| `rssi` | int \| None | dBm at discovery |
| `nickname` | str \| None | **new**, default `None`; set when the identifier is a known pedal |
| `chosen_by` | `"device_option"` \| `"environment"` \| `"selected"` \| `"only_one_found"` \| None | **new**, default `None`; set on the device of a session opened through target resolution |

Frozen; the two new fields are optional and last, so 0.4.0 constructors still work.

## ScanEntry (new)

One row of `scan`.

| Field | Type | Notes |
|---|---|---|
| `device` | DeviceInfo | with `nickname` when known |
| `tank_g` | bool | `name == "TANK-Gv2_BLE"`; always true unless `include_all` |
| `known` | bool | the identifier is in the configuration |
| `selected` | bool | it is the default |
| `firmware` | int \| None | only after `--identify` |
| `identify_error` | str \| None | why identify failed for this row |

Order: Tank-G rows first, by `rssi` descending (unknown last), ties by identifier; then the others
the same way.

## KnownDevice (new)

| Field | Type | Rules |
|---|---|---|
| `identifier` | str | unique in the file, case-insensitive; MAC or UUID shape |
| `nickname` | str \| None | `[A-Za-z0-9_-]{1,32}`; unique case-insensitive; not identifier-shaped; not all hex with length ≥ 4 |
| `added_at` | datetime (UTC) | set once |
| `selected_at` | datetime \| None | last time it became the default |
| `last_name` | str \| None | advertised name last seen |
| `last_firmware` | int \| None | from the last handshake |
| `last_seen_at` | datetime \| None | last successful connection or identify |

## KnownDevices (new): the configuration

| Field | Type | Rules |
|---|---|---|
| `path` | Path | where it was loaded from / will be saved |
| `devices` | tuple[KnownDevice, ...] | insertion order |
| `default` | KnownDevice \| None | must be one of `devices` |

Operations (each returns a new value; `save()` writes the file atomically):

| Operation | Effect | Refused when |
|---|---|---|
| `select(identifier, nickname=None, *, name=None, now)` | adds the device if new, sets nickname if given, makes it the default, sets `selected_at` | nickname invalid or used by another device |
| `rename(target, new)` | changes one nickname | target unknown; `new` invalid or in use |
| `forget()` | clears the default; devices stay | — (no default: no change) |
| `forget(target)` | removes that device; clears the default if it was it | target unknown |
| `forget_all()` | empty list, no default | — |
| `find(value)` | the device with that identifier or nickname, or `None` | — |
| `record_seen(identifier, name, firmware, now)` | updates the three `last_*` fields of a known device | — (unknown identifier: no change) |

State of the default:

```text
(none) --select X--> X --select Y--> Y        (X stays known)
   ^                 |                |
   +---- forget() ---+---- forget() --+
   X --forget(X)--> (none)   X --forget(Y)--> X   (Y removed)
```

File: [contracts/devices-file.schema.json](contracts/devices-file.schema.json), `format_version` 1.
Invalid (`ConfigError`): unreadable, not JSON, wrong `format_version`, `default` not in `devices`,
duplicate identifier or nickname, a field of the wrong type.

## Target (new)

The result of choosing a pedal before scanning (research R5).

| Field | Type | Notes |
|---|---|---|
| `identifier` | str | what the scan waits for |
| `nickname` | str \| None | when known |
| `chosen_by` | `"device_option"` \| `"environment"` \| `"selected"` | `only_one_found` is never a Target: it is what a scan without a Target yields |

`resolve_target(option, environment, known) → Target | None`:

| `--device` | `OPENVAVE_DEVICE` | default | Result |
|---|---|---|---|
| identifier | any | any | Target(option, nickname if known, `device_option`) |
| known nickname | any | any | Target(that device, `device_option`) |
| other text | any | any | `ConfigError` unknown nickname (exit 2), lists known nicknames |
| absent | identifier / known nickname | any | Target(…, `environment`) |
| absent | other text | any | `ConfigError` unknown nickname |
| absent | absent / empty | set | Target(default, `selected`) |
| absent | absent / empty | none | `None` → 0.4.0 scan rules |

## Scan outcome for a command

| Target | Seen in scan | Outcome |
|---|---|---|
| set | target seen | connect to it (scan stops at first sight) |
| set | target not seen (anything else or nothing seen) | `TargetNotFoundError` (exit 3): target + Tank-G pedals seen |
| none | exactly one Tank-G | connect, `chosen_by = only_one_found` |
| none | no Tank-G | `NoDeviceFoundError` (exit 3) |
| none | several Tank-G | `MultipleDevicesError` (exit 4) |

## Errors (changed, `openvave.errors`)

| Error | Base | Exit | Carries |
|---|---|---|---|
| `TargetNotFoundError` (new) | `NoDeviceFoundError` | 3 | `target: Target`, `seen: tuple[DeviceInfo, ...]` (Tank-G only, strongest first) |
| `ConfigError` (new) | `OpenvaveError` | 2 | `path: Path \| None`, `reason` (`invalid_file`, `unknown_nickname`, `bad_nickname`, `nickname_in_use`, `unknown_device`), message |

## Session lifecycle (changed, `TankG`)

```text
closed --open()/async with--> open --close()/exit--> closed --open()--> open …
                               |
                               +--link lost--> lost --close()--> closed
```

| State | `is_connected` | Operations |
|---|---|---|
| closed | False | `ConnectionLostError("session is closed")` (as today outside `async with`) |
| open | True | run |
| lost | False | `ConnectionLostError` at once; nothing is sent, nothing reconnects |

`open()` on an open or lost session raises `RuntimeError` (close it first). `close()` is idempotent
in every state.
