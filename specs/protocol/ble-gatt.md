# Tank-G BLE: advertising & GATT table

Status: early research. Confidence levels per Constitution II
(`confirmed` = reproduced on hardware, `observed` = seen in captures, `hypothesis`).

Evidence: `captures/private/20261116-102548-ble.jsonl` (raw, not committed), scan of 2026-11-16.
Firmware version: unknown (not exposed over GATT; TODO read from pedal menu / app).

## Advertising

| Field | Value | Confidence |
|---|---|---|
| Local name | `TANK-Gv2_BLE` | confirmed |
| Service UUID | `03b80e5a-ede8-4b33-a751-6ce34ec4c700` (BLE-MIDI) | confirmed |
| Manufacturer data | company id `0x6973`, payload `6e 63 6f` | confirmed |
| Manufacturer data meaning | LE bytes `73 69` + `6e 63 6f` = ASCII `"sinco"` (chip/firmware vendor tag?) | hypothesis |

The vendor service `ae40` is not advertised; it only appears after connecting.

The identifier openvave shows on macOS is a CoreBluetooth UUID assigned per computer, not the
pedal's MAC address; the same pedal has another identifier on another Mac (by design of
CoreBluetooth; the same UUID was reported by `scan`, `info` and `select` throughout a session,
observed 2026-11-19, fw 96). The pedal stops advertising while any central is connected,
including another openvave process on the same computer (observed, 2026-11-16 and 2026-11-19).
The identifier survived turning the Mac's Bluetooth off and on (`device --check` saw it, observed 2026-11-19, macOS 26).

## GATT

ATT MTU negotiated by macOS: 185 (confirmed).

| Service | Characteristic | Properties | Role | Confidence |
|---|---|---|---|---|
| `0000ae40-…-00805f9b34fb` (vendor) | `0000ae41-…` | write-without-response | host → pedal command channel | hypothesis |
| | `0000ae42-…` | notify (CCCD present) | pedal → host response channel | hypothesis |
| `03b80e5a-ede8-4b33-a751-6ce34ec4c700` (BLE-MIDI) | `7772e5db-3868-4112-a1a9-f2669d106bf3` | read, notify, write-without-response | standard BLE-MIDI I/O; read returns empty | confirmed (properties) |

`ae40/ae41/ae42` matches the stock "BLE UART" layout shipped by several Chinese BLE SoC
SDKs; the app protocol likely runs over it rather than over BLE-MIDI (hypothesis).

## Behaviour

- With both notify characteristics subscribed, the pedal sent **no notifications in 90 s** while
  presets were changed, knobs turned and effects toggled (observed, 1 session).
  → The pedal appears to be request/response only: it does not push state unsolicited.
- No device information service (`180a`) or battery service is exposed (confirmed).

## Dual-mode radio

- Besides the BLE peripheral, the pedal exposes a **Classic Bluetooth** identity named
  `TANK-Gv2` (no `_BLE` suffix) that Android pairs as an **A2DP sink** (audio output), with a
  different MAC from the BLE side (confirmed, Android bugreport 2026-11-16; MAC omitted per
  Constitution VI).
- AVRCP absolute volume is not supported on the A2DP link (observed).

## Open questions

- Command layer on `ae41`/`ae42`: see [command-layer.md](command-layer.md) (app handshake,
  register map and frame sizes known; raw bytes still missing).
- Does the pedal emit MIDI on `7772e5db` once some mode is enabled, or only accept MIDI in?
