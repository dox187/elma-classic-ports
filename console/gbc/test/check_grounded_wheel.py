"""Compare one prepared contact and the public rolling ABI on two linked cartridges."""
import argparse
from io import BytesIO
from pathlib import Path
import random
import re
import struct

from pyboy import PyBoy


FIELDS = {
    '_Bike': 119, '_move_residual': 32, '_Ct': 20,
    '_riding_audio_impact': 2, '_riding_audio_contact': 2,
    '_riding_landing_contact': 2, '_riding_landing_nx': 4,
    '_riding_landing_ny': 4, '_q24_fraction': 4, '_q24_saturated': 1,
}


class Cartridge:
    def __init__(self, rom):
        self.symbols = {k: int(v, 16) for k, v in re.findall(
            r'DEF (\S+) 0x([0-9a-fA-F]+)', rom.with_suffix('.noi').read_text())}
        image = bytearray(rom.read_bytes())
        image[0x100:0x102] = bytes([0x18, 0xfe])
        # Enter the real banked wheel entry with one ordered, already prepared
        # contact. Geometry is an input here. The resolver, audio, rolling,
        # coefficient tables and circle motion run from each cartridge.
        for symbol in ('_riding_cert_hit', '_riding_prepare_contacts'):
            address = self.symbols[symbol]
            offset = (address >> 16) * 0x4000 + (address & 0x3fff)
            image[offset:offset+3] = bytes([0x3e, 1, 0xc9])
        self.emu = PyBoy(BytesIO(image), window='null', cgb=True, sound_emulated=False)
        self.emu.set_emulation_speed(0)
        self.emu.tick(200, False)
        mem = self.emu.memory
        mem[0xffff] = mem[0xff0f] = 0

    def run(self, fields, mode, phase, slot, impulses):
        mem, regs = self.emu.memory, self.emu.register_file
        for name, data in fields.items():
            addr = self.symbols[name]
            mem[addr:addr + len(data)] = data
        mem[self.symbols['_riding_subphase']] = phase
        wheel = self.symbols['_Bike'] + (1 + slot) * 24
        stack, code = 0xdf80, 0xdfd0
        addr = self.symbols['_riding_wheel' if mode == 'single' else '_riding_roll32']
        bank = addr >> 16
        mem[0x3000], mem[0x2000], mem[self.symbols['__current_bank']] = 0, bank, bank
        # A banked caller has four extra bytes before k. The public near
        # rolling ABI has its contact pointer between k and the impulses.
        args = (b'\x5a' * 4 + struct.pack('<H', wheel) if mode == 'single'
                else struct.pack('<HH', wheel, self.symbols['_Ct']))
        args += struct.pack('<iii', *impulses)
        guard = args + b'\x96\x69'
        mem[stack:stack + len(guard)] = guard
        mem[code:code+5] = [0xcd, addr & 255, addr >> 8 & 255, 0x18, 0xfe]
        regs.SP, regs.PC = stack, code
        for _ in range(10):
            self.emu.tick(1, False)
            if regs.PC == code+3:
                break
        assert (regs.PC, regs.SP) == (code+3, stack), (mode, regs.PC, regs.SP)
        assert bytes(mem[stack:stack+len(guard)]) == guard
        assert mem[self.symbols['__current_bank']] == bank
        # Read bank-9 code where it actually appears in the switchable window.
        original = self.symbols['_riding_cert_hit'] & 0xffff
        assert bytes(mem[original:original+3]) == b'\x3e\x01\xc9'
        return {name: bytes(mem[self.symbols[name]:self.symbols[name]+size])
                for name, size in FIELDS.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--rom', type=Path, required=True)
    args = parser.parse_args()
    base, target = Cartridge(args.reference), Cartridge(args.rom)
    rng = random.Random(31043)
    normals = [(0, 0), (0, 16384), (0, -16384), (16384, 0), (-16384, 0),
               (-32768, 32767), (32767, -32768), (11585, 11585), (1, -1)]
    values = [-2**31, -2**31+1, -65537, -65536, -46138, -46137, -46136,
              -32769, -232, -231, -230, -1, 0, 1, 231, 232, 32768,
              46136, 46137, 46138, 65535, 2**31-1]
    observed = set()
    cases = 0
    try:
        for i in range(1200):
            fields = {key: rng.randbytes(size) for key, size in FIELDS.items()}
            slot, phase, prior = i & 1, i >> 1 & 1, i >> 2 & 1
            if i < len(values) * 8:
                # Both sides of the exact support and first-impact thresholds.
                normal, vx, vy = (16384, 0), values[i // 8], 0
                impulses = (1, 0, 0)
            else:
                normal = (rng.choice(normals) if i % 2 else
                          (rng.randint(-32768, 32767), rng.randint(-32768, 32767)))
                sample = lambda: (rng.choice(values) if rng.randrange(2) else
                                  rng.randint(-2**31, 2**31-1))
                vx, vy = sample(), sample()
                impulses = tuple(sample() for _ in range(3))
            k = bytearray(fields['_Bike'])
            struct.pack_into('<ii', k, 24*(1+slot)+8, vx, vy)
            fields['_Bike'] = k
            fields['_Ct'] = struct.pack('<hh', *normal) + fields['_Ct'][4:]
            prior_contact = bytearray(fields['_riding_audio_contact'])
            prior_contact[slot] = prior
            fields['_riding_audio_contact'] = prior_contact
            # Residuals reachable between calls are signed Q24 fractions.
            fields['_move_residual'] = struct.pack('<8i', *[
                rng.randint(-0x800000, 0x7fffff) for _ in range(8)])
            for mode in ('single', 'roll'):
                params = fields, mode, phase, slot, impulses
                expected, actual = base.run(*params), target.run(*params)
                for name in FIELDS:
                    assert expected[name] == actual[name], (
                        i, mode, phase, slot, prior, vx, vy, normal, impulses,
                        name, expected[name].hex(), actual[name].hex())
                if mode == 'single':
                    observed.add((actual['_riding_audio_contact'][slot],
                                  actual['_riding_audio_impact'][slot]))
                cases += 1
        assert observed == {(0, 0), (1, 0), (1, 1)}, observed
    finally:
        base.emu.stop(save=False)
        target.emu.stop(save=False)
    print(f'{cases} native wheel comparisons passed, including motion residuals, '
          'Q24 fractions and saturation, contact/audio bytes, bank and stack.')


if __name__ == '__main__':
    main()
