# openvave

Open-source, reverse-engineered protocol and client library for the **M-VAVE Tank-G** multi-effects pedal (Bluetooth / USB).

> Unofficial project. Not affiliated with or endorsed by M-VAVE / Cuvave.

## Goals

- Document the Tank-G communication protocol (BLE GATT services, MIDI/SysEx messages, USB).
- Read and write presets, effect blocks, parameters and global settings.
- Stream / control audio over Bluetooth where the hardware allows it.
- Provide a reusable library + CLI that other projects can build on.

## Status

Early research. Specs live in `specs/` and are driven by [Spec Kit](https://github.com/github/spec-kit)
(`/speckit-constitution` → `/speckit-specify` → `/speckit-plan` → `/speckit-tasks` → `/speckit-implement`).

## License

MIT — see [LICENSE](LICENSE).
