# Examples

Small, complete scripts using the `openvave` library. Run them from the repository root (the
`--fake` mode reads a committed capture by relative path).

| Script | Writes? | What it does |
|---|---|---|
| [`read_preset.py`](read_preset.py) | no | Prints every decoded field of the current preset, with effect types. `--fake` replays a recorded session, no pedal needed. |
| [`dial_in_sound.py`](dial_in_sound.py) | volatile | Plans several fields at once, applies them over one connection, then discards them with `reload_preset()`. `--plan` only reads. |
| [`backup_and_save.py`](backup_and_save.py) | `--save-to` only: **persistent** | Backs up all 36 presets to a JSON file; with `--save-to 1C` saves the current sound there, after the automatic backup. |

```bash
python docs/examples/read_preset.py --fake
python docs/examples/dial_in_sound.py --plan
python docs/examples/backup_and_save.py
```

See the [library guide](../library.md) for the API they use.
