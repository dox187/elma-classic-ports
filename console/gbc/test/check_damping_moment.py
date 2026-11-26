#!/usr/bin/env python3
"""Check the native Q18 damping moment against an unbounded integer sum."""
import argparse
import json
import random
import re
import struct
import subprocess
from pathlib import Path

from pyboy import PyBoy

BASE = Path(__file__).resolve().parents[1]
MIN32, MAX32 = -(1 << 31), (1 << 31) - 1
MIN24, MAX24 = -(1 << 23), (1 << 23) - 1


def vectors():
    rng = random.Random(9607)
    edges = (MIN24, MIN24 + 1, -65537, -65536, -32768, -257, -256, -255,
             -2, -1, 0, 1, 2, 255, 256, 257, 32767, 32768, 65535, 65536, MAX24)

    # Slow signed16 and full-width calls captured from the scheduled suites.
    yield [-25533, -3674, -27204, 7205, -195628, 223407, -116755, -116755]
    yield [-6818, -64, -10623, -1471, -165966, 233614, -138150, -138150]
    yield [-801053270, -807214358, 910186697, -893176796, -93731681, -89003737, 84218705, -90711199]
    # Equal full-width products cancel down to a single raw Q18 bit.
    # Each nonzero limb can occur above or below a run of zero digits.
    for bit in (0, 8, 16, 24, 30):
        for arm in (MIN32, MAX32, -(1 << bit), 1 << bit):
            for speed in (MIN32, MAX32, -(1 << bit), 1 << bit):
                for tail in (-(1 << 18) - 1, -1, 0, 1, (1 << 18) + 1):
                    yield [speed, 1, speed, 0, arm, MAX32, arm, tail]
    # The two positive products carry into bit 63, then a large negative
    # pair cancels most of the subtotal. Exercise both signs of the remainder.
    for limb in (0, 1, 255, 256, 65535, 65536):
        yield [MIN32 + limb, MIN32, MIN32, MIN32, MIN32, MIN32, MIN32, MIN32]
        yield [MIN32, MIN32, MIN32 + limb, MIN32, MIN32, MIN32, MIN32, MIN32]
    # A zero arm must discard even the widest speed, in any term position.
    for pair in ((2, 4), (0, 6), (3, 5), (1, 7)):
        for speed in (MIN32, MIN24, -65536, 65536, MAX24, MAX32):
            values = [1, -1, 1, -1, 1 << 18, -(1 << 18), 1, -1]
            values[pair[0]], values[pair[1]] = speed, 0
            yield values
    # Exercise every late transfer to the nine-byte accumulator, including
    # partial sums of either sign and cancellation back into signed32.
    for position in range(8):
        for wide in (MIN32, MIN24 - 1, MAX24 + 1, MAX32):
            for _ in range(16):
                values = [rng.choice(edges) for _ in range(8)]
                values[position] = wide
                yield values
    # Equal vertical velocities on opposite arms cancel. INT_MIN has no
    # positive signed32 counterpart, even though INT_MIN + INT_MIN wraps to 0.
    for arm in (MIN32, MIN32 + 1, -1, 0, 1, MAX32):
        for speed in (MIN32, -1, 0, 1, MAX32):
            for opposite in (arm, max(MIN32, min(MAX32, -arm))):
                yield [0, 0, speed, speed, arm, opposite, MIN32, MAX32]
    for x in (MIN32, MAX32):
        for y in (MIN32, MAX32):
            yield [x, x, x, x, x, x, y, y]
    for a in edges:
        for b in edges:
            for delta in (-1, 0, 1):
                yield [a, b, a, b + delta, a, b, a, b]
                yield [a, 1, a, 1, b, 1 << 18, b, -delta]
    # Exhaust every one-byte speed magnitude and its two immediate wide
    # neighbours at each stage. Other terms keep the zero shortcut out of
    # the path. Exercise carries across bytes 2, 3 and 4 and both arm signs.
    for position, arm_position in ((2, 4), (0, 6), (3, 5), (1, 7)):
        for speed in range(-256, 257):
            for arm in (MIN24, MIN24 + 1, -65537, -1, 0, 65535, 65536, MAX24):
                values = [7, -11, 13, -17, MAX24, MIN24, -262143, 262145]
                values[position], values[arm_position] = speed, arm
                yield values
    for _ in range(8192):
        yield ([rng.randrange(-255, 256) for _ in range(4)] +
               [rng.randrange(MIN24, MAX24 + 1) for _ in range(4)])
    # Transfer signed40 prefixes with large positive and negative high bytes
    # to the signed24 and nine-byte solvers at each possible term.
    for speed_pos, arm_pos in ((2, 4), (0, 6), (3, 5), (1, 7)):
        for sign in (-1, 1):
            for wide in (MIN32, MIN24 - 1, -65537, -256, 256, 65536, MAX24 + 1, MAX32):
                for position in (speed_pos, arm_pos):
                    values = [-255 * sign, -255 * sign, 255 * sign, 255 * sign] + [MIN24] * 4
                    values[position] = wide
                    yield values

    for width in (24, 32):
        limit = 1 << (width - 1)
        for _ in range(2048):
            yield [rng.randrange(-limit, limit) for _ in range(8)]
    for result in (MIN32, -1, 0, 1, MAX32):
        # The first product is within one raw unit of a final shift boundary.
        for delta in (-1, 0, 1):
            yield [1, 0, 1 << 18, 0, result, 0, -delta, 0]


def expected(values):
    rx0, rx1, ry0, ry1, ax0, ax1, ay0, ay1 = values
    total = ry0 * ax0 - rx0 * ay0 + ry1 * ax1 - rx1 * ay1
    return max(MIN32, min(MAX32, total >> 18))


def fixture_rom(native, out):
    # Reuse this profile's linked dependencies, and assemble the current
    # production moment and multiplier so the test also covers new edits.
    source = BASE / 'src'
    compiler = BASE / '.toolchain/gbdk/bin/lcc'
    flags = [compiler, '-msm83:gb', '-Wf--opt-code-size', '-Wm-yC',
             '-Wm-yt0x19', '-Wm-yoA', '-Wl-j']
    driver = out / 'driver.c'
    driver.write_text('''#include <gb/gb.h>
#include <gb/cgb.h>
#include <stdint.h>
volatile int32_t fixture_inputs[8], fixture_answer;
volatile uint8_t fixture_marker;
int32_t fixture_moment(void) __sdcccall(0);
void fixture_before(void) {}
void fixture_after(void) {}
void main(void) {
    disable_interrupts(); cpu_fast(); SWITCH_ROM(8);
    while (1) {
        fixture_before(); fixture_answer=fixture_moment(); fixture_after();
    }
}
''')
    assembly = out / 'physics_suspension_scheduled.s'
    assembly.write_text((source / assembly.name).read_text() + '''
.area _CODE_8
_fixture_moment::
 ld hl,#_fixture_inputs
 ld de,#ss_damping
 ld b,#32
001$:
 ld a,(hl+)
 ld (de),a
 inc de
 dec b
 jr nz,001$
 call ss_damping_torque18
 ld a,(#fixture_bank_marker)
 ld (#_fixture_marker),a
 ret
fixture_bank_marker: .db 0xa5
''')
    overrides = (driver, assembly, source / 'physics_math32_exact.s')
    objects = sorted(native.glob('[0-9]*.o'))
    for path in overrides:
        index, = [i for i, obj in enumerate(objects) if obj.stem.split('-', 1)[1] == path.stem]
        objects[index] = out / objects[index].name
        subprocess.run([*flags, '-c', '-o', objects[index], path], check=True)
    rom = out / 'moment.gbc'
    subprocess.run([*flags, '-o', rom, *objects], check=True)
    return rom


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native', type=Path, required=True,
                        help='object directory produced by check_scheduled_native.py')
    parser.add_argument('--out', type=Path, default=BASE / 'build/damping-moment-check')
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    rom = fixture_rom(args.native.resolve(), out)
    symbols = {key: int(value, 16) for key, value in re.findall(
        r'DEF (_\w+) 0x([\da-fA-F]+)', rom.with_suffix('.noi').read_text())}
    work = list(vectors())
    index = 0
    errors = []
    emu = PyBoy(str(rom), window='null', sound_emulated=False, cgb=True)
    emu.set_emulation_speed(0)

    def before(_):
        if index < len(work) and not errors:
            addr = symbols['_fixture_inputs']
            emu.memory[addr:addr + 32] = struct.pack('<8i', *work[index])

    def after(_):
        nonlocal index
        if index == len(work) or errors:
            return
        addr = symbols['_fixture_answer']
        actual, = struct.unpack('<i', bytes(emu.memory[addr:addr + 4]))
        wanted = expected(work[index])
        bank_marker = emu.memory[symbols['_fixture_marker']]
        if actual != wanted or bank_marker != 0xa5:
            errors.append(dict(index=index, inputs=work[index], actual=actual,
                               expected=wanted, bank_marker=bank_marker))
        index += 1

    try:
        emu.hook_register(0, symbols['_fixture_before'], before, None)
        emu.hook_register(0, symbols['_fixture_after'], after, None)
        for _ in range(1000):
            emu.tick(10, False)
            if index == len(work) or errors:
                break
    finally:
        emu.stop(save=False)
    report = dict(cases=index, requested=len(work), errors=errors,
                  passed=index == len(work) and not errors)
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
