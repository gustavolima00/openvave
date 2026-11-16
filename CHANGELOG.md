# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0]

First release: a **read-only** BLE client for the M-VAVE Tank-G.

### Added

- `openvave info`: finds the pedal, runs the handshake and reads the device info, global settings,
  current preset and status regions.
- `openvave preset dump`: reads the 21-byte current preset buffer and prints it with offsets and
  confidence-labelled fields (`confirmed` / `observed` / `hypothesis`).
- `--json` output for both commands, `schema_version` 1
  ([`info`](specs/001-readonly-ble-connection/contracts/info.schema.json),
  [`preset dump`](specs/001-readonly-ble-connection/contracts/preset-dump.schema.json)).
- Global options `--device`, `--scan-timeout`, `--timeout`, `--trace` (hex of every frame on stderr).
- Exit codes 0–7 as a public contract
  ([CLI contract](specs/001-readonly-ble-connection/contracts/cli.md#exit-codes)).
- Python library: `TankG` (`connect()`, `over()`, `read()`, `snapshot()`), `discover()`, typed
  models and errors, and `FakeTransport` for testing without a pedal
  ([library contract](specs/001-readonly-ble-connection/contracts/library-api.md)).
- Safety: only the handshake query (`0x11`) and region reads (`0x23`) can be encoded; every other
  command byte raises `UnsafeCommandError`.

### Tested

- Firmware 96 on macOS 26. Other firmware versions work with a `warning:` on stderr. Linux and
  Windows are untested on hardware.
