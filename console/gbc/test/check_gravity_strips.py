"""Check every Gravity Ride strip center, both wheels, edge fallbacks and terrain prefixes."""
import argparse
from collections import Counter
from pathlib import Path
import struct
import sys

from check_corner_results import WheelQueries

TOOLS = Path(__file__).resolve().parents[1] / 'tools'
sys.path.insert(0, str(TOOLS))
from gravity_strips import STRIPS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', type=Path, required=True)
    parser.add_argument('--reference', type=Path, required=True)
    args = parser.parse_args()
    target = WheelQueries(args.rom)
    oracle = WheelQueries(args.reference)
    regions, probes = set(), set()
    for bank, (page, pages, strips) in STRIPS.items():
        prefix = target.sym[f'_riding_gravity_strip_{bank}'] & 16383
        start = bank * 16384
        assert target.image[start:start+prefix] == oracle.image[start:start+prefix]
        assert target.sym[f'_riding_gravity_end_{bank}'] <= (bank << 16) + 0x8000
        for x, y, height in strips:
            regions.update((x+dx, y+dy) for dx in range(8) for dy in range(height))
            probes.update((x+dx, y+dy) for dx in range(-1, 9) for dy in range(-1, height+1))
            for alias in (-65536, 65536):
                probes.update(((x+alias, y), (x, y+alias)))
        probes.update((x, y) for x in range(page*256, (page+pages)*256, 8)
                      for y in (0, 65535))
    poison = bytes(range(20))
    counts = Counter()
    try:
        for cart in (target, oracle):
            assert cart.invoke('_physics_collision_select', a=10) == 1
        for x, y in sorted(regions | probes):
            if (x, y) in regions:
                n = oracle.full_query(x, y)
                expected = 255 if n == 2 else n
                ct = oracle.read('_Ct', 6) if n == 1 else b''
            else:
                expected, ct = 255, b''
            for slot in range(2):
                wheel = target.prepare(slot, struct.pack('<ii', x*256 + 255*slot,
                                                         y*256 + 255*(1-slot)), poison)
                count = target.invoke('_riding_gravity_strip', de=wheel)
                assert count == expected, (x, y, slot, count, expected)
                assert target.read('_Ct', 20) == ct + poison[len(ct):], (x, y, slot)
                counts[count] += 1
    finally:
        target.p.stop(save=False)
        oracle.p.stop(save=False)
    print(f'{len(regions)} strip centers, {sum(counts.values())} native lookups, '
          f'{dict(sorted(counts.items()))} results')


if __name__ == '__main__':
    main()
