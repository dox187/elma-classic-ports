"""Compare both scheduled wheel solves with test12, including their intervening state."""
import argparse
from io import BytesIO
from pathlib import Path
import random
import re
import struct

from pyboy import PyBoy

from check_grounded_wheel import FIELDS


class Cartridge:
    def __init__(self, rom):
        self.sym = {name: int(value, 16) for name, value in re.findall(
            r'DEF (\S+) 0x([\da-fA-F]+)', rom.with_suffix('.noi').read_text())}
        self.wheels = [self.sym['_Bike'] + offset for offset in (24, 48)]
        self.inputs = self.sym['_riding_suspension_state']
        image = bytearray(rom.read_bytes())
        main = self.sym['_main']
        image[main:main+3] = b'\xf3\x18\xfe'  # Run the CRT, including initialized wheel inputs.
        addr = self.sym['_riding_cert_hit']
        offset = (addr >> 16) * 0x4000 + (addr & 0x3fff)
        # Supply a coarse contact count per wheel. The normal fine filter,
        # pushout, motion and audio run on each wheel in cartridge order.
        self.counts = 0xdfb0
        lo = self.counts & 255
        stub = bytes([0x7b, 0xfe, self.wheels[0] & 255,
                      0xfa, lo, 0xdf, 0xc8, 0xfa, lo+1, 0xdf, 0xc9])
        image[offset:offset+len(stub)] = stub
        self.emu = PyBoy(BytesIO(image), window='null', sound_emulated=False, cgb=True)
        self.emu.set_emulation_speed(0)
        self.emu.tick(200, False)
        self.mem = self.emu.memory
        self.mem[0xffff] = self.mem[0xff0f] = 0
        self.emu.hook_register(addr >> 16, addr & 0xffff, self.before_query, None)

    def state(self):
        return {name: bytes(self.mem[self.sym[name]:self.sym[name]+size]) for name, size in FIELDS.items()}

    def before_query(self, _):
        wheel = (self.emu.register_file.D << 8) | self.emu.register_file.E
        self.seen.append(self.wheels.index(wheel))
        if len(self.seen) == 2:
            self.between = self.state()

    def run(self, fields, phase, counts, impulses):
        self.seen, self.between = [], None
        for name, data in fields.items():
            self.mem[self.sym[name]:self.sym[name]+len(data)] = data
        self.mem[self.sym['_riding_subphase']] = phase
        self.mem[self.counts:self.counts+2] = counts
        start = self.inputs + 8
        if '_riding_wheel_inputs' in self.sym:
            records = b''.join(struct.pack('<H3i', k, *xyz) for k, xyz in zip(self.wheels, impulses))
        else:
            records = b''.join(struct.pack('<2i', *(xyz[j] for xyz in impulses)) for j in (2, 0, 1))
        self.mem[start:start+len(records)] = records
        addr = self.sym['_riding_step_wheels']
        bank = addr >> 16
        self.mem[0x3000] = 0
        self.mem[0x2000] = self.mem[self.sym['__current_bank']] = bank
        code, stack = 0xdfd0, 0xdf80
        self.mem[code:code+5] = [0xcd, addr & 255, (addr >> 8) & 255, 0x18, 0xfe]
        self.mem[stack:stack+8] = bytes(range(8))
        regs = self.emu.register_file
        regs.PC, regs.SP = code, stack
        for _ in range(30):
            self.emu.tick(1, False)
            if regs.PC == code+3:
                break
        assert (regs.PC, regs.SP, self.seen) == (code+3, stack, [0, 1])
        assert bytes(self.mem[start:start+len(records)]) == records
        assert bytes(self.mem[stack:stack+8]) == bytes(range(8))
        assert self.mem[self.sym['__current_bank']] == bank
        assert self.mem[addr & 0xffff] == self.mem[bank, addr & 0xffff]
        return self.between, self.state()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', required=True, type=Path)
    parser.add_argument('--rom', required=True, type=Path)
    args = parser.parse_args()
    ref, target = Cartridge(args.reference), Cartridge(args.rom)
    rng = random.Random(0x96313)
    edges = [-2**31, -2**31+1, -65537, -32768, -1, 0, 1, 32767, 65536, 2**31-1]
    normals = [(0, 16384), (16384, 0), (-16384, 0), (-11585, 11585)]
    lengths = [0, 397, 402, 404, 405, 407, 409, 410]
    cases = 900
    try:
        for i in range(cases):
            fields = {name: rng.randbytes(size) for name, size in FIELDS.items()}
            fields['_move_residual'] = struct.pack('<8i', *(rng.randrange(-2**23, 2**23) for _ in range(8)))
            fields['_Ct'] = b''.join(struct.pack('<5h', *rng.choice(normals), rng.choice(lengths),
                                     rng.randrange(-1000, 1001), rng.randrange(-1000, 1001)) for _ in range(2))
            fields['_riding_audio_contact'] = bytes(((i // 18) % 3, (i // 54) % 3))
            fields['_riding_audio_impact'] = bytes((i & 1, (i >> 1) & 1))
            counts = bytes((i % 3, (i // 3) % 3))
            impulses = [tuple(rng.choice(edges) if i & 2 else rng.randrange(-2**31, 2**31)
                              for _ in range(3)) for _ in range(2)]
            params = fields, (i // 9) & 1, counts, impulses
            for stage, (expected, actual) in enumerate(zip(ref.run(*params), target.run(*params))):
                for field in FIELDS:
                    assert expected[field] == actual[field], (i, stage, field, expected[field].hex(), actual[field].hex())
    finally:
        ref.emu.stop(save=False)
        target.emu.stop(save=False)
    print(f'{cases} scheduled wheel pairs matched between wheels and after both solves.')


if __name__ == '__main__':
    main()
