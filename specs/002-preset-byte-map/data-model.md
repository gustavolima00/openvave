# Data Model: Preset and global byte map (read-only decoding)

Phase 1 output for [plan.md](plan.md). It extends the 001 model
([`../001-readonly-ble-connection/data-model.md`](../001-readonly-ble-connection/data-model.md));
`Region`, `RegionRead`, `DeviceIdentity` and `DeviceSnapshot` are unchanged. All types are
immutable value objects unless marked "state".

## Encoding (enum, closed)

| Member | Interpreted value | In range when | `display` |
|---|---|---|---|
| `continuous` | int | `min ≤ v ≤ max` | `"60"` |
| `switch` | bool | `v ∈ {on_value, off_value}` | `"on"` / `"off"` |
| `selector` | int index | `min ≤ v ≤ max` | label if defined, else `"#7"` |
| `flag` | bool (`v & mask ≠ 0`) | always | `"on"` / `"off"` |
| `index` | int (position, base stated in `notes`) | `min ≤ v ≤ max` | `"1"` |
| `unknown` | — (raw only) | always | `"0x0f"` |

For `flag`, `raw` is the whole byte and `value` is `raw & mask`.

## ByteMapEntry

One row of the byte map. It is mirrored 1:1 from the `command-layer.md` table (research R1).

| Field | Type | Rule |
|---|---|---|
| `region` | `Region` | one of `GLOBAL`, `CURRENT_PRESET`, `STATUS` (device info is out of scope) |
| `offset` | int | `0 ≤ offset < region.length` |
| `mask` | int \| None | `None` = whole byte; else a non-zero 8-bit mask (`flag` only) |
| `name` | str \| None | snake_case, unique per region; `None` iff `encoding = unknown` |
| `label` | str | human text in our own words (e.g. "reverb decay") |
| `encoding` | `Encoding` | see above |
| `min`, `max` | int \| None | required for `continuous`, `selector`, `index`; `None` otherwise |
| `on_value`, `off_value` | int \| None | required for `switch` |
| `labels` | Mapping[int, str] | optional, `selector` only; our own words, never vendor asset names |
| `control` | str \| None | name from the control inventory; `None` if not linked to a control |
| `confidence` | `confirmed` \| `observed` \| `hypothesis` \| None | `None` iff `unknown` |
| `firmware` | int | firmware the evidence came from (96) |
| `evidence` | tuple[str, ...] | capture paths; ≥ 1 for `observed`, ≥ 2 sessions for `confirmed` (FR-009, FR-010) |
| `notes` | str | values seen, controls tried, refuted claims |

Invariants of `BYTE_MAP` (checked by unit tests):

- **Coverage**: for each of the three regions, every offset `0 … length−1` is covered by at
  least one entry (an `unknown` entry counts). That is 26 offsets in total (FR-006, SC-002).
- **No overlap**: whole-byte entries do not share an offset with any other entry. `flag`
  entries on the same offset have disjoint masks.
- **Uniqueness**: `(region, name)` is unique among named entries.
- **Confidence rules**: `hypothesis` entries may have empty `evidence`; `observed` needs ≥ 1
  path; `confirmed` needs paths from ≥ 2 distinct sessions.
- **Doc match**: the set of entries equals the parsed doc table (R1).

`MAP_FIRMWARE = 96`.

Initial content (M0, from current knowledge): preset 6 `knob_unknown` (continuous 0–127,
observed); preset 15 `reverb_decay` (continuous 0–127, observed); preset 16 `reverb_mix`
(continuous 0–127, hypothesis); preset 17 `ir_cab` (selector, hypothesis; range to be
established); global 3 `not_in_edit_mode` (switch on=1/off=0, observed); every other offset
`unknown`.

## DecodedField

A `ByteMapEntry` applied to the bytes of one read.

| Field | Type | Rule |
|---|---|---|
| `entry` | `ByteMapEntry` | the named, non-`unknown` entry |
| `raw` | int | the whole byte |
| `value` | int | `raw`, or `raw & mask` for `flag` (keeps 001's JSON meaning) |
| `interpreted` | int \| bool | per encoding |
| `display` | str | per encoding table |
| `out_of_range` | bool | true when the encoding's range rule fails; `display` then shows the raw value (FR-015) |

## DecodedRegion

| Field | Type | Rule |
|---|---|---|
| `read` | `RegionRead` | raw bytes, unchanged |
| `fields` | tuple[`DecodedField`, ...] | in offset (then mask) order |
| `unknown_offsets` | tuple[int, ...] | offsets covered only by `unknown` entries |
| `map_firmware` | int | `MAP_FIRMWARE` |
| `firmware_untested` | bool | copied from the identity (decoding uses the fw-96 map anyway, FR-018) |

`decode_region(read: RegionRead, firmware: int) -> DecodedRegion` is pure (FR-013). For
`DEVICE_INFO` it returns no fields and every offset unknown.

## ByteChange

| Field | Type | Rule |
|---|---|---|
| `region` | `Region` | |
| `offset` | int | |
| `old`, `new` | int | `old ≠ new` |
| `field` | `ByteMapEntry` \| None | the whole-byte entry, or `None` if unknown. A byte with flag entries lists all of them via `fields` |

`diff(before: RegionRead, after: RegionRead) -> tuple[ByteChange, ...]` is pure, in offset order.

## WatchEvent (library, yielded by `TankG.watch()`)

| Variant | Fields | When |
|---|---|---|
| `WatchStart` | `t`, `identity`, `regions: Mapping[Region, DecodedRegion]` | after the first full cycle |
| `WatchChange` | `t`, `cycle: int`, `changes: tuple[ByteChange, ...]` (≥ 1), `regions` (decoded after-state) | a cycle that differs from the previous one; all changed bytes of one cycle are in one event (FR-005) |

`t` = seconds since the watch started (monotonic clock). Labels and stopping are CLI concerns
(below). The library iterator ends only when the caller stops iterating or the connection
fails (which raises the 001 error).

## Watch session (CLI, state)

| State | Event | Next / effect |
|---|---|---|
| connecting | handshake ok | polling; record `meta` + handshake frames |
| polling | cycle with no change | polling (only `tx`/`rx` recorded) |
| polling | cycle with changes | polling; print + record one `change` per byte, tagged with the current label |
| polling | stdin line (not `q`/`quit`) | polling; current label := line; print + record `label` |
| polling | stdin EOF | polling (labels no longer read) |
| polling | `q` / `quit` / Ctrl-C / `--duration` elapsed | stopped; record `stop`; exit 0 |
| polling | connection lost / protocol error | stopped; record `stop` with error; exit 6 / 7 |

The current label stays active until the next label. The file is flushed after every event
(FR-004).

## Session record (file)

A capture-format JSONL file (research R5; event list in
[contracts/session-record.md](contracts/session-record.md)). Relationships:

- 1 record = 1 connection = 1 `meta` + 1 handshake + N cycles.
- A **mapping step** = one `label` event + the cycles until the next `label`. Its evidence is
  the `change` events inside it.
- A committed **excerpt** = `meta` + handshake + the `tx`/`rx` of the cycle before the step and
  the cycle(s) showing the change, plus the `label` and `change` events. It loads with
  `FakeTransport.from_capture` (ordered replay, R9).

## Control (documentation entity)

Lives in the `command-layer.md` "Control inventory" table, not in code.

| Field | Rule |
|---|---|
| name | our own words, unique |
| kind | `continuous` / `selector` / `switch` / `mode` |
| needs edit mode | yes / no / unknown |
| result | mapped `region[offset]` list, or `no change` with the session date |
