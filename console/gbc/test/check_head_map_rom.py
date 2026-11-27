"""Compare production head sweeps on the same original terrain in two cartridges."""
import argparse
from collections import Counter
from io import BytesIO
import json
from pathlib import Path
import random
import re
import struct
import sys

from pyboy import PyBoy

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / 'tools'))
from physics_level import Resource, geometry, internal_levels


class HeadProbe:
    def __init__(self, rom):
        symbols = {k: int(v, 16) for k, v in re.findall(
            r'^DEF (\S+) 0x([0-9A-Fa-f]+)$', rom.with_suffix('.noi').read_text(), re.M)}
        self.symbols = symbols
        self.start = symbols['_main']
        self.select = self.start + 3
        self.sweep = self.select + 5
        self.current_bank = symbols['__current_bank']
        self.level_index = symbols['_physics_level_index']
        head = symbols['_riding_swept_head']
        def call(name):
            return bytes([0xcd]) + struct.pack('<H', symbols[name])
        wait = bytes([0x18, 0xfe])
        # Keep CRT initialization. Replace main with an interrupt-free test
        # entry and two calls using the same ABI as the game's callers.
        code = (bytes([0xf3]) + wait + call('_physics_collision_select') + wait
                + bytes([0x1e, head >> 16, 0x21]) + struct.pack('<H', head & 65535)
                + call('___sdcc_bcall_ehl') + wait)
        image = bytearray(rom.read_bytes())
        image[self.start:self.start+len(code)] = code
        self.rom = PyBoy(BytesIO(image), window='null', cgb=True, sound_emulated=False)
        self.rom.set_emulation_speed(0)
        self.rom.tick(200, False)
        assert self.rom.register_file.PC == self.start + 1
        self.sp = 0xdfe0

    def run(self, entry, end):
        regs = self.rom.register_file
        bank = self.rom.memory[self.current_bank]
        regs.PC, regs.SP = entry, self.sp
        for _ in range(80):
            self.rom.tick(1, False)
            if regs.PC == end:
                assert regs.SP == self.sp and self.rom.memory[self.current_bank] == bank
                return regs.A
        raise RuntimeError(f'Call did not return, PC={regs.PC:04x}')

    def select_level(self, index):
        self.rom.register_file.A = index
        assert self.run(self.select, self.select+3) == 1
        assert self.rom.memory[self.level_index] == index

    def check(self, points):
        self.rom.memory[self.sp:self.sp+16] = list(struct.pack('<4i', *points))
        return self.run(self.sweep, self.sweep+8)

    def close(self):
        self.rom.stop(save=False)


def inputs(level, rng):
    _, _, w, h, segments, _, _ = geometry(level)
    # Test both sides of the 244-unit head radius at actual segment ends
    # and midpoints. Include zero-length sweeps and both travel directions.
    for x, y, dx, dy, ex, ey, _ in rng.sample(segments, min(12, len(segments))):
        for ax, ay in ((x, y), (x+dx//2, y+dy//2), (x+dx, y+dy)):
            for radius in (-245, -244, -243, 243, 244, 245):
                qx, qy = ax-round(ey*radius/16384), ay+round(ex*radius/16384)
                yield 'stationary', (qx, qy, qx, qy)
                yield 'crossing', (qx, qy, ax, ay)
                yield 'reverse', (ax, ay, qx, qy)
    # Exercise 1 m tile and 4 m coarse-cell borders, grid exits and the
    # 8 m threshold where the original solver expands its search radius.
    for _ in range(32):
        x = rng.randrange(-1, 4*w+2)*1024 + rng.choice((-1, 0, 1))
        y = rng.randrange(-1, 4*h+2)*1024 + rng.choice((-1, 0, 1))
        for distance in (-8193, -8192, -1024, -1, 1, 1024, 8192, 8193):
            yield 'boundary', (x, y, x+distance, y+distance//3)


def check_small_head_cache(actual, ref, level, x, y):
    mask = actual.symbols['_riding_head_clear_mask']
    query = actual.symbols['_riding_head_terrain_query']
    misses = []
    actual.rom.hook_register(query >> 16, query & 65535, lambda _: misses.append(1), None)
    comparisons = 0
    base = (x, y, x, y)

    def select(course):
        actual.select_level(course)
        ref.select_level(course)
        assert actual.rom.memory[mask] == 0, 'course selection kept an old head certificate'

    def check(points):
        nonlocal comparisons
        value = actual.check(points)
        assert value == ref.check(points), (points, value)
        comparisons += 1
        return value

    def warm():
        assert check(base) == 0
        assert actual.rom.memory[mask] == 1, 'expected an eight-unit certificate'
        misses.clear()

    try:
        select(level)
        warm()
        ox, oy = x & ~7, y & ~7
        for dy in range(8):
            for dx in range(8):
                assert check((ox+dx, oy+dy, ox+7-dx, oy+7-dy)) == 0
        assert not misses, 'both endpoints remained inside the certified region'
        for offset in (-8, 8, -256, 256, -65536, 65536, 1 << 24, -(1 << 24)):
            for component in range(4):
                warm()
                p = list(base)
                p[component] += offset
                # Keep very long aliases stationary to test all high bits
                # without requesting thousands of 8 m DDA subdivisions.
                if abs(offset) >= 65536:
                    p[component ^ 2] += offset
                check(tuple(p))
                assert misses, (component, offset, 'unsafe cached hit')
        # Walk through the clear/occupied boundary of the actual terrain.
        for direction in (-1, 1):
            for distance in range(1, 97):
                p = y + direction * distance
                if ref.check((x, p, x, p)):
                    warm()
                    assert check((x, y, x, p)) == 1
                    assert check((x, p, x, y)) == 1
                    break
            else:
                continue
            break
        else:
            raise AssertionError(f'Course {level+1} fixture did not reach terrain')
        warm()
        select(level)
        warm()
        select(2)
        check(base)
    finally:
        actual.rom.hook_deregister(query >> 16, query & 65535)
    return comparisons


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('rom', 'reference', 'res', 'out'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    rng = random.Random(0x10face)
    counts = Counter()
    unique_levels = internal_levels(Resource(args.res))
    ref, actual = HeadProbe(args.reference), HeadProbe(args.rom)
    try:
        if '_riding_head_near_clear' in actual.symbols:
            for level, x, y in ((31, 24226, 40406), (47, 72982, 5526)):
                counts['small_cache'] += check_small_head_cache(actual, ref, level, x, y)
        for i, level in enumerate(unique_levels):
            ref.select_level(i)
            actual.select_level(i)
            for kind, points in inputs(level, rng):
                expected, got = ref.check(points), actual.check(points)
                assert expected == got, (i+1, kind, points, expected, got)
                counts[f'{kind}_{got}'] += 1
    finally:
        ref.close()
        actual.close()
    assert len(unique_levels) == 54 and counts['stationary_0'] and counts['stationary_1']
    report = dict(levels=len(unique_levels), compared=sum(counts.values()), results=counts)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report))

if __name__ == '__main__':
    main()
