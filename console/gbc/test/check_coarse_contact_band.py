"""Verify the generated contact band and compare both linked wheel responses."""
import argparse
from collections import Counter
import math
from pathlib import Path
import random
import re
import struct
import sys

ROOT = next(p for p in Path(__file__).resolve().parents if (p/'src/physics_contacts.c').exists())
sys.path.insert(0, str(ROOT/'test'))
from check_ordered_pair import Cartridge, FIELDS


def radial(x, y, roots):
    d2 = x*x + y*y
    if d2 < 16384:
        length = math.isqrt(d2)
        if length == 0:
            return 0, 16384, 0
        # C integer division truncates toward zero.
        nx = (abs(x)*16384//length) * (-1 if x < 0 else 1)
        ny = (abs(y)*16384//length) * (-1 if y < 0 else 1)
        return nx, ny, length
    reciprocal = roots[min((d2-16384) >> 9, len(roots)-1)]
    nx = max(-32768, min(32767, x*reciprocal >> 4))
    ny = max(-32768, min(32767, y*reciprocal >> 4))
    return nx, ny, (x*nx+y*ny+8192) >> 14


def generated_normals():
    source = (ROOT.parent/'nes/src/rsqrt.inc').read_text().split('\n', 1)[1]
    roots = list(map(int, re.findall(r'\d+', source)))
    assert len(roots) == 297
    # A fresh segment has |nx|, |ny| <= 16384 and length <= 409.
    # Its length-based projected point is at most 409 from the center
    # along either axis. Fresh radial endpoints lie inside radius 410.
    fresh = 0
    reach = 409
    for x in range(-409, 410):
        for y in range(-409, 410):
            if x*x+y*y < 410**2:
                nx, ny, length = radial(x, y, roots)
                reach = max(reach, abs((nx*length+8192) >> 14), abs((ny*length+8192) >> 14))
                fresh += 1
    assert reach == 409
    # Merge accepts |dx|, |dy| < 102. The signed midpoint stays within
    # 51 of the fresh second contact regardless of any previous merges.
    limit = reach + 51
    vectors = {length: [] for length in range(403, 411)}
    for x in range(-limit, limit+1):
        for y in range(-limit, limit+1):
            nx, ny, length = radial(x, y, roots)
            if length in vectors:
                vectors[length].append((nx, ny))
    # Segment normals come from independently rounding two components
    # of a length-16384 vector. Rounding increases L1 by at most one.
    assert math.sqrt(2)*16384+1 <= 23181
    max_l1 = {}
    for length in range(405, 409):
        max_l1[length] = max(abs(nx)+abs(ny) for nx, ny in vectors[length])
        assert max_l1[length] <= 23181
        for nx, ny in vectors[length]:
            if length == 405 and (ny < 0 or nx < -8192):
                continue
            low = (255*(min(0, nx)+min(0, ny))+8192) >> 14
            high = (255*(max(0, nx)+max(0, ny))+8192) >> 14
            assert 103547 <= 256*length + low <= 256*length + high < 104858
    print(f'{fresh} fresh endpoint offsets and {(2*limit+1)**2} merged offsets checked. '
          f'Maximum normal L1 at each length: {max_l1}.')
    return vectors


def verify_wheels(reference, target, vectors):
    rng = random.Random(41405)
    coverage = Counter()
    for cart in (reference, target):
        symbol = cart.symbols['_riding_cert_hit']
        # Supply a fresh single candidate, leaving both fine filters,
        # the complete support response and wheel motion in the guest.
        for i, opcode in enumerate((0x3e, 0x01, 0xc9)):
            cart.mem[symbol >> 16, (symbol & 65535)+i] = opcode
    for i in range(6500):
        length = rng.randrange(403, 411)
        nx, ny = rng.choice(vectors[length])
        slot, phase = i & 1, (i >> 1) & 1
        fx, fy = rng.choice([(0, 0), (0, 255), (255, 0), (255, 255),
                             (122, 123), (123, 122), (rng.randrange(256), rng.randrange(256))])
        projection = (fx*nx+fy*ny+8192) >> 14
        push = 103547 - 256*length - projection
        coverage['push' if push > 0 else 'reject' if push <= -1311 else 'clear'] += 1
        fields = {key: rng.randbytes(size) for key, size in FIELDS.items()}
        offset = 24*(1+slot)
        bike = bytearray(fields['_Bike'])
        bike[offset], bike[offset+4] = fx, fy
        fields['_Bike'] = bike
        fields['_Ct'] = struct.pack('<3h', nx, ny, length) + fields['_Ct'][6:]
        force = tuple(rng.randrange(-60000, 60001) for _ in range(3))
        expected = reference.run(fields, phase, slot, force, True)
        actual = target.run(fields, phase, slot, force, True)
        for field in FIELDS:
            assert actual[field] == expected[field], (i, length, nx, ny, fx, fy, field)
    assert set(coverage) == {'clear', 'push', 'reject'}
    print(f'{sum(coverage.values())} linked wheel entries matched, including {dict(coverage)}.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', required=True, type=Path)
    parser.add_argument('--rom', required=True, type=Path)
    args = parser.parse_args()
    vectors = generated_normals()
    reference, target = Cartridge(args.reference), Cartridge(args.rom)
    try:
        verify_wheels(reference, target, vectors)
    finally:
        reference.emu.stop(save=False)
        target.emu.stop(save=False)


if __name__ == '__main__':
    main()
