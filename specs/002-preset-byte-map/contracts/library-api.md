# Library API additions: `openvave` (feature 002)

Extends [001 `library-api.md`](../../001-readonly-ble-connection/contracts/library-api.md).
All additions are additive (MINOR version bump: 0.2.0). Types: [data-model.md](../data-model.md).

```python
import openvave
from openvave.protocol import BYTE_MAP, MAP_FIRMWARE, decode_region, diff

# Offline decoding (pure, no connection)
decoded = decode_region(read, firmware=96)        # DecodedRegion
for f in decoded.fields:
    f.entry.name, f.display, f.entry.confidence, f.out_of_range
decoded.unknown_offsets                           # (0, 1, 2, ...)

# Watching a pedal (the only polling API)
async with openvave.TankG.connect() as pedal:
    async for event in pedal.watch(interval=0.5):
        match event:
            case openvave.WatchStart(regions=regions): ...
            case openvave.WatchChange(changes=changes): ...
            # break to stop; the connection closes on leaving `async with`

# Deterministic tests
fake = openvave.FakeTransport.from_capture("captures/fw96/<date>-step-reverb_decay.jsonl")
async with openvave.TankG.over(fake) as pedal:
    events = [e async for e in pedal.watch(interval=0.5, sleep=no_sleep, cycles=3)]
```

## New exports

| Name | Kind |
|---|---|
| `Encoding` | enum (6 members, closed) |
| `ByteMapEntry`, `DecodedField`, `DecodedRegion`, `ByteChange` | frozen dataclasses |
| `WatchStart`, `WatchChange` (`WatchEvent` = their union) | frozen dataclasses |
| `TankG.watch(interval=0.5, *, regions=(GLOBAL, CURRENT_PRESET, STATUS), cycles=None, sleep=asyncio.sleep)` | async iterator method |
| `openvave.protocol.BYTE_MAP` | `tuple[ByteMapEntry, ...]` |
| `openvave.protocol.MAP_FIRMWARE` | `int` (96) |
| `openvave.protocol.decode_region`, `openvave.protocol.diff` | pure functions |

`FakeTransport`: when a script/capture holds several replies for one request label, they are
served in order and the last one repeats (`from_capture` builds this automatically). Existing
single-reply behaviour is unchanged.

`KNOWN_FIELDS` / `FieldSpec` (001) remain importable as deprecated aliases derived from
`BYTE_MAP` until 1.0, documented in the CHANGELOG.

## Guarantees (in addition to 001's)

- `watch()` sends only `0x23` reads of the requested regions. `regions` accepts only
  `Region.GLOBAL`, `Region.CURRENT_PRESET` and `Region.STATUS` (`ValueError` otherwise).
- `interval` < 0.2 raises `ValueError`. One request is in flight at a time. A cycle that
  overruns its interval starts the next one immediately (no overlap, no backlog).
- `snapshot()`, `read()` and the CLI commands other than `watch` still never poll.
- `decode_region()` and `diff()` perform no I/O and never raise on valid `RegionRead`s. Bytes out
  of range are flagged, never clamped.
