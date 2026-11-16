# Quickstart: validating feature 002

Runnable checks that prove the byte map, the decoder and `openvave watch` work. Contracts:
[cli.md](contracts/cli.md), [library-api.md](contracts/library-api.md),
[session-record.md](contracts/session-record.md). Model: [data-model.md](data-model.md).

## Prerequisites

- Repo checkout with `uv` installed. `uv sync` installs the dev group.
- For hardware steps: a Tank-G (fw 96) powered on, the **phone app disconnected**, and a terminal
  that has macOS Bluetooth permission (an app without it gets the process killed on first
  Bluetooth access, see `command-layer.md` host observations).

## 1. Hardware-free suite (every milestone)

```bash
uv run pytest
```

```bash
uv run ruff check . && uv run mypy
```

Expected: all green with no Bluetooth adapter. This includes:

- `tests/unit/test_bytemap_doc.py`: the `command-layer.md` byte map table equals `BYTE_MAP`.
- `tests/unit/test_bytemap.py`: 26 offsets covered, no overlaps, confidence/evidence rules.
- `tests/integration/test_fixture_pairs.py`: each mapped field's before/after excerpt changes
  exactly that field (SC-004).
- the 001 command audit: only `0x11`/`0x23` sent, now including `watch` tests (SC-006).

## 2. Offline decoding of the committed capture (M0)

```bash
uv run python -c "from openvave.protocol import decode_region; from openvave import Region, RegionRead; r = RegionRead(Region.CURRENT_PRESET, bytes.fromhex('01 00 00 01 0f 04 3c 3c 46 32 32 00 00 00 00 05 04 07 43 16 43')); print([(f.entry.name, f.display, f.entry.confidence) for f in decode_region(r, 96).fields])"
```

Expected (0.2.0): 18 fields, all `confirmed`, from `amp_on on` to `ir_cab #7`, including
`gain 60`, `reverb_decay 5` and `reverb_mix 4`. (At M0 it was `knob_unknown 60 observed`,
`reverb_decay 5 observed`, `reverb_mix 4 hypothesis`, `ir_cab #7 hypothesis`.)

## 3. Decoded `preset dump` (hardware, opt-in)

```bash
uv run openvave preset dump
```

```bash
uv run openvave preset dump --json
```

Expected: hex dump unchanged from 001; one line per named field (hypothesis rows end with ` ?`);
an `unknown:` line listing the remaining offsets. The JSON validates against the 001 schema plus
[decoded-field.schema.json](contracts/decoded-field.schema.json).

## 4. Watch session (hardware, M1 gate)

```bash
uv run openvave watch
```

Then, typing each label before acting on the pedal:

1. `edit mode on`, then enter edit mode → `global[3] mode normal → edit`.
2. `reverb decay min→max`, then turn only the reverb decay knob fully down, then fully up →
   only `preset[15]` lines, reaching `0` and `127`.
3. `leave edit mode`, then leave edit mode without saving → preset bytes revert, `global[3] mode edit → normal`.
4. `q`.

Expected: exit 0; the record path printed at the end is under `captures/private/` and holds
`meta`, handshake, `tx`/`rx` for every cycle, three `label` events, the `change` events and a
`stop` event. Combined with the 2026-11-16 observation, this second session promotes preset 15
to `confirmed` (FR-010).

Scripted variant (no typing, fixed length):

```bash
uv run openvave watch --json --duration 10 < /dev/null
```

Expected: JSON Lines (`start`, then `change`s if anything moved, then `stop` with reason
`duration`), each valid against [watch-event.schema.json](contracts/watch-event.schema.json).

## 5. Turning a session into evidence (M2/M3)

1. From the record, cut an excerpt for one step (meta + handshake + the cycle before + the
   cycle(s) with the change + `label`/`change` events) into
   `captures/fw96/<date>-step-<field>.jsonl`, following [session-record.md](contracts/session-record.md).
2. Check that label text holds no personal names.
3. Add the fixture to the fixture-pair index and run the tests: they must fail until the map row
   exists.
4. Add the row to the `command-layer.md` table (R1 columns) and to `BYTE_MAP`, citing the excerpt.
5. Run section 1 again: green.

## 6. Completion checks (M3/M4)

- Every control in the `command-layer.md` "Control inventory" has a result (SC-001).
- The byte map lists all 26 offsets (SC-002). Preset bytes 4–17 are each named at `observed`+
  or documented as unchanged by every control (SC-003).
- ≥ 5 stored presets compared and per-preset values recorded for bytes that differ (SC-008).
- With the owner setting known knobs to min and max, `preset dump` shows the documented range
  ends (SC-005).
- A reviewer decodes `01 00 00 01 0f 04 3c 3c 46 32 32 00 00 00 00 05 04 07 43 16 43` by hand
  from `command-layer.md` and gets the same values as `preset dump` (SC-007).
