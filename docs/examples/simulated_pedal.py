"""Drive a simulated Tank-G: no pedal, no Bluetooth (openvave 0.7.0).

    python docs/examples/simulated_pedal.py

Builds a simulated pedal from a recorded session (``captures/fw96/20261116-probe-connect.jsonl``),
prints the front panel and which groups the current preset has enabled, selects 2C, changes two
fields, backs up, saves, restores the backup and counts the frames sent. Everything happens in
memory: the simulated pedal is a model built from the protocol document, not evidence of what a
pedal does.
"""

import asyncio
from pathlib import Path

from openvave import Backup, FakeTransport, Region, TankG, preset_index, preset_position
from openvave.protocol import PANEL_CONTROLS, PANEL_GROUPS, group_enabled

CAPTURE = Path(__file__).resolve().parents[2] / "captures/fw96/20261116-probe-connect.jsonl"


def keep(backup: Backup) -> None:
    """The automatic backup before a persistent write (a real program writes it to a file)."""
    print(f"automatic backup: {len(backup.presets)} presets")


async def main() -> None:
    fake = FakeTransport.simulated(CAPTURE)
    async with TankG.over(fake) as pedal:
        state = await pedal.state()
        print("state:", state.kind, state.position)

        print("front panel, in order:")
        for control in PANEL_CONTROLS:
            where = f"{control.field} (byte {control.offset})" if control.field else "no byte"
            print(f"  {control.order:2} {control.label:<10} {control.group:<6} {where}")

        preset = (await pedal.read(Region.CURRENT_PRESET)).data
        for group in PANEL_GROUPS:
            enabled = group_enabled(group.name, preset)
            shown = "no on/off" if enabled is None else ("on" if enabled else "off")
            note = f" ({group.enabled_confidence})" if group.enabled_confidence else ""
            print(f"{group.name}: {shown}{note}")

        target = preset_index("2C")
        await pedal.select_preset(target)
        print("selected:", preset_position(target))
        await pedal.set_fields({"gain": 95, "delay_on": False})

        backup = await pedal.backup()
        result = await pedal.save_preset(unsafe=True, on_backup=keep)
        print("saved:", "verified" if result.verified else "NOT verified")

        await pedal.restore(backup, slot=target, unsafe=True, on_backup=keep)
        print("restored:", preset_position(target))

    print("frames sent:", len(fake.sent))


if __name__ == "__main__":
    asyncio.run(main())
