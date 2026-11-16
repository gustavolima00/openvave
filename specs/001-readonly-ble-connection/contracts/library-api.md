# Library API contract: `openvave`

Public surface (semver-governed, Constitution V). Everything not listed here is internal.
Types are described in [data-model.md](../data-model.md).

```python
import openvave

# Discovery
devices: list[openvave.DeviceInfo] = await openvave.discover(timeout=5.0)

# Session over BLE (picks the single pedal found, or the given identifier)
async with openvave.TankG.connect(device=None, scan_timeout=5.0, timeout=2.0) as pedal:
    pedal.identity                      # DeviceIdentity (handshake done on enter)
    snap = await pedal.snapshot()       # DeviceSnapshot: all four regions
    read = await pedal.read(openvave.Region.CURRENT_PRESET)   # RegionRead

# Session over any transport (tests, other tools)
fake = openvave.FakeTransport.from_capture("captures/fw96/20261116-probe-connect.jsonl")
async with openvave.TankG.over(fake, timeout=2.0) as pedal:
    ...
fake.sent                               # list[bytes]: every frame written, in order
```

## Exports

| Name | Kind |
|---|---|
| `discover` | async function |
| `TankG` | session class: `connect(...)`, `over(transport, ...)`, `.identity`, `.device`, `snapshot()`, `read(region)` |
| `Region` | enum (4 members, closed) |
| `DeviceInfo`, `DeviceIdentity`, `RegionRead`, `DeviceSnapshot` | frozen dataclasses |
| `Transport` | `typing.Protocol` |
| `FakeTransport` | test/simulation transport |
| `TESTED_FIRMWARE` | `frozenset[int]` |
| `OpenvaveError` and subclasses listed in data-model.md | exceptions |
| `openvave.protocol` | pure codec module: `encode_frame`, `decode_frame`, `FrameAssembler`, `build_query`, `build_read`, `parse_read_reply`, `parse_identity` |

## Transport protocol

```python
class Transport(Protocol):
    async def open(self) -> None: ...                 # connect + enable notifications
    async def write(self, frame: bytes) -> None: ...  # write-without-response to ae41
    def on_notify(self, callback: Callable[[bytes], None]) -> None: ...  # ae42 chunks
    async def close(self) -> None: ...                # idempotent
```

Implementations: `BleakTransport` (internal construction via `TankG.connect`), `FakeTransport`.

## Guarantees

- `TankG` never sends a frame whose command byte is not `0x11` or `0x23`.
- `read()` accepts only `Region` members; there is no address-based read.
- On exit from the `async with` block (normal or exceptional) the transport is closed.
- Requests are strictly sequential: one in flight at a time (pedal is request/response).
- Hex trace via logger `openvave.trace` (DEBUG); off unless a handler is attached.
- No background tasks survive `close()`; no polling.
