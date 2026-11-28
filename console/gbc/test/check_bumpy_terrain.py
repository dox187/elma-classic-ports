"""Compare the linked Bumpy Journey strip reader to the full ordered wheel solver."""
import argparse
from collections import Counter
from pathlib import Path
import struct
import sys

from check_corner_results import WheelQueries

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from bumpy_terrain import COURSE, MISS, STRIPS, geometry


def probes(tiles):
    for strip, (along, across, vertical) in enumerate(STRIPS):
        for column in range(64):
            offset = strip*256 + column*4
            base, *codes = tiles[offset:offset+4]
            if base == 255:
                continue
            for row in range(-1, 7):
                code = (codes[row//2] >> (4*(row%2))) & 15 if 0 <= row < 6 else MISS
                for x, y in ((0, 0), (0, 15), (15, 0), (15, 15), (7, 9)):
                    u, v = along + column*16 + x, across + (base+row)*16 + y
                    yield (v, u, code) if vertical else (u, v, code)
    for x, y in ((65722, 68843), (65516, 68752), (63407, 64232), (63309, 64069)):
        for delta in (-65536, 65536, -1048576, 1048576):
            yield x+delta, y, MISS
            yield x, y+delta, MISS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', type=Path, required=True)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--gen', type=Path, required=True)
    args = parser.parse_args()
    _, _, tiles = geometry(args.gen)
    target, oracle = WheelQueries(args.rom), WheelQueries(args.reference)
    counts = Counter()
    try:
        assert target.invoke('_physics_collision_select', a=COURSE) == 1
        assert oracle.invoke('_physics_collision_select', a=COURSE) == 1
        address = target.sym['_bumpy_query']
        call = struct.pack('<BBBHBHBB', 0x1e, address >> 16, 0x21, address & 65535,
                           0xcd, target.sym['___sdcc_bcall_ehl'], 0x18, 0xfe)
        target.m[target.code:target.code+len(call)] = call
        poison = bytes(range(20))
        for x, y, code in probes(tiles):
            n = MISS if code == MISS else oracle.full_query(x, y)
            assert n in (0, 1, MISS)
            expected = oracle.read('_Ct', 6)+poison[6:] if n == 1 else poison
            for slot in range(2):
                pos = struct.pack('<ii', x*256+255*slot, y*256+255*(1-slot))
                wheel = target.prepare(slot, pos, poison)
                target.reg.B, target.reg.C = wheel >> 8, wheel & 255
                target.reg.PC, target.reg.SP = target.code, target.stack
                target.p.tick(1, False)
                assert (target.reg.PC, target.reg.SP) == (target.code+len(call)-2, target.stack)
                assert target.reg.A == (255 if n == MISS else n)
                assert target.read('_Ct', 20) == expected, (x, y, slot, code)
                assert target.m[target.sym['__current_bank']] == 9
                assert bytes(target.m[0x4000:0x4020]) == target.signature
                counts[target.reg.A] += 1
    finally:
        target.p.stop(save=False)
        oracle.p.stop(save=False)
    print(f'{sum(counts.values())} Bumpy Journey wheel queries, {dict(sorted(counts.items()))}')


if __name__ == '__main__':
    main()
