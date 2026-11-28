"""Compare complete ROM contact tiles and misses to the ordered iterator."""
import argparse
from collections import Counter
import json
from pathlib import Path
import struct
import sys

from check_corner_results import WheelQueries

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from wheel_extended_tiles import BANKS, PROFILE, SIDE


def call(cart, wheel, x, y):
    address = cart.sym['_riding_extended_contacts']
    cart.m[cart.code:cart.code+5] = struct.pack('<BHBB', 0xcd, address, 0x18, 0xfe)
    cart.m[cart.stack:cart.stack+6] = struct.pack('<iH', y, wheel)
    cart.reg.SP, cart.reg.PC = cart.stack, cart.code
    cart.reg.D, cart.reg.E, cart.reg.B, cart.reg.C = struct.pack('>i', x)
    for _ in range(12):
        cart.p.tick(1, False)
        if cart.reg.PC == cart.code+3:
            break
    assert (cart.reg.PC, cart.reg.SP) == (cart.code+3, cart.stack+4), (x,y,hex(cart.reg.PC),hex(cart.reg.SP),bytes(cart.m[address:address+24]).hex())
    assert cart.m[cart.sym['__current_bank']] == 9
    return cart.reg.A


def check(rom, reference):
    target, oracle = WheelQueries(rom), WheelQueries(reference)
    poison = bytes(range(20))
    counts = Counter()
    try:
        profile = json.loads(PROFILE.read_text())
        for bank, courses in zip(BANKS, profile, strict=True):
            for level, tiles in courses:
                assert target.sym[f'direct_extended_{bank}_{level}_tiles'] >> 16 == bank
                assert target.invoke('_physics_collision_select', a=level) == 1
                assert oracle.invoke('_physics_collision_select', a=level) == 1
                points = {(x+dx, y+dy) for x, y in tiles
                          for dy in range(-1, SIDE+1) for dx in range(-1, SIDE+1)}
                x, y = tiles[0]
                points.update(((x-(1 << 16), y), (x+(1 << 16), y),
                               (x, y-(1 << 16)), (x, y+(1 << 16))))
                for x, y in sorted(points):
                    expected = oracle.result(oracle.full_query(x, y))
                    fx, fy = (x+3*y) & 255, (3*x+y) & 255
                    wheel = target.prepare((x+y) & 1, struct.pack('<ii', 256*x+fx, 256*y+fy), poison)
                    count = call(target, wheel, x, y)
                    actual = target.result(count)
                    assert actual == expected, (level, x, y, actual, expected)
                    counts[count] += 1
        print(f'{sum(counts.values())} exact complete-tile centers and neighboring misses: {dict(counts)}')
    finally:
        target.p.stop(save=False)
        oracle.p.stop(save=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', required=True, type=Path)
    parser.add_argument('--reference', required=True, type=Path)
    args = parser.parse_args()
    check(args.rom, args.reference)
