"""Exercise Hang Tight's linked wheel reader at every column and admission edge."""
import argparse
from collections import Counter
from pathlib import Path
import random
import struct
import sys

from check_corner_results import WheelQueries

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from hang_terrain import BANDS, COURSE, X_BASE, Y_BASE


def admitted(x, y):
    column = (x-X_BASE)//32 - 8
    if 0 <= column < len(BANDS):
        _, lower, upper = BANDS[column]
        return lower <= (y-Y_BASE)//16 < upper
    return False


def probes():
    rng = random.Random(0x4854)
    points = set()
    for column, (_, lower, upper) in enumerate(BANDS, 8):
        x = X_BASE + 32*column
        bottom, top = Y_BASE+16*lower, Y_BASE+16*upper
        for dx in (-1, 0, 1, 15, 30, 31, 32):
            for y in (bottom-1, bottom, bottom+1, (bottom+top)//2, top-1, top):
                points.add((x+dx, y))
        points.update((x+rng.randrange(32), rng.randrange(bottom, top)) for _ in range(24))
        for shift in (-1048576, -65536, -4096, 4096, 65536, 1048576):
            points.update(((x+shift, bottom), (x, bottom+shift)))
    return sorted(points)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', type=Path, required=True)
    parser.add_argument('--reference', type=Path, required=True)
    args = parser.parse_args()
    target, oracle = WheelQueries(args.rom), WheelQueries(args.reference)
    counts = Counter()
    try:
        assert oracle.invoke('_physics_collision_select', a=COURSE)
        assert target.invoke('_physics_collision_select', a=COURSE)
        end = target.sym['_hang_wheel_select'] & 16383
        start = 87*16384
        assert target.image[start:start+end] == oracle.image[start:start+end]
        address = target.sym['_hang_query']
        call = struct.pack('<BBBHBHBB', 0x1e, address >> 16, 0x21, address & 65535,
                           0xcd, target.sym['___sdcc_bcall_ehl'], 0x18, 0xfe)
        target.m[target.code:target.code+len(call)] = call
        poison = bytes(range(20))
        for x, y in probes():
            count = oracle.full_query(x, y) if admitted(x,y) else 255
            wanted = oracle.result(count) if count < 255 else None
            assert count in (0,1,255)
            for slot in range(2):
                pos = struct.pack('<ii', 256*x+255*slot, 256*y+255*(1-slot))
                wheel = target.prepare(slot, pos, poison)
                target.reg.B, target.reg.C = wheel >> 8, wheel & 255
                target.reg.PC, target.reg.SP = target.code, target.stack
                target.p.tick(1, False)
                assert (target.reg.PC, target.reg.SP) == (target.code+len(call)-2, target.stack)
                assert target.reg.A == count, (x,y,slot,target.reg.A,count)
                if wanted:
                    assert target.result(count) == wanted, (x,y,slot)
                else:
                    assert target.read('_Ct',20) == poison
                assert target.m[target.sym['__current_bank']] == 9
                assert bytes(target.m[0x4000:0x4020]) == target.signature
                counts[count] += 1
    finally:
        target.p.stop(save=False)
        oracle.p.stop(save=False)
    print(f'{sum(counts.values())} native Hang Tight queries, {dict(sorted(counts.items()))} results')


if __name__ == '__main__':
    main()
