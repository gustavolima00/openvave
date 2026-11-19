# CLI contract additions: `openvave` (feature 005)

Extends [004 `cli.md`](../../004-remote-edit-save-restore/contracts/cli.md). Exit codes, stdout of
existing commands and the JSON envelope are unchanged unless stated. Decisions:
[research.md](../research.md). Identifiers below are made up.

## Choosing the pedal (every pedal command)

Order (first present wins, research R5): `--device VALUE` → `OPENVAVE_DEVICE` → the default in the
configuration → the only Tank-G in range.

- `--device VALUE` (changed): VALUE is an identifier (MAC or UUID shape) or a known nickname. An
  identifier is connected to whatever its advertised name, as in 0.4.0. Another text that is not a
  known nickname: exit 2 before any scan, listing the known nicknames.
- `OPENVAVE_DEVICE`: same values; empty = unset. Neither changes the configuration.
- `OPENVAVE_CONFIG`: path of the configuration file (default: research R1).
- With a target, the scan ends when it is seen. Not seen within `--scan-timeout`: exit 3.

```text
$ openvave info
error: stage (8F3A21C4-0000-4000-8000-000000000001) not found
  seen: 8F3A21C4-0000-4000-8000-000000000002  TANK-Gv2_BLE  -61 dBm
hint: switch it on and close the M-VAVE phone app (a connected pedal stops advertising).
hint: use another pedal once with --device ID, or make it the default with: openvave select ID
```

  (no `seen:` lines when no Tank-G was seen; for an identifier unknown to the configuration the
  first line is `error: device <identifier> not found`.)
- Without a target: 0.4.0 behaviour. Several pedals, exit 4:

```text
error: 2 pedals found
  8F3A21C4-0000-4000-8000-000000000001  TANK-Gv2_BLE  -58 dBm
  8F3A21C4-0000-4000-8000-000000000002  TANK-Gv2_BLE  -61 dBm
hint: use one once with --device ID, or remember one with: openvave select ID
```

  (strongest first; a known pedal's row ends with its nickname.)
- Invalid configuration file, and the configuration is needed (no `--device`/`OPENVAVE_DEVICE`
  identifier): exit 2, `error: <path>: <problem>`, `hint: fix the file or reset it with: openvave
  forget --all`. With an identifier from the option or the environment the command runs and
  prints `warning: <path>: <problem> (nicknames unavailable)`.

### The "pedal" line

Human mode, stderr, once the pedal is chosen and before connecting (research R8):

```text
pedal: stage  8F3A21C4…  -58 dBm  (selected)
```

Reason is one of `(selected)`, `(--device)`, `(OPENVAVE_DEVICE)`, `(only one found)`. No nickname →
the identifier comes first. An advertised name other than `TANK-Gv2_BLE` appends
`name: <name> (not a Tank-G name)`. Not printed with `--json`. stdout is byte-identical to 0.4.0.

### JSON `device` object (every document that has one)

Adds `"nickname": string | null` and `"chosen_by": "device_option" | "environment" | "selected" |
"only_one_found"`. `schema_version` stays 2.

## `openvave scan [--all] [--identify]`

Scans for the whole `--scan-timeout` (default 5 s). Connects to nothing unless `--identify`.

```text
$ openvave scan
Scanning for 5 s…
* stage  8F3A21C4-0000-4000-8000-000000000001  TANK-Gv2_BLE  -58 dBm
         8F3A21C4-0000-4000-8000-000000000002  TANK-Gv2_BLE  -61 dBm
2 pedals found. * = default. Select one: openvave select ID [--name NICKNAME]
```

- `Scanning for N s…` goes to stderr (human mode only). Rows: default marker, nickname (known pedals), identifier in
  full, advertised name, signal strength (`? dBm` when unknown); strongest first.
- The default is known but not seen: a last line `stage (8F3A21C4-0000-4000-8000-000000000001) not
  seen` (full identifier; `default <identifier> not seen` when it has no nickname).
- `--all`: other advertisers follow, each ending with `(not a Tank-G)`; an empty name shows `-`.
- `--identify`: each Tank-G row gains `fw 96`, or `fw ? (<reason>)` when the connection or
  handshake failed. Sends only the confirmed `0x11` query.
- None found (exit 3; the first line on stdout, the hint on stderr):

```text
No Tank-G found.
hint: switch the pedal on and close the M-VAVE phone app; a pedal that is connected to the app
      or to another program stops advertising.
```

- Invalid configuration file: the pedals are still listed (no nicknames, no default marker) after
  `warning: <path>: <problem> (nicknames unavailable)` on stderr.
- `--json`: one document, [`scan.schema.json`](scan.schema.json), also when the list is empty
  (then exit 3).
- Exit: 0 at least one Tank-G listed · 3 none · 5 Bluetooth unavailable.

## `openvave select [TARGET] [--name NICKNAME] [--offline]`

TARGET (research R4): a known nickname · a full identifier · an identifier prefix (≥ 4 hex
characters) matching exactly one Tank-G in range. No TARGET: the only Tank-G in range.

```text
$ openvave select 8F3A --name stage
Default pedal: stage  8F3A21C4-0000-4000-8000-000000000001  (TANK-Gv2_BLE, -58 dBm)
Saved in /Users/me/.config/openvave/devices.json
```

- When it replaces a default: a line `Was: home  AA:BB:CC:DD:EE:01`. The old default stays known.
- A full identifier or a prefix is checked by a scan; not seen → exit 3, nothing saved.
  `--offline` (full identifier only) saves without scanning. A known nickname needs no scan.
- `--name` on a pedal that already has a nickname renames it.
- Several matches or several pedals with no TARGET: exit 4, the list, nothing saved. None: exit 3.
- Bad nickname or one used by another pedal: exit 2, nothing saved.
- Never prompts. `--json`: [`device.schema.json`](device.schema.json) (`"command": "select"`).

## `openvave device [--check]`

Shows the configuration. No Bluetooth without `--check`.

```text
$ openvave device
Default pedal: stage  8F3A21C4-0000-4000-8000-000000000001
  selected 2026-11-19 10:02, last seen 2026-11-19 10:05 (TANK-Gv2_BLE, firmware 96)
Known pedals:
* stage  8F3A21C4-0000-4000-8000-000000000001
  home   8F3A21C4-0000-4000-8000-000000000002
Configuration: /Users/me/.config/openvave/devices.json
openvave connects for the length of one command; this is a choice, not an open connection.
```

- Nothing selected: `No default pedal. Commands use the only Tank-G in range.` and
  `Choose one: openvave scan, then openvave select ID`, then the known pedals (if any) and the
  `Configuration:` line. Exit 0.
- `OPENVAVE_DEVICE` set: a line `OPENVAVE_DEVICE=<value> overrides the default in this shell.`
- `--check`: scans for the default (stops when seen) and adds `In range: yes (-58 dBm)` (exit 0) or
  `In range: no` (exit 3). With no default, `--check` exits 2.
- `--json`: [`device.schema.json`](device.schema.json) (`"command": "device"`).

## `openvave device rename OLD NEW`

Renames a nickname (OLD may also be an identifier of a known pedal). Unknown OLD, bad or used NEW:
exit 2. Prints `Renamed stage → live  8F3A21C4-…`. No Bluetooth.

## `openvave forget [TARGET | --all]`

- No argument: clears the default, keeps the known pedals. `Forgot the default (stage
  8F3A21C4-…). It is still a known pedal; remove it with: openvave forget stage`. No default:
  `No default pedal.`, exit 0.
- TARGET (nickname or identifier): removes that known pedal; unknown → exit 2.
- `--all`: removes everything. On an invalid file it moves it to
  `devices.json.invalid-<YYYYmmdd-HHMMSS>` and says so (`--json`: `moved_to`).
- No Bluetooth. `--json`: [`device.schema.json`](device.schema.json) (`"command": "forget"`).

## Exit codes (no new code)

| Code | New situations in 0.5.0 |
|---|---|
| 2 | unknown nickname; bad or duplicate nickname; invalid configuration file; `device --check` with no default |
| 3 | the chosen pedal was not seen (any source); `scan` / `select` found no Tank-G; `device --check` not in range |
| 4 | `select` with several candidates |
