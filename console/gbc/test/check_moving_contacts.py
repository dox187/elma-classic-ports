"""Compare ordered mixed plane/cap writes, source cursors and moving queries."""
import argparse
from collections import Counter
import math
from pathlib import Path
import random
import struct

from check_normal_atlas import Cartridge
from check_shared_cap import read_contacts


def segment(x, y, dx, dy, flags=0, visible=True):
    length = math.hypot(dx, dy)
    ex, ey = (round(v * 16384 / length) for v in (dx, dy))
    box = (0, 255, 0, 255) if visible else (0, 0, 0, 0)
    return struct.pack('<6hH4B', x, y, dx, dy, ex, ey, round(length) | flags, *box)


def check(rom, reference):
    target, oracle = Cartridge(rom), Cartridge(reference)
    rng = random.Random(0xC037)
    stats = Counter()
    base = 1792
    guard = segment(0, 0, 1024, 0, visible=False)
    directions = ((1024, 0), (0, -1024), (-169, 181), (-248, -224),
                  (2, 1619), (-1500, 40), (33, -129), (-3, -1))
    def merge(_):
        ct = target.sym['_Ct']
        kind = 'equal' if bytes(target.m[ct:ct+6]) == bytes(target.m[ct+10:ct+16]) else 'mixed'
        stats[kind, target.reg.B] += 1
    addr = target.sym['_riding_contact_merge_kind']
    target.p.hook_register(addr >> 16, addr & 65535, merge, None)
    try:
        for dx, dy in directions:
            for ux, uy in directions:
                for split in (0, 13):
                    for start_flag, end_flag in ((0, 0), (0x4000, 0), (0, 0x8000)):
                        first = segment(base - dx, base - dy, dx, dy, end_flag)
                        second = segment(base + split, base, ux, uy, start_flag)
                        third = segment(base - 295, base - 160, 701, 390)
                        for _ in range(3):
                            ox, oy = rng.choice(((0, 409), (0, -410), (397, 53), (291, -281),
                                                  (-280, -292), (35, 24), (-389, 127), (410, 0)))
                            pair = (first, second) if rng.randrange(2) else (second, first)
                            mids = b'' if rng.randrange(2) else guard
                            records = guard + pair[0] + mids + pair[1] + (third if rng.randrange(2) else b'') + guard
                            for visit, delta in enumerate((0, 1, 3, 2, 0, 15, -1)):
                                x, y = base + ox + delta, base + oy - (delta // 3)
                                seed = rng.randbytes(20)
                                expected = read_contacts(oracle, records, x, y, seed, True)
                                actual = read_contacts(target, records, x, y, seed, visit == 0)
                                assert actual == expected, (dx, dy, ux, uy, split, x, y, actual, expected)
                                stats['queries'] += 1
        # Full signed input and wrapped endpoints with a cold scan on each side.
        for x in (0, 1, 32767, 32768, 32769, 65535):
            for y in (0, 409, 410, 32768, 65127, 65535):
                for v in (-32768, -1, 0, 32767):
                    records = segment(v, 0, -1, 1024) + segment(v, 0, 1024, 0)
                    seed = rng.randbytes(20)
                    assert read_contacts(target, records, x, y, seed, True) == read_contacts(oracle, records, x, y, seed, True)
                    stats['wide'] += 1
        assert all(stats[kind, 1] for kind in ('equal', 'mixed')), stats
        print(dict(stats))
    finally:
        target.p.stop(save=False)
        oracle.p.stop(save=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', type=Path, required=True)
    parser.add_argument('--reference', type=Path, required=True)
    args = parser.parse_args()
    check(args.rom, args.reference)
