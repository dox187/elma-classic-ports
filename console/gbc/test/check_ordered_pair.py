"""Compare prepared contact pairs on two linked cartridges, including exact cache hits."""
import argparse
from collections import Counter
from io import BytesIO
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
        assert self.mem[self.symbols['__current_bank']] == self.bank
        # Observe the mapped ROM through its switchable window as well.
        offset = self.symbols['_riding_wheel_contact'] & 0xffff
        assert self.mem[offset:offset+8] == self.mem[self.bank, offset:offset+8]
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
    finally:
        reference.emu.stop(save=False)
        target.emu.stop(save=False)
    assert set(results) == {(cached, n, impact) for cached in (False, True)
                            for n, impact in ((0, 0), (1, 0), (1, 1), (2, 0), (2, 1))}, results
    print(f'{sum(results.values())} native ordered-pair comparisons passed, including '
          '700 real cache hits, full-width impulses, residuals, Q24 and reporting.')

if __name__ == '__main__':
    main()
