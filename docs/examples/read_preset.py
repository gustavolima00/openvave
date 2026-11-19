"""Print every decoded field of the current preset, with the type reading of typed knobs.

Run with a pedal nearby:      python docs/examples/read_preset.py
Run without one (replay):     python docs/examples/read_preset.py --fake
"""

import asyncio
import sys

from openvave import FakeTransport, Region, TankG
from openvave.protocol import TYPED_FIELDS, decode_region, type_parts

CAPTURE = "captures/fw96/20261116-probe-connect.jsonl"


def session() -> TankG:
    if "--fake" in sys.argv:
        return TankG.over(FakeTransport.from_capture(CAPTURE))
    return TankG.connect()


async def main() -> None:
    async with session() as pedal:
        print(f"{pedal.identity.name}, firmware {pedal.identity.firmware}")
        print("state:", (await pedal.state()).kind)
        preset = await pedal.read(Region.CURRENT_PRESET)
        decoded = decode_region(preset, pedal.identity.firmware)
        for field in decoded.fields:
            line = f"[{field.entry.offset:2}] {field.entry.name:<13} {field.display:>6}"
            if field.entry.name in TYPED_FIELDS:
                kind, position = type_parts(field.entry.name, field.raw)
                line += f"   {kind} {position}" if kind else "   off (between types)"
            print(line)
        print("unknown offsets:", decoded.unknown_offsets)


asyncio.run(main())
