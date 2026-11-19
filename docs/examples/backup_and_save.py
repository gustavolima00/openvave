"""Back up all 36 stored presets to a file, then (optionally) save the current sound.

    python docs/examples/backup_and_save.py                 # backup only (read-only)
    python docs/examples/backup_and_save.py --save-to 1C    # UNSAFE: overwrites stored 1C

save_preset() always takes its own verified backup first and hands it to on_backup before the
first write; if on_backup raises, nothing is written.
"""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

from openvave import Backup, OpenvaveError, TankG


def write_backup(backup: Backup, suffix: str = "") -> Path:
    path = Path(f"tankg-backup-{datetime.now():%Y%m%d-%H%M%S}{suffix}.json")
    with path.open("x", encoding="utf-8") as fh:  # "x": never overwrite
        json.dump(backup.to_document(), fh, indent=2)
    return path


def index_of(position: str) -> int:
    """'1A'..'9D' -> 0..35 (bank * 4 + slot)."""
    bank, slot = int(position[0]), "ABCD".index(position[1].upper())
    return (bank - 1) * 4 + slot


async def main() -> None:
    async with TankG.connect() as pedal:
        backup = await pedal.backup()  # 36 single reads + whole image, cross-checked
        print("backup:", write_backup(backup))
        for preset in backup.presets[:4]:
            print(preset.position, preset.data.hex(" "))

        if "--save-to" not in sys.argv:
            return
        to = index_of(sys.argv[sys.argv.index("--save-to") + 1])
        plan = await pedal.plan_save(to, unsafe=True)
        if plan.no_change:
            print("that slot already holds this sound; nothing to do")
            return
        if plan.refusal:
            print("refused:", plan.refusal)
            return
        try:
            result = await pedal.save_preset(
                to,
                unsafe=True,
                on_backup=lambda b: print("automatic backup:", write_backup(b, "-before-save")),
            )
        except OpenvaveError as err:
            if err.sequence is not None:  # failed mid-sequence: every step's status
                for step in err.sequence.steps:
                    print(step.step.kind, step.status)
                print("stored presets may have changed:", err.sequence.stored_may_have_changed)
            raise
        print("saved and verified:", result.verified)


asyncio.run(main())
