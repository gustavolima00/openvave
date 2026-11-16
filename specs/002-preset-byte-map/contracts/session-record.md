# Session record format (`openvave watch --record`)

A record is a capture file in the format of [`captures/README.md`](../../../captures/README.md).
It adds the event types below, so a contiguous excerpt replays with
`FakeTransport.from_capture` (research R5, R9).

## Lines

| `event` | Fields | Notes |
|---|---|---|
| `meta` | `firmware`, `device`, `platform`, `att_mtu`, `date`, `tool: "openvave watch <version>"`, `interval`, `sanitized: []` | first line |
| `tx` / `rx-chunk` / `rx` | as in captures; `label` ∈ `query`, `global`, `preset`, `status` | every frame of every cycle |
| `label` | `t`, `text` | owner typed a line |
| `change` | `t`, `cycle`, `region` (`global`/`preset`/`status`), `offset`, `old`, `new`, `label` (current label text or `null`) | one per changed byte |
| `stop` | `t`, `reason` (`quit`, `interrupt`, `duration`, `connection_lost`, `protocol_error`), `error` (string or `null`) | last line |

Every line is flushed when written. A record cut short by a crash is still valid JSONL up to its
last complete line.

## Privacy and committing

- Records are written to `captures/private/` (git-ignored) by default.
- A committed excerpt (`captures/fw96/<date>-step-<field>.jsonl`) keeps `meta`, the handshake
  `tx`/`rx`, the `tx`/`rx` of the cycle before the step and of the cycle(s) that show the change,
  and the step's `label` and `change` events. Label text is reviewed so it holds no personal
  preset names (Constitution VI). Preset, global and status bytes hold no identifiers. If a
  byte is ever replaced, it is listed in `sanitized` and the frame checksum is recomputed (as
  for 001 captures).
