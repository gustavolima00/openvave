# Hardware check D (spec 007 US5, T026): copy, swap, export, import

Run by the owner in their own terminal. Only confirmed writes are used (stored slot, stored image,
commit, preset select). Every persistent step runs `--dry-run` first; its frames are compared with
the ones below (encoded independently from `specs/protocol/command-layer.md`) or, for the swap,
with an image computed from backup D0, and approved in chat before the real run. The scratch slot
is **9D** (factory content, restored at the end from D0). The pedal starts on **1B**.

## Setup

```bash
cd /Users/gustavomarques/personal/riffmind/openvave/.claude/worktrees/recursing-shannon-99d063
P=/Users/gustavomarques/personal/riffmind/openvave/captures/private
```

## Steps

| # | Step | Command | Expected | Check |
|---|---|---|---|---|
| 0 | backup D0 | `uv run openvave preset backup --output $P/20261119-gate007-D0.json` | reads only | cross-check OK |
| 1 | export 1A | `uv run openvave preset export 1A --output $P/20261119-gate007-1A.json` | reads only | `raw` = `01 00 01 01 12 05 41 37 41 37 32 00 00 0c 28 35 0f 07 ff f7 00` |
| 2 | copy dry run | `uv run openvave preset copy 1A 9D --unsafe --dry-run` | slot `00 59 22 1d 00 00 04 e1 02 00 00 15 00 00 01 00 01 01 12 05 41 37 41 37 32 00 00 0c 28 35 0f 07 ff f7 00 52`, commit `00 59 22 08 00 00 04 00 00 00 f0 00 00 00 0b`, select 9D `00 59 22 09 00 00 04 23 00 00 e0 01 00 00 01 f6` | equal |
| 3 | copy | `uv run openvave --trace preset copy 1A 9D --unsafe --backup-dir $P 2> $P/20261119-gate007-copy_d.trace` | 3 × ACK | `verify … copied`; pedal on 9D sounds like 1A |
| 4 | swap dry run | `uv run openvave preset swap 9C 9D --unsafe --dry-run` | image write, commit, select 9D | I compare the image with D0 + 9D = 1A, then 9C ↔ 9D |
| 5 | swap | `uv run openvave --trace preset swap 9C 9D --unsafe --backup-dir $P 2> $P/20261119-gate007-swap_d.trace` | 3 × ACK | `verify … swapped`; 9C now sounds like 1A |
| 6 | import dry run | `uv run openvave preset import $P/20261119-gate007-1A.json --to 9D --unsafe --dry-run` | slot write = step 2's frame, commit, select 9D | equal |
| 7 | import | `uv run openvave --trace preset import $P/20261119-gate007-1A.json --to 9D --unsafe --backup-dir $P 2> $P/20261119-gate007-import_d.trace` | 3 × ACK | `verify … imported` |
| 8 | restore all | `uv run openvave preset restore $P/20261119-gate007-D0.json --all --unsafe --backup-dir $P` (dry run first: `differ: 9C 9D (2 of 36)`) | 3 × ACK | `restored` |
| 9 | select 1B | `uv run openvave preset select 1B` | `00 59 22 09 00 00 04 01 00 00 e0 01 00 00 01 18` | back on 1B |
| 10 | backup D1 | `uv run openvave preset backup --output $P/20261119-gate007-D1.json` | reads only | equal to D0 apart from `created_at` |

## Result (2026-11-19, owner at the pedal)

Every persistent step ran its dry run first; each frame was compared with the independent encoding
(copy, import, selects) or with the image computed from D0 (swap: 773 bytes equal, checksum `88`;
restore: D0's image, checksum `7a`) and approved in chat before the real run.

| Step | Result |
|---|---|
| export 1A | read-only; `raw` = the public 1A bytes |
| copy 1A → 9D | slot write, commit, select 9D: 3 × ACK; `verify stored 9D = 1A … copied` |
| swap 9C ↔ 9D | image write (773 bytes, 5 Bluetooth writes), commit, select 9D: 3 × ACK; `verify 36 of 36 … swapped` |
| import 1A file → 9D | slot write (same frame as the copy), commit, select 9D: 3 × ACK; `imported` |
| restore all from D0 | `differ: 9C 9D (2 of 36)`; 3 × ACK; `restored` |
| select 1B | ACK, applied |
| D1 vs D0 | equal apart from `created_at` |

Each command took its automatic backup first (`captures/private/tankg-backup-20261119-1703*-before-copy|swap.json`,
`…-170509-before-import.json`, `…-170602-before-restore.json`). Traces stay in `captures/private/`
(`20261119-gate007-{copy,swap,import}_d.trace`): they carry the stored presets read by the
automatic backups, and no new message was sent (the stored-slot, stored-image, commit and select
rows were already `confirmed`), so no excerpt is committed.
