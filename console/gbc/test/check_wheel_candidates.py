"""Compare sparse terrain programs to the preceding cartridge's ordered wheel iterator."""
import argparse
from collections import Counter
from pathlib import Path
import sys

from check_corner_results import WheelQueries

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from wheel_candidates import REGIONS


def query(cart, x, y, seed, skip=0, trim=0):
    qx, qy = x & 4095, y & 4095
    cart.invoke('_seg_query', a=x >> 12, de=y >> 12, stack_arg=(qx >> 10) | ((qy >> 8) & 12))
    start = int.from_bytes(cart.read('_Seg_cur', 2), 'little')
    if skip or trim:
        start += 18 * skip
        count = cart.read('_Seg_left', 1)[0]
        assert count >= skip + trim
        cur = cart.sym['_Seg_cur']
        cart.m[cur:cur+2] = start.to_bytes(2, 'little')
        cart.m[cart.sym['_Seg_left']] = count - skip - trim
    ct = cart.sym['_Ct']
    cart.m[ct:ct+20] = seed
    count = cart.invoke('_riding_contacts_loop', de=qx, bc=qy)
    end = int.from_bytes(cart.read('_Seg_cur', 2), 'little')
    return count, cart.read('_Ct', 20), end-start, cart.read('_Seg_left', 1)[0]


def points(x, y, w, h, exhaustive):
    # Cross every tile boundary in the region, then query its one-unit outer ring.
    for oy in range(h):
        for ox in range(w):
            if exhaustive or ((ox & 15) in (0, 7, 15) and (oy & 15) in (0, 7, 15)):
                yield x+ox, y+oy
    for xx in range(x-1, x+w+1):
        yield xx,y-1
        yield xx,y+h
    for yy in range(y, y+h):
        yield x-1, yy
        yield x+w, yy


def check(rom, reference, exhaustive):
    carts = [WheelQueries(p) for p in (rom, reference)]
    target, oracle = carts
    hits = Counter()
    stats = Counter()
    region = None

    def observe(_):
        hits[region] += 1

    try:
        sym = target.sym['_riding_candidate_solve']
        target.p.hook_register(sym >> 16, sym & 65535, observe, None)
        for region in REGIONS:
            level, x, y, w, h = region
            for cart in carts:
                cart.invoke('_physics_collision_select', a=level)
            for i, (xx, yy) in enumerate(points(x, y, w, h, exhaustive)):
                seed = bytes((i+k*31) & 255 for k in range(20))
                before = hits[region]
                got = query(target, xx, yy, seed)
                want = query(oracle, xx, yy, seed)
                assert got == want, (level+1, xx, yy, got, want)
                if hits[region] != before:
                    assert any(l == level and rx <= xx < rx+rw and ry <= yy < ry+rh
                               for l, rx, ry, rw, rh in REGIONS), ('out-of-region hit', level+1, xx, yy)
                stats[got[0]] += 1
            # A shortened leaf can share either the full-list pointer or its end.
            # Both must delegate to the ordinary iterator, even after a warm hit.
            for skip, trim in ((0, 1), (1, 0), (1, 1)):
                before = hits[region]
                got, want = (query(cart, x, y, bytes(20), skip, trim) for cart in carts)
                assert got == want and hits[region] == before, ('partial leaf', region, skip, trim)
            assert hits[region], ('candidate region was never exercised', region)
    finally:
        for cart in carts:
            cart.p.stop(save=False)
    print(f'{sum(stats.values())} ordered queries and {3*len(REGIONS)} partial leaves matched, '
          f'including cursor and remaining row count. '
          f'{sum(hits.values())} candidate hits over {len(hits)} regions, contact counts {dict(stats)}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', required=True, type=Path)
    parser.add_argument('--reference', required=True, type=Path)
    parser.add_argument('--exhaustive', action='store_true', help='compare every integer center in each region')
    args = parser.parse_args()
    check(args.rom, args.reference, args.exhaustive)
