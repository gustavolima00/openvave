"""Plan, then apply, several fields over one connection; then discard them.

Nothing here is saved: the edits live in the pedal's edit buffer until you select a preset,
reload, or save. Run with a pedal:  python docs/examples/dial_in_sound.py
Plan only (reads, sends no write): python docs/examples/dial_in_sound.py --plan
"""

import asyncio
import sys

from openvave import OpenvaveError, TankG, WriteRefusedError

CHANGES = {
    "gain": 95,
    "treble": 58,
    "reverb_decay": ("room", 18),  # (type, position 1-40)
    "mod_fx": (None, 12),  # position 12 of the type the preset already uses
    "delay_on": True,  # block switch: 'observed', needs experimental=True
}


async def main() -> None:
    async with TankG.connect() as pedal:
        plan = await pedal.plan_set_fields(CHANGES, experimental=True)
        if plan.refusal:
            print(f"refused: {plan.refusal} ({plan.refused_field})")
            return
        for edit in plan.fields:
            change = f"{edit.current.hex()} -> {edit.wanted.hex()}"
            note = "already set" if edit.no_change else change
            print(f"{edit.field:<13} {note}")
        for write in plan.writes:
            print("write", write.frame.hex(" "))
        if "--plan" in sys.argv:
            return

        try:
            result = await pedal.set_fields(CHANGES, experimental=True)
        except WriteRefusedError as err:
            print("refused:", err.reason)
            return
        except OpenvaveError as err:
            # stopped mid-batch (NAK, lost link, re-read differs): nothing was retried
            if err.edit is not None:
                for field, status in err.edit.field_status:
                    print(f"{field:<13} {status}")
            raise
        for field, status in result.field_status:
            print(f"{field:<13} {status}")

        input("Listen, then press Enter to discard the edits... ")
        await pedal.reload_preset()


asyncio.run(main())
