# Data Model: Read-only BLE connection to the Tank-G

Phase 1 output for [plan.md](plan.md). Byte-level facts come from
[`specs/protocol/command-layer.md`](../protocol/command-layer.md); all are `confirmed` on fw 96
unless marked otherwise.

All model types are immutable value objects.

## Frame

One protocol message on the `ae41`/`ae42` channel.

| Field | Type | Rule |
|---|---|---|
| `command` | int (1 byte) | Encoding: MUST be in `ALLOWED_COMMANDS = {0x11, 0x23}` else `UnsafeCommandError`. Decoding: any byte is parsed, but the session rejects a reply whose command ≠ the request's. |
| `body` | bytes | length 0 … 2²⁴−1 |
| `checksum` | int (1 byte) | `(~sum(body)) & 0xFF`; header not summed |

Wire layout: `00 59 | command | len(body) as 3 bytes LE | body | checksum`
(total = `len(body) + 7`).

Decode validation (each failure → `ProtocolError` with a specific reason):
`bad_marker` (bytes 0–1 ≠ `00 59`), `length_mismatch` (buffer ≠ `7 + len`), `bad_checksum`.

## FrameAssembler (state)

Accumulates `ae42` notification chunks into complete frames.

| State | Event | Next |
|---|---|---|
| empty | chunk starting with `00 59` | collecting (expected = 7 + len from header, once ≥ 6 bytes) |
| empty | chunk not starting with `00 59` | empty; chunk reported as `stray` (trace + ignored) |
| collecting | bytes received < expected | collecting |
| collecting | bytes received == expected | emit frame → empty |
| collecting | bytes received > expected | emit frame, remainder treated as new input |
| any | `reset()` (new request / timeout) | empty |

Reassembly across notifications is `observed` (app code), not yet seen on hardware (R6).

## Region

Closed enumeration — the only memory reads this feature can issue (FR-008, FR-011).

| Member | type | address | length | Meaning (confidence) |
|---|---|---|---|---|
| `DEVICE_INFO` | 5 | `0xD0000000` | 32 | device info block (hypothesis); bytes 0–3 = `0a 30 39 36` on fw 96 |
| `GLOBAL` | 4 | `0x20000000` | 4 | global settings (hypothesis); byte 3 = 1 normally, 0 in edit mode (observed; "edited" hypothesis refuted 2026-11-16) |
| `CURRENT_PRESET` | 4 | `0x10000000` | 21 | current/edit preset buffer (hypothesis); byte 6 = a knob 0–127 (observed); 15 = reverb decay 0–127 (observed); 16 = reverb mix?, 17 = IR cab? (hypothesis) |
| `STATUS` | 4 | `0xD0000000` | 1 | status byte (hypothesis: current preset index?) |

The read *operations* are confirmed; the *meanings* are not, so renderers show raw bytes and only
attach meanings with their confidence label (FR-017).

## Read request / reply

| | Body layout |
|---|---|
| Request (`0x23`) | `type (1) · address (4, LE) · length (3, LE)` — 8 bytes; frame 15 bytes |
| Reply (`0x23`) | same 8-byte prefix echoed · `data (length)` |

Reply validation (→ `ProtocolError`): `wrong_command`, `echo_mismatch` (type/address/length ≠
request), `short_data` (data length ≠ requested length).

## DeviceInfo (discovery result)

| Field | Type | Notes |
|---|---|---|
| `identifier` | str | platform id: MAC (Linux/Windows) or CoreBluetooth UUID (macOS) |
| `name` | str | advertised local name, `TANK-Gv2_BLE` |
| `rssi` | int \| None | dBm, for disambiguation |

## DeviceIdentity (handshake result)

Parsed from the 27-byte `0x11` reply payload.

| Field | Type | Rule |
|---|---|---|
| `raw` | bytes (27) | payload as received |
| `name` | str | ASCII up to first NUL, split at the **last** `_`: left part (`TANK-Gv2`) |
| `firmware` | int | right part as decimal (`096` → 96) |
| `firmware_untested` | bool | `firmware not in TESTED_FIRMWARE` (= `{96}`) — clarification Q1 |

Validation: payload not 27 bytes, non-ASCII before NUL, no `_`, or non-numeric version →
`ProtocolError("bad_identity")`.

## RegionRead

| Field | Type |
|---|---|
| `region` | Region |
| `data` | bytes (len == region.length) |

## DeviceSnapshot

Result of one connection's full read sequence (what `info` shows).

| Field | Type |
|---|---|
| `device` | DeviceInfo \| None (None with `FakeTransport`) |
| `identity` | DeviceIdentity |
| `regions` | mapping Region → RegionRead (all four, in connect order) |
| `read_at` | datetime, UTC, taken after the last read |

Lifecycle of a session (`TankG`):

```text
disconnected → connecting → subscribed (notify on ae42, 200 ms settle)
            → identified (handshake ok, ≤ 3 attempts) → reading → closed
any state ──error/timeout──▶ closed (transport always disconnected; error raised)
```

## Errors (→ CLI exit code, see contracts/cli.md)

| Error | Exit |
|---|---|
| `NoDeviceFoundError` | 3 |
| `MultipleDevicesError` (carries candidate `DeviceInfo` list) | 4 |
| `BluetoothUnavailableError` (adapter off / permission denied) | 5 |
| `ConnectionLostError`, `RequestTimeoutError` | 6 |
| `ProtocolError` (reason code), `HandshakeError` (after 3 attempts) | 7 |
| `UnsafeCommandError` (programming error; never reachable from CLI) | 1 |

All derive from `OpenvaveError`.
