"""Compare Bowling's linked wheel shortcut and its admission edges to the original solver."""
import argparse
from collections import Counter
from pathlib import Path
import random
import struct
import sys

from check_corner_results import WheelQueries

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from bowling_planes import BANK, COURSE, FLAT_RUNS, FLAT_Y, SHARED_CAP, slope_contains


def probes():
    points = set()
    for start, end, code in FLAT_RUNS:
        if code == SHARED_CAP:
            points.update((x, y) for x in range(start, end) for y in range(FLAT_Y, FLAT_Y+64))
        for x in (start-1, start, start+1, end-2, end-1, end):
            points.update((x, y) for y in range(FLAT_Y-1, FLAT_Y+65))
    for x in (171775, 171776, 171887, 171888, 171983, 171984, 172287, 172288):
        for boundary in (65024, x-106691, 65280, 65344, 65536, 65792):
            points.update((x, y) for y in range(boundary-2, boundary+3))
    for x in range(171888, 171984):
        points.update((x, x-106691+dy) for dy in (-1, 0, 1))
    rng = random.Random(0xB055)
    points.update((rng.randrange(171776,172288), rng.randrange(65024,65792)) for _ in range(128))
    for x, y in ((173600,66532), (172350,66540), (172040,65440), (171928,65260)):
        for alias in (-1048576, -65536, 65536, 1048576):
            points.update(((x+alias, y), (x, y+alias)))
    return sorted(points)


def check_course_switches(cart):
    dispatch = cart.sym['step_solve_wheels']
    for level in (0, COURSE, 46, COURSE, 10, COURSE, 37, COURSE, 0, COURSE):
        assert cart.invoke('_physics_collision_select', a=level) == 1
        if level == COURSE:
            expected = cart.sym['_riding_sparse_bind']+1
        else:
            name = {10: '_riding_corner_wheel_inputs', 37: '_riding_patch_wheel_inputs'}.get(
                level, '_riding_sparse_wheel_inputs')
            expected = cart.sym[name] & 65535
        for operand in (4, 10):
            address = dispatch+operand
            assert int.from_bytes(bytes(cart.m[address:address+2]), 'little') == expected, level


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', type=Path, required=True)
    parser.add_argument('--reference', type=Path, required=True)
    args = parser.parse_args()
    target, oracle = WheelQueries(args.rom), WheelQueries(args.reference)
    counts = Counter()
    try:
        check_course_switches(target)
        assert oracle.invoke('_physics_collision_select', a=COURSE) == 1
        start = BANK*16384
        prefix = target.sym['_bowling_wheel_select'] & 16383
        assert target.image[start:start+prefix] == oracle.image[start:start+prefix]
        # Call the actual banked reader through the same GBDK trampoline as the wheel bridge.
        address = target.sym['_bowling_flat'] & 65535
        trampoline = target.sym['___sdcc_bcall_ehl']
        call = struct.pack('<BBBHBHBB', 0x1e, BANK, 0x21, address, 0xcd, trampoline, 0x18, 0xfe)
        target.m[target.code:target.code+len(call)] = call
        poison = bytes(range(20))
        for x, y in probes():
            accepted = (slope_contains(x, y) or
                        FLAT_Y <= y < FLAT_Y+64 and any(lo <= x < hi for lo, hi, _ in FLAT_RUNS))
            n = oracle.full_query(x, y) if accepted else 255
            assert n in (0,1,255)
            ct = oracle.read('_Ct', 6) if n == 1 else b''
            for slot in range(2):
                pos = struct.pack('<ii', x*256+255*slot, y*256+255*(1-slot))
                wheel = target.prepare(slot, pos, poison)
                target.reg.B, target.reg.C = wheel >> 8, wheel & 255
                target.reg.PC, target.reg.SP = target.code, target.stack
                target.p.tick(1, False)
                assert (target.reg.PC, target.reg.SP) == (target.code+len(call)-2, target.stack)
                assert target.reg.A == n and target.read('_Ct',20) == ct+poison[len(ct):], (x,y,slot,n)
                assert target.m[target.sym['__current_bank']] == 9
                assert bytes(target.m[0x4000:0x4020]) == target.signature
                counts[n] += 1
    finally:
        target.p.stop(save=False)
        oracle.p.stop(save=False)
    print(f'{sum(counts.values())} native Bowling queries, {dict(sorted(counts.items()))} results')


if __name__ == '__main__':
    main()
