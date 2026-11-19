# Quickstart: validating feature 005

Contracts: [cli.md](contracts/cli.md), [library-api.md](contracts/library-api.md). Shapes:
[data-model.md](data-model.md). Sections 1–3 need no pedal. Section 4 is run by the owner in their
own terminal (reads only; no write is sent anywhere in this feature).

## 1. Hardware-free suite (every milestone)

```bash
uv run pytest
```

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy
```

Expected: green. The suite never touches `~/.config/openvave` (it sets `OPENVAVE_CONFIG` to a
temporary file) and loads no Bluetooth backend.

## 2. Configuration commands without Bluetooth (M1)

```bash
export OPENVAVE_CONFIG="$(mktemp -d)/devices.json"
```

```bash
openvave device
```

Expected: `No default pedal…`, exit 0.

```bash
openvave select AA:BB:CC:DD:EE:01 --name stage --offline
```

```bash
openvave select AA:BB:CC:DD:EE:02 --name home --offline
```

```bash
openvave device
```

Expected: default `home`, both listed, the "this is a choice, not an open connection" line.

```bash
openvave select stage && openvave device rename home rehearsal && openvave forget && openvave device --json
```

Expected: no default, two known pedals (`stage`, `rehearsal`); the document validates against
`contracts/device.schema.json`.

```bash
openvave info --device nobody; echo "exit $?"
```

Expected: `unknown nickname`, the known nicknames listed, exit 2, no scan.

## 3. Choice rules without a pedal (M2)

Covered by tests with a fake scanner; the table in data-model.md ("Scan outcome for a command") is
the checklist. Spot check with Bluetooth on and no pedal:

```bash
openvave info --device stage; echo "exit $?"
```

Expected: after the scan timeout, `error: stage (AA:BB:CC:DD:EE:01) not found`, hints, exit 3.

## 4. Hardware (owner, pedal on, phone app closed) — M4

Use a fresh shell without `OPENVAVE_CONFIG` (or keep the temporary one to leave your real file
untouched).

```bash
openvave scan
```

Expected: one row with the pedal's identifier and signal strength, exit 0, about 5 s.

```bash
openvave scan --identify
```

Expected: the row gains `fw 96`.

```bash
openvave select --name stage
```

Expected: `Default pedal: stage …`, the configuration path.

```bash
openvave info
```

Expected: stderr `pedal: stage  <id>…  <rssi> dBm  (selected)`; stdout as in 0.4.0; noticeably
faster than before (no 1 s grace).

```bash
openvave device --check
```

Expected: `In range: yes`.

```bash
openvave info --json | python3 -c "import json,sys; print(json.load(sys.stdin)['device'])"
```

Expected: `nickname: 'stage'`, `chosen_by: 'selected'`.

Then, with the **phone app connected** to the pedal:

```bash
openvave scan; echo "exit $?"
```

```bash
openvave info; echo "exit $?"
```

Expected: `No Tank-G found` / `stage (…) not found`, the "connected pedal stops advertising" hint,
exit 3 both. Close the app again.

Two commands at once (second terminal while the first runs):

```bash
openvave watch --duration 15
```

```bash
openvave info; echo "exit $?"
```

Expected: the second exits 3 with the same hint.

Optional observation for the protocol notes (macOS): turn Bluetooth off and on, run
`openvave device --check`, and report whether the identifier is still seen.

```bash
openvave forget
```

Expected: `Forgot the default (stage …)`; `openvave info` then reports `(only one found)`.

If a second Tank-G is available: repeat `scan` (two rows, strongest first), `info` with no default
(exit 4, both listed with both hints), `select <prefix>`, `info` (uses the selected one), switch
the selected one off and run `info` (exit 3, the other listed under `seen:`).

## 5. Long-lived connection (M3, hardware optional)

```python
import asyncio, openvave

async def main() -> None:
    pedal = openvave.TankG.connect_selected()
    await pedal.open()
    try:
        for _ in range(5):
            print((await pedal.state()).kind, pedal.is_connected)
            await asyncio.sleep(1)
    finally:
        await pedal.close()

asyncio.run(main())
```

Expected: five lines over one connection; switching the pedal off mid-loop raises
`ConnectionLostError` and `is_connected` is false.
