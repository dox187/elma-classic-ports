"""Compare prepared contact pairs on two linked cartridges, including exact cache hits."""
import argparse
from collections import Counter
from io import BytesIO
from math import isqrt
from pathlib import Path
import random
import re
import struct

from pyboy import PyBoy

from check_grounded_wheel import FIELDS


class Cartridge:
    def __init__(self, rom):
        self.symbols = {k: int(v, 16) for k, v in re.findall(
            r'DEF (\S+) 0x([\da-fA-F]+)', rom.with_suffix('.noi').read_text())}
        image = bytearray(rom.read_bytes())
        image[0x100:0x102] = b'\x18\xfe'
        self.emu = PyBoy(BytesIO(image), window='null', cgb=True, sound_emulated=False)
        self.emu.set_emulation_speed(0)
        self.emu.tick(200, False)
        self.mem = self.emu.memory
        self.mem[0xffff] = self.mem[0xff0f] = 0
        self.bank = self.symbols['_riding_wheel_contact'] >> 16
        self.mem[0x3000] = 0
        self.mem[0x2000] = self.mem[self.symbols['__current_bank']] = self.bank

    def call(self, name, de, a, stack=0xdf80):
        bank = self.mem[self.symbols['__current_bank']]
        code = 0xdfd0
        addr = self.symbols[name] & 0xffff
        program = [0x11, de & 255, de >> 8, 0x3e, a,
                   0xcd, addr & 255, addr >> 8, 0x18, 0xfe]
        self.mem[code:code+len(program)] = program
        regs = self.emu.register_file
        regs.SP, regs.PC = stack, code
        for _ in range(10):
            self.emu.tick(1, False)
            if regs.PC == code + 8:
                break
        assert (regs.SP, regs.PC) == (stack, code + 8), (name, regs.SP, regs.PC)
        assert self.mem[self.symbols['__current_bank']] == bank
        # Observe the mapped ROM through its switchable window as well.
        offset = self.symbols['_riding_wheel_contact'] & 0xffff
        assert self.mem[offset:offset+8] == self.mem[bank, offset:offset+8]
        return regs.A

    def fill(self, slot, center, records):
        wheel = self.symbols['_Bike'] + 24*(1+slot)
        ct = self.symbols['_Ct']
        self.call('_physics_collision_reset', 0, 0)
        self.mem[wheel:wheel+8] = center
        assert self.call('_riding_cert_hit', wheel, 0) == 255
        self.mem[ct:ct+20] = records
        assert self.call('_riding_prepare_contacts', wheel, 2) == 2
        assert bytes(self.mem[wheel:wheel+8]) == center

    def run(self, fields, phase, slot, force, cached):
        for name, data in fields.items():
            addr = self.symbols[name]
            self.mem[addr:addr+len(data)] = data
        self.mem[self.symbols['_riding_subphase']] = phase
        wheel = self.symbols['_Bike'] + 24*(1+slot)
        stack = 0xdf80
        args = b'\x5a' * 4 + struct.pack('<Hiii', wheel, *force) + b'\x93\x69'
        self.mem[stack:stack+len(args)] = args
        if cached:
            self.call('_riding_wheel', 0, 0, stack)
        else:
            self.call('_riding_wheel_contact', stack+4, 2, stack)
        assert bytes(self.mem[stack:stack+len(args)]) == args
        return {key: bytes(self.mem[self.symbols[key]:self.symbols[key]+size])
                for key, size in FIELDS.items()}


def check_removal_products(reference, target):
    # Install the SRAM routine through the same initializer as a course reset.
    init_bank = target.symbols['ss_pair_init'] >> 16
    mapper = target.symbols['__current_bank']
    target.mem[0x2000] = target.mem[mapper] = init_bank
    target.call('ss_pair_init', 0, 0)
    target.mem[0x2000] = target.mem[mapper] = target.bank
    assert target.mem[target.symbols['ss_pair_ready']]
    rng = random.Random(72812)
    scalars = (-2**31, -65537, -65536, -65535, -32769, -32768, -8193,
               -8192, -1, 0, 1, 8191, 8192, 32767, 32768, 65535, 65536, 2**31-1)
    axes = (-32768, -32767, -16384, -8192, -257, -256, -1, 0, 1, 255, 256, 8192, 16384, 32767)
    pairs = [(v, n) for v in scalars for n in axes]
    pairs += [(rng.randrange(-65536,65536), rng.randrange(-32768,32768)) for _ in range(8192)]
    for value, normal in pairs:
        outputs = []
        for cart, direct in ((reference, False), (target, True)):
            operand = cart.symbols['pair_nv'] if direct else 0xdf50
            cart.mem[operand:operand+4] = struct.pack('<i', value)
            regs = cart.emu.register_file
            regs.B, regs.C = normal>>8 & 255, normal & 255
            regs.HL = operand
            cart.call('pair_removal_product' if direct else '_riding_mulq14_regs', 0, 0)
            high = (regs.B<<8 | regs.C) if direct else regs.HL
            outputs.append(high<<16 | regs.D<<8 | regs.E)
            assert bytes(cart.mem[operand:operand+4]) == struct.pack('<i', value)
        assert outputs[0] == outputs[1], (value, normal, outputs)
    return len(pairs)


def check_first_push(reference, target):
    # The first contact moves the wheel. Compare the second contact at the
    # original acceptance boundary and again after that movement.
    normals = ((32767, 32767), (-32768, -32768), (32767, -32768),
               (0, 16384), (-16384, 0))
    # Include the largest signed-word pushes and adjacent full-width ones.
    # With l=341 and a +X normal, fx=123 gives a push of exactly 63*256.
    cases = [(16384, 0, 400, nx, ny, length, fx, fy)
             for length in (-32768, -1, 0, 255, 256, 404, 405, 406, 409, 410)
             for nx, ny in normals
             for fx, fy in ((0, 0), (0, 255), (255, 0), (255, 255))]
    cases.extend((ax, ay, distance, nx, ny, 400, fx, 255-fx)
                 for ax, ay in (*normals, (16384, 0), (11385, -11385))
                 for distance in (340, 341, 342, 403)
                 for nx, ny in normals
                 for fx in (0, 122, 123, 124, 255))
    # Select exact pushes across byte/word projection boundaries.
    for boundary in (32768, 65536, 98304, 131072):
        for push in range(boundary-2, boundary+3):
            length, fx = divmod(103547-push, 256)
            for nx, ny in normals:
                cases.append((16384, 0, length, nx, ny, 404, fx, 255-fx))
    for length in (276, 148, 20, -108):
        for a, b in normals:
            for nx, ny in normals:
                cases.append((a, b, length, nx, ny, 402, 111, 217))
    rng = random.Random(41069)
    for _ in range(1800):
        axes = [rng.randint(-32768,32767) for _ in range(4)]
        cases.append((*axes[:2],rng.randint(-150,403),*axes[2:],rng.randint(380,403),
                      rng.randrange(256),rng.randrange(256)))
    for slot in (0, 1):
        for ax, ay, distance, nx, ny, length, fx, fy in cases:
            center = struct.pack('<II', 0x12340000 + fx, 0xfedc0000 + fy)
            contacts = struct.pack('<10h', ax, ay, distance, 80, 90,
                                   nx, ny, length, -100, 130)
            observed = []
            for cart in (reference, target):
                wheel = cart.symbols['_Bike'] + 24 * (1 + slot)
                ct = cart.symbols['_Ct']
                cart.mem[wheel:wheel+8] = center
                cart.mem[ct:ct+20] = contacts
                count = cart.call('_riding_prepare_contacts', wheel, 2)
                observed.append((count, bytes(cart.mem[wheel:wheel+8]),
                                 bytes(cart.mem[ct:ct+20])))
            assert observed[0] == observed[1], (slot, ax, ay, distance, nx, ny, length, fx, fy)
    return 2 * len(cases)


def check_moving_pivots(reference, target, rng):
    # The first and second pivots face opposite separation signs. Positive
    # normal impulse and velocity can leave the wheel airborne, including
    # the full-substep zero torque case that preserves the last Q24 result.
    checked = 0
    speeds = [(vx, 1600) for vx in (-1048576, -65537, -65536, -32769,
                                      32768, 65535, 65536, 1048575)]
    speeds.extend(((101917, 18392), (154505, 3754), (-131073, 65536),
                   (0x140000, 0x13ffff), (-0x150001, 0x140000),
                   (0xff0000, 0x20000), (-0x1000001, 65535)))
    for vx, vy in speeds:
        x_bin = (vx if vx >= 0 else ~vx) >> 16
        old_limit = 2048 * (x_bin + 1)
        # Test the high-byte threshold from both sides, including signed16
        # overflow, unsigned bin-sum overflow and full-phase zero torque.
        sum_limit = 768 * (x_bin + (vy >> 16) + 2)
        moments = {32768, -32769}
        for limit in (old_limit, sum_limit, sum_limit + 256):
            for delta in (-1, 0, 1):
                moments.update((limit + delta, -limit + delta))
        for omega in sorted(moments):
            for phase in (0, 1):
                for torque in (0, 1234):
                    for direction in (-1, 1):
                        fields = {key: rng.randbytes(size) for key, size in FIELDS.items()}
                        bike = bytearray(fields['_Bike'])
                        struct.pack_into('<ii', bike, 32, vx, vy*direction)
                        struct.pack_into('<i', bike, 44, omega)
                        fields['_Bike'] = bike
                        fields['_Ct'] = struct.pack('<10h', 0,16384,404,110,80,
                                                    0,16384,409,-110,75)
                        fields['_move_residual'] = bytes(32)
                        force = (2400, direction*2048, torque)
                        expected = reference.run(fields,phase,0,force,False)
                        actual = target.run(fields,phase,0,force,False)
                        assert expected == actual, (vx, omega, phase, torque, direction)
                        checked += 1
    return checked



def check_pivot_intervals(reference, target):
    # Exercise actual overlapping-contact responses on both sides of each
    # magnitude/length cutoff. Perpendicular contact displacements exercise
    # Q24 replay when a deferred first pivot precedes zero separation.
    rng = random.Random(72461)
    velocities = [-262145, -262144, -262143, -65537, -65536, -65535,
                  -256, -1, 0, 1, 255, 65535, 65536, 65537, 262143, 262144]
    axes = [-16641, -16385, -16384, -16383, -256, -1, 0, 255,
            256, 16383, 16384, 16639, 16640]
    lengths = (383, 384, 385, 403, 405, 414, 415, 416)
    for i in range(1600):
        dx, dy = (rng.choice(velocities) if rng.randrange(2) else rng.randint(-262144, 262143)
                  for _ in range(2))
        def record():
            return [rng.choice(axes), rng.choice(axes), rng.choice(lengths),
                    rng.randint(-1024, 1024), rng.randint(-1024, 1024)]
        first, second = record(), record()
        if i % 7 == 0:
            # Perpendicular displacement makes the second pivot's dot zero
            # while leaving the first nonzero whenever its tangent differs.
            first[0:2] = [16384, 0]
            second[4] = first[4]
        nx, ny, length = (second, first)[i & 1][:3]
        tangent = (dy*nx - dx*ny + 8192) >> 14
        change = (((tangent*length >> 6)*330579) + (1 << 23)) >> 24
        torque = -change + rng.choice((-1024, -129, -1, 0, 1, 127, 1024))
        if i % 4 == 0:
            torque = rng.choice((-8193, -8192, -129, -128, 0, 127, 128, 8191, 8192))
        fields = {key: rng.randbytes(size) for key, size in FIELDS.items()}
        bike = bytearray(fields['_Bike'])
        struct.pack_into('<ii', bike, 32, rng.randint(-1600, 1600), rng.randint(-1600, 1600))
        fields['_Bike'] = bike
        fields['_Ct'] = struct.pack('<10h', *first, *second)
        force = dx, dy, torque
        phase = int(i % 13 == 0)
        assert reference.run(fields, phase, 0, force, False) == target.run(fields, phase, 0, force, False), (
            first, second, force, phase)
    return 1600



def check_pivot_replay(reference, target):
    # The support rejects the outward impulse and free motion with zero
    # torque retains the pivot's Q24 fraction. Swap the contact order
    # for rejection on the first pivot, second pivot, or a zero separation.
    cases = 0
    for slot in (0, 1):
        for phase in (0, 1):
            for vx in (0, 2048, 25000, 65537, 262143):
                for length in (384, 415, 416, 447):
                    for n0, x in (((0, 16384), -200), ((0, 16384), 200),
                                  ((16384, 0), 200)):
                        fields = {key: bytes(size) for key, size in FIELDS.items()}
                        wheel = 24*(1+slot)
                        bike = bytearray(fields['_Bike'])
                        struct.pack_into('<i', bike, wheel+8, vx)
                        fields['_Bike'] = bike
                        fields['_Ct'] = struct.pack('<10h', *n0, length, x, 0,
                                                    0, 16384, length, 0, 0)
                        force = (60017, 5041, 0)
                        want = reference.run(fields, phase, slot, force, False)
                        got = target.run(fields, phase, slot, force, False)
                        assert got == want, (slot, phase, vx, length, n0, x)
                        assert got['_riding_landing_contact'][slot] == 0
                        assert any(got['_q24_fraction'])
                        cases += 1
    return cases


def check_locked_supports(reference, target):
    # Coincident contact points accept both zero-separation pivots. The
    # second predicate therefore sees either the first velocity removal or
    # a silent two-support lock. Test both sides of the threshold with each
    # audio history, swapping the two wheels and the order of the normals.
    cases = 0
    for slot in (0, 1):
        for axis in (0, 1):
            n0, n1 = ((16384, 0), (0, 16384)) if axis == 0 else ((0, 16384), (16384, 0))
            for prior in (0, 1, 2):
                for vx, vy in ((-232,-230),(-231,-230),(-230,-231),(0,0),
                               (-230,-232),(1,-32769),(-65537,32768),(65535,65536)):
                    for fx, fy in ((0,0), (300,-500), (-500,300), (1,1)):
                        fields = {key: bytes(size) for key, size in FIELDS.items()}
                        circle = 24*(1+slot)
                        bike = bytearray(fields['_Bike'])
                        struct.pack_into('<ii',bike,circle+8,vx,vy)
                        fields['_Bike'] = bike
                        fields['_Ct'] = struct.pack('<10h',*n0,404,411,518,*n1,409,411,518)
                        fields['_riding_audio_contact'] = bytes((prior,0)) if not slot else bytes((0,prior))
                        for phase in (0, 1):
                            force = (fx,fy,0)
                            assert reference.run(fields,phase,slot,force,False) == target.run(
                                fields,phase,slot,force,False), (slot, axis, prior, vx, vy, fx, fy, phase)
                            cases += 1
    return cases


def check_speed_class(cart):
    velocity = cart.symbols['_Bike'] + 32
    limit = 23069
    pairs = set()
    for x in (0, 1, 255, 256, 8191, 10856, 16128, 16384, 20355, 22528, limit-1, limit):
        edge = isqrt(limit*limit - x*x)
        for y in (0, 1, edge-1, edge, edge+1, 23295, 23296, 32768, 65536):
            for sx in (-1, 1):
                for sy in (-1, 1):
                    pairs.add((sx*x, sy*y))
                    pairs.add((sy*y, sx*x))
    pairs.update(((1 << 30, 0), (0, -1 << 31), (-65536, 65535)))
    if 'pair_speed_bands' in cart.symbols:
        address = cart.symbols['pair_speed_bands'] & 65535
        bands = bytes(cart.mem[address:address+13])
        assert list(bands) == [isqrt(max(0,limit**2-(2048*i)**2))//256 for i in range(13)]
        for i in range(12):
            for x in (2048*i-1,2048*i,2048*i+1):
                for high in (bands[i],bands[i+1]):
                    for y in (high*256-1,high*256,high*256+1):
                        pairs.update(((x,y),(-x,y),(x,-y),(-x,-y)))
    seen = set()
    # The two off-axis integer points (10856, 20355) and its transpose
    # lie exactly on this circle. Only equality on an axis selects fast.
    inputs = 0xdf84
    cart.mem[inputs:inputs+14] = struct.pack('<Hiii', velocity-8, 0, 0, 0)
    cart.mem[cart.symbols['_riding_subphase']] = 0
    ct = cart.symbols['_Ct']
    contacts = struct.pack('<10h', 0, 16384, 404, 110, 80, 0, 16384, 409, -110, 75)
    for vx, vy in pairs:
        cart.mem[velocity:velocity+8] = struct.pack('<ii', vx, vy)
        answer = cart.call('_riding_pair_speed_class', velocity, 0)
        fast = max(abs(vx), abs(vy)) >= limit or vx*vx+vy*vy > limit*limit
        expected = 2 if fast else int(bool(vx or vy))
        assert answer in (expected, 3), (vx, vy, answer, expected)
        if answer == 3:
            cart.mem[ct:ct+20] = contacts
            cart.call('_riding_wheel_contact', inputs, 2)
            assert cart.mem[cart.symbols['_riding_pair_shift']] == (10 if fast else 6), (vx, vy)
        seen.add(answer)
    assert seen == {0, 1, 2, 3}, seen
    return len(pairs)


def check_length_scaling(cart):
    regs = cart.emu.register_file
    cases = 0
    for tangent in (-2147483648, -131073, -131072, -131071, -65537, -65536,
                    -32769, -32768, -1, 0, 1, 32767, 65535, 65536,
                    131070, 131071, 131072, 2147483647):
        for length in (-32768, -1, 0, 1, 255, 256, 257, 404, 510, 511, 512, 32767):
            for shift in (6, 10):
                cart.mem[cart.symbols['_riding_pair_shift']] = shift
                regs.HL = (tangent >> 16) & 65535
                regs.B, regs.C = (length >> 8) & 255, length & 255
                cart.call('pair_length_scale', tangent & 65535, 0)
                got = int.from_bytes(bytes((regs.C, regs.B, regs.E, regs.D)), 'little', signed=True)
                expect = min(2147483647, max(-2147483648, tangent * length >> shift))
                assert got == expect, (tangent, length, shift, got, expect)
                cases += 1
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--rom', type=Path, required=True)
    args = parser.parse_args()
    reference, target = Cartridge(args.reference), Cartridge(args.rom)
    rng = random.Random(413887)
    s16 = lambda: rng.randint(-32768, 32767)
    s32 = lambda: rng.randint(-2**31, 2**31-1)
    normals = [(0, 0), (16384, 0), (-16384, 0), (0, 16384), (0, -16384),
               (11585, -11585), (-32768, 32767), (32767, -32768)]
    edges = [-2**31, -2**31+1, -65537, -65536, -46138, -46137, -46136,
             -32769, -32768, -23070, -23069, -23068, -232, -231, -230, -1,
             0, 1, 230, 231, 232, 23068, 23069, 23070, 32767, 32768, 46136,
             46137, 46138, 65535, 2**31-1]
    sample = lambda: rng.choice(edges) if rng.randrange(2) else s32()
    normal = lambda: rng.choice(normals) if rng.randrange(2) else (s16(), s16())
    center = struct.pack('<II', 0x12340000, 0xfedc0000)
    results = Counter()
    try:
        for i in range(5600):
            slot, phase, prior = i & 1, (i >> 1) & 1, (i >> 2) % 3
            cached = False
            if i >= 4800:
                # Install a fresh ordered pair, then alternate real cache hits
                # with unrelated direct resolver calls at the same wheel/center.
                slot = (i//8) & 1
                cached = (i % 8) != 3
                if i % 8 == 0:
                    def record():
                        return (*normal(), rng.choice((405, 406, 407)), s16(), s16())
                    records = struct.pack('<10h', *record(), *record())
                    for cart in (reference, target):
                        cart.fill(slot, center, records)

            if i % 6 == 0:
                vx, vy = 0, 0
            elif i % 6 == 1:
                vx, vy = rng.choice(edges), 0
            elif i % 6 == 2:
                vx, vy = rng.randint(-23069, 23069), rng.randint(-23069, 23069)
            else:
                vx, vy = sample(), sample()
            n0, n1 = normal(), normal()
            l0, l1 = (s16(), s16()) if i % 3 == 2 else (rng.randrange(411), rng.randrange(411))
            tx0, ty0, tx1, ty1 = [s16() if i % 3 else rng.randrange(4096) for _ in range(4)]
            if i % 17 == 0:
                tx1, ty1 = tx0, ty0
            ct = struct.pack('<10h', *n0, l0, tx0, ty0, *n1, l1, tx1, ty1)
            if i % 9 == 0:
                force = (0, 0, sample())
            elif i % 9 == 1:
                force = (sample(), sample(), 0)
            elif i % 9 == 2:
                force = tuple(s16() for _ in range(3))
            else:
                force = tuple(sample() for _ in range(3))
            fields = {key: rng.randbytes(size) for key, size in FIELDS.items()}
            wheel = 24*(1+slot)
            bike = bytearray(fields['_Bike'])
            if cached:
                bike[wheel:wheel+8] = center
            struct.pack_into('<ii', bike, wheel+8, vx, vy)
            struct.pack_into('<i', bike, wheel+20, sample())
            # For cache hits Ct starts poisoned with *different* geometry.
            fields['_Bike'], fields['_Ct'] = bike, ct
            fields['_move_residual'] = struct.pack('<8i', *[
                rng.randint(-0x800000, 0x7fffff) for _ in range(8)])
            audio = bytearray(fields['_riding_audio_contact'])
            audio[slot] = prior
            fields['_riding_audio_contact'] = audio
            expected = reference.run(fields, phase, slot, force, cached)
            actual = target.run(fields, phase, slot, force, cached)
            for key, value in expected.items():
                assert value == actual[key], (i, cached, phase, slot, key, value.hex(), actual[key].hex())
            results[(cached, actual['_riding_landing_contact'][slot],
                     actual['_riding_audio_impact'][slot])] += 1
        print(f'{check_first_push(reference, target)} two-contact push boundaries matched.')
        moving = check_moving_pivots(reference, target, rng)
        if '_riding_pair_final_support' in target.symbols:
            print(f'{check_locked_supports(reference, target)} lock and first-impact boundaries matched.')
        if 'pair_removal_product' in target.symbols and 'pair_reduction_code' in target.symbols:
            print(f'{check_removal_products(reference, target)} signed normal removals matched.')
        if '_riding_pivot_bound' in target.symbols:
            print(f'{check_pivot_intervals(reference, target)} slow-pivot interval boundaries matched.')
            print(f'{check_pivot_replay(reference, target)} zero-torque pivot replays matched.')
        if '_riding_pair_speed_class' in target.symbols:
            print(f'{check_speed_class(target)} velocity boundaries passed.')
        if 'pair_length_scale' in target.symbols:
            print(f'{check_length_scaling(target)} tangent and contact-length boundary cases passed.')
    finally:
        reference.emu.stop(save=False)
        target.emu.stop(save=False)
    assert set(results) == {(cached, n, impact) for cached in (False, True)
                            for n, impact in ((0, 0), (1, 0), (1, 1), (2, 0), (2, 1))}, results
    print(f'{sum(results.values())} native ordered-pair comparisons passed, including '
          '700 real cache hits, full-width impulses, residuals, Q24 and reporting. '
          f'{moving} additional moving-pivot boundary and Q24 visibility comparisons passed.')

if __name__ == '__main__':
    main()
