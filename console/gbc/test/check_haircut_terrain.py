"""Compare Haircut's compiled wheel queries with the complete cartridge iterator."""
import argparse
from collections import Counter
from pathlib import Path
import struct
import sys

from check_corner_results import WheelQueries

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from haircut_terrain import COURSE, HEIGHT, MISS, TILE, WIDTH, X, Y, tile_map


def probes(grid):
    # Opposite fractional extremes on the two wheels must yield the same
    # coarse result. Walk every tile at its boundaries and one interior point.
    for row, codes in enumerate(grid):
        for col, code in enumerate(codes):
            for dx, dy in ((0, 0), (31, 31), (col % TILE, row % TILE)):
                yield X+col*TILE+dx, Y+row*TILE+dy, code
    for dx, dy in ((-1, 0), (0, -1), (WIDTH*TILE, 0), (0, HEIGHT*TILE),
                   (-65536, 0), (65536, 0), (0, -65536), (0, 65536)):
        yield X+dx, Y+dy, MISS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ('rom', 'reference', 'gen'):
        parser.add_argument('--'+arg, type=Path, required=True)
    args = parser.parse_args()
    grid = tile_map(args.gen)
    target, oracle = WheelQueries(args.rom), WheelQueries(args.reference)
    counts = Counter()
    try:
        for cart in (target, oracle):
            assert cart.invoke('_physics_collision_select', a=COURSE) == 1
        addr = target.sym['_haircut_query']
        call = struct.pack('<BBBHBHBB', 0x1e, addr >> 16, 0x21, addr & 65535,
                           0xcd, target.sym['___sdcc_bcall_ehl'], 0x18, 0xfe)
        target.m[target.code:target.code+len(call)] = call
        poison = bytes(range(20))
        for x, y, code in probes(grid):
            n = 255 if code == MISS else oracle.full_query(x, y)
            assert n in (0, 1, 255)
            expected = oracle.read('_Ct', 6)+poison[6:] if n == 1 else poison
            for slot in range(2):
                pos = struct.pack('<ii', x*256+255*slot, y*256+255*(1-slot))
                wheel = target.prepare(slot, pos, poison)
                target.reg.B, target.reg.C = wheel >> 8, wheel & 255
                target.reg.PC, target.reg.SP = target.code, target.stack
                target.p.tick(1, False)
                assert (target.reg.PC, target.reg.SP) == (target.code+len(call)-2, target.stack)
                assert target.reg.A == n, (x, y, slot, code, n, target.reg.A)
                assert target.read('_Ct', 20) == expected, (x, y, slot, code)
                assert target.m[target.sym['__current_bank']] == 9
                assert bytes(target.m[0x4000:0x4020]) == target.signature
                counts[n] += 1
    finally:
        target.p.stop(save=False)
        oracle.p.stop(save=False)
    print(f'{sum(counts.values())} Haircut wheel queries, {dict(sorted(counts.items()))}')


if __name__ == '__main__':
    main()
