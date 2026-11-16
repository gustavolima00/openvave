# Quickstart & validation: Read-only BLE connection to the Tank-G

Run guide proving the feature works. Contracts: [cli.md](contracts/cli.md),
[library-api.md](contracts/library-api.md); types: [data-model.md](data-model.md).

## Prerequisites

- Python ≥ 3.11 and [`uv`](https://docs.astral.sh/uv/)
- For hardware scenarios only: a Tank-G (fw 96 for byte-exact checks), the M-effects phone app
  **closed/disconnected** (the pedal accepts one BLE central), Bluetooth on, and on macOS the
  terminal granted Bluetooth permission (System Settings → Privacy & Security → Bluetooth).

```bash
uv sync
```

## Hardware-free scenarios (CI)

| # | Command | Expected |
|---|---|---|
| 1 | `uv run pytest` | All tests pass with Bluetooth off / no adapter; `tests/hardware` reported as skipped (SC-003) |
| 2 | `uv run pytest tests/unit -k round_trip` | Each of the 5 captured requests and replies in `captures/fw96/20261116-probe-connect.jsonl` round-trips byte-identically (FR-020) |
| 3 | `uv run pytest tests/unit -k reject` | bad marker, length mismatch, bad checksum, wrong command echo, address/length echo mismatch, short data are each rejected with their reason code (FR-005) |
| 4 | `uv run pytest tests/integration` | Full capture replayed through `FakeTransport`: identity `TANK-Gv2`/96, four regions equal the recorded data; split-notification variants reassemble (FR-006); no-reply variant times out within `timeout` (FR-009); handshake succeeds on the 3rd attempt and fails after 3 (FR-007) |
| 5 | `uv run pytest tests/contract` | `info`/`preset dump` JSON (from `FakeTransport`) validate against the schemas; exit codes 3–7 produced for their error conditions; stdout empty on failure with `--json` |
| 6 | (automatic, every run) | SC-004 audit fixture: no frame with a command byte other than `0x11`/`0x23` was written by any test |

## Hardware scenarios (opt-in, macOS required for v1)

```bash
uv run openvave info
```

Expected on fw 96: `TANK-Gv2 (firmware 96)`; Global `00 00 01 01` (unless a knob was moved
since the last preset load); Status `01`; exit 0; < 10 s (SC-001).

```bash
uv run openvave info --json | python -m json.tool
```

Expected: a single JSON document, `schema_version: 1`, `firmware_untested: false`, all four
regions present; nothing else on stdout.

```bash
uv run openvave preset dump
```

Expected: 21 bytes at offsets 0–20. Turn one knob on the pedal, run again: byte 6 (or another
parameter byte) changes; the tool does not cache (US3 scenario 3).

```bash
uv run openvave --trace preset dump
```

Expected on stderr: `TX 00 59 11 00 00 00 ff`, the handshake `RX`, then
`TX 00 59 23 08 00 00 04 00 00 00 10 15 00 00 d6` and its `RX` — and no other `TX`.

```bash
uv run pytest --hardware tests/hardware
```

Expected: pass on macOS + fw 96. Record OS version, firmware and result in the PR (constitution
development workflow).

## Error-path spot checks (hardware or none)

| Situation | Command | Expected |
|---|---|---|
| Pedal off | `uv run openvave info --scan-timeout 3` | `error: no Tank-G found…` on stderr, exit 3, ~3 s |
| Bluetooth off | `uv run openvave info` | `error: Bluetooth unavailable…` + hint, exit 5 |
| Phone app still connected | `uv run openvave info` | `error: no TANK-Gv2_BLE found` + hint to close the phone app, exit 3 after the full scan — the pedal stops advertising while the app is connected (observed 2026-11-16, fw 96) |
