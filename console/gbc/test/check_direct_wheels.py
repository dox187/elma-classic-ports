"""Check every direct wheel result against the cartridge's ordered terrain iterator."""
import argparse
from collections import Counter
from pathlib import Path
import struct
import sys

from check_corner_results import WheelQueries

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from wheel_direct_tiles import BANK, TILES


def call(cart, name, wheel):
    address = cart.sym[name]
    bank = address >> 16
    # The projector switches to lookup banks and restores its tracked low bank.
    cart.m[0x2000] = cart.m[cart.sym['__current_bank']] = bank & 255
    cart.m[0x3000] = bank >> 8
    cart.m[cart.code:cart.code+5] = struct.pack('<BHBB', 0xcd, address & 65535, 0x18, 0xfe)
    cart.reg.SP, cart.reg.PC = cart.stack, cart.code
    cart.reg.D, cart.reg.E = wheel >> 8, wheel & 255
    cart.p.tick(1, False)
    assert (cart.reg.PC, cart.reg.SP) == (cart.code+3, cart.stack)
    cart.m[0x3000] = 0
    cart.m[0x2000] = cart.m[cart.sym['__current_bank']] = 9
    return cart.reg.A


def check(rom, reference):
    target, oracle = WheelQueries(rom), WheelQueries(reference)
    try:
        counts = Counter()
        poison = bytes(range(20))
        for name, (level, tiles) in TILES.items():
            reader = f'direct_{name}_tiles'
            assert target.sym[reader] >> 16 == BANK
            assert oracle.invoke('_physics_collision_select', a=level) == 1
            for x, y in tiles:
                for dy in range(-1, 17):
                    for dx in range(-1, 17):
                        xx, yy = x+dx, y+dy
                        expected = oracle.result(oracle.full_query(xx, yy))
                        admitted = (xx & ~15, yy & ~15) in tiles
                        for slot in (0, 1):
                            fx, fy = (xx+3*yy+slot) & 255, (3*xx+yy-slot) & 255
                            position = struct.pack('<ii', 256*xx+fx, 256*yy+fy)
                            wheel = target.prepare(slot, position, poison)
                            cache = target.sym['_wheel_surface_cache']+29*slot
                            target.m[cache:cache+29] = bytes(29)
                            count = call(target, reader, wheel)
                            where = (level, xx, yy, slot)
                            if not admitted:
                                assert count == 255 and target.read('_Ct', 20) == poison, where
                                counts['outside'] += 1
                                continue
                            if count == 2:
                                assert bytes(target.m[cache:cache+4]) == position[2:4]+position[6:8], where
                                call(target, 'direct_project_pair', wheel)
                            assert target.result(count) == expected, (where, target.result(count), expected)
                            counts[count] += 1
                for slot in (0, 1):
                    position = struct.pack('<ii', x*256+127, y*256+128)
                    for ax, ay in ((1 << 16, 0), (0, -(1 << 16)), (256, 0), (0, 256)):
                        if ((x+ax) & ~15, (y+ay) & ~15) in tiles:
                            continue
                        wheel = target.prepare(slot, struct.pack('<ii', (x+ax)*256+127, (y+ay)*256+128), poison)
                        assert call(target, reader, wheel) == 255
                    # A potentially matching prepared pair must reach the full certificate.
                    wheel = target.prepare(slot, position, poison)
                    cache = target.sym['_wheel_surface_cache']+29*slot
                    target.m[cache+4:cache+6] = bytes((9, 127))
                    assert call(target, reader, wheel) == 255
                    assert target.read('_Ct', 20) == poison
        print(dict(counts))
    finally:
        target.p.stop(save=False)
        oracle.p.stop(save=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', required=True, type=Path)
    parser.add_argument('--reference', required=True, type=Path)
    args = parser.parse_args()
    check(args.rom, args.reference)
