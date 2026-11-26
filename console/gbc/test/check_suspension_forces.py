#!/usr/bin/env python3
"""Check the eight batched suspension forces, wheel wrap and signed40 body sums."""
import argparse
import json
import random
import re
import struct
import subprocess
from pathlib import Path

from pyboy import PyBoy

Q = 1 << 24
EDGES = (-2**31, -2**31+1, -2**24-1, -2**24, -2**24+1, -2**23-1, -2**23,
         -65537, -65536, -65535, -32769, -32768, -32767, -257, -256, -255,
         -2, -1, 0, 1, 2, 255, 256, 257, 32767, 32768, 32769, 65535,
         65536, 65537, 2**23-1, 2**23, 2**24-1, 2**24, 2**24+1, 2**31-1)

DRIVER = """#include <gb/gb.h>
#include <gb/cgb.h>
#include <stdint.h>
volatile int32_t fixture_input[8];
volatile uint8_t fixture_index[2], fixture_bank, fixture_paired;
void fixture_before(void) {}
void fixture_after(void) {}
void fixture_forces(void) __sdcccall(0);
void main(void) {
    disable_interrupts(); cpu_fast(); SWITCH_ROM(8);
    while (1) { fixture_before(); fixture_forces(); fixture_after(); }
}
"""

ENTRY = """
.area _CODE
_fixture_forces::
 call ss_try_mirrored
 ld a,(#ss_paired)
 ld (#_fixture_paired),a
 ld a,(#_fixture_index)
 ld hl,#_fixture_input
 ld de,#ss_force_products
 call ss_force_four
 ld a,(#_fixture_index+1)
 ld hl,#_fixture_input+16
 ld de,#ss_force_products+28
 call ss_force_four
 ld a,(#ss_paired)
 or a
 jr z,ff_general
 ld e,#15
 ld hl,#ss_paired_forces
 call ___sdcc_bcall_ehl
 jp ff_done
ff_general:
 ss_force_axis 0,0,ff_x0_pos,ff_x1_pos
 ss_force_axis 14,1,ff_y0_pos,ff_y1_pos
ff_done:
 ld a,(#ff_bank)
 ld (#_fixture_bank),a
 ret
.area _CODE_8
ff_bank: .db 0xa5
_fixture_mirror::
 call ss_spring_total
 ss_read ss_ts
 ret
"""


def coefficients(gen):
    def pairs(name, prefix):
        pattern = prefix + r'(C_\w+)\[2\]=\{(-?\d+),(-?\d+)\}'
        return {k: (int(a), int(b)) for k, a, b in re.findall(pattern, (gen / name).read_text())}
    indices = pairs('physics_q24_dispatch.c', 'q24_index_')
    values = pairs('riding_constants.h', 'q24_')
    by_index = {i: v for k in indices for i, v in zip(indices[k], values[k])}
    phases = tuple(zip(indices['C_SPRING_FW'], indices['C_FRIC_W']))
    return phases, by_index


def vectors(phases, scales, rng):
    for indices in phases:
        for v in EDGES:
            for w in EDGES:
                yield indices, [v, w, ~v, ~w, w, v, ~w, ~v]
        for bits in (8, 12, 16, 20, 24, 32):
            limit = 1 << (bits - 1)
            for _ in range(300):
                yield indices, [rng.randrange(-limit, limit) for _ in range(8)]
        for i in indices:
            if scales[i] % 2:
                # Every odd scale has a modular inverse. Hit the exact half
                # tie and its two neighbors at multiple signed magnitudes.
                inverse = pow(scales[i], -1, Q)
                for error in (-1, 0, 1):
                    low = ((Q // 2 + error) * inverse) % Q
                    for high in (-128, -16, -1, 0, 1, 16, 127):
                        yield indices, [high * Q + low] * 8
    candidates = sorted(scales)
    for _ in range(1400):
        # Exercise the generic clamping path with the cartridge's larger scales.
        yield [rng.choice(candidates) for _ in range(2)], [rng.choice(EDGES) for _ in range(8)]


def paired_vectors(phases, scales, rng):
    # Both wheels see the same vertical spring/damper. Include saturating
    # scales whose combined signed33 wheel value can overflow either way.
    large = max(scales, key=scales.get)
    for indices in (*phases, (large, large), (large, phases[0][1])):
        for spring in EDGES:
            for damper in EDGES:
                yield indices, [0, 0, spring, spring, 0, 0, damper, damper]
    for _ in range(1024):
        spring, damper = (rng.randrange(-2**31, 2**31) for _ in range(2))
        indices = [rng.choice(tuple(scales)) for _ in range(2)]
        yield indices, [0, 0, spring, spring, 0, 0, damper, damper]
    # A difference in any input byte must reject the paired force path.
    for lane in range(8):
        for bit in range(32):
            values = [0, 0, 73, 73, 0, 0, -301, -301]
            values[lane] = ((values[lane] ^ (1 << bit)) + 2**31) % 2**32 - 2**31
            yield phases[0], values


def expected(indices, inputs, residual, scales):
    units, fractions = [], []
    for lane, value in enumerate(inputs):
        raw = value * scales[indices[lane // 4]]
        rounded = (raw + Q // 2) // Q
        clamped = min(2**31 - 1, max(-2**31, rounded))
        units.append(clamped)
        fractions.append(raw - rounded * Q if clamped == rounded else 0)
    sums = bytearray()
    for axis, prior in enumerate(residual):
        lanes = (axis * 2, axis * 2 + 1, axis * 2 + 4, axis * 2 + 5)
        integer = (prior >> 24) - sum(units[j] for j in lanes)
        fraction = (prior & (Q - 1)) - sum(fractions[j] for j in lanes)
        sums.extend(struct.pack('<i', fraction))
        sums.extend((integer & ((1 << 40) - 1)).to_bytes(5, 'little'))
    wheels = struct.pack('<4I', *[(units[i] + units[i + 4]) & 0xffffffff for i in range(4)])
    return bytes(sums), wheels


def fixture(native, source, out, lcc):
    objects = sorted(native.glob('[0-9]*.o'))
    flags = [lcc, '-msm83:gb', '-Wf--opt-code-size', '-Wm-yC', '-Wm-yt0x19',
             '-Wm-yoA', '-Wl-j', '-I' + str(source)]
    driver = out / 'driver.c'
    driver.write_text(DRIVER)
    assembly = out / 'fixture.s'
    assembly.write_text((source / 'physics_suspension_scheduled.s').read_text() + ENTRY)
    for name, path in [('driver', driver), ('physics_suspension_scheduled', assembly),
                       ('physics_force', source / 'physics_force.c')]:
        index, = [i for i, obj in enumerate(objects) if obj.stem.split('-', 1)[1] == name]
        objects[index] = out / objects[index].name
        subprocess.run([*flags, '-c', '-o', objects[index], path], check=True)
    rom = out / 'check.gbc'
    subprocess.run([*flags, '-o', rom, *objects], check=True)
    bank_size = re.search(r'^_CODE_8\s+\w+\s+(\w+)\s+=', rom.with_suffix('.map').read_text(), re.M)
    if not bank_size or int(bank_size[1], 16) > 0x4000:
        raise ValueError('suspension fixture exceeds bank 8')
    return rom


def mirrored_cases():
    for a in range(13):
        for b in range(13):
            for sign in (-1, 1):
                arm = sign * ((1 << a) + 8192)
                delta = sign * ((1 << b) + 12288)
                yield arm, -arm, 0, 0, delta, delta
    for bit in range(32):
        mask = 1 << bit
        def flip(x):
            return ((x ^ mask) + 2**31) % 2**32 - 2**31
        yield -101, flip(101), 0, 0, 77, 77
        yield -101, 101, flip(0), 0, 77, 77
        yield -101, 101, 0, flip(0), 77, 77
        yield -101, 101, 0, 0, 77, flip(77)
    yield -2**31, -2**31, 0, 0, 1, 1


def check_mirrored(emulator, symbols):
    # Invoke the same bank-8 helper used during both idle and active work.
    mem, reg = emulator.memory, emulator.register_file
    code, stack = 0xc900, 0xcff0
    entry = symbols['_fixture_mirror']
    mem[0x3000] = 0
    mem[0x2000] = mem[symbols['__current_bank']] = entry >> 16
    mem[code:code+5] = [0xcd, entry & 255, (entry >> 8) & 255, 0x18, 0xfe]
    anchor = symbols['_riding_pose_anchor']
    displacement = symbols['_riding_spring_product_rows'] + 28
    count = 0
    for left, right, dx0, dx1, dy0, dy1 in mirrored_cases():
        mem[anchor:anchor+16] = struct.pack('<4i', left, right, 537, -129)
        mem[displacement:displacement+16] = struct.pack('<4i', dx0, dx1, dy0, dy1)
        reg.SP, reg.PC = stack, code
        emulator.tick(1, False)
        assert (reg.PC, reg.SP) == (code+3, stack), (count, hex(reg.PC), hex(reg.SP))
        expected = ((left*dy0 - 537*dx0) // 4096 + (right*dy1 + 129*dx1) // 4096) & 0xffffffff
        assert (reg.B << 24 | reg.C << 16 | reg.D << 8 | reg.E) == expected
        count += 1
    return count


def main():
    base = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native', type=Path, required=True, help='Completed scheduled-native fixture')
    parser.add_argument('--source', type=Path, default=base / 'src')
    parser.add_argument('--lcc', type=Path, default=base / '.toolchain/gbdk/bin/lcc')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    rom = fixture(args.native.resolve(), args.source.resolve(), out, args.lcc.resolve())
    symbols = {k: int(v, 16) for k, v in re.findall(r'DEF (_\w+) 0x([\dA-Fa-f]+)',
                                                      rom.with_suffix('.noi').read_text())}
    phases, scales = coefficients(args.native / 'gen')
    rng = random.Random(0x242833)
    work = list(vectors(phases, scales, rng))
    general_count = len(work)
    residuals = [(rng.randrange(-2**63, 2**63), rng.randrange(-2**63, 2**63)) for _ in work]
    for case in paired_vectors(phases, scales, rng):
        work.append(case)
        residuals.append((rng.randrange(-2**63, 2**63), rng.randrange(-2**63, 2**63)))
    emulator = PyBoy(str(rom), window='null', sound_emulated=False, cgb=True)
    emulator.set_emulation_speed(0)
    index, failures = 0, []

    def before(_):
        if index >= len(work) or failures:
            return
        indices, inputs = work[index]
        # Opposite pose anchors allow exactly the (0,0,y,y) spring prefix.
        # Feed both real scratch arrays as the preparation stage would.
        rows = symbols['_riding_spring_product_rows'] + 28
        damping = symbols['_riding_spring_ready'] + 1
        emulator.memory[rows:rows+16] = struct.pack('<4i', *inputs[:4])
        emulator.memory[damping:damping+16] = struct.pack('<4i', *inputs[4:])
        for name, data in (('_riding_pose_anchor', struct.pack('<4i', -101, 101, 537, -129)),
                           ('_fixture_index', bytes(indices)), ('_fixture_input', struct.pack('<8i', *inputs)),
                           ('_force_residual', struct.pack('<2q', *residuals[index]))):
            addr = symbols[name]
            emulator.memory[addr:addr + len(data)] = data

    def after(_):
        nonlocal index
        if index >= len(work) or failures:
            return
        indices, inputs = work[index]
        sums, wheels = expected(indices, inputs, residuals[index], scales)
        addr = symbols['_riding_force_sums']
        actual_sums = bytes(emulator.memory[addr:addr + 18])
        addr = symbols['_riding_suspension_state']
        # The oracle uses axis order. Each native record holds k*, X, Y, torque.
        actual_wheels = b''.join(bytes(emulator.memory[addr+i:addr+i+4])
                                 for i in (10, 24, 14, 28))
        bank = emulator.memory[symbols['_fixture_bank']]
        paired = emulator.memory[symbols['_fixture_paired']]
        expected_paired = (inputs[0] == inputs[1] == inputs[4] == inputs[5] == 0 and
                           inputs[2] == inputs[3] and inputs[6] == inputs[7])
        if (actual_sums, actual_wheels, bank, paired) != (sums, wheels, 0xa5, expected_paired):
            failures.append(dict(index=index, indices=indices, inputs=inputs, residual=residuals[index],
                                 expected_sums=sums.hex(), actual_sums=actual_sums.hex(),
                                 paired=paired, expected_paired=expected_paired,
                                 expected_wheels=wheels.hex(), actual_wheels=actual_wheels.hex(), bank=bank))
        index += 1

    try:
        emulator.hook_register(0, symbols['_fixture_before'], before, None)
        emulator.hook_register(0, symbols['_fixture_after'], after, None)
        for _ in range(3000):
            emulator.tick(10, False)
            if index == len(work) or failures:
                break
        mirrored = check_mirrored(emulator, symbols)
    finally:
        emulator.stop(save=False)
    report = dict(mirrored_cases=mirrored, general_vectors=general_count,
                  paired_and_near_paired_vectors=len(work) - general_count,
                  vectors=index, expected=len(work), errors=failures,
                  passed=index == len(work) and not failures)
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
