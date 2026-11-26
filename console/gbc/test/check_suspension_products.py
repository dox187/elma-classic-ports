#!/usr/bin/env python3
"""Verify native batched spin and spring cross products with unbounded integers."""
import argparse
import json
import random
import re
import struct
import subprocess
from pathlib import Path

from pyboy import PyBoy


def signed32(x):
    return ((x + (1 << 31)) & 0xffffffff) - (1 << 31)


def vectors():
    randomizer = random.Random(0x518a)
    edges = (-2**31, -2**31+1, -2**23-1, -2**23, -2**23+1, -65537,
             -65536, -65535, -32769, -32768, -32767, -257, -256, -255, -2,
             -1, 0, 1, 2, 255, 256, 257, 32767, 32768, 32769, 65535, 65536,
             65537, 2**23-1, 2**23, 2**31-1)
    for i, omega in enumerate(edges):
        for j, arm in enumerate(edges):
            yield omega, [arm, edges[(j+1) % len(edges)], edges[i], edges[-i-1]]
    for _ in range(400):
        # Each wide arm must independently send this call to the fallback.
        arms = [randomizer.randrange(-2**23,2**23) for _ in range(4)]
        arms[randomizer.randrange(4)] = randomizer.choice((-2**23-1, 2**23, -2**31, 2**31-1))
        yield randomizer.choice(edges), arms
    for width in (8, 16, 19, 24, 32):
        bound = 1 << (width - 1)
        for _ in range(1000):
            yield randomizer.randrange(-bound, bound), [
                randomizer.randrange(-bound, bound) for _ in range(4)]
    for omega in (1, -1, 2, -2, 256, -256, 32768, -32768, 65536, -65536):
        half = (1 << 17) // abs(omega)
        yield omega, [half - 1, half, half + 1, -half]
        yield omega, [-half - 1, -half, -half + 1, 3 * half]

    # For each byte multiplier, this arm puts an odd multiple of 2^17
    # in the product. Exercise exact Q18 ties and their adjacent inputs.
    for digit in range(1, 256):
        half_arm = (1 << 17) // (digit & -digit)
        for omega in (-digit, digit):
            for tie in (-half_arm, half_arm):
                yield omega, [tie - 1, tie, tie + 1, 3 * tie]
            yield omega, [-2**23, -2**23 + 1, 2**23 - 2, 2**23 - 1]

    # Equal products at every width cancel before the per-wheel floor.
    for x in edges:
        for y in edges:
            yield 0, [x, y, x, y]
            if x < 2**31 - 1:
                yield 0, [x + 1, y, x, y]
    # Differences immediately on either side of the 12-bit floor.
    for k in (-(1 << 31), -32768, -1, 0, 1, 32767, (1 << 31) - 1):
        for addend in (-1, 0, 1):
            yield 0, [addend, k, -4096, 1]
            yield 0, [k, 1, -addend, 4096]
    # Every combination of product signs, with 0xff and unit upper digits.
    for ax in (-2**23, -222822, 0, 222822, 2**23 - 1):
        for ay in (-2**23, -157286, 0, 157286, 2**23 - 1):
            for dx in (-32768, -512, -511, -256, -255, -1, 0, 1, 255, 256, 511, 512, 32767):
                for dy in (-32768, -511, -256, -1, 0, 1, 256, 511, 32767):
                    yield 0, [ax, ay, dx, dy]


def fixture(native, source, out):
    compiler = Path(__file__).resolve().parents[1] / '.toolchain/gbdk/bin/lcc'
    flags = [str(compiler), '-msm83:gb', '-Wf--opt-code-size', '-Wm-yC',
             '-Wm-yt0x19', '-Wm-yoA', '-Wl-j']
    driver = out / 'driver.c'
    driver.write_text('''#include <gb/gb.h>
#include <gb/cgb.h>
#include <stdint.h>
volatile int32_t fixture_input[5], fixture_answer[5];
volatile uint8_t fixture_marker;
void fixture_products(void) __sdcccall(0);
void fixture_before(void) {}
void fixture_after(void) {}
void main(void) {
    disable_interrupts(); cpu_fast(); SWITCH_ROM(8);
    while (1) { fixture_before(); fixture_products(); fixture_after(); }
}
''')
    assembly = out / 'fixture.s'
    # The driver selects bank 8. Exercise the production first-wheel entry
    # and its actual anchor and wheel-displacement layout.
    assembly.write_text(source.read_text() + '''
.area _CODE
_fixture_products::
 ss_read _fixture_input
 ss_write _riding_suspension_state+4
 ld hl,#_fixture_input+4
 ld de,#ss_damping+16
 .rept 16
 ld a,(hl+)
 ld (de),a
 inc de
 .endm
 call ss_spin_four
 ld hl,#ss_damping
 ld de,#_fixture_answer
 .rept 16
 ld a,(hl+)
 ld (de),a
 inc de
 .endm
 ss_read _fixture_input+4
 ss_write _riding_pose_anchor
 ss_read _fixture_input+8
 ss_write _riding_pose_anchor+8
 ss_read _fixture_input+12
 ss_write ss_force_products+28
 ss_read _fixture_input+16
 ss_write ss_force_products+36
 call ss_first_moment
 ss_read ss_ts
 ss_write _fixture_answer+16
 ld a,(#fixture_bank_marker)
 ld (#_fixture_marker),a
 ret
.area _CODE_8
fixture_bank_marker: .db 0xa5
''')
    objects = sorted(native.glob('[0-9]*.o'))
    for name, replacement in (('driver', driver), ('physics_suspension_scheduled', assembly)):
        index, = [i for i, obj in enumerate(objects) if obj.stem.split('-', 1)[1] == name]
        objects[index] = out / objects[index].name
        subprocess.run([*flags, '-c', '-o', objects[index], replacement], check=True)
    rom = out / 'check.gbc'
    result = subprocess.run([*flags, '-o', rom, *objects], text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True)
    if any(text in result.stdout for text in ('spans into the next', 'Multiple write', 'Possible overflow')):
        raise ValueError(f'Fixture ROM banks overlap: {result.stdout}')
    return rom


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native', type=Path, required=True)
    parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[1] /
                        'src/physics_suspension_scheduled.s')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    rom = fixture(args.native.resolve(), args.source.resolve(), out)
    symbols = {k:int(v,16) for k,v in re.findall(r'DEF (_\w+) 0x([0-9A-Fa-f]+)',
                                                 rom.with_suffix('.noi').read_text())}
    work = list(vectors())
    index = 0
    errors = []
    emu = PyBoy(str(rom), window='null', sound_emulated=False, cgb=True)
    emu.set_emulation_speed(0)

    def before(_):
        if index < len(work) and not errors:
            omega, arms = work[index]
            addr = symbols['_fixture_input']
            emu.memory[addr:addr+20] = struct.pack('<5i', omega, *arms)

    def after(_):
        nonlocal index
        if index >= len(work) or errors:
            return
        omega, arms = work[index]
        def spin(a):
            return max(-2**31, min(2**31-1, (omega*a + 2**17) >> 18))
        wanted = [spin(a) for a in arms[2:] + arms[:2]]
        wanted.append(signed32((arms[0]*arms[3]-arms[1]*arms[2]) >> 12))
        addr = symbols['_fixture_answer']
        actual = list(struct.unpack('<5i', bytes(emu.memory[addr:addr+20])))
        marker = emu.memory[symbols['_fixture_marker']]
        if actual != wanted or marker != 0xa5:
            errors.append(dict(index=index, omega=omega, arms=arms, expected=wanted,
                               actual=actual, marker=marker))
        index += 1

    try:
        emu.hook_register(0, symbols['_fixture_before'], before, None)
        emu.hook_register(0, symbols['_fixture_after'], after, None)
        for _ in range(3000):
            emu.tick(10, False)
            if index >= len(work) or errors:
                break
    finally:
        emu.stop(save=False)
    report = dict(cases=index, requested=len(work), errors=errors,
                  passed=index == len(work) and not errors)
    print(json.dumps(report))
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
